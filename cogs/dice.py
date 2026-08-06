import os
import random
import re
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands


class Dice(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.pool = None

    async def cog_load(self):
        """Cogがロードされた時にデータベースプールを作成し、テーブルとカラムを初期化する"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("環境変数 'DATABASE_URL' が設定されていません。")
        
        # ★ statement_cache_size=0 を追加してキャッシュエラーを防ぐ
        self.pool = await asyncpg.create_pool(database_url, statement_cache_size=0)
        
        # テーブルおよびカラムの確実な初期化
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL
                )
                """
            )
            # すでにテーブルが存在していてカラムがない場合の対策
            await connection.execute(
                """
                ALTER TABLE guild_settings 
                ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT FALSE
                """
            )

    async def cog_unload(self):
        """Cogがアンロードされる時にプールを閉じる"""
        if self.pool:
            await self.pool.close()

    async def get_enabled(self, guild_id: int) -> bool:
        """サーバーのダイス設定を取得する（デフォルトはFalse）"""
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT enabled FROM guild_settings WHERE guild_id = $1", guild_id
            )
            if row is None:
                return False
            return row["enabled"]

    async def set_enabled(self, guild_id: int, enabled: bool):
        """サーバーのダイス設定を保存する（UPSERT）"""
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO guild_settings (guild_id, enabled)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) 
                DO UPDATE SET enabled = EXCLUDED.enabled
                """,
                guild_id, enabled
            )

    @app_commands.command(name="roll", description="このサーバーのダイス機能の有効/無効を切り替えます")
    @app_commands.describe(status="有効にするか無効にするかを選択してください")
    @app_commands.choices(status=[
        app_commands.Choice(name="有効", value="enable"),
        app_commands.Choice(name="無効", value="disable"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def roll_setting(self, interaction: discord.Interaction, status: str):
        guild_id = interaction.guild_id

        if status == "enable":
            await self.set_enabled(guild_id, True)
            await interaction.response.send_message("✅ このサーバーでダイス機能を**有効**にしました", ephemeral=True)
        else:
            await self.set_enabled(guild_id, False)
            await interaction.response.send_message("❌ このサーバーでダイス機能を**無効**にしました", ephemeral=True)

    @roll_setting.error
    async def roll_setting_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ このコマンドを実行するには**サーバー管理者**の権限が必要です。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # データベースから非同期で設定を取得
        if not await self.get_enabled(message.guild.id):
            return
            
        match = re.search(r"\b(\d+)d(\d+)\b", message.content.lower())
        if not match:
            return

        count = int(match.group(1))
        sides = int(match.group(2))
        dice_str = f"{count}d{sides}"

        if count <= 0 or sides <= 0 or count > 100 or sides > 100000:
            return
        
        results = [random.randint(1, sides) for _ in range(count)]
        total = sum(results)

        if count > 1:
            results_str = ", ".join(map(str, results))
            if len(results_str) > 1900:
                results_str = " (出目が多すぎるため省略されました) "
            description = f"**{dice_str}**\n[{results_str}] > {total}"
        else:
            description = f"**{dice_str}**\n[{results[0]}] > {total}"

        embed = discord.Embed(
            description=description, 
            color=discord.Color.dark_embed()
        )

        await message.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Dice(bot))