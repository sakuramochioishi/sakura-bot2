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
        
        # 🌟 デフォルトのヘルプコマンドをここで削除（クラスの中に書くのが正解）
        self.remove_command("help")

    async def setup_hook(self):
        # 📁 cogs フォルダの中にある拡張子 .py のファイルを自動でループして読み込む
        cogs_dir = "./cogs"
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py"):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(cog_name)
                        print(f"✅ {cog_name} を読み込みました")
                    except Exception as e:
                        print(f"❌ {cog_name} の読み込みに失敗しました: {e}")
        else:
            print("⚠️ cogs フォルダが見つかりません。")

        # スラッシュコマンドをDiscordに同期
        try:
            synced = await self.tree.sync()
            print(f"{len(synced)}個のスラッシュコマンドを同期しました")
        except Exception as e:
            print(f"同期エラー: {e}")

# Botのインスタンスを作成（ここで初めてbotが作られます）
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