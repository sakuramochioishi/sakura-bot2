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
        アクション="【冷笑用】チャンネルを追加(set)するか削除(unset)するか選択します",
        制限時間="【クイズ用】問題全体の制限時間（分単位で入力、例: 30）",
        回答時間="【クイズ用】ボタンを押してからの回答時間（秒単位で入力、例: 20）",
        チャンネル="【冷笑用】機能を適用・解除したいチャンネル（未指定なら現在のチャンネル）"
    )
    @app_commands.choices(
        機能=[
            app_commands.Choice(name="クイズ設定 (quiz)", value="quiz"),
            app_commands.Choice(name="冷笑削除設定 (reishou)", value="reishou"),
            app_commands.Choice(name="設定の確認 (status)", value="status") 
        ],
        アクション=[
            app_commands.Choice(name="対象に追加 (set)", value="set"),
            app_commands.Choice(name="対象から削除 (unset)", value="unset")
        ]
    )
    @app_commands.default_permissions(administrator=True) # 管理者ロール持ちのみ実行可能
    async def setting(
        self, 
        interaction: discord.Interaction, 
        機能: str, 
        アクション: str = None,  # 👈 新しく追加
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
            # アクション（set / unset）が指定されていない場合はエラー
            if アクション is None:
                await interaction.response.send_message(
                    "❌ 冷笑設定を変更する場合は「アクション（set または unset）」を選択してください。",
                    ephemeral=True
                )
                return

            # チャンネルが選ばれなかった場合は、コマンドを実行したチャンネルを対象にする
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
        
        # 🟡 設定の確認
        elif 機能 == "status":
            channels_list = self.settings["reishou"].get("channels", [])
            
            # 登録されているチャンネルIDをメンションテキスト（<#ID>）に変換
            active_channels = []
            for cid in list(channels_list):
                # サーバー内にチャンネルが存在するか確認
                channel = interaction.guild.get_channel(cid) if interaction.guild else None
                if channel:
                    active_channels.append(channel.mention)
                else:
                    # サーバーから消えたチャンネルは安全に削除
                    if cid in self.settings["reishou"]["channels"]:
                        self.settings["reishou"]["channels"].remove(cid)
            
            self.save_settings()

            # 表示用テキストの用意
            if active_channels:
                channel_text = "\n".join(f"• {ch}" for ch in active_channels)
            else:
                channel_text = "❌ 対象チャンネルは登録されていません\n（※未登録の場合は、すべてのチャンネルが削除対象になります）"

            # クイズ設定の取得
            q_timeout_min = int(self.settings["quiz"].get("quiz_timeout", 900.0) / 60)
            a_timeout_sec = int(self.settings["quiz"].get("answer_timeout", 15.0))

            # Embedを作成
            embed = discord.Embed(
                title="⚙️ Bot 現在の設定状況", 
                color=discord.Color.blue()
            )
            embed.add_field(
                name="🛡️ 冷笑削除：対象チャンネル", 
                value=channel_text, 
                inline=False
            )
            embed.add_field(
                name="❓ 早押しクイズ設定", 
                value=f"• 問題制限時間: `{q_timeout_min}分`\n• 回答制限時間: `{a_timeout_sec}秒`", 
                inline=False
            )
            embed.set_footer(text="管理者のみ /setting から変更可能です")

            # 全員に見える埋め込みで送信
            await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))