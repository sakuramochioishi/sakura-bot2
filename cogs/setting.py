import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import asyncpg
import logging

logger = logging.getLogger(__name__)

# ==========================================
# 1. 環境変数の読み込み (.env)
# ==========================================
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================================
# 2. テーブル作成 & カラム自動追加 用 SQL
# ==========================================
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT PRIMARY KEY,
    
    -- LevelingCog 連携用
    log_levelup_channel_id BIGINT,
    log_rankup_channel_id BIGINT,
    leveling_enabled BOOLEAN DEFAULT TRUE,
    
    -- QuizCog 連携用
    quiz_answer_time INT DEFAULT 30,
    quiz_time_limit INT DEFAULT 60,
    quiz_channel_id BIGINT,
    
    -- ModerationCog 連携用
    reishou_channel_id BIGINT,
    mod_log_channel_id BIGINT,
    auto_mod_enabled BOOLEAN DEFAULT TRUE,
    
    -- EEWCog 連携用
    eew_channel_id BIGINT,
    
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 既存テーブルが存在する場合に足りない列を自動で追加するマイグレーションSQL
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS log_levelup_channel_id BIGINT;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS log_rankup_channel_id BIGINT;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS leveling_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS quiz_answer_time INT DEFAULT 30;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS quiz_time_limit INT DEFAULT 60;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS quiz_channel_id BIGINT;

ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS reishou_channel_id BIGINT;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS mod_log_channel_id BIGINT;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS auto_mod_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS eew_channel_id BIGINT;
ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
"""

# ==========================================
# 3. スタンドアロン型ヘルパー関数
# ==========================================
async def get_guild_settings(pool: asyncpg.Pool, guild_id: int) -> dict | None:
    """指定したサーバーの設定を辞書形式で取得する関数（汎用）"""
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM guild_settings WHERE guild_id = $1::bigint", guild_id
        )
        return dict(row) if row else None


class SettingsCog(commands.Cog):
    """設定管理用 Cog (LevelingCog, QuizCog, ModerationCog, EEWCog 連携)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self) -> asyncpg.Pool:
        return getattr(self.bot, "db_pool", None)

    # ==================================================
    # 🤝 各 Cog 連携用インターフェース (Getter メソッド)
    # ==================================================

    async def get_setting(self, guild_id: int) -> dict | None:
        """指定ギルドの全設定を取得"""
        return await get_guild_settings(self.db, guild_id)

    # 1. LevelingCog 連携用
    async def get_leveling_config(self, guild_id: int) -> dict:
        settings = await self.get_setting(guild_id)
        if not settings:
            return {
                "levelup_channel_id": None,
                "rankup_channel_id": None,
                "enabled": True,
            }
        return {
            "levelup_channel_id": settings.get("log_levelup_channel_id"),
            "rankup_channel_id": settings.get("log_rankup_channel_id"),
            "enabled": settings.get("leveling_enabled", True),
        }

    # 2. QuizCog 連携用
    async def get_quiz_config(self, guild_id: int) -> dict:
        settings = await self.get_setting(guild_id)
        if not settings:
            return {
                "answer_time": 30,
                "time_limit": 60,
                "quiz_channel_id": None,
            }
        return {
            "answer_time": settings.get("quiz_answer_time", 30),
            "time_limit": settings.get("quiz_time_limit", 60),
            "quiz_channel_id": settings.get("quiz_channel_id"),
        }

    # 3. ModerationCog 連携用
    async def get_moderation_config(self, guild_id: int) -> dict:
        settings = await self.get_setting(guild_id)
        if not settings:
            return {
                "reishou_channel_id": None,
                "mod_log_channel_id": None,
                "auto_mod_enabled": True,
            }
        return {
            "reishou_channel_id": settings.get("reishou_channel_id"),
            "mod_log_channel_id": settings.get("mod_log_channel_id"),
            "auto_mod_enabled": settings.get("auto_mod_enabled", True),
        }

    # 4. EEWCog 連携用
    async def get_all_eew_targets(self) -> list[int]:
        """地震速報送信対象のチャンネルIDリストを取得"""
        if not self.db:
            return []
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT eew_channel_id FROM guild_settings WHERE eew_channel_id IS NOT NULL"
                )
                return [row["eew_channel_id"] for row in rows]
        except Exception as e:
            logger.error(f"[SettingsCog] EEW送信先の取得失敗: {e}")
            return []

    # ==================================================
    # 🎛️ Slash Commands (/setting ...)
    # ==================================================
    setting_group = app_commands.Group(
        name="setting", description="Botの各種設定を行います"
    )

    # --------------------------------------------------
    # /setting leveling (LevelingCog 用)
    # --------------------------------------------------
    @setting_group.command(
        name="leveling", description="レベル・ランクアップ通知や有効化を設定します"
    )
    @app_commands.describe(
        levelup_channel="レベルアップ通知先のチャンネル",
        rankup_channel="ランクアップ通知先のチャンネル",
        enabled="レベル機能を有効にするか",
    )
    async def setting_leveling(
        self,
        interaction: discord.Interaction,
        levelup_channel: discord.TextChannel = None,
        rankup_channel: discord.TextChannel = None,
        enabled: bool = None,
    ):
        if levelup_channel is None and rankup_channel is None and enabled is None:
            await interaction.response.send_message(
                "設定変更する項目を少なくとも1つ指定してください。",
                ephemeral=True,
            )
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, log_levelup_channel_id, log_rankup_channel_id, leveling_enabled
                )
                VALUES ($1::bigint, $2::bigint, $3::bigint, COALESCE($4::boolean, TRUE))
                ON CONFLICT (guild_id) DO UPDATE SET
                    log_levelup_channel_id = COALESCE($2::bigint, guild_settings.log_levelup_channel_id),
                    log_rankup_channel_id = COALESCE($3::bigint, guild_settings.log_rankup_channel_id),
                    leveling_enabled = COALESCE($4::boolean, guild_settings.leveling_enabled),
                    updated_at = CURRENT_TIMESTAMP
                """,
                interaction.guild_id,
                levelup_channel.id if levelup_channel else None,
                rankup_channel.id if rankup_channel else None,
                enabled,
            )

        msg = "レベル機能の設定を更新しました:\n"
        if levelup_channel:
            msg += f"- レベルアップ通知先: {levelup_channel.mention}\n"
        if rankup_channel:
            msg += f"- ランクアップ通知先: {rankup_channel.mention}\n"
        if enabled is not None:
            msg += f"- レベル機能状態: {'有効' if enabled else '無効'}\n"

        await interaction.response.send_message(msg, ephemeral=True)

    # --------------------------------------------------
    # /setting quiz (QuizCog 用)
    # --------------------------------------------------
    @setting_group.command(
        name="quiz", description="クイズの制限時間や専用チャンネルを設定します"
    )
    @app_commands.describe(
        answer_time="回答受付時間（秒）",
        time_limit="全体制限時間（秒）",
        quiz_channel="クイズ実施専用チャンネル",
    )
    async def setting_quiz(
        self,
        interaction: discord.Interaction,
        answer_time: int = None,
        time_limit: int = None,
        quiz_channel: discord.TextChannel = None,
    ):
        if answer_time is None and time_limit is None and quiz_channel is None:
            await interaction.response.send_message(
                "設定変更する項目を少なくとも1つ指定してください。",
                ephemeral=True,
            )
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, quiz_answer_time, quiz_time_limit, quiz_channel_id
                )
                VALUES ($1::bigint, COALESCE($2::int, 30), COALESCE($3::int, 60), $4::bigint)
                ON CONFLICT (guild_id) DO UPDATE SET
                    quiz_answer_time = COALESCE($2::int, guild_settings.quiz_answer_time),
                    quiz_time_limit = COALESCE($3::int, guild_settings.quiz_time_limit),
                    quiz_channel_id = COALESCE($4::bigint, guild_settings.quiz_channel_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                interaction.guild_id,
                answer_time,
                time_limit,
                quiz_channel.id if quiz_channel else None,
            )

        msg = "クイズの設定を更新しました:\n"
        if answer_time is not None:
            msg += f"- 回答受付時間: {answer_time}秒\n"
        if time_limit is not None:
            msg += f"- 全体制限時間: {time_limit}秒\n"
        if quiz_channel:
            msg += f"- 専用チャンネル: {quiz_channel.mention}\n"

        await interaction.response.send_message(msg, ephemeral=True)

    # --------------------------------------------------
    # /setting moderation (ModerationCog 用)
    # --------------------------------------------------
    @setting_group.command(
        name="moderation", description="モデレーション・冷笑削除・ログチャンネルを設定します"
    )
    @app_commands.describe(
        reishou_channel="冷笑自動削除を適用するチャンネル",
        mod_log_channel="モデレーションログの送信先チャンネル",
        auto_mod="自動モデレーションを有効にするか",
    )
    async def setting_moderation(
        self,
        interaction: discord.Interaction,
        reishou_channel: discord.TextChannel = None,
        mod_log_channel: discord.TextChannel = None,
        auto_mod: bool = None,
    ):
        if reishou_channel is None and mod_log_channel is None and auto_mod is None:
            await interaction.response.send_message(
                "設定変更する項目を少なくとも1つ指定してください。",
                ephemeral=True,
            )
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, reishou_channel_id, mod_log_channel_id, auto_mod_enabled
                )
                VALUES ($1::bigint, $2::bigint, $3::bigint, COALESCE($4::boolean, TRUE))
                ON CONFLICT (guild_id) DO UPDATE SET
                    reishou_channel_id = COALESCE($2::bigint, guild_settings.reishou_channel_id),
                    mod_log_channel_id = COALESCE($3::bigint, guild_settings.mod_log_channel_id),
                    auto_mod_enabled = COALESCE($4::boolean, guild_settings.auto_mod_enabled),
                    updated_at = CURRENT_TIMESTAMP
                """,
                interaction.guild_id,
                reishou_channel.id if reishou_channel else None,
                mod_log_channel.id if mod_log_channel else None,
                auto_mod,
            )

        msg = "モデレーション設定を更新しました:\n"
        if reishou_channel:
            msg += f"- 冷笑削除チャンネル: {reishou_channel.mention}\n"
        if mod_log_channel:
            msg += f"- モデレーションログ: {mod_log_channel.mention}\n"
        if auto_mod is not None:
            msg += f"- 自動モデレーション: {'有効' if auto_mod else '無効'}\n"

        await interaction.response.send_message(msg, ephemeral=True)

    # --------------------------------------------------
    # /setting eew (EEWCog 用)
    # --------------------------------------------------
    @setting_group.command(
        name="eew", description="地震速報の送信先チャンネルを設定します"
    )
    @app_commands.describe(channel="送信先のチャンネル")
    async def setting_eew(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO guild_settings (guild_id, eew_channel_id)
                VALUES ($1::bigint, $2::bigint)
                ON CONFLICT (guild_id) DO UPDATE SET
                    eew_channel_id = $2::bigint,
                    updated_at = CURRENT_TIMESTAMP
                """,
                interaction.guild_id,
                channel.id,
            )

        await interaction.response.send_message(
            f"地震速報送信先チャンネルを {channel.mention} に設定しました。",
            ephemeral=True,
        )

    # --------------------------------------------------
    # /setting status (確認コマンド)
    # --------------------------------------------------
    @setting_group.command(
        name="status", description="現在のすべての設定状況を確認します"
    )
    async def setting_status(self, interaction: discord.Interaction):
        settings = await get_guild_settings(self.db, interaction.guild_id)

        if not settings:
            embed = discord.Embed(
                title="⚙️ 設定状況",
                description="まだ設定が登録されていません。",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(
                embed=embed, ephemeral=True
            )
            return

        embed = discord.Embed(
            title="⚙️ 現在の設定状況", color=discord.Color.blue()
        )

        def ch_fmt(ch_id):
            return f"<#{ch_id}>" if ch_id else "未設定"

        # Leveling 設定
        lvl_status = "有効" if settings.get("leveling_enabled", True) else "無効"
        embed.add_field(
            name="📊 レベル機能",
            value=f"状態: {lvl_status}\nLevelUp: {ch_fmt(settings.get('log_levelup_channel_id'))}\nRankUp: {ch_fmt(settings.get('log_rankup_channel_id'))}",
            inline=False,
        )

        # Quiz 設定
        embed.add_field(
            name="🧩 クイズ設定",
            value=f"専用Ch: {ch_fmt(settings.get('quiz_channel_id'))}\n回答時間: {settings.get('quiz_answer_time', 30)}秒\n制限時間: {settings.get('quiz_time_limit', 60)}秒",
            inline=False,
        )

        # Moderation 設定
        mod_status = "有効" if settings.get("auto_mod_enabled", True) else "無効"
        embed.add_field(
            name="🛡️ モデレーション",
            value=f"自動Mod: {mod_status}\n冷笑削除Ch: {ch_fmt(settings.get('reishou_channel_id'))}\nModログCh: {ch_fmt(settings.get('mod_log_channel_id'))}",
            inline=False,
        )

        # EEW 設定
        embed.add_field(
            name="🚨 地震速報",
            value=f"送信先Ch: {ch_fmt(settings.get('eew_channel_id'))}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    if not hasattr(bot, "db_pool") or bot.db_pool is None:
        if not DATABASE_URL:
            raise ValueError("環境変数 DATABASE_URL が設定されていません。")
        bot.db_pool = await asyncpg.create_pool(DATABASE_URL)

    async with bot.db_pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)

    await bot.add_cog(SettingsCog(bot))