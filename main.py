import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("token")

# 全てのインテントを有効化
intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        # 接頭辞を !skr_ に設定
        super().__init__(command_prefix="!skr_", intents=intents)

    async def setup_hook(self):
        # 📁 cogsフォルダ内の3つのファイルを読み込む
        extensions = ["cogs.help", "cogs.commands", "cogs.tasks"]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} を読み込みました")
            except Exception as e:
                print(f"❌ {ext} の読み込みに失敗しました: {e}")

        # スラッシュコマンドをDiscordに同期
        try:
            synced = await self.tree.sync()
            print(f"{len(synced)}個のスラッシュコマンドを同期しました")
        except Exception as e:
            print(f"同期エラー: {e}")

# Botのインスタンスを作成
bot = MyBot()

# 👑 オーナー（あなた）限定の全体制限ルールを設定
@bot.check
async def globally_restrict_to_owner(ctx):
    return await bot.is_owner(ctx.author)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.NotOwner, commands.CommandNotFound)):
        return
    raise error

# Botの起動
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env から 'token' が読み込めませんでした。")