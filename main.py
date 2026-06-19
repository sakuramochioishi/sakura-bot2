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
import datetime  

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

# 📋 監査ログを送信するチャンネルのID（お使いのチャンネルIDに書き換えてください）
LOG_CHANNEL_ID = 1517390946667335790

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
# 🆕 0. ヘルプコマンド (/help) - 全員用
# ==========================================
@bot.tree.command(name="help", description="Botのコマンド一覧と使い方を表示します")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 sakura-bot2 コマンド一覧",
        description="このBotで利用可能なコマンドの一覧です。\n`/` から始まるコマンドは全員が使用できます。",
        color=discord.Color.blurple()
    )

    # 1. 一般ユーザー用（スラッシュコマンド）
    general_cmds = (
        "🧠 **/quiz [問題] [正解]**\n"
        "└ 本格的な早押しクイズを出題（10分スルーで自動終了・お手付き時は他者に権利移行）。\n\n"
        "🎯 **/roulette**\n"
        "└ サーバー内の全メンバー（Bot除く）からランダムに1人を選出。\n\n"
        "🔮 **/omikuji**\n"
        "└ 今日の運勢を占います。\n\n"
        "⏰ **/timer [分]**\n"
        "└ 指定した時間（分単位）が経過したらメンションでお知らせ。\n\n"
        "🔗 **/redirect [URL]**\n"
        "└ 入力されたURLの最終的なリダイレクト先（移動先）を安全に確認。\n\n"
        "🏮 **/koubun [言葉1] [言葉2]**\n"
        "└ コウメ太夫風のネタ文章を生成。"
    )
    embed.add_field(name="👥 全員が使えるコマンド", value=general_cmds, inline=False)


    embed.set_footer(text="sakura-bot2 • 快適なサーバーライフを！")
    
    # 全員が見える形で返信
    await interaction.response.send_message(embed=embed)


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
        super().__init__(timeout=600)  # 10分
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

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
            item.label = "時間切れ ⏰"
            item.style = discord.ButtonStyle.secondary
            
        if self.quiz_message:
            await self.quiz_message.edit(view=self)
            await self.quiz_message.channel.send(f"⏰ **10分間誰の解答もなかったため、クイズを終了します。**\n正解は「**{self.answer}**」でした！")

@bot.tree.command(name="quiz", description="早押しクイズを出題します（間違えたら他の人に回答権が回ります）")
@app_commands.describe(question="出題する問題文", answer="クイズの正解")
async def quiz(interaction: discord.Interaction, question: str, answer: str):
    embed = discord.Embed(
        title="❓ 早押しクイズ出題！",
        description=f"【問題】\n**{question}**\n\n分かった人は下のボタンを素早くプッシュ！",
        color=discord.Color.gold()
    )
    embed.set_footer(text="🚨 間違えたり15秒答えないとお手付きになり、他の人が押せるようになります。")

    start_time = time.time()
    view = QuizBuzzerView(bot, answer, start_time, embed)
    
    await interaction.response.send_message(embed=embed, view=view)
    view.quiz_message = await interaction.original_response()

# ==========================================
# 🔘 リアクションロール（ボタン付パネル）機能
# ==========================================

