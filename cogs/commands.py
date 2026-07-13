import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import time
import sys

# --- ロールパネル用のView（永続化対応） ---
class RolePanelView(discord.ui.View):
    def __init__(self):
        # timeout=None にすることでBot再起動後もボタンが有効になります
        super().__init__(timeout=None)

    # 永続化を有効にするため、custom_idを固定したボタンをデコレータで定義
    # 引数として受け取るのではなく、ボタン自体をViewに固定するか、動的IDをパースする必要があります。
    # ここでは一般的な「ボタン1」「ボタン2」の汎用実装の例として、カスタムIDを固定します。
    # ※実際の運用ではロールIDをカスタムIDに埋め込むため、callback内でパースします。

    @discord.ui.button(label="ロール1", style=discord.ButtonStyle.primary, custom_id="persistent_role_1")
    async def role_one_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # パネル作成時にBotの特定の設定等からロールIDを取得する設計が理想ですが、
        # 簡易的に、ここではボタン名（または事前に保存されたID）から処理するロジックを想定
        await interaction.response.send_message("⚠️ 永続ボタンのロール割り当てロジックをここに実装します。", ephemeral=True)


# --- 早押しクイズ用のView ---
class QuizBuzzerView(discord.ui.View):
    def __init__(self, bot, answer: str, start_time: float, embed: discord.Embed, quiz_timeout: float = 60.0, answer_timeout: float = 15.0):
        # 💡 quiz_timeout（問題全体の制限時間）を外部から受け取れるように変更
        super().__init__(timeout=quiz_timeout)
        self.bot = bot
        self.answer = answer.strip()
        self.start_time = start_time
        self.base_embed = embed
        self.is_processing = False
        self.wrong_users = set()
        self.quiz_message = None
        
        # 💡 カスタム可能な時間制限を保持
        self.answer_timeout = answer_timeout  # ボタンを押してからの回答時間（秒）

    @discord.ui.button(label="押しボタン 🔴", style=discord.ButtonStyle.danger)
    async def press_buzzer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_processing:
            await interaction.response.send_message("遅かった！すでに他の人がボタンを押しています。", ephemeral=True)
            return
        if interaction.user.id in self.wrong_users:
            await interaction.response.send_message("❌ あなたはすでに解答権を失っています（お手付き）。", ephemeral=True)
            return

        self.is_processing = True
        button.disabled = True
        button.style = discord.ButtonStyle.secondary
        button.label = "考え中... 💬"
        await interaction.response.edit_message(view=self)

        elapsed_time = time.time() - self.start_time
        announce_msg = await interaction.channel.send(
            f"📢 **早押し成功！** （タイム: `{elapsed_time:.2f}秒` ⏱️）\n"
            f"解答権： {interaction.user.mention} さん！\n🚨 **{int(self.answer_timeout)}秒以内**に答えを入力してください！"
        )

        def check_answer(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            # 💡 カスタムされた回答時間（self.answer_timeout）を使用
            user_msg = await self.bot.wait_for('message', check=check_answer, timeout=self.answer_timeout)
            if user_msg.content.strip().lower() == self.answer.lower():
                await user_msg.reply(f"🎉 **正解！！**\n答えは「**{self.answer}**」でした！")
                self.stop()
                button.label = "正解が出ました 🎉"
                button.style = discord.ButtonStyle.success
                await self.quiz_message.edit(view=self)
                return
            else:
                await user_msg.reply(f"❌ **不正解！** {interaction.user.mention} さんは解答権を失いました。")
        except asyncio.TimeoutError:
            await interaction.channel.send(f"⏰ タイムアップ！ {interaction.user.mention} さんは時間切れです。")

        self.wrong_users.add(interaction.user.id)
        self.is_processing = False
        button.disabled = False
        button.style = discord.ButtonStyle.danger
        button.label = "押しボタン 🔴"
        
        # メンションのテキスト変換
        lost_mentions = [f"<@{uid}>" for uid in self.wrong_users]
        self.base_embed.set_footer(text=f"※解答権喪失: {', '.join(lost_mentions)}\nまだの人はボタンを押せます！")
        await self.quiz_message.edit(embed=self.base_embed, view=self)
        try:
            await announce_msg.delete()
        except discord.NotFound:
            pass

    async def on_timeout(self):
        """⏰ 問題全体の制限時間が切れたときの処理"""
        for item in self.children:
            item.disabled = True
            item.label = "時間切れ ⏰"
            item.style = discord.ButtonStyle.secondary
            
        if self.quiz_message:
            try:
                # 元々のクイズのボタンを「時間切れ」に更新
                await self.quiz_message.edit(view=self)
                
                # 💡 【新機能】元の問題メッセージ（self.quiz_message）にリプライする形で答えを表示！
                await self.quiz_message.reply(
                    f"⏰ **時間切れでクイズ終了です！**\n正解は「**{self.answer}**」でした！"
                )
            except discord.NotFound:
                pass

# --- ルーレット用のView ---
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


# --- メインのCogクラス ---
class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- スラッシュコマンド (一般向け) ---

    @app_commands.command(name="omikuji", description="今日のおみくじを引きます")
    async def omikuji(self, interaction: discord.Interaction):
        fortunes = ["大吉 🌟", "吉 🎯", "中吉 😊", "小吉 👍", "末吉 🌿", "凶 👻", "半吉", "元凶", "大凶", "反凶", "大狂", "狂"]
        result = random.choice(fortunes)
        await interaction.response.send_message(f"{interaction.user.mention} さんの今日の運勢は... **{result}** です！")

    @app_commands.command(name="timer", description="指定した分数後にメンションで通知します（最大180分）")
    @app_commands.describe(minutes="タイマーの分数 (1〜180分)")
    async def timer(self, interaction: discord.Interaction, minutes: int):
        # 悪意ある長時間占有を防ぐバリデーション
        if minutes < 1 or minutes > 180:
            await interaction.response.send_message("❌ 1分から180分（3時間）の間で指定してください。", ephemeral=True)
            return
        await interaction.response.send_message(f"🔔 {minutes}分間のタイマーを開始しました。時間が来たらお知らせします！")
        await asyncio.sleep(minutes * 60)
        await interaction.channel.send(f"⏰ {interaction.user.mention} さん、{minutes}分が経過しました！")

    @app_commands.command(name="roulette", description="サーバー内の全メンバーからランダムに1人選んでメンションします")
    async def roulette(self, interaction: discord.Interaction):
        guild = interaction.guild
        candidates = [m for m in guild.members if not m.bot]
        if not candidates:
            await interaction.response.send_message("❌ 抽選対象となるメンバーが見つかりませんでした。", ephemeral=True)
            return
        await interaction.response.send_message(f"🎰 **全サーバーメンバーから選出中... ドラムロールスタート！**")
        await asyncio.sleep(2.0)
        chosen_member = random.choice(candidates)
        embed = discord.Embed(title="🎯 ルーレット結果", description=f"対象: 全サーバーメンバー ({len(candidates)}人)\n\n選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！", color=discord.Color.red())
        view = MemberRouletteView(candidates)
        await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=view)

    @app_commands.command(name="koubun", description="ふたつの言葉からコウメ太夫のネタを生成します")
    @app_commands.describe(word1="〜かと思ったら", word2="〜でした")
    async def koubun(self, interaction: discord.Interaction, word1: str, word2: str):
        # 文字数過多によるDiscord APIエラー防止
        if len(word1) > 500 or len(word2) > 500:
            await interaction.response.send_message("❌ 文字数が長すぎます（各500文字以内にしてね）。", ephemeral=True)
            return
        joke = f"チャンチャカチャンチャン チャチャンチャチャンチャン♪\n\n**{word1}** かと思ったら〜〜〜\n\n**{word2}** でした〜〜〜\n\n**チクショーー！！** 😭"
        await interaction.response.send_message(joke)
    
    @app_commands.command(name="quiz", description="早押しクイズを出題します（間違えたら他の人に回答権が回ります）")
    @app_commands.describe(question="出題する問題文", answer="クイズの正解")
    async def quiz(self, interaction: discord.Interaction, question: str, answer: str):
        # 問題文の最後に @ユーザー名 を追加
        formatted_question = f"{question} ({interaction.user.mention})"

        embed = discord.Embed(
            title="❓ 早押しクイズ出題！", 
            description=f"【問題】\n**{formatted_question}**\n\n分かった人は下のボタンを素早くプッシュ！", 
            color=discord.Color.gold()
        )
        embed.set_footer(text="🚨 間違えたり15秒答えないとお手付きになり、他の人が押せるようになります。")
        
        start_time = time.time()
        view = QuizBuzzerView(self.bot, answer, start_time, embed)
        
        try:
            # 1. チャンネル全体にクイズを投稿（Botからの新規投稿扱いにする）
            quiz_msg = await interaction.channel.send(embed=embed, view=view)
            view.quiz_message = quiz_msg
            
            # 2. コマンドを打った本人にだけ成功メッセージを返す（これで「〜さんが使用しました」が消えます）
            await interaction.response.send_message("✅ クイズを正常に出題しました！", ephemeral=True)
            
        except Exception as e:
            # 万が一、権限不足などで投稿できなかった場合
            print(f"クイズ出題エラー: {e}")
            await interaction.response.send_message("❌ クイズの出題に失敗しました。Botのメッセージ送信権限を確認してください。", ephemeral=True)
    # --- スラッシュコマンド (管理者限定) ---

    @app_commands.command(name="role_panel", description="【管理者用】ロール付与用のパネルを作成します")
    @app_commands.describe(title="パネルのタイトル", description="説明文")
    @app_commands.default_permissions(administrator=True) # スラッシュコマンドの権限制限
    async def create_role_panel(self, interaction: discord.Interaction, title: str, description: str):
        # デコレータに加えてコード側でも二重チェック
        if not interaction.permissions.administrator:
            await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
            return
        
        embed = discord.Embed(title=title, description=description, color=discord.Color.green())
        view = RolePanelView() # 永続ビューの呼び出し
        await interaction.response.send_message("📢 ロールパネルを作成しました！", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)


    # --- テキストコマンド (権限・セキュリティ強化版) ---

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True) # メッセージ管理権限が必須
    async def msg_clear(self, ctx, amount: int):
        if amount < 1 or amount > 100:
            await ctx.send("❌ 1から100の間の数値を指定してください。", delete_after=5)
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 正常に {len(deleted) - 1} 件のメッセージを削除しました！", delete_after=5)

    @commands.command(name="servers")
    @commands.is_owner() # Botの開発者（オーナー）しか実行できない
    async def list_servers(self, ctx):
        guild_count = len(self.bot.guilds)
        server_list = ""
        for guild in self.bot.guilds:
            server_list += f"• **{guild.name}** (メンバー数: {guild.member_count}人, ID: `{guild.id}`)\n"
            if len(server_list) > 1800: # 2000文字制限対策
                server_list += "• ...他多数"
                break
        embed = discord.Embed(title="🤖 Bot所属サーバー一覧", description=f"現在 **{guild_count}** 個のサーバーに参加しています。\n\n{server_list}", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name="say")
    @commands.has_permissions(administrator=True) # 管理者のみ
    async def say_message(self, ctx, channel: discord.TextChannel, *, message: str):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await channel.send(message)

    @commands.command(name="status")
    @commands.is_owner() # オーナーのみ
    async def change_status(self, ctx, *, text: str):
        await self.bot.change_presence(activity=discord.Game(name=text))
        await ctx.send(f"🤖 Botのステータスを「**{text} をプレイ中**」に変更しました！")

    @commands.command(name="ping")
    async def ping_check(self, ctx):
        raw_ping = self.bot.latency * 1000
        start_time = time.time()
        message = await ctx.send("⚡ Ping測定中...")
        end_time = time.time()
        msg_ping = (end_time - start_time) * 1000
        embed = discord.Embed(title="📶 Bot回線状態（レイテンシ）", color=discord.Color.green())
        embed.add_field(name="WebSocket Ping (APIとの通信)", value=f"`{raw_ping:.2f} ms`", inline=False)
        embed.add_field(name="Message Ping (メッセージ送信速度)", value=f"`{msg_ping:.2f} ms`", inline=False)
        status_text = "🟢 非常に快適" if raw_ping < 50 else "🟡 普通" if raw_ping < 150 else "🔴 遅延気味"
        embed.set_footer(text=f"稼働状況: {status_text}")
        await message.edit(content=None, embed=embed)

    @commands.command(name="restart")
    @commands.is_owner() # オーナーのみがBotを停止可能
    async def restart_bot(self, ctx):
        await ctx.send("**再起動処理を実行中 (プロセスを終了します)**")
        await self.bot.close()
        sys.exit(0)


# ⚙️ スラッシュコマンドと永続Viewのセットアップ
async def setup(bot: commands.Bot):
    # ロールパネルのViewを永続化（再起動後も動作させる）
    bot.add_view(RolePanelView())
    await bot.add_cog(CommandsCog(bot))