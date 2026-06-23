import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import time
import sys

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

class RolePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

class QuizBuzzerView(discord.ui.View):
    def __init__(self, bot, answer: str, start_time: float, embed: discord.Embed):
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
            f"解答権： {interaction.user.mention} さん！\n🚨 **15秒以内**に答えを入力してください！"
        )

        def check_answer(msg):
            return msg.author == interaction.user and msg.channel == interaction.channel

        try:
            user_msg = await self.bot.wait_for('message', check=check_answer, timeout=15.0)
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
            await self.quiz_message.channel.send(f"⏰ **クイズを終了します。**\n正解は「**{self.answer}**」でした！")

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


class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="omikuji", description="今日のおみくじを引きます")
    async def omikuji(self, interaction: discord.Interaction):
        fortunes = ["大吉 🌟", "吉 🎯", "中吉 😊", "小吉 👍", "末吉 🌿", "凶 👻"]
        result = random.choice(fortunes)
        await interaction.response.send_message(f"{interaction.user.mention} さんの今日の運勢は... **{result}** です！")

    @app_commands.command(name="timer", description="指定した分数後にメンションで通知します")
    async def timer(self, interaction: discord.Interaction, minutes: int):
        if minutes < 1:
            await interaction.response.send_message("1分以上の時間を指定してください。", ephemeral=True)
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
        joke = f"チャンチャカチャンチャン チャチャンチャチャンチャン♪\n\n**{word1}** かと思ったら〜〜〜\n\n**{word2}** でした〜〜〜\n\n**チクショーー！！** 😭"
        await interaction.response.send_message(joke)

    @app_commands.command(name="quiz", description="早押しクイズを出題します（間違えたら他の人に回答権が回ります）")
    @app_commands.describe(question="出題する問題文", answer="クイズの正解")
    async def quiz(self, interaction: discord.Interaction, question: str, answer: str):
        embed = discord.Embed(title="❓ 早押しクイズ出題！", description=f"【問題】\n**{question}**\n\n分かった人は下のボタンを素早くプッシュ！", color=discord.Color.gold())
        embed.set_footer(text="🚨 間違えたり15秒答えないとお手付きになり、他の人が押せるようになります。")
        start_time = time.time()
        view = QuizBuzzerView(self.bot, answer, start_time, embed)
        await interaction.response.send_message(embed=embed, view=view)
        view.quiz_message = await interaction.original_response()

    @app_commands.command(name="role_panel", description="【管理者用】ロール付与用のボタン付きパネルを作成します")
    @app_commands.describe(title="パネルのタイトル", description="説明文", role1="ボタン1で付与する役職", role1_label="ボタン1の文字", role2="ボタン2で付与する役職（任意）", role2_label="ボタン2の文字（任意）")
    @app_commands.default_permissions(administrator=True)
    async def create_role_panel(self, interaction: discord.Interaction, title: str, description: str, role1: discord.Role, role1_label: str, role2: discord.Role = None, role2_label: str = None):
        if not interaction.permissions.administrator:
            await interaction.response.send_message("❌ このコマンドを実行する権限がありません。", ephemeral=True)
            return
        embed = discord.Embed(title=title, description=description, color=discord.Color.green())
        view = RolePanelView()
        view.add_item(RoleButton(role_id=role1.id, label=role1_label, style=discord.ButtonStyle.primary))
        if role2 and role2_label:
            view.add_item(RoleButton(role_id=role2.id, label=role2_label, style=discord.ButtonStyle.success))
        await interaction.response.send_message("📢 ロールパネルを作成しました！", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

    @commands.command(name="clear")
    async def msg_clear(self, ctx, amount: int):
        if amount < 1:
            await ctx.send("1以上の数値を指定してください。", delete_after=5)
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 正常に {len(deleted) - 1} 件のメッセージを削除しました！", delete_after=5)

    @commands.command(name="servers")
    async def list_servers(self, ctx):
        guild_count = len(self.bot.guilds)
        server_list = ""
        for guild in self.bot.guilds:
            server_list += f"• **{guild.name}** (メンバー数: {guild.member_count}人, ID: `{guild.id}`)\n"
        embed = discord.Embed(title="🤖 Bot所属サーバー一覧", description=f"現在 **{guild_count}** 個のサーバーに参加しています。\n\n{server_list}", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name="say")
    async def say_message(self, ctx, channel: discord.TextChannel, *, message: str):
        await ctx.message.delete()
        await channel.send(message)

    @commands.command(name="status")
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
    async def restart_bot(self, ctx):
        await ctx.send("**再起動処理を実行中**")
        await self.bot.close()
        sys.exit(0)

# 🚨 クラスの外（一番左端）に配置
async def setup(bot: commands.Bot):
    bot.add_view(RolePanelView())
    await bot.add_cog(CommandsCog(bot))