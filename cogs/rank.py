import asyncio
from datetime import datetime, timezone
import logging
import os
import random
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

# 冒険者ランクの設定 (必要レベル : (ロール名, ロールカラー))
ADVENTURER_RANKS = {
    777: ("🪽 God (神)", discord.Color.from_rgb(255, 0, 0)),  # 赤
    600: ("👑 Legend（伝説の勇者）", discord.Color.from_rgb(255, 215, 0)),  # 黄金
    400: ("🛡️ Adamantite（金剛級）", discord.Color.from_rgb(112, 128, 144)),  # アダマンタイト
    200: ("🔮 Mythril（神銀級）", discord.Color.from_rgb(138, 43, 226)),  # ミスリル
    100: ("⚜️ Platinum（白金級）", discord.Color.from_rgb(229, 228, 226)),  # プラチナ
    50: ("🥇 Gold（黄金級）", discord.Color.gold()),  # ゴールド
    25: ("⚔️ Silver（白銀級）", discord.Color.light_grey()),  # シルバー
    5: ("🗡️ Bronze（青銅級）", discord.Color.dark_orange()),  # ブロンズ
    1: ("🔰 Novice（駆け出し）", discord.Color.green()),  # グリーン
}


class LevelingCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_pool: Optional["asyncpg.Pool"] = None
        self._roles_ensured: bool = False  # on_ready の重複実行防止フラグ

    async def cog_load(self):
        """Cogロード時にDB接続 & テーブル自動作成"""
        import asyncpg

        db_url = os.getenv("DATABASE_URL3")
        if not db_url:
            raise ValueError(
                "環境変数 'DATABASE_URL3' が設定されていません。"
            )

        self.db_pool = await asyncpg.create_pool(db_url)

        async with self.db_pool.acquire() as conn:
            # ユーザーレベル管理テーブル
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_levels (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    xp INT DEFAULT 0,
                    level INT DEFAULT 1,
                    last_message_at TIMESTAMP WITH TIME ZONE,
                    PRIMARY KEY (guild_id, user_id)
                );
            """
            )

    async def cog_unload(self):
        """Cogアンロード時にDB接続を切断"""
        if self.db_pool:
            await self.db_pool.close()

    def calculate_level(self, xp: int) -> int:
        """累積XPからレベルを計算"""
        return int((xp / 100) ** (1 / 1.5)) + 1

    def calculate_required_xp(self, level: int) -> int:
        """レベル到達に必要な累積XPを計算"""
        if level <= 1:
            return 0
        return int(100 * ((level - 1) ** 1.5))

    def get_rank_info(self, level: int) -> tuple[str, discord.Color]:
        """レベルに応じた (ロール名, ロールカラー) を返す"""
        for req_lvl, (rank_name, color) in ADVENTURER_RANKS.items():
            if level >= req_lvl:
                return rank_name, color
        return "🔰 Novice（駆け出し）", discord.Color.green()

    # ==========================================
    # 📢 通知チャンネル取得メソッド (SettingsCog 連携)
    # ==========================================
    async def get_notification_channel(
        self, guild: discord.Guild, origin_channel: discord.TextChannel, kind: str = "levelup"
    ) -> discord.TextChannel:
        """SettingsCog から通知用チャンネルIDを取得する"""
        target_channel_id = None
        settings_cog = self.bot.get_cog("SettingsCog")

        if settings_cog and hasattr(settings_cog, "get_leveling_config"):
            try:
                config = await settings_cog.get_leveling_config(guild.id)
                if config:
                    if kind == "levelup":
                        target_channel_id = config.get("levelup_channel_id")
                    elif kind == "rankup":
                        target_channel_id = config.get("rankup_channel_id") or config.get("levelup_channel_id")
            except Exception as e:
                logger.warning(f"SettingsCog からの設定取得に失敗しました: {e}")

        if target_channel_id:
            try:
                channel_id_int = int(target_channel_id)
                target_channel = guild.get_channel(channel_id_int)
                if target_channel is None:
                    try:
                        target_channel = await self.bot.fetch_channel(channel_id_int)
                    except Exception:
                        target_channel = None

                if (
                    target_channel
                    and isinstance(target_channel, discord.TextChannel)
                    and target_channel.permissions_for(guild.me).send_messages
                ):
                    return target_channel
            except ValueError:
                logger.error(f"取得されたチャンネルID ({target_channel_id}) を int に変換できませんでした。")

        if kind == "rankup":
            return await self.get_notification_channel(guild, origin_channel, kind="levelup")

        return origin_channel

    async def ensure_roles(
        self, guild: discord.Guild
    ) -> tuple[list[str], list[str]]:
        """サーバー内に必要な発言ランクロールが存在しなければ自動作成する"""
        if not guild.me.guild_permissions.manage_roles:
            return [], []

        existing_role_names = {role.name for role in guild.roles}
        created_roles = []
        already_existing_roles = []

        for req_lvl, (role_name, color) in ADVENTURER_RANKS.items():
            if role_name not in existing_role_names:
                try:
                    await guild.create_role(
                        name=role_name,
                        color=color,
                        reason="発言レベルシステム用のロール自動生成",
                    )
                    created_roles.append(role_name)
                except discord.Forbidden:
                    logger.warning(f"[{guild.name}] ロール作成権限が不足しています: {role_name}")
                except Exception as e:
                    logger.error(f"[{guild.name}] ロール作成エラー ({role_name}): {e}")
            else:
                already_existing_roles.append(role_name)

        return created_roles, already_existing_roles

    async def update_user_roles(
        self, member: discord.Member, new_level: int
    ) -> bool:
        """レベルに応じて発言ランクロールを自動付与・付け替え"""
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return False

        target_rank_name, _ = self.get_rank_info(new_level)
        all_rank_names = {info[0] for info in ADVENTURER_RANKS.values()}

        target_role = discord.utils.get(guild.roles, name=target_rank_name)

        roles_to_remove = [
            role
            for role in member.roles
            if role.name in all_rank_names and role.name != target_rank_name
        ]

        is_rank_changed = False
        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove, reason="レベルアップに伴う旧ランクの削除"
                )

            if target_role and target_role not in member.roles:
                await member.add_roles(
                    target_role, reason="レベルアップに伴う新ランクの付与"
                )
                is_rank_changed = True
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] ロール変更権限が不足しています")
        except Exception as e:
            logger.error(f"[{guild.name}] {member.display_name} のロール更新失敗: {e}")

        return is_rank_changed

    # ==========================================
    # 🎧 イベントリスナー
    # ==========================================
    @commands.Cog.listener()
    async def on_ready(self):
        if not self._roles_ensured:
            for guild in self.bot.guilds:
                await self.ensure_roles(guild)
            self._roles_ensured = True

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.ensure_roles(guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not self.db_pool:
            return

        # SettingsCog から有効フラグを確認
        settings_cog = self.bot.get_cog("SettingsCog")
        if settings_cog and hasattr(settings_cog, "get_leveling_config"):
            try:
                config = await settings_cog.get_leveling_config(message.guild.id)
                if config and not config.get("enabled", True):
                    return  # レベリングが無効化されている場合はスキップ
            except Exception:
                pass

        guild_id = message.guild.id
        user_id = message.author.id
        now = datetime.now(timezone.utc)

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT xp, level, last_message_at 
                    FROM user_levels 
                    WHERE guild_id = $1 AND user_id = $2
                """,
                    guild_id,
                    user_id,
                )

                if row and row["last_message_at"]:
                    delta = (now - row["last_message_at"]).total_seconds()
                    if delta < 30:
                        return

                current_xp = row["xp"] if row else 0
                current_level = row["level"] if row else 1

                added_xp = random.randint(10, 30)
                new_xp = current_xp + added_xp
                new_level = self.calculate_level(new_xp)

                await conn.execute(
                    """
                    INSERT INTO user_levels (guild_id, user_id, xp, level, last_message_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (guild_id, user_id) 
                    DO UPDATE SET 
                        xp = EXCLUDED.xp,
                        level = EXCLUDED.level,
                        last_message_at = EXCLUDED.last_message_at
                """,
                    guild_id,
                    user_id,
                    new_xp,
                    new_level,
                    now,
                )

                if new_level > current_level:
                    rank_name, _ = self.get_rank_info(new_level)

                    if isinstance(message.channel, discord.TextChannel):
                        level_channel = await self.get_notification_channel(
                            message.guild, message.channel, kind="levelup"
                        )

                        try:
                            await level_channel.send(
                                f"🎉 {message.author.mention} が **Lv.{new_level}** にレベルアップ！\n"
                                f"現在の発言ランク: **{rank_name}**",
                                allowed_mentions=discord.AllowedMentions(users=False),
                            )
                        except discord.Forbidden:
                            logger.warning(f"チャンネル {level_channel.name} への送信権限がありません。")

                    if isinstance(message.author, discord.Member):
                        prev_rank_name, _ = self.get_rank_info(current_level)
                        is_rank_changed = await self.update_user_roles(
                            message.author, new_level
                        )

                        if (prev_rank_name != rank_name or is_rank_changed) and isinstance(
                            message.channel, discord.TextChannel
                        ):
                            rank_channel = await self.get_notification_channel(
                                message.guild, message.channel, kind="rankup"
                            )
                            embed = discord.Embed(
                                title="👑 RANK UP!",
                                description=f"{message.author.mention} が新しいランク **【{rank_name}】** に昇格しました！",
                                color=discord.Color.purple(),
                            )
                            try:
                                await rank_channel.send(
                                    embed=embed,
                                    allowed_mentions=discord.AllowedMentions(users=False),
                                )
                            except discord.Forbidden:
                                pass

        except Exception as e:
            logger.error(f"on_message の処理中にエラーが発生しました: {e}", exc_info=True)

    @app_commands.command(name="level", description="自分または指定ユーザーのレベルと発言ランクを確認します")
    async def level(self, interaction: discord.Interaction, target_user: discord.User | None = None):
        user = target_user or interaction.user
        guild_id = interaction.guild_id

        if not interaction.guild or not self.db_pool or not guild_id:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
            return

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT xp, level FROM user_levels WHERE guild_id = $1 AND user_id = $2", guild_id, user.id)

        xp = row["xp"] if row else 0
        level = row["level"] if row else 1
        next_level_xp = int(100 * (level**1.5))
        rank_name, rank_color = self.get_rank_info(level)

        embed = discord.Embed(title=f"⚔️ {user.display_name} の発言ステータス", color=rank_color)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="発言ランク", value=f"**{rank_name}**", inline=False)
        embed.add_field(name="レベル", value=f"**Lv. {level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp}** / {next_level_xp} XP", inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))