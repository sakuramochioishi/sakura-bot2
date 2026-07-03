import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("token")

# 開発時は Intents.all() で問題ありませんが、
# 本番運用時は必要なインテント（特に Members, Message Content など）だけ絞るのがセキュリティ上推奨されます
intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!skr_", intents=intents)
        self.remove_command("help")

    async def setup_hook(self):
        self.tree.on_error = self.on_tree_error  # スラッシュコマンドのエラーハンドラ
        
        # Cogの自動読み込み
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

        # 🚨 起動時の自動 tree.sync() はレートリミット（API制限）回避のため削除しました。
        # 代わりに下の管理用コマンド（!skr_sync）で手動同期します。

    async def on_ready(self):
        """Botがログインしたときに動く処理"""
        print(f"Logged in as {self.user.name} ({self.user.id})")
        print("--------------------------------------------")

    async def on_tree_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        """スラッシュコマンドでエラーが出た場合の共通受け皿"""
        print(f"⚠️ スラッシュコマンドエラー発生: {error}")
        
        # ユーザーへのエラー通知（親切設計）
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ コマンドの実行中にエラーが発生したか、権限が足りません。", 
                ephemeral=True
            )

bot = MyBot()

# --- テキストコマンド（管理用・オーナー限定） ---

@bot.command(name="sync")
@commands.is_owner() # オーナー以外が叩いても反応しない
async def sync_commands(ctx):
    """【オーナー限定】スラッシュコマンドをDiscordと同期します"""
    message = await ctx.send("⚡ スラッシュコマンドを同期中...")
    try:
        synced = await bot.tree.sync()
        await message.edit(content=f"✅ {len(synced)}個のスラッシュコマンドをグローバル同期しました！\n（反映に数分〜最大1時間かかる場合があります）")
    except Exception as e:
        await message.edit(content=f"❌ 同期エラーが発生しました: {e}")

# --- エラーハンドリング ---

@bot.event
async def on_command_error(ctx, error):
    """通常のテキストコマンドでエラーが出た場合"""
    if isinstance(error, (commands.NotOwner, commands.CommandNotFound, commands.MissingPermissions)):
        return  # 権限不足や存在しないコマンドは無視（ログを汚さない）
    raise error

# --- 起動処理 ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env から 'token' が読み込めませんでした。")