import discord
from discord.ext import commands

class GreetingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 💡 最後の挨拶からのチャット数をカウントする辞書（チャンネルごとに管理）
        self.chat_counters = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """💬 誰かがメッセージを送信したときに動くイベント」"""
        # Bot自身の発言には反応しない
        if message.author.bot:
            return

        channel_id = message.channel.id
        content = message.content

        # チャンネルごとのカウンターがまだ無ければ初期化（最初は制限なしで反応できるように5にしておく）
        if channel_id not in self.chat_counters:
            self.chat_counters[channel_id] = 5

        # ☀️ 「おはよう」の判定
        if "おはよう" in content:
            # 5チャット以上開いているかチェック
            if self.chat_counters[channel_id] >= 5:
                await message.channel.send(f"おはようございます、{message.author.display_name}さん！今日も頑張りましょう！☀️")
                self.chat_counters[channel_id] = 0  # カウンターをリセット
            return

        # 🌙 「おやすみ」の判定
        if "おやすみ" in content:
            # 5チャット以上開いているかチェック
            if self.chat_counters[channel_id] >= 5:
                await message.channel.send(f"おやすみなさい、{message.author.display_name}さん。良い夢を！🌙")
                self.chat_counters[channel_id] = 0  # カウンターをリセット
            return

        # 📈 挨拶以外の普通のチャットが流れたら、カウンターを+1する
        self.chat_counters[channel_id] += 1

async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingsCog(bot))