import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import random
import asyncio
import urllib.request  # リダイレクトチェッカー用に追加

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("token")

# 全てのインテントを有効化
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

# ==========================================
# 🔒 セキュリティ設定（!コマンドの権限制限）
# ==========================================
@bot.check
async def globally_restrict_to_owner(ctx):
    # 今後増えるものも含め、全ての「!」コマンドを実行できるのはBotのオーナー（あなた）だけに制限します
    return await bot.is_owner(ctx.author)

@bot.event
async def on_command_error(ctx, error):
    # オーナー以外の人が「!」コマンドを打った時は、エラーメッセージを出さずに完全にスルー（無視）します
    if isinstance(error, commands.NotOwner):
        return
    raise error

# ==========================================
# 🟢 起動確認イベント
# ==========================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")


# ==========================================
# 1. おみくじコマンド (/omikuji) - 全員用
# ==========================================
@bot.tree.command(name="omikuji", description="今日のおみくじを引きます")
async def omikuji(interaction: discord.Interaction):
    fortunes = ["大吉 🌟", "吉 🎯", "中吉 😊", "小吉 👍", "末吉 🌿", "凶 👻"]
    result = random.choice(fortunes)
    await interaction.response.send_message(f"{interaction.user.mention} さんの今日の運勢は... **{result}** です！")


# ==========================================
# 2. メッセージ一括削除コマンド (/clear [件数]) - 管理者用
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
# 3. タイマーコマンド (/timer [分]) - 全員用
# ==========================================
@bot.tree.command(name="timer", description="指定した分数後にメンションで通知します")
async def timer(interaction: discord.Interaction, minutes: int):
    if minutes < 1:
        await interaction.response.send_message("1分以上の時間を指定してください。", ephemeral=True)
        return

    await interaction.response.send_message(f"🔔 {minutes}分間のタイマーを開始しました。時間が来たらお知らせします！")
    await asyncio.sleep(minutes * 60)
    await interaction.channel.send(f"⏰ {interaction.user.mention} さん、{minutes}分が経過しました！")


# ==========================================
# 4. 所属サーバー確認コマンド (!servers) - あなた専用
# ==========================================
@bot.command(name="servers")
async def list_servers(ctx):
    guild_count = len(bot.guilds)
    
    server_list = ""
    for guild in bot.guilds:
        server_list += f"• **{guild.name}** (メンバー数: {guild.member_count}人, ID: `{guild.id}`)\n"
    
    embed = discord.Embed(
        title="🤖 Bot所属サーバー一覧",
        description=f"現在 **{guild_count}** 個のサーバーに参加しています。\n\n{server_list}",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

    
# ==========================================
# 5. リダイレクト先チェッカー (/redirect [URL]) - 全員用
# ==========================================
@bot.tree.command(name="redirect", description="URLのリダイレクト先（最終的な移動先）をチェックします")
async def check_redirect(interaction: discord.Interaction, url: str):
    # URLが http から始まっているか簡易チェック
    if not url.startswith(("http://", "https://")):
        await interaction.response.send_message("❌ URLは `http://` または `https://` から始めてください。", ephemeral=True)
        return

    # 処理に時間がかかる可能性があるので、先に「調べています」と応答
    await interaction.response.defer()

    try:
        # リクエストを送信して最終的なURLを取得
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'} # ブロック対策のブラウザ偽装
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            final_url = response.geturl()
        
        # 元のURLと転送先が同じかどうかでメッセージを変える
        if url == final_url:
            await interaction.followup.send(f"🔗 **転送なし（安全な直リンクです）**\n`{final_url}`")
        else:
            await interaction.followup.send(f"➡️ **リダイレクトを検出しました！**\n元のURL: <{url}>\n↓\n最終目的地: **`{final_url}`**")

    except Exception as e:
        await interaction.followup.send(f"❌ URLの解析に失敗しました。（タイムアウト、または存在しないサイトの可能性があります）\nエラー内容: `{e}`")

# ==========================================
# 6. サーバー全員対象ルーレットコマンド (/roulette) - 全員用
# ==========================================
class MemberRouletteView(discord.ui.View):
    def __init__(self, target_members):
        super().__init__(timeout=60)
        self.target_members = target_members

    @discord.ui.button(label="もう一度引く 🔁", style=discord.ButtonStyle.green)
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🎰 **サーバーメンバー全員から選出中... ドラムロールスタート！**", embed=None)
        await asyncio.sleep(2.0)
        
        chosen_member = random.choice(self.target_members)
        embed = discord.Embed(
            title="🎯 ルーレット結果",
            description=f"選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=self)

@bot.tree.command(name="roulette", description="サーバー内の全メンバーからランダムに1人選んでメンションします")
async def roulette(interaction: discord.Interaction):
    guild = interaction.guild
    
    # サーバーの全メンバーからBotを除外して、そのまま全員を候補にする
    candidates = [m for m in guild.members if not m.bot]
    mode_text = "👥 全サーバーメンバー"

    if not candidates:
        await interaction.response.send_message("❌ 抽選対象となるメンバーが見つかりませんでした。", ephemeral=True)
        return

    # 演出開始
    await interaction.response.send_message(f"🎰 **{mode_text}から選出中... ドラムロールスタート！**")
    await asyncio.sleep(2.0)

    # ランダムで1人選出
    chosen_member = random.choice(candidates)
    
    embed = discord.Embed(
        title="🎯 ルーレット結果",
        description=f"対象: {mode_text} ({len(candidates)}人)\n\n選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！",
        color=discord.Color.red()
    )
    
    view = MemberRouletteView(candidates)
    
    await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=view)

# ==========================================
# 7. コウメ太夫構文コマンド (/koubun [言葉1] [言葉2]) - 全員用
# ==========================================
@bot.tree.command(name="koubun", description="ふたつの言葉からコウメ太夫のネタを生成します")
@app_commands.describe(word1="〜と思ったら", word2="〜した")
async def koubun(interaction: discord.Interaction, word1: str, word2: str):
    # 改行を入れて、あの独特のテンポをテキストで表現します
    joke = (
        f"チャンチャカチャンチャン チャチャンチャチャンチャン♪\n\n"
        f"**{word1}** と思ったら〜〜〜\n\n"
        f"**{word2}** した〜〜〜\n\n"
        f"**チクショーー！！** 😭"
    )
    
    await interaction.response.send_message(joke)


# ==========================================
# Botの起動
# ==========================================
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env ファイルから 'token' が読み込めませんでした。設定を確認してください。")