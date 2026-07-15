import discord
from discord import app_commands
from discord.ext import commands
import json
import os

SETTINGS_FILE = "bot_config.json"

class SettingsCog(commands.GroupCog, name="setting"): # 👈 GroupCogにして /setting コマンド群にする
    def __init__(self, bot: commands.Bot):
        super().__init__() # GroupCogの初期化
        self.bot = bot
        self.settings = self.load_settings()

    def load_settings(self):
        """JSONファイルから設定を読み込む（超安全版）"""
        # 初期設定データ
        default_settings = {
            "quiz": {
                "quiz_timeout": 900.0,
                "answer_timeout": 25.0
            },
            "reishou": {
                "channels": []
            }
        }

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                # 📌 ここがポイント：JSONが壊れていようが文字コードがバグっていようが、
                # 画面にログだけ残して、何事もなかったかのように初期データを返して起動を続行する
                print(f"⚠️ 設定ファイルが壊れているため無視します: {e}")
                return default_settings
        
        return default_settings

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ 設定ファイルの保存に失敗しました: {e}")

    # ==========================================
    # 1. /setting status コマンド
    # ==========================================
    @app_commands.command(name="status", description="Botの現在の設定状況を確認します")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def status(self, interaction: discord.Interaction):
        channels_list = self.settings["reishou"].get("channels", [])
        active_channels = []
        
        # interaction.guild が必ず存在することを前提にできる（guild_onlyのため）
        for cid in list(channels_list):
            channel = interaction.guild.get_channel(cid)
            if channel:
                active_channels.append(channel.mention)
            else:
                if cid in self.settings["reishou"]["channels"]:
                    self.settings["reishou"]["channels"].remove(cid)
        
        self.save_settings()

        if active_channels:
            channel_text = "\n".join(f"• {ch}" for ch in active_channels)
        else:
            channel_text = "❌ 対象チャンネルは登録されていません\n（※未登録の場合は、すべてのチャンネルが削除対象になります）"

        q_timeout_min = int(self.settings["quiz"].get("quiz_timeout", 900.0) / 60)
        a_timeout_sec = int(self.settings["quiz"].get("answer_timeout", 15.0))

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

        embed = discord.Embed(title="⚙️ クイズ設定を更新しました", color=discord.Color.green())
        
        if 制限時間 is not None:
            seconds = float(制限時間 * 60)
            self.settings["quiz"]["quiz_timeout"] = seconds
            embed.add_field(name="問題の制限時間", value=f"`{制限時間} 分` (`{int(seconds)} 秒`)", inline=False)
            
        if 回答時間 is not None:
            self.settings["quiz"]["answer_timeout"] = float(回答時間)
            embed.add_field(name="解答権の回答時間", value=f"`{回答時間} 秒`", inline=False)

        self.save_settings()
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
        channels_list = self.settings["reishou"]["channels"]
        
        if アクション == "set":
            if target_channel.id in channels_list:
                await interaction.response.send_message(
                    f"ℹ️ {target_channel.mention} はすでに冷笑削除の対象に登録されています。",
                    ephemeral=True
                )
            else:
                channels_list.append(target_channel.id)
                self.save_settings()
                await interaction.response.send_message(
                    f"✅ {target_channel.mention} を冷笑削除の**対象チャンネル**に設定しました！",
                    ephemeral=True
                )

        elif アクション == "unset":
            if target_channel.id in channels_list:
                channels_list.remove(target_channel.id)
                self.save_settings()
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