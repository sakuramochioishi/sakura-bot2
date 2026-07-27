from datetime import datetime, timezone
import os
import random
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

# 冒険者ランクの設定 (必要レベル : (ロール名, ロールカラー))
ADVENTURER_RANKS = {
    100: ("👑 Legend（伝説の勇者）", discord.Color.from_rgb(255, 215, 0)),  # 黄金
    70: ("🛡️ Adamantite（金剛級）", discord.Color.from_rgb(112, 128, 144)), # アダマンタイト・スレート
    50: ("🔮 Mythril（神銀級）", discord.Color.from_rgb(138, 43, 226)),     # ミスリル・バイオレット
    35: ("⚜️ Platinum（白金級）", discord.Color.from_rgb(229, 228, 226)),   # プラチナ
    20: ("🥇 Gold（黄金級）", discord.Color.gold()),                        # ゴールド
    10: ("⚔️ Silver（白銀級）", discord.Color.light_grey()),                 # シルバー
    5:  ("🗡️ Bronze（青銅級）", discord.Color.dark_orange()),               # ブロンズ
    1:  ("🔰 Novice（駆け出し）", discord.Color.green()),                    # グリーン
}


class Leveling(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_pool = None

    async def cog_load(self):
        """Cogロード時にNeonへ接続"""
        db_url = os.getenv("DATABASE_URL")
        self.db_pool = await asyncpg.create_pool(db_url)

    async def cog_unload(self):
        """Cogアンロード時に接続切断"""
        if self.db_pool:
            await self.db_pool.close()

    def calculate_level(self, xp: int) -> int:
        return int((xp / 100) ** (1 / 1.5)) + 1

    def get_rank_info(self, level: int) -> tuple[str, discord.Color]:
        """レベルに応じた (ロール名, ロールカラー) を返す"""
        for req_lvl, (rank_name, color) in ADVENTURER_RANKS.items():
            if level >= req_lvl:
                return rank_name, color
        return "🔰 Novice（駆け出し）", discord.Color.green()

    async def ensure_roles(
        self, guild: discord.Guild
    ) -> tuple[list[str], list[str]]:
        """サーバー内に必要な発言ランクロールが存在しなければ自動作成する"""
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
                except Exception as e:
                    print(
                        f"[{guild.name}] ロール作成エラー ({role_name}): {e}"
                    )
            else:
                already_existing_roles.append(role_name)

        return created_roles, already_existing_roles

    async def update_user_roles(
        self, member: discord.Member, new_level: int
    ):
        """レベルに応じて発言ランクロールを自動付与・付け替え"""
        guild = member.guild
        await self.ensure_roles(guild)

        target_rank_name, _ = self.get_rank_info(new_level)
        all_rank_names = {info[0] for info in ADVENTURER_RANKS.values()}

        roles_to_remove = [
            role
            for role in member.roles
            if role.name in all_rank_names
            and role.name != target_rank_name
        ]
        target_role = discord.utils.get(guild.roles, name=target_rank_name)

        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)

        if target_role and target_role not in member.roles:
            await member.add_roles(target_role)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.ensure_roles(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.ensure_roles(guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = datetime.now(timezone.utc)

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

            # 10秒のクールダウン
            if row and row["last_message_at"]:
                delta = (now - row["last_message_at"]).total_seconds()
                if delta < 10:
                    return

            current_xp = row["xp"] if row else 0
            current_level = row["level"] if row else 1

            added_xp = random.randint(15, 25)
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
                await message.channel.send(
                    f"🎉 {message.author.mention} が **Lv.{new_level}** にレベルアップ！\n"
                    f"現在の発言ランク: **{rank_name}**"
                )

                if isinstance(message.author, discord.Member):
                    await self.update_user_roles(message.author, new_level)

    # --- /level コマンド ---
    @app_commands.command(
        name="level", description="自分のレベルと発言ランクを確認します"
    )
    async def level(
        self,
        interaction: discord.Interaction,
        target_user: discord.User = None,
    ):
        user = target_user or interaction.user
        guild_id = interaction.guild_id

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
            title=f"⚔️ {user.display_name} の発言数ステータス", color=rank_color
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="発言ランク", value=f"**{rank_name}**", inline=False)
        embed.add_field(name="レベル", value=f"**Lv. {level}**", inline=True)
        embed.add_field(
            name="XP", value=f"**{xp}** / {next_level_xp} XP", inline=True
        )

        await interaction.response.send_message(embed=embed)

    # --- /rank コマンド ---
    @app_commands.command(
        name="rank",
        description="このサーバーの発言数レベルランキングTOP 10を表示します",
    )
    async def rank(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
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

    # --- /role コマンド (管理者限定) ---
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

    @role.error
    async def role_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ このコマンドを実行するには**管理者権限（Administrator）**が必要です。",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))