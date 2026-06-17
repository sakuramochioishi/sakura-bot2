import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import random
import asyncio

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("token")

# 全てのインテントを有効化（必要に応じて調整してください）
intents = discord.Intents.all()

# スラッシュコマンドに対応したBotクラスの定義
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    # Bot起動時にスラッシュコマンドをDiscordに同期する
    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"{len(synced)}個のスラッシュコマンドを同期しました")
        except Exception as e:
            print(f"同期エラー: {e}")

# Botのインスタンスを作成
bot = MyBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


# ==========================================
# 1. おみくじコマンド (/omikuji)
# ==========================================
@bot.tree.command(name="omikuji", description="今日のおみくじを引きます")
async def omikuji(interaction: discord.Interaction):
    fortunes = ["大吉 🌟", "吉 🎯", "中吉 😊", "小吉 👍", "末吉 🌿", "凶 👻"]
    result = random.choice(fortunes)
    await interaction.response.send_message(f"{interaction.user.mention} さんの今日の運勢は... **{result}** です！")


# ==========================================
# 2. メッセージ一括削除コマンド (/clear [件数])
# ==========================================
@bot.tree.command(name="clear", description="指定した件数のメッセージを一括削除します")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    if amount < 1:
        await interaction.response.send_message("1以上の数値を指定してください。", ephemeral=True)
        return

    await interaction.response.send_message(f"{amount}件のメッセージを削除しています...", ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"正常に {len(deleted)} 件のメッセージを削除しました！", ephemeral=True)

@clear.error
async def clear_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("このコマンドを実行する権限（メッセージの管理）がありません。", ephemeral=True)


# ==========================================
# 3. タイマーコマンド (/timer [分])
# ==========================================
@bot.tree.command(name="timer", description="指定した分数後にメンションで通知します")
async def timer(interaction: discord.Interaction, minutes: int):
    if minutes < 1:
        await interaction.response.send_message("1分以上の時間を指定してください。", ephemeral=True)
        return

    await interaction.response.send_message(f"🔔 {minutes}分間のタイマーを開始しました。時間が来たらお知らせします！")
    await asyncio.sleep(minutes * 60)
    await interaction.channel.send(f"⏰ {interaction.user.mention} さん、{minutes}分が経過しました！")


# Botを起動
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env ファイルから 'token' が読み込めませんでした。設定を確認してください。")