import asyncio
from datetime import datetime, timezone
import logging
import os
import random
from typing import Optional

asyncpg = None  # 型補完用ダミー
try:
    import asyncpg
except ImportError:
    pass

import discord
from discord import app_commands
from discord.ext import commands

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


# --- Botオーナー判定用チェック関数 ---
async def is_bot_owner(interaction: discord.Interaction) -> bool:
    """実行者がBotの所有者であるかを判定する"""
    return await interaction.client.is_owner(interaction.user)


class LevelingCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_pool: Optional[asyncpg.Pool] = None
        self._roles_ensured: bool = False  # on_ready の重複実行防止フラグ

    async def cog_load(self):
        """Cogロード時にDB接続 & テーブル自動作成"""
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
        """レベル到達に必要な累積XPを計算（calculate_levelの逆算）"""
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
    # 📢 通知チャンネル取得メソッド
    # ==========================================
    async def get_notification_channel(
        self, guild: discord.Guild, origin_channel: discord.TextChannel, kind: str = "levelup"
    ) -> discord.TextChannel:
        """
        SettingsCog から直接通知用チャンネルIDを取得する。
        kind="levelup" -> log_levelup_channel_id
        kind="rankup"  -> log_rankup_channel_id
        """
        target_channel_id = None
        settings_cog = self.bot.get_cog("SettingsCog")

        if not settings_cog:
            logger.debug("デバッグ: SettingsCog がロードされていません。")
        else:
            method_name = f"get_log_{kind}_channel_id"
            attr_name = f"log_{kind}_channel_id"

            try:
                # 1. get_log_levelup_channel_id / get_log_rankup_channel_id メソッドが存在する場合
                if hasattr(settings_cog, method_name):
                    func = getattr(settings_cog, method_name)
                    if asyncio.iscoroutinefunction(func):
                        target_channel_id = await func(guild.id)
                    else:
                        target_channel_id = func(guild.id)

                # 2. log_levelup_channel_id / log_rankup_channel_id 属性または辞書を直接参照する場合
                elif hasattr(settings_cog, attr_name):
                    attr = getattr(settings_cog, attr_name)
                    if isinstance(attr, dict):
                        target_channel_id = attr.get(guild.id)
                    else:
                        target_channel_id = attr
            except Exception as e:
                logger.warning(
                    f"SettingsCog から {attr_name} の取得に失敗しました: {e}"
                )

        if target_channel_id:
            try:
                channel_id_int = int(target_channel_id)
                # キャッシュから取得を試み、無ければ API から取得
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
                else:
                    logger.warning(f"指定されたチャンネル(ID: {channel_id_int})への送信権限が無いか存在しません。")
            except ValueError:
                logger.error(f"取得されたチャンネルID ({target_channel_id}) を int に変換できませんでした。")

        # rankup チャンネルが指定されていない・見つからない場合は levelup チャンネルにフォールバック
        if kind == "rankup":
            return await self.get_notification_channel(
                guild, origin_channel, kind="levelup"
            )

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
                    logger.warning(
                        f"[{guild.name}] ロール作成権限が不足しています: {role_name}"
                    )
                except Exception as e:
                    logger.error(
                        f"[{guild.name}] ロール作成エラー ({role_name}): {e}"
                    )
            else:
                already_existing_roles.append(role_name)

        return created_roles, already_existing_roles

    async def update_user_roles(
        self, member: discord.Member, new_level: int
    ) -> bool:
        """レベルに応じて発言ランクロールを自動付与・付け替え（ランクが変化した場合はTrueを返す）"""
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return False

        target_rank_name, _ = self.get_rank_info(new_level)
        all_rank_names = {info[0] for info in ADVENTURER_RANKS.values()}

        target_role = discord.utils.get(guild.roles, name=target_rank_name)

        # 剥奪すべき古いランクロールを抽出
        roles_to_remove = [
            role
            for role in member.roles
            if role.name in all_rank_names and role.name != target_rank_name
        ]

        is_rank_changed = False
        try:
            # 古いランクの削除
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove, reason="レベルアップに伴う旧ランクの削除"
                )

            # 新ランクの付与（所有していない場合のみ）
            if target_role and target_role not in member.roles:
                await member.add_roles(
                    target_role, reason="レベルアップに伴う新ランクの付与"
                )
                is_rank_changed = True
        except discord.Forbidden:
            logger.warning(
                f"[{guild.name}] ロール変更権限が不足しています（Botのロール順位を確認してください）"
            )
        except Exception as e:
            logger.error(
                f"[{guild.name}] {member.display_name} のロール更新失敗: {e}"
            )

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
        # BotやDMでの発言は無視
        if message.author.bot or not message.guild or not self.db_pool:
            return

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

                # 30秒のクールダウンチェック
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

                # レベルアップ時の処理
                if new_level > current_level:
                    rank_name, _ = self.get_rank_info(new_level)

                    # SettingsCog から log_levelup_channel_id を取得
                    if isinstance(message.channel, discord.TextChannel):
                        level_channel = await self.get_notification_channel(
                            message.guild, message.channel, kind="levelup"
                        )

                        try:
                            # メンション通知の送信
                            await level_channel.send(
                                f"🎉 {message.author.mention} が **Lv.{new_level}** にレベルアップ！\n"
                                f"現在の発言ランク: **{rank_name}**",
                                allowed_mentions=discord.AllowedMentions(users=False),
                            )
                        except discord.Forbidden:
                            logger.warning(
                                f"[{message.guild.name}] チャンネル {level_channel.name} への送信権限がありません。"
                            )

                    # ロール更新とランクアップチェック
                    if isinstance(message.author, discord.Member):
                        prev_rank_name, _ = self.get_rank_info(current_level)
                        is_rank_changed = await self.update_user_roles(
                            message.author, new_level
                        )

                        # ランク帯自体が上がった場合の通知処理（log_rankup_channel_id を取得）
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
                                logger.warning(
                                    f"[{message.guild.name}] チャンネル {rank_channel.name} への送信権限がありません。"
                                )

        except Exception as e:
            logger.error(f"on_message の処理中にエラーが発生しました: {e}", exc_info=True)

    # ==========================================
    # ⚔️ 一般ユーザー用スラッシュコマンド
    # ==========================================
    @app_commands.command(
        name="level", description="自分または指定ユーザーのレベルと発言ランクを確認します"
    )
    async def level(
        self,
        interaction: discord.Interaction,
        target_user: discord.User | None = None,
    ):
        user = target_user or interaction.user
        guild_id = interaction.guild_id

        if not interaction.guild or not self.db_pool or not guild_id:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT xp, level FROM user_levels 
                WHERE guild_id = $1 AND user_id = $2
            """,
                guild_id,
                user.id,
            )

        xp = row["xp"] if row else 0
        level = row["level"] if row else 1

        next_level_xp = int(100 * (level**1.5))
        rank_name, rank_color = self.get_rank_info(level)

        embed = discord.Embed(
            title=f"⚔️ {user.display_name} の発言ステータス", color=rank_color
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="発言ランク", value=f"**{rank_name}**", inline=False)
        embed.add_field(name="レベル", value=f"**Lv. {level}**", inline=True)
        embed.add_field(
            name="XP", value=f"**{xp}** / {next_level_xp} XP", inline=True
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="rank",
        description="このサーバーの発言数レベルランキングTOP 10を表示します",
    )
    async def rank(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild or not self.db_pool:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        await interaction.response.defer()

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, xp, level 
                FROM user_levels 
                WHERE guild_id = $1 
                ORDER BY xp DESC 
                LIMIT 10
            """,
                guild.id,
            )

        if not rows:
            await interaction.followup.send(
                "まだこのサーバーにはレベルデータが存在しません。"
            )
            return

        embed = discord.Embed(
            title=f"🏆 {guild.name} の発言数レベルランキング",
            color=discord.Color.gold(),
        )

        rank_list = []
        for index, row in enumerate(rows, start=1):
            user_id = row["user_id"]
            xp = row["xp"]
            level = row["level"]

            member = guild.get_member(user_id)
            user_name = member.display_name if member else f"ユーザー({user_id})"
            rank_name, _ = self.get_rank_info(level)

            medal = (
                "🥇"
                if index == 1
                else "🥈" if index == 2 else "🥉" if index == 3 else f"**{index}.**"
            )
            rank_list.append(
                f"{medal} **{user_name}** - Lv.{level} ({rank_name}) | `{xp} XP`"
            )

        embed.description = "\n".join(rank_list)
        await interaction.followup.send(embed=embed)

    # ==========================================
    # 🔨 サーバー管理者用スラッシュコマンド
    # ==========================================
    @app_commands.command(
        name="role",
        description="発言システム用ロールの確認および未作成ロールを追加します（管理者専用）",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def role(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        created_roles, _ = await self.ensure_roles(guild)

        if not created_roles:
            await interaction.response.send_message(
                "✅ 発言システムに必要なロールはすでにすべて存在しています！",
                ephemeral=True,
            )
            return

        created_list_str = "\n".join([f"・{r}" for r in created_roles])
        embed = discord.Embed(
            title="🔨 発言ランクロールの自動生成完了",
            description=f"不足していた以下のロールを追加しました：\n\n{created_list_str}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="sync_beginner_roles",
        description="いずれかのランクロールを未所有のユーザーに初期ロール（Novice）を一括付与します（管理者専用）",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_beginner_roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        await self.ensure_roles(guild)

        target_role_name = "🔰 Novice（駆け出し）"
        beginner_role = discord.utils.get(guild.roles, name=target_role_name)

        if not beginner_role:
            await interaction.followup.send(
                f"❌ ロール `{target_role_name}` が見つかりませんでした。"
            )
            return

        all_rank_role_names = {info[0] for info in ADVENTURER_RANKS.values()}

        added_count = 0
        already_has_novice_count = 0
        has_higher_rank_count = 0

        members = guild.members
        if len(members) < guild.member_count:
            try:
                members = [m async for m in guild.fetch_members(limit=None)]
            except Exception:
                pass

        for member in members:
            if member.bot:
                continue

            user_rank_roles = [
                role.name for role in member.roles if role.name in all_rank_role_names
            ]

            if user_rank_roles:
                if target_role_name in user_rank_roles:
                    already_has_novice_count += 1
                else:
                    has_higher_rank_count += 1
                continue

            try:
                await member.add_roles(beginner_role, reason="一括初期ロール付与")
                added_count += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(
                    f"[{guild.name}] {member.display_name} へのロール付与失敗: {e}"
                )

        await interaction.followup.send(
            f"✅ **一括付与が完了しました！**\n"
            f"・新規付与: **{added_count} 人**\n"
            f"・既に Novice 所有済み: **{already_has_novice_count} 人**\n"
            f"・上位ランク所有（除外）: **{has_higher_rank_count} 人**"
        )

    # ==========================================
    # 👑 Bot所有者(オーナー)専用コマンド
    # ==========================================
    @app_commands.command(
        name="level_debug", description="【デバッグ】指定ユーザーのDB生データや状態を確認します（Botオーナー専用）"
    )
    @app_commands.check(is_bot_owner)
    async def level_debug(
        self,
        interaction: discord.Interaction,
        target: Optional[discord.Member] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user = target or interaction.user

        if not interaction.guild_id or not self.db_pool:
            await interaction.followup.send("DBまたはギルド情報が取得できません。", ephemeral=True)
            return

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT xp, level, last_message_at FROM user_levels WHERE guild_id = $1 AND user_id = $2",
                interaction.guild_id,
                user.id,
            )
            total_users = await conn.fetchval(
                "SELECT COUNT(*) FROM user_levels WHERE guild_id = $1",
                interaction.guild_id,
            )

        embed = discord.Embed(
            title=f"🛠️ デバッグ情報: {user.display_name}", color=discord.Color.gold()
        )
        embed.add_field(name="ユーザーID", value=f"`{user.id}`", inline=True)
        embed.add_field(name="ギルドID", value=f"`{interaction.guild_id}`", inline=True)

        if row:
            embed.add_field(name="DB XP", value=f"`{row['xp']}`", inline=True)
            embed.add_field(name="DB Level", value=f"`{row['level']}`", inline=True)
            embed.add_field(
                name="最終獲得日時 (UTC)",
                value=f"`{row['last_message_at']}`",
                inline=False,
            )
        else:
            embed.add_field(name="DB レコード", value="❌ レコードが存在しません", inline=False)

        embed.add_field(name="ギルド内登録ユーザー数", value=f"{total_users} 人", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="add_xp", description="【管理者】指定したユーザーにXPを付与します（Botオーナー専用）"
    )
    @app_commands.describe(target="対象ユーザー", amount="付与するXP量")
    @app_commands.check(is_bot_owner)
    async def add_xp(
        self, interaction: discord.Interaction, target: discord.Member, amount: int
    ):
        if amount <= 0:
            await interaction.response.send_message("付与するXPは1以上にしてください。", ephemeral=True)
            return

        if not interaction.guild or not self.db_pool:
            await interaction.response.send_message("ギルドまたはDB接続が存在しません。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        now = datetime.now(timezone.utc)
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT xp, level FROM user_levels WHERE guild_id = $1 AND user_id = $2",
                interaction.guild_id,
                target.id,
            )

            current_xp = row["xp"] if row else 0
            old_level = row["level"] if row else 1
            new_xp = current_xp + amount
            new_level = self.calculate_level(new_xp)

            await conn.execute(
                """
                INSERT INTO user_levels (guild_id, user_id, xp, level, last_message_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) 
                DO UPDATE SET xp = $3, level = $4, last_message_at = $5;
                """,
                interaction.guild_id,
                target.id,
                new_xp,
                new_level,
                now,
            )

        # ロール更新と通知処理
        if new_level > old_level:
            await self.update_user_roles(target, new_level)
            if isinstance(interaction.channel, discord.TextChannel):
                notify_channel = await self.get_notification_channel(
                    interaction.guild, interaction.channel, kind="levelup"
                )
                await notify_channel.send(
                    f"🎉 {target.mention} がレベルアップしました！ **Lv.{old_level}** ➔ **Lv.{new_level}**",
                    allowed_mentions=discord.AllowedMentions(users=False),
                )

        await interaction.followup.send(
            f"✅ **{target.mention}** に `{amount} XP` を付与しました。\n"
            f"現在のXP: `{new_xp}` | レベル: `{new_level}`",
            ephemeral=True,
        )

    @app_commands.command(
        name="set_level", description="【管理者】指定したユーザーのレベルを直接変更します（Botオーナー専用）"
    )
    @app_commands.describe(target="対象ユーザー", level="設定するレベル")
    @app_commands.check(is_bot_owner)
    async def set_level(
        self, interaction: discord.Interaction, target: discord.Member, level: int
    ):
        if level < 1:
            await interaction.response.send_message("レベルは1以上で指定してください。", ephemeral=True)
            return

        if not interaction.guild or not self.db_pool:
            await interaction.response.send_message("ギルドまたはDB接続が存在しません。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        required_xp = self.calculate_required_xp(level)
        now = datetime.now(timezone.utc)

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_levels (guild_id, user_id, xp, level, last_message_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) 
                DO UPDATE SET xp = $3, level = $4, last_message_at = $5;
                """,
                interaction.guild_id,
                target.id,
                required_xp,
                level,
                now,
            )

        await self.update_user_roles(target, level)

        await interaction.followup.send(
            f"✅ **{target.mention}** のレベルを `{level}`（累積XP: `{required_xp}`）に設定しました。",
            ephemeral=True,
        )

    @app_commands.command(
        name="reset_level", description="【管理者】指定したユーザーのXP・レベルをリセットします（Botオーナー専用）"
    )
    @app_commands.describe(target="対象ユーザー")
    @app_commands.check(is_bot_owner)
    async def reset_level(
        self, interaction: discord.Interaction, target: discord.Member
    ):
        if not interaction.guild_id or not self.db_pool:
            await interaction.response.send_message("ギルドまたはDB接続が存在しません。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_levels WHERE guild_id = $1 AND user_id = $2",
                interaction.guild_id,
                target.id,
            )

        # レベル1（初期ランク）に更新
        await self.update_user_roles(target, 1)

        await interaction.followup.send(
            f"🔄 **{target.mention}** のレベルデータをリセットしました。",
            ephemeral=True,
        )

    # ==========================================
    # ⚠️ エラーハンドラー
    # ==========================================
    @role.error
    @sync_beginner_roles.error
    @add_xp.error
    @set_level.error
    @reset_level.error
    @level_debug.error
    async def command_error_handler(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ このコマンドを実行するには**管理者権限（Administrator）**が必要です。"
        elif isinstance(error, app_commands.CheckFailure):
            msg = "🚫 このコマンドはBotの所有者のみ実行できます。"
        else:
            logger.error(f"コマンドエラーが発生しました: {error}", exc_info=True)
            msg = f"❌ エラーが発生しました: {error}"

        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))