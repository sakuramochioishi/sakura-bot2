from __future__ import annotations

import asyncio
import json
import os
import discord
from discord import app_commands
from discord.ext import commands
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SETTINGS_FILE = "bot_config.json"


class SettingsCog(commands.GroupCog, name="setting"):

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def cog_load(self):
        """Cog読み込み時に非同期でDB初期化および移行を実施"""
        await asyncio.to_thread(self._init_db)
        await asyncio.to_thread(self._migrate_json_to_db)

    def _get_connection(self):
        """DB接続を取得するヘルパー"""
        return psycopg2.connect(DATABASE_URL)

    def _init_db(self):
        """データベースに設定保存用のテーブルを作成し、必要なカラムを保証する"""
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS guild_settings (
                            guild_id BIGINT PRIMARY KEY,
                            quiz_timeout TEXT DEFAULT '900.0',
                            answer_timeout TEXT DEFAULT '15.0',
                            channels TEXT[] DEFAULT '{}'::TEXT[],
                            level_channel_id BIGINT DEFAULT NULL,
                            rank_channel_id BIGINT DEFAULT NULL,
                            eew_channel_id BIGINT DEFAULT NULL
                        );
                    """)

                    # カラムが存在しない場合の安全な追加
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS quiz_timeout TEXT DEFAULT '900.0';")
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS answer_timeout TEXT DEFAULT '15.0';")
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS channels TEXT[] DEFAULT '{}'::TEXT[];")
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS level_channel_id BIGINT DEFAULT NULL;")
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS rank_channel_id BIGINT DEFAULT NULL;")
                    cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS eew_channel_id BIGINT DEFAULT NULL;")
        finally:
            conn.close()

    def _migrate_json_to_db(self):
        """古い bot_config.json があれば、自動的にデータベースへ移行する"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    old_data = json.load(f)

                if old_data:
                    quiz_timeout = str(old_data.get("quiz", {}).get("quiz_timeout", 900.0))
                    answer_timeout = str(old_data.get("quiz", {}).get("answer_timeout", 15.0))
                    channels = [str(cid) for cid in old_data.get("reishou", {}).get("channels", [])]

                    conn = self._get_connection()
                    try:
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    INSERT INTO guild_settings (guild_id, quiz_timeout, answer_timeout, channels)
                                    VALUES (0, %s, %s, %s)
                                    ON CONFLICT (guild_id) DO NOTHING;
                                """,
                                    (quiz_timeout, answer_timeout, channels),
                                )
                        print("⚙️ 【移行完了】設定JSONデータをデータベースに引っ越ししました！")
                    finally:
                        conn.close()

                os.rename(SETTINGS_FILE, f"{SETTINGS_FILE}.bak")
                print(f"📦 古い設定ファイルを {SETTINGS_FILE}.bak に退避しました。")
            except Exception as e:
                print(f"⚠️ 設定JSONの移行中にエラーが発生しました: {e}")

    def _get_guild_settings_sync(self, guild_id: int) -> dict:
        """指定されたギルドの設定を取得する（同期処理）"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id
                    FROM guild_settings WHERE guild_id = %s;
                """,
                    (guild_id,),
                )
                row = cur.fetchone()

                if row is None:
                    # デフォルト行(guild_id=0)を取得
                    cur.execute(
                        "SELECT quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id FROM guild_settings WHERE guild_id = 0;"
                    )
                    default_row = cur.fetchone()

                    if default_row:
                        quiz_t, answer_t, chs, l_ch, r_ch, e_ch = default_row
                    else:
                        quiz_t, answer_t, chs, l_ch, r_ch, e_ch = (
                            "900.0", "15.0", [], None, None, None
                        )

                    with conn:
                        cur.execute(
                            """
                            INSERT INTO guild_settings (guild_id, quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (guild_id) DO NOTHING;
                        """,
                            (guild_id, quiz_t, answer_t, chs, l_ch, r_ch, e_ch),
                        )
                    row = (quiz_t, answer_t, chs, l_ch, r_ch, e_ch)

            return {
                "quiz_timeout": float(row[0]) if row[0] else 900.0,
                "answer_timeout": float(row[1]) if row[1] else 15.0,
                "channels": [int(cid) for cid in row[2]] if row[2] else [],
                "level_channel_id": int(row[3]) if row[3] is not None else None,
                "rank_channel_id": int(row[4]) if row[4] is not None else None,
                "eew_channel_id": int(row[5]) if row[5] is not None else None,
            }
        finally:
            conn.close()

    async def _get_guild_settings(self, guild_id: int) -> dict:
        """非同期ラッパー"""
        return await asyncio.to_thread(self._get_guild_settings_sync, guild_id)

    def _save_guild_settings_sync(
        self,
        guild_id: int,
        quiz_timeout: float,
        answer_timeout: float,
        channels: list[int],
        level_channel_id: int | None,
        rank_channel_id: int | None,
        eew_channel_id: int | None,
    ):
        """指定されたギルドの設定を保存する（同期処理）"""
        channels_str_list = [str(cid) for cid in channels]

        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO guild_settings (
                            guild_id, quiz_timeout, answer_timeout, channels, 
                            level_channel_id, rank_channel_id, eew_channel_id
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (guild_id) DO UPDATE SET
                            quiz_timeout = EXCLUDED.quiz_timeout,
                            answer_timeout = EXCLUDED.answer_timeout,
                            channels = EXCLUDED.channels,
                            level_channel_id = EXCLUDED.level_channel_id,
                            rank_channel_id = EXCLUDED.rank_channel_id,
                            eew_channel_id = EXCLUDED.eew_channel_id;
                    """,
                        (
                            guild_id,
                            str(quiz_timeout),
                            str(answer_timeout),
                            channels_str_list,
                            level_channel_id,
                            rank_channel_id,
                            eew_channel_id,
                        ),
                    )
        finally:
            conn.close()

    async def _save_guild_settings(self, *args, **kwargs):
        """非同期ラッパー"""
        await asyncio.to_thread(self._save_guild_settings_sync, *args, **kwargs)

    # ==========================================
    # 👥 他のCogから呼び出すヘルパーメソッド
    # ==========================================
    async def get_quiz_timeout(self, guild_id: int) -> float:
        settings = await self._get_guild_settings(guild_id)
        return settings["quiz_timeout"]

    async def get_answer_timeout(self, guild_id: int) -> float:
        settings = await self._get_guild_settings(guild_id)
        return settings["answer_timeout"]

    async def is_reishou_target(self, guild_id: int, channel_id: int) -> bool:
        settings = await self._get_guild_settings(guild_id)
        channels = settings["channels"]
        if not channels:
            return True
        return channel_id in channels

    async def get_level_info(self, guild_id: int) -> int | None:
        s = await self._get_guild_settings(guild_id)
        return s["level_channel_id"]

    async def get_rank_info(self, guild_id: int) -> int | None:
        s = await self._get_guild_settings(guild_id)
        return s["rank_channel_id"]

    async def get_all_eew_targets(self) -> list[int]:
        def fetch():
            conn = self._get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT eew_channel_id FROM guild_settings WHERE eew_channel_id IS NOT NULL;")
                    rows = cur.fetchall()
                return [int(row[0]) for row in rows if row[0]]
            finally:
                conn.close()

        return await asyncio.to_thread(fetch)

    # ==========================================
    # 1. /setting status コマンド
    # ==========================================
    @app_commands.command(name="status", description="Botの現在の設定状況を確認します")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        current_settings = await self._get_guild_settings(interaction.guild_id)

        # 冷笑削除チャンネルのチェックとクリーンアップ
        channels_list = current_settings["channels"]
        active_channels = []
        valid_ids = []

        for cid in channels_list:
            channel = interaction.guild.get_channel(cid)
            if channel:
                active_channels.append(channel.mention)
                valid_ids.append(cid)

        if len(channels_list) != len(valid_ids):
            await self._save_guild_settings(
                interaction.guild_id,
                current_settings["quiz_timeout"],
                current_settings["answer_timeout"],
                valid_ids,
                current_settings["level_channel_id"],
                current_settings["rank_channel_id"],
                current_settings["eew_channel_id"],
            )
            current_settings["channels"] = valid_ids

        channel_text = (
            "\n".join(f"• {ch}" for ch in active_channels)
            if active_channels
            else "❌ 対象チャンネル未登録（※未登録の場合は全チャンネル対象）"
        )

        level_ch = interaction.guild.get_channel(current_settings["level_channel_id"]) if current_settings["level_channel_id"] else None
        rank_ch = interaction.guild.get_channel(current_settings["rank_channel_id"]) if current_settings["rank_channel_id"] else None
        eew_ch = interaction.guild.get_channel(current_settings["eew_channel_id"]) if current_settings["eew_channel_id"] else None

        level_text = level_ch.mention if level_ch else "未設定"
        rank_text = rank_ch.mention if rank_ch else "未設定"
        eew_text = eew_ch.mention if eew_ch else "未設定（※通知されません）"

        q_timeout_min = current_settings["quiz_timeout"] / 60.0
        q_timeout_str = f"{q_timeout_min:.1f}".rstrip('0').rstrip('.')
        a_timeout_sec = int(current_settings["answer_timeout"])

        embed = discord.Embed(title="⚙️ Bot 現在の設定状況", color=discord.Color.blue())
        embed.add_field(
            name="📢 通知用チャンネル設定",
            value=f"• レベルアップ通知: {level_text}\n• ランクアップ通知: {rank_text}\n• 地震速報(震度4以上): {eew_text}",
            inline=False,
        )
        embed.add_field(
            name="🛡️ 冷笑削除：対象チャンネル",
            value=channel_text,
            inline=False,
        )
        embed.add_field(
            name="❓ 早押しクイズ設定",
            value=f"• 問題制限時間: `{q_timeout_str}分`\n• 回答制限時間: `{a_timeout_sec}秒`",
            inline=False,
        )
        embed.set_footer(text="管理者のみ /setting から変更可能です")

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # 2. /setting notification コマンド
    # ==========================================
    @app_commands.command(
        name="notification",
        description="各種通知の送信先チャンネルを設定します",
    )
    @app_commands.describe(
        種類="設定する通知の種類を選択してください",
        チャンネル="通知を送りたいチャンネル（指定しない場合は設定を解除します）",
    )
    @app_commands.choices(
        種類=[
            app_commands.Choice(name="レベルアップ通知 (level)", value="level"),
            app_commands.Choice(name="ランクアップ通知 (rank)", value="rank"),
            app_commands.Choice(name="緊急地震速報 (eew)", value="eew"),
        ],
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def notification_setting(
        self,
        interaction: discord.Interaction,
        種類: str,
        チャンネル: discord.TextChannel = None,
    ):
        current_settings = await self._get_guild_settings(interaction.guild_id)

        target_id = チャンネル.id if チャンネル else None

        embed = discord.Embed(
            title="⚙️ 通知設定を更新しました",
            color=discord.Color.green(),
        )

        if 種類 == "level":
            current_settings["level_channel_id"] = target_id
            msg = (
                f"送信先: {チャンネル.mention}"
                if チャンネル
                else "レベルアップ通知の送信先設定を解除しました。"
            )
            embed.add_field(name="📈 レベルアップ通知", value=msg, inline=False)

        elif 種類 == "rank":
            current_settings["rank_channel_id"] = target_id
            msg = (
                f"送信先: {チャンネル.mention}"
                if チャンネル
                else "ランクアップ通知の送信先設定を解除しました。"
            )
            embed.add_field(name="👑 ランクアップ通知", value=msg, inline=False)

        elif 種類 == "eew":
            current_settings["eew_channel_id"] = target_id
            msg = (
                f"送信先: {チャンネル.mention}"
                if チャンネル
                else "地震速報の通知先設定を解除しました。"
            )
            embed.add_field(name="🚨 緊急地震速報", value=msg, inline=False)

        await self._save_guild_settings(
            interaction.guild_id,
            current_settings["quiz_timeout"],
            current_settings["answer_timeout"],
            current_settings["channels"],
            current_settings["level_channel_id"],
            current_settings["rank_channel_id"],
            current_settings["eew_channel_id"],
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # 3. /setting reishou コマンド
    # ==========================================
    @app_commands.command(
        name="reishou",
        description="冷笑削除機能の対象チャンネルを設定します"
    )
    @app_commands.describe(
        操作="実行したい操作を選択してください",
        チャンネル="対象のテキストチャンネル（追加/削除の場合に指定）"
    )
    @app_commands.choices(
        操作=[
            app_commands.Choice(name="チャンネルを追加 (add)", value="add"),
            app_commands.Choice(name="チャンネルを削除 (remove)", value="remove"),
            app_commands.Choice(name="設定をリセット（全チャンネル対象化）", value="reset"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def reishou_setting(
        self,
        interaction: discord.Interaction,
        操作: str,
        チャンネル: discord.TextChannel = None
    ):
        current_settings = await self._get_guild_settings(interaction.guild_id)
        channels = current_settings["channels"]

        embed = discord.Embed(color=discord.Color.blue())

        if 操作 == "reset":
            channels = []
            embed.title = "⚙️ 冷笑削除設定をリセットしました"
            embed.description = "すべてのチャンネルが監視対象となります。"

        elif 操作 in ["add", "remove"]:
            if not チャンネル:
                await interaction.response.send_message(
                    "❌ 追加・削除操作を行う場合は、`チャンネル` オプションを指定してください。",
                    ephemeral=True
                )
                return

            if 操作 == "add":
                if チャンネル.id not in channels:
                    channels.append(チャンネル.id)
                    embed.title = "⚙️ 監視チャンネルを追加しました"
                    embed.description = f"対象チャンネル: {チャンネル.mention}"
                else:
                    await interaction.response.send_message(
                        f"⚠️ {チャンネル.mention} は既に登録されています。",
                        ephemeral=True
                    )
                    return

            elif 操作 == "remove":
                if チャンネル.id in channels:
                    channels.remove(チャンネル.id)
                    embed.title = "⚙️ 監視チャンネルを削除しました"
                    embed.description = f"削除したチャンネル: {チャンネル.mention}"
                else:
                    await interaction.response.send_message(
                        f"⚠️ {チャンネル.mention} は登録されていません。",
                        ephemeral=True
                    )
                    return

        await self._save_guild_settings(
            interaction.guild_id,
            current_settings["quiz_timeout"],
            current_settings["answer_timeout"],
            channels,
            current_settings["level_channel_id"],
            current_settings["rank_channel_id"],
            current_settings["eew_channel_id"],
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ==========================================
    # 4. /setting quiz コマンド
    # ==========================================
    @app_commands.command(
        name="quiz",
        description="早押しクイズのタイムアウト時間を設定します"
    )
    @app_commands.describe(
        問題制限時間_分="問題が出題されてから終了するまでの時間（分）",
        回答制限時間_秒="ボタンを押してから回答を入力するまでの制限時間（秒）"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def quiz_setting(
        self,
        interaction: discord.Interaction,
        問題制限時間_分: app_commands.Range[float, 0.5, 60.0] = None,
        回答制限時間_秒: app_commands.Range[float, 3.0, 120.0] = None
    ):
        if 問題制限時間_分 is None and 回答制限時間_秒 is None:
            await interaction.response.send_message(
                "❌ `問題制限時間_分` または `回答制限時間_秒` のどちらか一方以上を指定してください。",
                ephemeral=True
            )
            return

        current_settings = await self._get_guild_settings(interaction.guild_id)

        quiz_timeout = current_settings["quiz_timeout"]
        answer_timeout = current_settings["answer_timeout"]

        changes = []
        if 問題制限時間_分 is not None:
            quiz_timeout = 問題制限時間_分 * 60.0
            q_str = f"{問題制限時間_分:.1f}".rstrip('0').rstrip('.')
            changes.append(f"• 問題制限時間: `{q_str}分` (`{int(quiz_timeout)}秒`)")

        if 回答制限時間_秒 is not None:
            answer_timeout = 回答制限時間_秒
            changes.append(f"• 回答制限時間: `{int(回答制限時間_秒)}秒`")

        await self._save_guild_settings(
            interaction.guild_id,
            quiz_timeout,
            answer_timeout,
            current_settings["channels"],
            current_settings["level_channel_id"],
            current_settings["rank_channel_id"],
            current_settings["eew_channel_id"],
        )

        embed = discord.Embed(
            title="⚙️ クイズ設定を更新しました",
            description="\n".join(changes),
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))