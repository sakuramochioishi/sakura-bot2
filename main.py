import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("token")

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!skr_", intents=intents)
        self.remove_command("help")

    async def setup_hook(self):
        self.tree.on_error = self.on_tree_error  # エラーハンドラ
        
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

        try:
            synced = await self.tree.sync()
            print(f"{len(synced)}個のスラッシュコマンドを同期しました")
        except Exception as e:
            print(f"同期エラー: {e}")

    async def on_ready(self):
        """Botがログインしたときに動く処理"""
        print(f"Logged in as {self.user.name} ({self.user.id})")

    async def on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """スラッシュコマンドでエラーが出た場合の共通受け皿"""
        print(f"⚠️ コマンドエラー発生: {error}")

bot = MyBot()

# 🛠️ エラーの原因になっていた @bot.tree.before_command のブロックは綺麗に削除しました

@bot.check
async def globally_restrict_to_owner(ctx):
    return await bot.is_owner(ctx.author)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.NotOwner, commands.CommandNotFound)):
        return
    raise error

if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env から 'token' が読み込めませんでした。")