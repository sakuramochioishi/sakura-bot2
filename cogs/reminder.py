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
        # 環境変数 DATABASE_URL から接続情報を取得
        self.db_pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))

    def cog_unload(self):
        self.check_reminders.cancel()
        if self.db_pool:
            self.bot.loop.run_until_complete(self.db_pool.close())

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
            # 1. 1回限りのリマインダーチェック
            rows = await conn.fetch("SELECT id, channel_id, mention, message, time FROM reminders WHERE time IS NOT NULL")
            for row in rows:
                if row["time"].strftime("%Y-%m-%d %H:%M") == current_date_str:
                    channel = self.bot.get_channel(row["channel_id"])
                    if channel:
                        await channel.send(f"{row['mention']} {row['message']}")
                    await conn.execute("DELETE FROM reminders WHERE id = $1", row["id"])

            # 2. 毎週の繰り返しリマインダーチェック
            rows_weekly = await conn.fetch("SELECT id, channel_id, mention, message, daily_time, repeat_days, last_fired FROM reminders WHERE repeat_days IS NOT NULL")
            for row in rows_weekly:
                if row["daily_time"] and current_weekday in row["repeat_days"]:
                    if row["daily_time"].strftime("%H:%M") == current_time_str:
                        if row["last_fired"] != today_date:
                            channel = self.bot.get_channel(row["channel_id"])
                            if channel:
                                await channel.send(f"{row['mention']} {row['message']}")
                            await conn.execute("UPDATE reminders SET last_fired = $1 WHERE id = $2", today_date, row["id"])

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="remind", description="日時を指定して1回限りのリマインダーを設定します")
    @app_commands.describe(
        datetime_str="日時 (例: 2026-12-31 23:59)",
        mention="メンション先 (@ロール または @ユーザー)",
        message="リマインドするメッセージ"
    )
    async def set_reminder(self, interaction: discord.Interaction, datetime_str: str, mention: str, message: str):
        try:
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ 日付と時刻の形式は `YYYY-MM-DD HH:MM` で指定してください。", ephemeral=True)
            return

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reminders (channel_id, mention, message, time) VALUES ($1, $2, $3, $4)",
                interaction.channel_id, mention, message, dt
            )

        await interaction.response.send_message(f"✅ リマインダーを設定しました！\n日時: `{datetime_str}`\n対象: {mention}\n内容: {message}")

    @app_commands.command(name="remind_weekly", description="曜日を指定して毎週のリマインダーを設定します")
    @app_commands.describe(
        time_str="時刻 (例: 20:00)",
        days="曜日 (例: mon,wed,fri または 月,水,金)",
        mention="メンション先",
        message="リマインドするメッセージ"
    )
    async def set_weekly_reminder(self, interaction: discord.Interaction, time_str: str, days: str, mention: str, message: str):
        try:
            t = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            await interaction.response.send_message("❌ 時刻の形式は `HH:MM` で指定してください。", ephemeral=True)
            return

        day_list = []
        for d in days.split(","):
            d_clean = d.strip().lower()
            if d_clean in DAY_MAP:
                day_list.append(DAY_MAP[d_clean])
            else:
                await interaction.response.send_message(f"❌ 無効な曜日が含まれています: `{d_clean}`", ephemeral=True)
                return

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reminders (channel_id, mention, message, daily_time, repeat_days) VALUES ($1, $2, $3, $4, $5)",
                interaction.channel_id, mention, message, t, day_list
            )

        await interaction.response.send_message(f"🔄 毎週のリマインダーを設定しました！\n時刻: `{time_str}`\n対象: {mention}\n内容: {message}")

    @app_commands.command(name="remind_list", description="登録されているリマインダーの一覧を表示します")
    async def list_reminders(self, interaction: discord.Interaction):
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, channel_id, mention, message, time, daily_time, repeat_days FROM reminders")

        if not rows:
            await interaction.response.send_message("📭 登録されているリマインダーはありません。", ephemeral=True)
            return

        embed = discord.Embed(title="⏰ 登録済みリマインダー一覧", color=discord.Color.blue())
        days_rev_map = {v: k for k, v in DAY_MAP.items()}

        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            channel_name = channel.name if channel else "不明なチャンネル"

            if row["time"]:
                info = f"日時: `{row['time'].strftime('%Y-%m-%d %H:%M')}` (1回限り)"
            else:
                day_names = [days_rev_map[d] for d in row["repeat_days"] if d in days_rev_map]
                info = f"時刻: `{row['daily_time'].strftime('%H:%M')}` / 曜日: `{', '.join(day_names)}` (毎週)"

            embed.add_field(
                name=f"ID: {row['id']} | チャンネル: #{channel_name}",
                value=f"{info}\n対象: {row['mention']}\n内容: {row['message']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remind_del", description="指定したIDのリマインダーを削除します")
    @app_commands.describe(reminder_id="削除するリマインダーのID")
    async def delete_reminder(self, interaction: discord.Interaction, reminder_id: int):
        async with self.db_pool.acquire() as conn:
            result = await conn.execute("DELETE FROM reminders WHERE id = $1", reminder_id)

        if result == "DELETE 1":
            await interaction.response.send_message(f"🗑️ ID `{reminder_id}` のリマインダーを削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 指定されたIDのリマインダーが見つかりません。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Reminder(bot))