# ① ボタンを押した時の処理を担当するクラス
class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: str, style: discord.ButtonStyle):
        super().__init__(label=label, style=style, custom_id=f"role_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        role = guild.get_role(self.role_id)
        
        if not role:
            await interaction.response.send_message("❌ 設定されたロールが見つかりません。", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ ロール【**{role.name}**】を外しました！", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ ロール【**{role.name}**】を付与しました！", ephemeral=True)


# ② ボタンを並べて保持するためのViewクラス
class RolePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


# ③ 管理者だけが実行できるスラッシュコマンド本体
@bot.tree.command(name="role_panel", description="【管理者用】ロール付与用のボタン付きパネルを作成します")
@app_commands.describe(
    title="パネルのタイトル（例: ゲーム選択）", 
    description="説明文（例: 下のボタンを押すと役職がつきます）",
    role1="ボタン1で付与する役職（選んでください）", role1_label="ボタン1の文字",
    role2="ボタン2で付与する役職（任意）", role2_label="ボタン2の文字（任意）"
)
@app_commands.default_permissions(administrator=True)
async def create_role_panel(
    interaction: discord.Interaction, 
    title: str, 
    description: str, 
    role1: discord.Role,       # ★変更点: 型を str から discord.Role に変更
    role1_label: str, 
    role2: discord.Role = None, # ★変更点: 型を str から discord.Role に変更
    role2_label: str = None
):
    # 実行したユーザーがサーバーの管理者権限を持っているかチェック
    if not interaction.permissions.administrator:
        await interaction.response.send_message("❌ このコマンドを実行する権限（管理者権限）がありません。", ephemeral=True)
        return

    # パネルの見た目（Embed）を作成
    embed = discord.Embed(title=title, description=description, color=discord.Color.green())
    view = RolePanelView()

    # ★変更点: role1.id で直接数字のIDが取得できるようになりました（ValueErrorのtry-exceptも不要に！）
    view.add_item(RoleButton(role_id=role1.id, label=role1_label, style=discord.ButtonStyle.primary))
    
    # ボタン2が指定されていれば追加
    if role2 and role2_label:
        view.add_item(RoleButton(role_id=role2.id, label=role2_label, style=discord.ButtonStyle.success))

    # コマンドを打った本人にだけ見える完了メッセージ
    await interaction.response.send_message("📢 ロールパネルを作成しました！", ephemeral=True)
    
    # チャンネルにパネルを送信
    await interaction.channel.send(embed=embed, view=view)

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
    await ctx.send(f"🧹 正常に {len(deleted) - 1} 件 of メッセージを削除しました！", delete_after=5)

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
    await ctx.send("**再起動処理を実行中**")
    print("管理者コマンドにより、プログラムを終了します。")
    await bot.close()
    sys.exit(0)

# ==========================================
# 🔒 セキュリティ設定 & 📋 監査ログ機能
# ==========================================
@bot.check
async def globally_restrict_to_owner(ctx):
    # 管理者専用コマンド（!skr_）が実行されたときのログ処理
    log_msg = f"🛡️ [管理者コマンド実行] ユーザー: {ctx.author} (ID: {ctx.author.id}) | コマンド: {ctx.message.content}"
    print(log_msg)
    
    # Discordのログチャンネルに送信
    bot.loop.create_task(send_audit_log(log_msg))
    
    return await bot.is_owner(ctx.author)

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: app_commands.Command):
    # スラッシュコマンド（/）が正常に実行完了したときのログ処理
    # 引数（options）があればそれも記録する
    options = ", ".join([f"{k}: {v}" for k, v in interaction.namespace.__dict__.items()])
    opt_text = f" (引数: {options})" if options else ""
    
    log_msg = f"⚙️ [スラッシュコマンド] ユーザー: {interaction.user} | コマンド: /{command.name}{opt_text} | サーバー: {interaction.guild.name if interaction.guild else 'DM'}"
    print(log_msg)
    
    await send_audit_log(log_msg)

@bot.event
async def on_command_error(ctx, error):
    # 権限がない人が!skr_コマンドを打った場合の不正アクセスログ
    if isinstance(error, commands.NotOwner):
        log_msg = f"⚠️ [不正アクセス検出] 権限のないユーザーが管理者コマンドを試行しました。\nユーザー: {ctx.author} (ID: {ctx.author.id}) | 内容: {ctx.message.content}"
        print(log_msg)
        await send_audit_log(log_msg)
        return
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

