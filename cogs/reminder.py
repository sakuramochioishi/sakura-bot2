import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, date
import os
import asyncpg

DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6
}

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.bot.loop.create_task(self.init_db())
        self.check_reminders.start()

    async def init_db(self):
        self.db_pool = await asyncpg.create_pool(os.getenv("DATABASE_URL3"))
        async with self.db_pool.acquire() as conn:
            # テーブル作成
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    channel_id BIGINT NOT NULL,
                    mention TEXT NOT NULL,
                    message TEXT NOT NULL,
                    time TIMESTAMP,
                    daily_time TIME,
                    repeat_days INTEGER[],
                    last_fired DATE
                );
            """)
            # 必要に応じてカラム追加
            await conn.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
            await conn.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS daily_time TIME;")
            await conn.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS repeat_days INTEGER[];")
            await conn.execute("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS last_fired DATE;")

    def cog_unload(self):
        self.check_reminders.cancel()
        if self.db_pool:
            self.bot.loop.run_until_complete(self.db_pool.close())

    async def get_target_channel_id(self, guild_id, original_channel_id):
        # SettingsCogで設定されたIDがあれば優先、なければ登録時のID
        if guild_id:
            settings_cog = self.bot.get_cog("SettingsCog")
            if settings_cog and hasattr(settings_cog, "get_reminder_channel_id"):
                guild_reminder_ch = await settings_cog.get_reminder_channel_id(guild_id)
                if guild_reminder_ch:
                    return guild_reminder_ch
        return original_channel_id

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        if not self.db_pool:
            return

        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d %H:%M")
        current_time_str = now.strftime("%H:%M")
        current_weekday = now.weekday()
        today_date = now.date()

        async with self.db_pool.acquire() as conn:
            # 1回限りのチェック
            rows = await conn.fetch("SELECT id, guild_id, channel_id, mention, message, time FROM reminders WHERE time IS NOT NULL")
            for row in rows:
                if row["time"].strftime("%Y-%m-%d %H:%M") == current_date_str:
                    target_id = await self.get_target_channel_id(row["guild_id"], row["channel_id"])
                    channel = self.bot.get_channel(target_id)
                    if channel:
                        await channel.send(f"{row['mention']} {row['message']}")
                    await conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])

            # 毎週のチェック
            rows_weekly = await conn.fetch("SELECT id, guild_id, channel_id, mention, message, daily_time, repeat_days, last_fired FROM reminders WHERE repeat_days IS NOT NULL")
            for row in rows_weekly:
                if row["daily_time"] and current_weekday in row["repeat_days"]:
                    if row["daily_time"].strftime("%H:%M") == current_time_str:
                        if row["last_fired"] != today_date:
                            target_id = await self.get_target_channel_id(row["guild_id"], row["channel_id"])
                            channel = self.bot.get_channel(target_id)
                            if channel:
                                await channel.send(f"{row['mention']} {row['message']}")
                            await conn.execute("UPDATE reminders SET last_fired = $1 WHERE id = $2", today_date, row["id"])

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="remind", description="日時を指定して1回限りのリマインダーを設定します" )
    async def set_reminder(self, interaction: discord.Interaction, datetime_str: str, mention: str, message: str):
        try:
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ 日付と時刻は `YYYY-MM-DD HH:MM` 形式で指定してください。", ephemeral=True)
            return

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reminders (guild_id, channel_id, mention, message, time) VALUES ($1, $2, $3, $4, $5)",
                interaction.guild_id, interaction.channel_id, mention, message, dt
            )
        await interaction.response.send_message(f"✅ リマインダーを設定しました！\n日時: `{datetime_str}`\n対象: {mention}", ephemeral=True)

    @app_commands.command(name="remind_weekly", description="曜日を指定して毎週のリマインダーを設定します")
    async def set_weekly_reminder(self, interaction: discord.Interaction, time_str: str, days: str, mention: str, message: str):
        try:
            t = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            await interaction.response.send_message("❌ 時刻は `HH:MM` 形式で指定してください。", ephemeral=True)
            return

        day_list = [DAY_MAP[d.strip().lower()] for d in days.split(",") if d.strip().lower() in DAY_MAP]
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reminders (guild_id, channel_id, mention, message, daily_time, repeat_days) VALUES ($1, $2, $3, $4, $5, $6)",
                interaction.guild_id, interaction.channel_id, mention, message, t, day_list
            )
        await interaction.response.send_message(f"🔄 毎週のリマインダーを設定しました！\n時刻: `{time_str}`\n対象: {mention}", ephemeral=True)

    @app_commands.command(name="remind_list", description="登録されているリマインダーの一覧を表示します")
    async def list_reminders(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM reminders WHERE guild_id = $1 ORDER BY time ASC, daily_time ASC", interaction.guild_id)

        if not rows:
            await interaction.response.send_message("📭 登録されているリマインダーはありません。", ephemeral=True)
            return

        embed = discord.Embed(title="⏰ 登録済みリマインダー一覧", color=discord.Color.green())
        days_rev_map = {v: k for k, v in DAY_MAP.items()}

        for row in rows:
            if row["time"]:
                info = f"📅 日時: `{row['time'].strftime('%Y-%m-%d %H:%M')}`"
            else:
                day_names = [days_rev_map[d] for d in row["repeat_days"] if d in days_rev_map]
                info = f"🔄 時刻: `{row['daily_time'].strftime('%H:%M')}` / 曜日: `{', '.join(day_names)}`"
            
            embed.add_field(name=f"ID: {row['id']} | {row['message']}", value=f"{info}\n👤 対象: {row['mention']}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remind_del", description="指定したIDのリマインダーを削除します")
    async def delete_reminder(self, interaction: discord.Interaction, reminder_id: int):
        async with self.db_pool.acquire() as conn:
            result = await conn.execute("DELETE FROM reminders WHERE id = $1 AND guild_id = $2", reminder_id, interaction.guild_id)
        
        if result == "DELETE 1":
            await interaction.response.send_message(f"🗑️ ID `{reminder_id}` を削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 指定したIDのリマインダーが見つからないか、権限がありません。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Reminder(bot))