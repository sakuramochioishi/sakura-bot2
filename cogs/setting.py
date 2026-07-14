import discord
from discord import app_commands
from discord.ext import commands
import json
import os

SETTINGS_FILE = "bot_settings.json"

class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = self.load_settings()

    def load_settings(self):
        """JSONファイルから設定を読み込む"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"❌ 設定ファイルの読み込みに失敗しました: {e}")
        
        # 初期設定データ
        return {
            "quiz": {
                "quiz_timeout": 900.0,  # デフォルト15分（900秒）
                "answer_timeout": 25.0   # デフォルト15秒
            },
            "reishou": {
                "channels": []  # 冷笑削除を適用するチャンネルIDのリスト
            }
        }

    def save_settings(self):
        """JSONファイルに設定を保存する"""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ 設定ファイルの保存に失敗しました: {e}")

    # 🛠️ /setting コマンドの作成
    @app_commands.command(name="setting", description="Botの各種設定を変更します（管理者限定）")
    @app_commands.describe(
        機能="設定を変更したい機能を選んでください",
        制限時間="【クイズ用】問題全体の制限時間（分単位で入力、例: 30）",
        回答時間="【クイズ用】ボタンを押してからの回答時間（秒単位で入力、例: 20）",
        チャンネル="【冷笑用】機能を適用したいチャンネル（未指定なら現在のチャンネル）"
    )
    @app_commands.choices(機能=[
        app_commands.Choice(name="クイズ設定 (quiz)", value="quiz"),
        app_commands.Choice(name="冷笑削除設定 (reishou)", value="reishou")
    ])
    @app_commands.default_permissions(administrator=True) # 管理者ロール持ちのみ実行可能
    async def setting(
        self, 
        interaction: discord.Interaction, 
        機能: str, 
        制限時間: int = None, 
        回答時間: int = None, 
        チャンネル: discord.TextChannel = None
    ):
        # 🟢 クイズの設定変更
        if 機能 == "quiz":
            if 制限時間 is None and 回答時間 is None:
                await interaction.response.send_message(
                    "❌ クイズ設定を変更する場合は「制限時間（分）」または「回答時間（秒）」を入力してください。",
                    ephemeral=True
                )
                return

            embed = discord.Embed(title="⚙️ クイズ設定を更新しました", color=discord.Color.green())
            
            if 制限時間 is not None:
                seconds = float(制限時間 * 60) # 分を秒に変換
                self.settings["quiz"]["quiz_timeout"] = seconds
                embed.add_field(name="問題の制限時間", value=f"`{制限時間} 分` (`{int(seconds)} 秒`)", inline=False)
                
            if 回答時間 is not None:
                self.settings["quiz"]["answer_timeout"] = float(回答時間)
                embed.add_field(name="解答権の回答時間", value=f"`{回答時間} 秒`", inline=False)

            self.save_settings()
            await interaction.response.send_message(embed=embed)

        # 🔵 冷笑の設定変更
        elif 機能 == "reishou":
            # チャンネルが選ばれなかった場合は、コマンドを実行したチャンネルを対象にする
            target_channel = チャンネル if チャンネル else interaction.channel
            
            channels_list = self.settings["reishou"]["channels"]
            
            if target_channel.id in channels_list:
                # すでに登録済みなら解除（トグル式）
                channels_list.remove(target_channel.id)
                await interaction.response.send_message(
                    f"✅ {target_channel.mention} を冷笑削除の**対象外**にしました。",
                    ephemeral=True
                )
            else:
                # 未登録なら新しく登録
                channels_list.append(target_channel.id)
                await interaction.response.send_message(
                    f"✅ {target_channel.mention} を冷笑削除の**対象チャンネル**に設定しました！",
                    ephemeral=True
                )
            
            self.save_settings()

# ファイルの最下部に記述します（SettingCogの部分は、ご自身で定義したCogのクラス名に合わせてください）
async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot)) # もしクラス名が 'Setting' なら Setting(bot) にします