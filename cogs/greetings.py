import discord
from discord.ext import commands
import time

class GreetingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 最後に挨拶した「時刻」を保存する辞書（チャンネルごとに管理）
        self.last_greet_times = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """💬 誰かがメッセージを送信したときに動くイベント"""
        # Bot自身の発言には反応しない
        if message.author.bot:
            return

        channel_id = message.channel.id
        content = message.content
        current_time = time.time()

        # ── 🔥 【新機能】Botへのメンション判定 ──
        # Botのユーザーオブジェクトがメッセージの「mentions」に含まれているかチェック
        if self.bot.user in message.mentions:
            # メッセージの送信者がBotのオーナーかどうかを判定
            is_owner = await self.bot.is_owner(message.author)
            
            if is_owner:
                # 🥰 オーナー（あなた）への優しい対応
                await message.reply(f"はーい！呼びましたか？{message.author.display_name}さんのお手伝いなら、いつでも喜んで承りますよ！✨")
            else:
                # 🧊 それ以外の人への冷たい対応
                await message.reply("……何か用ですか？用事がないなら、むやみにメンションしないでください。")
            return # メンションに反応した場合は、ここで処理を終了

        # ── ☀️ 「おはよう」の判定（5秒制限あり） ──
        if "おはよう" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 5.0:
                await message.channel.send(f"おはようございます、{message.author.display_name}さん！今日も頑張りましょう！☀️")
                self.last_greet_times[channel_id] = current_time
            return

        # ── 🌙 「おやすみ」の判定（5秒制限あり） ──
        if "おやすみ" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 5.0:
                await message.channel.send(f"おやすみなさい、{message.author.display_name}さん。良い夢を！🌙")
                self.last_greet_times[channel_id] = current_time
            return
        
        if "やぁ" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 5.0:
                await message.channel.send(f"やぁ")
                self.last_greet_times[channel_id] = current_time
            return

async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingsCog(bot))