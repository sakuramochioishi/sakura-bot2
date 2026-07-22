import discord
from discord import app_commands
from discord.ext import commands
import time
import asyncio
import traceback

class QuizBuzzerView(discord.ui.View):
    def __init__(self, bot: commands.Bot, answer: str, start_time: float, embed: discord.Embed, quiz_timeout: float = 900.0, answer_timeout: float = 15.0):
        super().__init__(timeout=quiz_timeout)
        self.bot = bot
        self.answer = answer.strip()
        self.start_time = start_time
        self.base_embed = embed
        self.is_processing = False
        self.wrong_users = set()
        self.quiz_message = None
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
                await self.quiz_message.edit(view=self)
                await self.quiz_message.reply(
                    f"⏰ **時間切れでクイズ終了です！**\n正解は「**{self.answer}**」でした！"
                )
            except discord.NotFound:
                pass


# ── 👑 クイズのコマンド群をまとめたCog ──
class QuizCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="quiz", description="早押しクイズを出題します！")
    @app_commands.describe(
        問題="クイズの問題文を入力してください",
        答え="クイズの正解を入力してください"
    )
    async def quiz(self, interaction: discord.Interaction, 問題: str, 答え: str):
        try:
            # 🟢 Embed（問題カード）の作成
            embed = discord.Embed(
                title="❓ 早押しクイズ！",
                description=f"**問題：**\n{問題}({interaction.user.mention})",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="下の赤いボタンを押して解答権を獲得してください！")

            # ⚙️ settings.py の SettingsCog から設定を取得する
            settings_cog = self.bot.get_cog("SettingsCog")
            if settings_cog:
                quiz_timeout = settings_cog.settings["quiz"].get("quiz_timeout", 900.0) 
                answer_timeout = settings_cog.settings["quiz"].get("answer_timeout", 15.0) 
            else:
                quiz_timeout = 900.0   
                answer_timeout = 15.0  

            # 💡 取得した設定値をViewに渡して作成
            view = QuizBuzzerView(
                bot=self.bot,
                answer=答え,
                start_time=time.time(),
                embed=embed,
                quiz_timeout=quiz_timeout,     
                answer_timeout=answer_timeout   
            )

            # 1️⃣ 出題者には隠しメッセージ（ephemeral）で送信完了を伝える
            await interaction.response.send_message("📢 クイズを出題しました！", ephemeral=True)
            
            # 2️⃣ チャンネルに直接、通常メッセージとして問題（Embed）とボタンを送信する
            quiz_message = await interaction.channel.send(embed=embed, view=view)
            
            # 3️⃣ 送信したメッセージオブジェクトをViewに記憶させる
            view.quiz_message = quiz_message

        except Exception as e:
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ クイズの作成中にエラーが発生しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(QuizCog(bot))