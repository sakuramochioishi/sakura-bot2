import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import random
import asyncio
import urllib.request
import time
import sys

# .envファイルから環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("token")

# 全てのインテントを有効化
intents = discord.Intents.all()

# スラッシュコマンドに対応したBotクラスの定義
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!skr_", intents=intents)

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
# 🔒 セキュリティ設定（!skr_コマンドの権限制限）
# ==========================================
@bot.check
async def globally_restrict_to_owner(ctx):
    return await bot.is_owner(ctx.author)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.NotOwner, commands.CommandNotFound)):
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
# 2. タイマーコマンド (/timer [分]) - 全員用
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
# 3. リダイレクト先チェッカー (/redirect [URL]) - 全員用
# ==========================================
@bot.tree.command(name="redirect", description="URLのリダイレクト先（最終的な移動先）をチェックします")
async def check_redirect(interaction: discord.Interaction, url: str):
    if not url.startswith(("http://", "https://")):
        await interaction.response.send_message("❌ URLは `http://` または `https://` から始めてください。", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            final_url = response.geturl()
        
        if url == final_url:
            await interaction.followup.send(f"🔗 **転送なし（直リンクです）**\n`{final_url}`")
        else:
            await interaction.followup.send(f"➡️ **リダイレクトを検出しました！**\n元のURL: <{url}>\n↓\n最終目的地: **`{final_url}`**")

    except Exception as e:
        await interaction.followup.send(f"❌ URLの解析に失敗しました。\nエラー内容: `{e}`")


# ==========================================
# 4. サーバー全員対象ルーレットコマンド (/roulette) - 全員用
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
    candidates = [m for m in guild.members if not m.bot]
    mode_text = "👥 全サーバーメンバー"

    if not candidates:
        await interaction.response.send_message("❌ 抽選対象となるメンバーが見つかりませんでした。", ephemeral=True)
        return

    await interaction.response.send_message(f"🎰 **{mode_text}から選出中... ドラムロールスタート！**")
    await asyncio.sleep(2.0)

    chosen_member = random.choice(candidates)
    
    embed = discord.Embed(
        title="🎯 ルーレット結果",
        description=f"対象: {mode_text} ({len(candidates)}人)\n\n選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！",
        color=discord.Color.red()
    )
    
    view = MemberRouletteView(candidates)
    await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=view)


# ==========================================
# 5. コウメ太夫構文コマンド (/koubun [言葉1] [言葉2]) - 全員用
# ==========================================
@bot.tree.command(name="koubun", description="ふたつの言葉からコウメ太夫のネタを生成します")
@app_commands.describe(word1="〜かと思ったら", word2="〜でした")
async def koubun(interaction: discord.Interaction, word1: str, word2: str):
    joke = (
        f"チャンチャカチャンチャン チャチャンチャチャンチャン♪\n\n"
        f"**{word1}** かと思ったら〜〜〜\n\n"
        f"**{word2}** でした〜〜〜\n\n"
        f"**チクショーー！！** 😭"
    )
    await interaction.response.send_message(joke)


