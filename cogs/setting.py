from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
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

    def _init_db(self):
        """Neonに設定保存用のテーブルを作成する"""
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # guild_id を主キー（PRIMARY KEY）にすることでサーバーごとにデータを独立管理します
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                guild_id VARCHAR(30) PRIMARY KEY,
                quiz_timeout TEXT DEFAULT '900.0',
                answer_timeout TEXT DEFAULT '15.0',
                channels TEXT[] DEFAULT '{}'::TEXT[]
            );
        """)
        conn.commit()
        cur.close()
        conn.close()

    def _migrate_json_to_db(self):
        """古い bot_config.json があれば、自動的にNeonへ移行する"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                
                if old_data:
                    # JSON内のデータを取得
                    quiz_timeout = str(old_data.get("quiz", {}).get("quiz_timeout", 900.0))
                    answer_timeout = str(old_data.get("quiz", {}).get("answer_timeout", 15.0))
                    channels = [str(cid) for cid in old_data.get("reishou", {}).get("channels", [])]
                    
                    # 移行先の一時的な初期データとして 'default' サーバー枠として保存
                    conn = psycopg2.connect(DATABASE_URL)
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO bot_settings (guild_id, quiz_timeout, answer_timeout, channels)
                        VALUES ('default', %s, %s, %s)
                        ON CONFLICT (guild_id) DO NOTHING;
                    """, (quiz_timeout, answer_timeout, channels))
                    conn.commit()
                    cur.close()
                    conn.close()
                    print("⚙️ 【移行完了】設定JSONデータをNeonデータベースに引っ越ししました！")
                
                # バックアップ化してJSONファイルを無効化
                os.rename(SETTINGS_FILE, f"{SETTINGS_FILE}.bak")
                print(f"📦 古い設定ファイルを {SETTINGS_FILE}.bak に退避しました。")
            except Exception as e:
                print(f"⚠️ 設定JSONの移行中にエラーが発生しました: {e}")

    def _get_guild_settings(self, guild_id: int | str) -> dict:
        """指定されたギルドの設定をデータベースから取得する（なければ初期値を作成）"""
        guild_id_str = str(guild_id)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("SELECT quiz_timeout, answer_timeout, channels FROM bot_settings WHERE guild_id = %s;", (guild_id_str,))
        row = cur.fetchone()
        
        # 該当ギルドの設定がまだない場合、'default'（移行データなど）の設定をコピーするか初期値で作る
        if row is None:
            cur.execute("SELECT quiz_timeout, answer_timeout, channels FROM bot_settings WHERE guild_id = 'default';")
            default_row = cur.fetchone()
            
            if default_row:
                quiz_t, answer_t, chs = default_row[0], default_row[1], default_row[2]
            else:
                quiz_t, answer_t, chs = '900.0', '15.0', []

            cur.execute("""
                INSERT INTO bot_settings (guild_id, quiz_timeout, answer_timeout, channels)
                VALUES (%s, %s, %s, %s);
            """, (guild_id_str, quiz_t, answer_t, chs))
            conn.commit()
            row = (quiz_t, answer_t, chs)
            
        cur.close()
        conn.close()
        
        return {
            "quiz_timeout": float(row[0]),
            "answer_timeout": float(row[1]),
            "channels": [int(cid) for cid in row[2]]
        }

    def _save_guild_settings(self, guild_id: int, quiz_timeout: float, answer_timeout: float, channels: list[int]):
        """指定されたギルドの設定を上書き保存する"""
        guild_id_str = str(guild_id)
        channels_str_list = [str(cid) for cid in channels]
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            UPDATE bot_settings 
            SET quiz_timeout = %s, answer_timeout = %s, channels = %s 
            WHERE guild_id = %s;
        """, (str(quiz_timeout), str(answer_timeout), channels_str_list, guild_id_str))
        conn.commit()
        cur.close()
        conn.close()

    # ==========================================
    # 👥 他のCogからサーバー別に値を呼び出すメソッド
    # ==========================================
    def get_quiz_timeout(self, guild_id: int) -> float:
        """指定されたサーバーのクイズ制限時間（秒）を取得"""
        return self._get_guild_settings(guild_id)["quiz_timeout"]

    def get_answer_timeout(self, guild_id: int) -> float:
        """指定されたサーバーの回答時間（秒）を取得"""
        return self._get_guild_settings(guild_id)["answer_timeout"]

    def is_reishou_target(self, guild_id: int, channel_id: int) -> bool:
        """指定されたチャンネルが、そのサーバーで冷笑削除の対象かどうかを判定"""
        settings = self._get_guild_settings(guild_id)
        channels = settings["channels"]
        if not channels:
            return True  # チャンネルが1つも登録されていなければ、すべてのチャンネルを対象とする
        return channel_id in channels

    # ==========================================
    # 1. /setting status コマンド
    # ==========================================
    @app_commands.command(name="status", description="Botの現在の設定状況を確認します")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        # データベースからこのギルドの設定を引っ張る
        current_settings = self._get_guild_settings(interaction.guild_id)
        
        channels_list = current_settings["channels"]
        active_channels = []
        valid_ids = []
        
        for cid in channels_list:
            channel = interaction.guild.get_channel(cid)
            if channel:
                active_channels.append(channel.mention)
                valid_ids.append(cid)
        
        # 削除されたチャンネルなどを除外してデータベースを綺麗にする
        if len(channels_list) != len(valid_ids):
            self._save_guild_settings(interaction.guild_id, current_settings["quiz_timeout"], current_settings["answer_timeout"], valid_ids)
            current_settings["channels"] = valid_ids

        if active_channels:
            channel_text = "\n".join(f"• {ch}" for ch in active_channels)
        else:
            channel_text = "❌ 対象チャンネルは登録されていません\n（※未登録の場合は、すべてのチャンネルが削除対象になります）"

        q_timeout_min = int(current_settings["quiz_timeout"] / 60)
        a_timeout_sec = int(current_settings["answer_timeout"])

        embed = discord.Embed(title="⚙️ Bot 現在の設定状況", color=discord.Color.blue())
        embed.add_field(name="🛡️ 冷笑削除：対象チャンネル", value=channel_text, inline=False)
        embed.add_field(name="❓ 早押しクイズ設定", value=f"• 問題制限時間: `{q_timeout_min}分`\n• 回答制限時間: `{a_timeout_sec}秒`", inline=False)
        embed.set_footer(text="管理者のみ /setting から変更可能です")

        await interaction.response.send_message(embed=embed)

    # ==========================================
    # 2. /setting quiz コマンド
    # ==========================================
    @app_commands.command(name="quiz", description="クイズ関連の設定を変更します")
    @app_commands.describe(
        制限時間="問題全体の制限時間（分単位で入力、例: 30）",
        回答時間="ボタンを押してからの回答時間（秒単位で入力、例: 20）"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def quiz_setting(self, interaction: discord.Interaction, 制限時間: int = None, 回答時間: int = None):
        if 制限時間 is None and 回答時間 is None:
            await interaction.response.send_message(
                "❌ 「制限時間（分）」または「回答時間（秒）」の少なくとも一方を入力してください。",
                ephemeral=True
            )
            return

        current_settings = self._get_guild_settings(interaction.guild_id)
        embed = discord.Embed(title="⚙️ クイズ設定を更新しました", color=discord.Color.green())
        
        if 制限時間 is not None:
            current_settings["quiz_timeout"] = float(制限時間 * 60)
            embed.add_field(name="問題の制限時間", value=f"`{制限時間} 分` (`{int(current_settings['quiz_timeout'])} 秒`)", inline=False)
            
        if 回答時間 is not None:
            current_settings["answer_timeout"] = float(回答時間)
            embed.add_field(name="解答権の回答時間", value=f"`{回答時間} 秒`", inline=False)

        self._save_guild_settings(interaction.guild_id, current_settings["quiz_timeout"], current_settings["answer_timeout"], current_settings["channels"])
        await interaction.response.send_message(embed=embed)

    # ==========================================
    # 3. /setting reishou コマンド
    # ==========================================
    @app_commands.command(name="reishou", description="冷笑削除機能の対象チャンネルを設定します")
    @app_commands.choices(
        アクション=[
            app_commands.Choice(name="対象に追加 (set)", value="set"),
            app_commands.Choice(name="対象から削除 (unset)", value="unset")
        ]
    )
    @app_commands.describe(
        アクション="チャンネルを追加(set)するか削除(unset)するか選択します",
        チャンネル="対象にするチャンネル（未指定なら現在のチャンネル）"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def reishou_setting(self, interaction: discord.Interaction, アクション: str, チャンネル: discord.TextChannel = None):
        target_channel = チャンネル if チャンネル else interaction.channel
        current_settings = self._get_guild_settings(interaction.guild_id)
        channels_list = current_settings["channels"]
        
        if アクション == "set":
            if target_channel.id in channels_list:
                await interaction.response.send_message(
                    f"ℹ️ {target_channel.mention} はすでに冷笑削除の対象に登録されています。",
                    ephemeral=True
                )
            else:
                channels_list.append(target_channel.id)
                self._save_guild_settings(interaction.guild_id, current_settings["quiz_timeout"], current_settings["answer_timeout"], channels_list)
                await interaction.response.send_message(
                    f"✅ {target_channel.mention} を冷笑削除の**対象チャンネル**に設定しました！",
                    ephemeral=True
                )

        elif アクション == "unset":
            if target_channel.id in channels_list:
                channels_list.remove(target_channel.id)
                self._save_guild_settings(interaction.guild_id, current_settings["quiz_timeout"], current_settings["answer_timeout"], channels_list)
                await interaction.response.send_message(
                    f"✅ {target_channel.mention} を冷笑削除の**対象外**にしました。",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"ℹ️ {target_channel.mention} は冷笑削除の対象に登録されていません。",
                    ephemeral=True
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))