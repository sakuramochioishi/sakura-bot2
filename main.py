import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio

# 🌟 db_manager をインポート
import db_manager

load_dotenv()
TOKEN = os.getenv("token")

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!skr_", intents=intents)
        self.remove_command("help")

    async def setup_hook(self):
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
        # 💡 起動時のカウント処理を、安全のために裏で10秒後に実行するよう予約する
        self.loop.create_task(self.initial_sync_dashboard())

    async def initial_sync_dashboard(self):
        """起動から10秒待って、確実にサーバー情報を取得・同期する関数"""
        await asyncio.sleep(10)  # 10秒間、Discordのデータ受信をじっと待つ
        
        guild_count = len(self.guilds)
        user_count = sum(guild.member_count for guild in self.guilds if guild.member_count)
        
        # 💾 データベースに書き込み
        db_manager.update_bot_counts(guild_count, user_count)
        db_manager.add_log(f"🤖 Sakura Bot 2 が正常に起動しました！({guild_count}本 / {user_count}人)")
        
        print(f"📊 【確実同期完了】 {guild_count}サーバー / {user_count}ユーザー をダッシュボードに反映しました")

bot = MyBot()

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