import discord
from discord.ext import commands
import time

# 📯 挨拶機能のコグ
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

        # ── ☀️ 「おはよう」の判定
        if "おはよう" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(f"おはようございます、{message.author.display_name}さん！今日も頑張りましょう！☀️")
                self.last_greet_times[channel_id] = current_time
            return

        # ── 🌙 「おやすみ」の判定
        if "おやすみ" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(f"おやすみなさい、{message.author.display_name}さん。良い夢を！🌙")
                self.last_greet_times[channel_id] = current_time
            return
        
        lower_content = content.lower().strip()

        # ── 👋 「やぁ」シリーズの判定
        ya_words = ["や", "やぁ", "ya", "yala", "yaxa"]
        if lower_content in ya_words:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(f"やぁ")
                self.last_greet_times[channel_id] = current_time
            return

        # ── 😎 【新機能】「よぉ」シリーズの判定
        yo_words = ["よ", "よぉ", "yo", "yoxo", "yolo"] 
        if lower_content in yo_words:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(f"よぉ")
                self.last_greet_times[channel_id] = current_time
            return


# 🛡️ モデレーション機能のコグ（独立させました）
class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # ❌ 反応させたいNGワード（削除対象）のリスト
        self.ng_words = ["おおw", "うおw", "oow", "uow", "おおｗ", "うおｗ", "うお", "uo"]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """💬 誰かがメッセージを送信したときに動くイベント"""
        # Bot自身の発言には反応しない（無限ループ防止）
        if message.author.bot:
            return

        # メッセージのテキストを小文字にして取得
        content = message.content.lower()

        # リストの中のNGワードがメッセージに含まれているかチェック
        for ng_word in self.ng_words:
            if ng_word in content:
                try:
                    # 1️⃣ 検知したメッセージを削除する
                    await message.delete()
                    
                    # 2️⃣ 代わりのメッセージをチャンネルに送信する
                    await message.channel.send("⚠️ 冷笑を検知し{message.author.display_name}のメッセージを削除しました！")
                    return 
                    
                except discord.Forbidden:
                    print("❌ 権限が足りないため、メッセージを削除できませんでした。")
                except Exception as e:
                    print(f"❌ エラーが発生しました: {e}")


# ⚙️ 両方のコグをBotに登録する
async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingsCog(bot))
    await bot.add_cog(ModerationCog(bot))  # ← ここでモデレーション機能も読み込むようにしました！