# ==========================================
# 6. 進化した早押しクイズコマンド (/quiz [問題] [正解]) - 全員用
# ==========================================
class QuizBuzzerView(discord.ui.View):
    def __init__(self, bot, answer: str, start_time: float, embed: discord.Embed):
        # 【変更点】10分（600秒）誰も押さなければタイムアウトして自動終了
        super().__init__(timeout=600)
        self.bot = bot
        self.answer = answer.strip()
        self.start_time = start_time
        self.base_embed = embed
        
        self.is_processing = False
        self.wrong_users = set()
        self.quiz_message = None

    @discord.ui.button(label="押しボタン 🔴", style=discord.ButtonStyle.danger)
    async def press_buzzer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_processing:
            await interaction.response.send_message("遅かった！すでに他の人がボタンを押しています。", ephemeral=True)
            return

        if interaction.user.id in self.wrong_users:
            await interaction.response.send_message("❌ あなたはすでに解答権を失っています（お手付き）。他の人の解答を待ちましょう！", ephemeral=True)
            return

        self.is_processing = True
        
        button.disabled = True
        button.style = discord.ButtonStyle.secondary
        button.label = "考え中... 💬"
        await interaction.response.edit_message(view=self)

        elapsed_time = time.time() - self.start_time

        announce_msg = await interaction.channel.send(
            f"📢 **早押し成功！** （タイム: `{elapsed_time:.2f}秒` ⏱️）\n"
            f"解答権： {interaction.user.mention} さん！\n"
            f"🚨 **15秒以内**にチャットに答えを入力してください！"
        )

        def check_answer(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            user_msg = await self.bot.wait_for('message', check=check_answer, timeout=15.0)
            
            if user_msg.content.strip().lower() == self.answer.lower():
                await user_msg.reply(f"🎉 **正解！！** おめでとうございます！\n答えは「**{self.answer}**」でした！")
                self.stop()
                
                button.label = "正解が出ました 🎉"
                button.style = discord.ButtonStyle.success
                await self.quiz_message.edit(view=self)
                return
            else:
                await user_msg.reply(f"❌ **不正解！** {interaction.user.mention} さんは解答権を失いました。")

        except asyncio.TimeoutError:
            await interaction.channel.send(f"⏰ タイムアップ！ {interaction.user.mention} さんは時間切れで解答権を失いました。")

        self.wrong_users.add(interaction.user.id)
        self.is_processing = False
        
        button.disabled = False
        button.style = discord.ButtonStyle.danger
        button.label = "押しボタン 🔴"
        
        lost_mentions = [f"<@{uid}>" for uid in self.wrong_users]
        self.base_embed.set_footer(text=f"※解答権喪失: {', '.join(lost_mentions)}\nまだの人はボタンを押せます！")
        
        await self.quiz_message.edit(embed=self.base_embed, view=self)
        await announce_msg.delete()

    # 10分間誰もボタンを押さずにタイムアウトした場合の処理
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
            item.label = "時間切れ ⏰"
            item.style = discord.ButtonStyle.secondary
            
        if self.quiz_message:
            await self.quiz_message.edit(view=self)
            # 【変更点】テキストを「10分間」に修正しました
            await self.quiz_message.channel.send(f"⏰ **10分間誰の解答もなかったため、クイズを終了します。**\n正解は「**{self.answer}**」でした！")

@bot.tree.command(name="quiz", description="早押しクイズを出題します（間違えたら他の人に回答権が回ります）")
@app_commands.describe(question="出題する問題文", answer="クイズの正解")
async def quiz(interaction: discord.Interaction, question: str, answer: str):
    embed = discord.Embed(
        title="❓ 早押しクイズ出題！",
        description=f"【問題】\n**{question}**\n\n分かった人は下のボタンを素早くプッシュ！",
        color=discord.Color.gold()
    )
    embed.set_footer(text="🚨 間間違えたり15秒答えないとお手付きになり、他の人が押せるようになります。")

    start_time = time.time()
    view = QuizBuzzerView(bot, answer, start_time, embed)
    
    await interaction.response.send_message(embed=embed, view=view)
    view.quiz_message = await interaction.original_response()


# ==========================================
# ⚙️ 7. 管理者専用コマンド群 (接頭辞: !skr_)
# ==========================================

# ① メッセージ一括削除コマンド
@bot.command(name="clear")
async def msg_clear(ctx, amount: int):
    if amount < 1:
        await ctx.send("1以上の数値を指定してください。", delete_after=5)
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 正常に {len(deleted) - 1} 件のメッセージを削除しました！", delete_after=5)

# ② 所属サーバー確認コマンド
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

# ③ Botにお喋りさせるコマンド
@bot.command(name="say")
async def bot_say(ctx, channel: discord.TextChannel, *, message: str):
    await ctx.message.delete()
    await channel.send(message)

# ④ Botのステータスを変更するコマンド
@bot.command(name="status")
async def change_status(ctx, *, text: str):
    await bot.change_presence(activity=discord.Game(name=text))
    await ctx.send(f"🤖 Botのステータスを「**{text} をプレイ中**」に変更しました！")

# ⑤ 回線速度（Ping値）を確認するコマンド
@bot.command(name="ping")
async def ping_check(ctx):
    raw_ping = bot.latency * 1000
    start_time = time.time()
    message = await ctx.send("⚡ Ping測定中...")
    end_time = time.time()
    msg_ping = (end_time - start_time) * 1000
    
    embed = discord.Embed(title="📶 Bot回線状態（レイテンシ）", color=discord.Color.green())
    embed.add_field(name="WebSocket Ping (APIとの通信)", value=f"`{raw_ping:.2f} ms`", inline=False)
    embed.add_field(name="Message Ping (メッセージ送信速度)", value=f"`{msg_ping:.2f} ms`", inline=False)
    
    if raw_ping < 50:
        status_text = "🟢 非常に快適（爆速です）"
    elif raw_ping < 150:
        status_text = "🟡 普通（通常利用に問題ありません）"
    else:
        status_text = "🔴 遅延気味（Discord側かサーバーが重い可能性があります）"
        
    embed.set_footer(text=f"稼働状況: {status_text}")
    await message.edit(content=None, embed=embed)

# ⑥ Botを強制終了（再起動）させるコマンド
@bot.command(name="restart")
async def restart_bot(ctx):
    await ctx.send(" **再起動処理を実行中**")
    print("管理者コマンドにより、プログラムを終了します。")
    await bot.close()
    sys.exit(0)


# ==========================================
# Botの起動
# ==========================================
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env ファイルから 'token' が読み込めませんでした。設定を確認してください。")