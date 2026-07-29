from __future__ import annotations

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

        # データベースの初期化とJSONからの自動移行
        self._init_db()
        self._migrate_json_to_db()

    def _get_connection(self):
        """DB接続を取得するヘルパー"""
        return psycopg2.connect(DATABASE_URL)

    def _init_db(self):
        """データベースに設定保存用のテーブルを作成し、必要なカラムを保証する"""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id VARCHAR(30) PRIMARY KEY,
                quiz_timeout TEXT DEFAULT '900.0',
                answer_timeout TEXT DEFAULT '15.0',
                channels TEXT[] DEFAULT '{}'::TEXT[],
                level_channel_id VARCHAR(30) DEFAULT NULL,
                rank_channel_id VARCHAR(30) DEFAULT NULL,
                eew_channel_id VARCHAR(30) DEFAULT NULL,
                level_mention TEXT DEFAULT NULL,
                rank_mention TEXT DEFAULT NULL,
                eew_mention TEXT DEFAULT NULL
            );
        """)

        # カラムが存在しない場合の安全な追加
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS quiz_timeout TEXT DEFAULT '900.0';")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS answer_timeout TEXT DEFAULT '15.0';")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS channels TEXT[] DEFAULT '{}'::TEXT[];")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS level_channel_id VARCHAR(30) DEFAULT NULL;")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS rank_channel_id VARCHAR(30) DEFAULT NULL;")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS eew_channel_id VARCHAR(30) DEFAULT NULL;")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS level_mention TEXT DEFAULT NULL;")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS rank_mention TEXT DEFAULT NULL;")
        cur.execute("ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS eew_mention TEXT DEFAULT NULL;")

        conn.commit()
        cur.close()
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
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO guild_settings (guild_id, quiz_timeout, answer_timeout, channels)
                        VALUES ('default', %s, %s, %s)
                        ON CONFLICT (guild_id) DO NOTHING;
                    """,
                        (quiz_timeout, answer_timeout, channels),
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    print("⚙️ 【移行完了】設定JSONデータをデータベースに引っ越ししました！")

                os.rename(SETTINGS_FILE, f"{SETTINGS_FILE}.bak")
                print(f"📦 古い設定ファイルを {SETTINGS_FILE}.bak に退避しました。")
            except Exception as e:
                print(f"⚠️ 設定JSONの移行中にエラーが発生しました: {e}")

    def _get_guild_settings(self, guild_id: int | str) -> dict:
        """指定されたギルドの設定を取得する"""
        guild_id_str = str(guild_id)
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id,
                   level_mention, rank_mention, eew_mention
            FROM guild_settings WHERE guild_id = %s;
        """,
            (guild_id_str,),
        )
        row = cur.fetchone()

        if row is None:
            cur.execute(
                "SELECT quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id, level_mention, rank_mention, eew_mention FROM guild_settings WHERE guild_id = 'default';"
            )
            default_row = cur.fetchone()

            if default_row:
                quiz_t, answer_t, chs, l_ch, r_ch, e_ch, l_m, r_m, e_m = default_row
            else:
                quiz_t, answer_t, chs, l_ch, r_ch, e_ch, l_m, r_m, e_m = (
                    "900.0", "15.0", [], None, None, None, None, None, None
                )

            cur.execute(
                """
                INSERT INTO guild_settings (guild_id, quiz_timeout, answer_timeout, channels, level_channel_id, rank_channel_id, eew_channel_id, level_mention, rank_mention, eew_mention)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
                (guild_id_str, quiz_t, answer_t, chs, l_ch, r_ch, e_ch, l_m, r_m, e_m),
            )
            conn.commit()
            row = (quiz_t, answer_t, chs, l_ch, r_ch, e_ch, l_m, r_m, e_m)

        cur.close()
        conn.close()

        return {
            "quiz_timeout": float(row[0]) if row[0] else 900.0,
            "answer_timeout": float(row[1]) if row[1] else 15.0,
            "channels": [int(cid) for cid in row[2]] if row[2] else [],
            "level_channel_id": int(row[3]) if row[3] else None,
            "rank_channel_id": int(row[4]) if row[4] else None,
            "eew_channel_id": int(row[5]) if row[5] else None,
            "level_mention": row[6],
            "rank_mention": row[7],
            "eew_mention": row[8],
        }

    def _save_guild_settings(
        self,
        guild_id: int,
        quiz_timeout: float,
        answer_timeout: float,
        channels: list[int],
        level_channel_id: int | None,
        rank_channel_id: int | None,
        eew_channel_id: int | None,
        level_mention: str | None = None,
        rank_mention: str | None = None,
        eew_mention: str | None = None,
    ):
        """指定されたギルドの設定を上書き保存する"""
        guild_id_str = str(guild_id)
        channels_str_list = [str(cid) for cid in channels]
        l_ch_str = str(level_channel_id) if level_channel_id is not None else None
        r_ch_str = str(rank_channel_id) if rank_channel_id is not None else None
        e_ch_str = str(eew_channel_id) if eew_channel_id is not None else None

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE guild_settings 
            SET quiz_timeout = %s, answer_timeout = %s, channels = %s, 
                level_channel_id = %s, rank_channel_id = %s, eew_channel_id = %s,
                level_mention = %s, rank_mention = %s, eew_mention = %s
            WHERE guild_id = %s;
        """,
            (
                str(quiz_timeout),
                str(answer_timeout),
                channels_str_list,
                l_ch_str,
                r_ch_str,
                e_ch_str,
                level_mention,
                rank_mention,
                eew_mention,
                guild_id_str,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()

    # ==========================================
    # 👥 他のCogから呼び出すヘルパーメソッド
    # ==========================================
    def get_quiz_timeout(self, guild_id: int) -> float:
        return self._get_guild_settings(guild_id)["quiz_timeout"]

    def get_answer_timeout(self, guild_id: int) -> float:
        return self._get_guild_settings(guild_id)["answer_timeout"]

    def is_reishou_target(self, guild_id: int, channel_id: int) -> bool:
        settings = self._get_guild_settings(guild_id)
        channels = settings["channels"]
        if not channels:
            return True
        return channel_id in channels

    def get_level_info(self, guild_id: int) -> tuple[int | None, str | None]:
        """(level_channel_id, level_mention) を返す"""
        s = self._get_guild_settings(guild_id)
        return s["level_channel_id"], s["level_mention"]

    def get_rank_info(self, guild_id: int) -> tuple[int | None, str | None]:
        """(rank_channel_id, rank_mention) を返す"""
        s = self._get_guild_settings(guild_id)
        return s["rank_channel_id"], s["rank_mention"]

    def get_all_eew_targets(self) -> list[tuple[int, str | None]]:
        """全サーバーの (eew_channel_id, eew_mention) 一覧を取得する"""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT eew_channel_id, eew_mention FROM guild_settings WHERE eew_channel_id IS NOT NULL;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [(int(row[0]), row[1]) for row in rows if row[0]]

    # ==========================================
    # 1. /setting status コマンド
    # ==========================================
    @app_commands.command(
        name="status", description="Botの現在の設定状況を確認します"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        current_settings = self._get_guild_settings(interaction.guild_id)

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
            self._save_guild_settings(
                interaction.guild_id,
                current_settings["quiz_timeout"],
                current_settings["answer_timeout"],
                valid_ids,
                current_settings["level_channel_id"],
                current_settings["rank_channel_id"],
                current_settings["eew_channel_id"],
                current_settings["level_mention"],
                current_settings["rank_mention"],
                current_settings["eew_mention"],
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

        level_text = f"{level_ch.mention} (メンション: `{current_settings['level_mention'] or 'なし'}`)" if level_ch else "未設定"
        rank_text = f"{rank_ch.mention} (メンション: `{current_settings['rank_mention'] or 'なし'}`)" if rank_ch else "未設定"
        eew_text = f"{eew_ch.mention} (メンション: `{current_settings['eew_mention'] or 'なし'}`)" if eew_ch else "未設定（※通知されません）"

        q_timeout_min = int(current_settings["quiz_timeout"] / 60)
        a_timeout_sec = int(current_settings["answer_timeout"])

        embed = discord.Embed(
            title="⚙️ Bot 現在の設定状況", color=discord.Color.blue()
        )
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
            value=f"• 問題制限時間: `{q_timeout_min}分`\n• 回答制限時間: `{a_timeout_sec}秒`",
            inline=False,
        )
        embed.set_footer(text="管理者のみ /setting から変更可能です")

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # 2. /setting notification コマンド
    # ==========================================
    @app_commands.command(
        name="notification",
        description="各種通知の送信先チャンネルとメンションを設定します",
    )
    @app_commands.describe(
        種類="設定する通知の種類を選択してください",
        チャンネル="通知を送りたいチャンネル（指定しない場合は設定を解除します）",
        メンション_タイプ="メンションの種類を選択してください（指定なしならメンションなし）",
        ロール="メンション_タイプで「特定のロール」を選んだ場合に指定してください",
    )
    @app_commands.choices(
        種類=[
            app_commands.Choice(name="レベルアップ通知 (level)", value="level"),
            app_commands.Choice(name="ランクアップ通知 (rank)", value="rank"),
            app_commands.Choice(name="緊急地震速報 (eew)", value="eew"),
        ],
        メンション_タイプ=[
            app_commands.Choice(name="メンションなし", value="none"),
            app_commands.Choice(name="@everyone", value="@everyone"),
            app_commands.Choice(name="@here", value="@here"),
            app_commands.Choice(name="特定のロール指定", value="role"),
        ],
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def notification_setting(
        self,
        interaction: discord.Interaction,
        種類: str,
        チャンネル: discord.TextChannel = None,
        メンション_タイプ: str = "none",
        ロール: discord.Role = None,
    ):
        current_settings = self._get_guild_settings(interaction.guild_id)

        target_id = チャンネル.id if チャンネル else None
        
        # メンション文字列の作成
        mention_str = None
        if チャンネル:
            if メンション_タイプ == "@everyone":
                mention_str = "@everyone"
            elif メンション_タイプ == "@here":
                mention_str = "@here"
            elif メンション_タイプ == "role":
                if ロール:
                    mention_str = ロール.mention
                else:
                    await interaction.response.send_message(
                        "❌ 「特定のロール指定」を選択した場合は、`ロール` オプションも指定してください。",
                        ephemeral=True,
                    )
                    return

        embed = discord.Embed(
            title="⚙️ 通知設定を更新しました",
            color=discord.Color.green(),
        )

        mention_disp = mention_str if mention_str else "なし"

        if 種類 == "level":
            current_settings["level_channel_id"] = target_id
            current_settings["level_mention"] = mention_str
            msg = (
                f"送信先: {チャンネル.mention}\nメンション: `{mention_disp}`"
                if チャンネル
                else "レベルアップ通知の送信先設定を解除しました。"
            )
            embed.add_field(name="📈 レベルアップ通知", value=msg, inline=False)

        elif 種類 == "rank":
            current_settings["rank_channel_id"] = target_id
            current_settings["rank_mention"] = mention_str
            msg = (
                f"送信先: {チャンネル.mention}\nメンション: `{mention_disp}`"
                if チャンネル
                else "ランクアップ通知の送信先設定を解除しました。"
            )
            embed.add_field(name="👑 ランクアップ通知", value=msg, inline=False)

        elif 種類 == "eew":
            current_settings["eew_channel_id"] = target_id
            current_settings["eew_mention"] = mention_str
            msg = (
                f"送信先: {チャンネル.mention}\nメンション: `{mention_disp}`"
                if チャンネル
                else "地震速報の通知先設定を解除しました。"
            )
            embed.add_field(name="🚨 緊急地震速報", value=msg, inline=False)

        self._save_guild_settings(
            interaction.guild_id,
            current_settings["quiz_timeout"],
            current_settings["answer_timeout"],
            current_settings["channels"],
            current_settings["level_channel_id"],
            current_settings["rank_channel_id"],
            current_settings["eew_channel_id"],
            current_settings["level_mention"],
            current_settings["rank_mention"],
            current_settings["eew_mention"],
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # (quiz_setting, reishou_setting は省略せず同様に含まれます)

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))