# ログを共通で送信するための補助関数
async def send_audit_log(message_text: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        # メンションが無闇に飛ばないようにプレーンテキストで送信
        await channel.send(f"```{message_text}```")

# ==========================================
# 📋 サーバーアクティビティ＆モデレーション監査ログ
# ==========================================

# ① メッセージが編集されたとき
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or before.content == after.content:
        return
    log_msg = (
        f"📝 [メッセージ編集]\n"
        f"ユーザー: {before.author} (ID: {before.author.id})\n"
        f"チャンネル: {before.channel.mention}\n"
        f"変更前: {before.content}\n"
        f"変更後: {after.content}"
    )
    print(log_msg)
    await send_audit_log(log_msg)

# ② メッセージが削除されたとき
@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot:
        return
    log_msg = (
        f"🗑️ [メッセージ削除]\n"
        f"ユーザー: {message.author} (ID: {message.author.id})\n"
        f"チャンネル: {message.channel.mention}\n"
        f"内容: {message.content if message.content else '（画像または埋め込み）'}"
    )
    print(log_msg)
    await send_audit_log(log_msg)

# ③ 新しいメンバーがサーバーに参加したとき
@bot.event
async def on_member_join(member: discord.Member):
    log_msg = f"📥 [サーバー参加] {member} (ID: {member.id}) がサーバーに参加しました。"
    print(log_msg)
    await send_audit_log(log_msg)

# ④ メンバーがサーバーから退出したとき
@bot.event
async def on_member_remove(member: discord.Member):
    log_msg = f"📤 [サーバー退出] {member} (ID: {member.id}) がサーバーから離脱しました。"
    print(log_msg)
    await send_audit_log(log_msg)

# ⑤ 手動での管理操作（タイムアウト・BAN・キック・招待リンク操作）の検知
@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
    log_msg = None
    user = entry.user

    # 1. タイムアウト（付与・解除）の検知 (メンバー更新イベント)
    if entry.action.value == 24:  # AuditLogAction.member_update の数値
        if hasattr(entry.after, 'communication_disabled_until'):
            target = entry.target
            before_timeout = entry.before.communication_disabled_until
            after_timeout = entry.after.communication_disabled_until

            if after_timeout and not before_timeout:
                log_msg = f"🔇 [タイムアウト付与]\n実行者: {user}\n対象者: {target}\n理由: {entry.reason}"
            elif not after_timeout and before_timeout:
                log_msg = f"🔊 [タイムアウト解除]\n実行者: {user}\n対象者: {target}"

    # 2. BAN（追放）の検知
    elif entry.action.value == 22:  # BAN追加の数値
        log_msg = f"🔨 [BAN 執行]\n実行者: {user}\n対象者: {entry.target}\n理由: {entry.reason}"

    # 3. BAN解除の検知
    elif entry.action.value == 23:  # BAN解除の数値
        log_msg = f"🔓 [BAN 解除]\n実行者: {user}\n対象者: {entry.target}"

    # 4. キック（強制退出）の検知
    elif entry.action.value == 20:  # キックの数値
        log_msg = f"👢 [キック 執行]\n実行者: {user}\n対象者: {entry.target}\n理由: {entry.reason}"

    # 5. 招待リンク作成の検知
    elif entry.action.value == 40:  # 招待作成の数値
        invite_code = getattr(entry.target, 'code', '不明')
        log_msg = f"✉️ [招待作成]\n作成者: {user}\nコード: discord.gg/{invite_code}"

    # 6. 招待リンク削除の検知
    elif entry.action.value == 41:  # 招待削除の数値
        invite_code = getattr(entry.target, 'code', '不明')
        log_msg = f"🗑️ [招待削除]\n削除者: {user}\nコード: discord.gg/{invite_code}"

    if log_msg:
        print(log_msg)
        await send_audit_log(log_msg)

from discord.ext import tasks  # 定期実行タスク用
import xml.etree.ElementTree as ET # YouTubeの更新データ（RSS）解析用

# 📺 YouTube通知の設定（お好みの情報に書き換えてください）
YOUTUBE_CHANNEL_ID = "UCo1RH7pR_wdgY_9LKONxXvA" # チェックしたいYouTubeチャンネルのID
NOTIFY_CHANNEL_ID = 1517395476155076728      # 通知を飛ばしたいDiscordのテキストチャンネルID

# 重複通知を防ぐために、最後に検知した動画IDを記憶する変数
last_video_id = None

# 15分ごとにYouTubeをチェックするタスク（秒換算: 900秒）
@tasks.loop(seconds=900)
async def check_youtube_update():
    global last_video_id
    
    # Botが完全に起動するまで待つ
    await bot.wait_until_ready()
    
    # Discordの通知先チャンネルを取得
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return

    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        # RSS(XML)の解析
        root = ET.fromstring(xml_data)
        
        # XMLの名前空間対策
        ns = {'ns': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        
        # 最新の動画エントリーを取得
        entry = root.find('ns:entry', ns)
        if entry is None:
            return
            
        video_id = entry.find('yt:videoId', ns).text
        video_title = entry.find('ns:title', ns).text
        video_url = entry.find('ns:link', ns).attrib['href']
        
        # 初回起動時はIDを覚えるだけで通知しない（過去動画が全部流れるのを防ぐ）
        if last_video_id == None:
            last_video_id = video_id
            print(f"📺 YouTube初期化: 現在の最新動画は「{video_title}」です。")
            return
            
        # 記憶しているIDと違っていれば「新着動画」と判定！
        if video_id != last_video_id:
            last_video_id = video_id
            
            # Discordに新着動画を通知
            await channel.send(
                f"🌟 **YouTube 新着動画通知** 🌟\n"
                f"チャンネルに新しい動画が投稿されました！\n\n"
                f"🎥 **{video_title}**\n"
                f"🔗 {video_url}"
            )
            print(f"📺 新着動画を通知しました: {video_title}")
            
    except Exception as e:
        print(f"⚠️ YouTubeチェック中にエラーが発生しました: {e}")

# Bot起動完了イベント（on_ready）の最後に、このタスクをスタートさせるコードを組み込みます
# ※既存の「@bot.event async def on_ready():」の関数内の一番最後に以下を追記してください
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    
    # YouTubeの定期チェックタスクが動いていなければ起動する
    if not check_youtube_update.is_running():
        check_youtube_update.start()

# 🐦 X（旧Twitter）通知の設定
# ※あらかじめ外部サービス等で作成した「XアカウントのRSSフィードURL」をここに貼り付けます
X_RSS_URL = "https://rss.app/feeds/o0UUr09aLtvjb39n.xml" 
X_NOTIFY_CHANNEL_ID = 1517444749743751169 # 通知を飛ばしたい管理鯖のチャンネルID

# 重複通知を防ぐために、最後に検知したポストのURL（またはID）を記憶する変数
last_tweet_url = None

# 15分ごとにXをチェックするタスク
@tasks.loop(seconds=900)
async def check_x_update():
    global last_tweet_url
    
    await bot.wait_until_ready()
    
    channel = bot.get_channel(X_NOTIFY_CHANNEL_ID)
    if not channel:
        return

    try:
        req = urllib.request.Request(X_RSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        
        # RSSフィード内の最新の投稿（item）を取得
        item = root.find('.//item')
        if item is None:
            return
            
        tweet_title = item.find('title').text
        tweet_url = item.find('link').text
        
        # 初回起動時は記憶するだけで通知しない（過去のポストが一気に流れるのを防ぐ）
        if last_tweet_url == None:
            last_tweet_url = tweet_url
            print(f"🐦 X初期化: 現在の最新ポストは「{tweet_title[:15]}...」です。")
            return
            
        # 記憶しているURLと違っていれば「新着ポスト」と判定！
        if tweet_url != last_tweet_url:
            last_tweet_url = tweet_url
            
            # Discordに新着ポストを通知
            await channel.send(
                f"📢 **X（旧Twitter）新着ポスト通知** 📢\n"
                f"アカウントが新しくポストしました！\n\n"
                f"📝 **内容:**\n{tweet_title}\n\n"
                f"🔗 **リンク:** {tweet_url}"
            )
            print(f"🐦 新着ポストを通知しました: {tweet_title[:15]}...")
            
    except Exception as e:
        print(f"⚠️ Xチェック中にエラーが発生しました: {e}")

# Bot起動完了イベント（on_ready）の最後に、このタスクをスタートさせるコードを組み込みます
# ※既存の「on_ready」関数内の一番最後に以下をさらに追記してください
@bot.event
async def on_ready():
    # (既存のYouTubeタスク起動コードなどの下に追記)
    if not check_x_update.is_running():
        check_x_update.start()

# ==========================================
# Botの起動
# ==========================================
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: .env ファイルから 'token' が読み込めませんでした。設定を確認してください。")