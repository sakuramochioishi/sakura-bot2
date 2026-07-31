import asyncio
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
        # 最後に挨拶した「時刻」を保存する辞書（チャンネルごとに管理）
        self.last_greet_times = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """💬 誰かがメッセージを送信したときに動くイベント"""
        # Bot自身の発言やDMでの発言は無視
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        content = message.content
        lower_content = content.lower().strip()
        current_time = time.time()

        # ── ☀️ 「おはよう」の判定（拡張版）
        ohayo_words = [
            "おは",
            "おはよ",
            "おはよう",
            "ぐっどもーにんぐ",
            "グッドモーニング",
            "good morning",
        ]

        # 指定されたキーワードのいずれかがメッセージに含まれているか判定
        if any(word in lower_content for word in ohayo_words):
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:  # 15分間のクールダウン
                await message.channel.send(
                    f"おはようございます、{message.author.display_name}さん！今日も頑張りましょう！☀️"
                )
                self.last_greet_times[channel_id] = current_time
            return

        # ── 🌙 「おやすみ」の判定
        if "おやすみ" in content:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send(
                    f"おやすみなさい、{message.author.display_name}さん。良い夢を！🌙"
                )
                self.last_greet_times[channel_id] = current_time
            return

        # ── 👋 「やぁ」シリーズの判定
        ya_words = ["や", "やぁ", "ya", "yala", "yaxa"]
        if lower_content in ya_words:
            last_time = self.last_greet_times.get(channel_id, 0)
            if current_time - last_time >= 900.0:
                await message.channel.send("やぁ")
                self.last_greet_times[channel_id] = current_time
            return

        # ── 😎 「よぉ」シリーズの判定
        yo_words = ["よ", "よぉ", "yo", "yoxo", "yolo"]
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
        # ❌ 反応させたいNGワード（削除対象）のリスト
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
        """setting Cog から冷笑対象のチャンネルリストを安全に取得する"""
        settings_cog = (
            self.bot.get_cog("setting")
            or self.bot.get_cog("Setting")
            or self.bot.get_cog("SettingsCog")
        )
        if not settings_cog:
            return []

        try:
            # 1. メソッド経由で取得を試みる (async def の場合と通常の関数の両方に対応)
            if hasattr(settings_cog, "get_reishou_channels"):
                func = getattr(settings_cog, "get_reishou_channels")
                if asyncio.iscoroutinefunction(func):
                    return await func(guild_id)
                return func(guild_id)

            elif hasattr(settings_cog, "get_reishou_channel_id"):
                func = getattr(settings_cog, "get_reishou_channel_id")
                res = (
                    await func(guild_id)
                    if asyncio.iscoroutinefunction(func)
                    else func(guild_id)
                )
                return [res] if res else []

            # 2. 辞書形式 (settings.py が辞書で保持している場合)
            elif hasattr(settings_cog, "settings"):
                settings_data = getattr(settings_cog, "settings", {})
                reishou_data = settings_data.get("reishou", {})

                # 辞書内に channels や guild_id による管理がある場合
                if isinstance(reishou_data, dict):
                    if "channels" in reishou_data:
                        return reishou_data.get("channels", [])
                    return reishou_data.get(guild_id, [])
                elif isinstance(reishou_data, list):
                    return reishou_data

        except Exception as e:
            logger.warning(
                f"冷笑チャンネル設定の取得中にエラーが発生しました: {e}"
            )

        return []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """💬 誰かがメッセージを送信したときに動くイベント"""
        # Bot自身の発言やDMでの発言は無視
        if message.author.bot or not message.guild or not message.channel:
            return

        # ⚙️ settings.py から冷笑削除の対象チャンネル設定を取得
        allowed_channels = await self.get_reishou_channels(message.guild.id)

        # チャンネルが設定されている場合、現在のチャンネルが対象リストになければスキップ
        if allowed_channels and (message.channel.id not in allowed_channels):
            return

        content = message.content.lower()

        # リストの中のNGワードをチェック
        for ng_word in self.ng_words:
            # 完全一致・前後スペース・単語境界など柔軟に検出する正規表現
            pattern = rf"(?:^|\s){re.escape(ng_word)}(?:$|\s)"

            # 単体で送られた場合、またはスペース区切りで送られた場合に削除
            if re.search(pattern, content) or content == ng_word:
                try:
                    # 1️⃣ 検知したメッセージを削除する
                    await message.delete()

                    # 2️⃣ 代わりのメッセージをチャンネルに送信する
                    await message.channel.send(
                        f"⚠️ 冷笑を検知し、**{message.author.display_name}** のメッセージを削除しました！"
                    )
                    return

                except discord.Forbidden:
                    logger.warning(
                        f"[{message.guild.name}] 権限が足りないため、メッセージを削除できませんでした。"
                    )
                except Exception as e:
                    logger.error(
                        f"冷笑削除処理中にエラーが発生しました: {e}"
                    )


# ⚙️ 両方のコグをBotに登録する
async def setup(bot: commands.Bot):
    await bot.add_cog(GreetingsCog(bot))
    await bot.add_cog(ModerationCog(bot))