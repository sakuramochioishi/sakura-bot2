import logging
import re
import time
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


# 📯 挨拶機能のコグ
class GreetingsCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_greet_times = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        content = message.content
        lower_content = content.lower().strip()
        current_time = time.time()

        ohayo_words = [
            "おは",
            "おはよ",
            "おはよう",
            "ぐっどもーにんぐ",
            "グッドモーニング",
            "good morning",
        ]

        if any(word in lower_content for word in ohayo_words):
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(
                    f"おはようございます、{message.author.display_name}さん！今日も頑張りましょう！☀️"
                )
                self.last_greet_times[channel_id] = current_time
            return

        if "おやすみ" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(
                    f"おやすみなさい、{message.author.display_name}さん。良い夢を！🌙"
                )
                self.last_greet_times[channel_id] = current_time
            return

        ya_words = ["や", "やぁ", "ya", "yala", "yaxa"]
        if lower_content in ya_words:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send("やぁ")
                self.last_greet_times[channel_id] = current_time
            return

        yo_words = ["よ", "よぁ", "yo", "yoxo", "yolo"]
        if lower_content in yo_words:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send("よぉ")
                self.last_greet_times[channel_id] = current_time
            return


# 🛡️ モデレーション機能のコグ（冷笑削除）
class ModerationCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ng_words = [
            "おおw",
            "うおw",
            "oow",
            "uow",
            "おおｗ",
            "うおｗ",
            "うお",
            "uo",
            "どわーｗ",
            "どわーw",
            "どわ-",
            "どわ-w",
            "dowa-w",
            "dowa-",
            "dowaーw",
            "きちーｗ",
            "きちーw",
            "kichi-w",
            "kiti-w",
        ]

    async def get_reishou_channels(self, guild_id: int) -> list[int]:
        """SettingsCog から対象チャンネルリストを取得する"""
        settings_cog = (
            self.bot.get_cog("SettingsCog")
            or self.bot.get_cog("setting")
            or self.bot.get_cog("Setting")
        )
        if not settings_cog:
            return []

        try:
            if hasattr(settings_cog, "get_reishou_channels"):
                func = getattr(settings_cog, "get_reishou_channels")
                if discord.utils.isawaitable(func(guild_id)):
                    return await func(guild_id)
                return func(guild_id)
        except Exception as e:
            logger.warning(f"チャンネル設定の取得中にエラーが発生しました: {e}")

        return []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.channel:
            return

        allowed_channels = await self.get_reishou_channels(message.guild.id)

        if not allowed_channels or (message.channel.id not in allowed_channels):
            return

        content = message.content.lower()

        for ng_word in self.ng_words:
            pattern = rf"(?:^|\s){re.escape(ng_word)}(?:$|\s)"

            if re.search(pattern, content) or content == ng_word:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ 冷笑を検知し、**{message.author.display_name}** のメッセージを削除しました！"
                    )
                    return
                except discord.Forbidden:
                    logger.warning(
                        f"[{message.guild.name}] 権限が足りないため削除できませんでした。"
                    )
                except Exception as e:
                    logger.error(f"冷笑削除処理中にエラーが発生しました: {e}")


# ⚙️ コグをBotに登録する
async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingsCog(bot))
    await bot.add_cog(ModerationCog(bot))