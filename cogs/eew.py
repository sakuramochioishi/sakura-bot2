import json
import asyncio
import re
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import websockets

WOLFX_EEW_WS = "wss://ws-api.wolfx.jp/jma_eew"

SCALE_MAP = {
    10: "震度1", 20: "震度2", 30: "震度3", 40: "震度4",
    45: "震度5弱", 50: "震度5強", 55: "震度6弱", 60: "震度6強", 70: "震度7"
}

def parse_shindo(shindo_str: str) -> float:
    if not shindo_str or shindo_str == "不明":
        return 0.0
    
    mapping = {
        "1": 1.0, "2": 2.0, "3": 3.0, "4": 4.0,
        "5-": 5.0, "5弱": 5.0, "5+": 5.5, "5強": 5.5,
        "6-": 6.0, "6弱": 6.0, "6+": 6.5, "6強": 6.5,
        "7": 7.0
    }
    
    clean_str = str(shindo_str).strip()
    if clean_str in mapping:
        return mapping[clean_str]
    
    match = re.search(r'\d+', clean_str)
    if match:
        return float(match.group())
    return 0.0


class EEWCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bg_task = None

    async def cog_load(self):
        self.bg_task = self.bot.loop.create_task(self.listen_eew())

    async def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()

    # ==========================================
    # 📡 リアルタイム緊急地震速報ループ
    # ==========================================
    async def listen_eew(self):
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                async with websockets.connect(WOLFX_EEW_WS) as ws:
                    print("[EEWCog] WebSocket 接続成功")
                    async for message in ws:
                        data = json.loads(message)
                        
                        if data.get("type") == "heartbeat" or "Shindo1" not in data:
                            continue
                        
                        max_shindo_raw = data.get("Shindo1", "0")
                        shindo_value = parse_shindo(max_shindo_raw)

                        # 震度4未満はスキップ
                        if shindo_value < 4.0:
                            continue

                        # setting.py から通知対象チャンネルを取得（"setting" または "SettingsCog" を検索）
                        settings_cog = self.bot.get_cog("setting") or self.bot.get_cog("SettingsCog")
                        if not settings_cog:
                            continue

                        target_channel_ids = settings_cog.get_all_eew_channel_ids()
                        if not target_channel_ids:
                            continue

                        hypocenter = data.get("Hypocenter", "不明")
                        mag = data.get("Magunitude", "不明")
                        is_warn = data.get("isWarn", False)

                        status = "🚨 **【緊急地震速報（警報）】**" if is_warn else "⚠️ **【緊急地震速報（予報）】**"
                        
                        embed = discord.Embed(
                            title=f"{status} (最大震度 {max_shindo_raw})",
                            description=f"**{hypocenter}** で地震が発生しました。",
                            color=discord.Color.red() if is_warn else discord.Color.gold()
                        )
                        embed.add_field(name="予想最大震度", value=str(max_shindo_raw), inline=True)
                        embed.add_field(name="マグニチュード", value=f"M{mag}" if mag != "不明" else "不明", inline=True)
                        embed.add_field(name="震源地", value=hypocenter, inline=False)
                        embed.set_footer(text="データ提供: Wolfx API")

                        for channel_id in target_channel_ids:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                try:
                                    await channel.send(embed=embed)
                                except Exception as send_error:
                                    print(f"[EEWCog] メッセージ送信失敗 ({channel_id}): {send_error}")

            except asyncio.CancelledError:
                print("[EEWCog] タスクが終了しました")
                break
            except Exception as e:
                print(f"[EEWCog] エラー発生: {e}. 5秒後に再接続します...")
                await asyncio.sleep(5)

    # ==========================================
    # 📜 /eew_history コマンド（直近の震度4以上・10件）
    # ==========================================
    @app_commands.command(
        name="eew_history",
        description="直近の最大震度4以上の地震履歴（10件）を取得します"
    )
    @app_commands.guild_only()
    async def eew_history(self, interaction: discord.Interaction):
        await interaction.response.defer()  # 取得待ちに対応

        url = "https://api.p2pquake.net/v2/history?codes=551&limit=100"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"User-Agent": "DiscordBot/1.0"}) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ 地震情報の取得に失敗しました。")
                        return

                    data = await resp.json()

            filtered_earthquakes = []
            for item in data:
                earthquake = item.get("earthquake", {})
                max_scale_num = earthquake.get("maxScale", 0)

                # 最大震度40以上（震度4以上）のみ抽出
                if max_scale_num >= 40:
                    filtered_earthquakes.append(item)
                    if len(filtered_earthquakes) >= 10:
                        break

            if not filtered_earthquakes:
                await interaction.followup.send("ℹ️ 直近で観測された震度4以上の地震はありません。")
                return

            embed = discord.Embed(
                title="🌋 直近の地震履歴（最大震度4以上）",
                description="直近で発生した最大震度4以上の地震情報（最大10件）です。",
                color=discord.Color.red()
            )

            for item in filtered_earthquakes:
                earthquake = item.get("earthquake", {})
                hypocenter = earthquake.get("hypocenter", {})

                place = hypocenter.get("name", "不明")
                time_str = earthquake.get("time", "不明")
                max_scale_num = earthquake.get("maxScale", -1)
                shindo_str = SCALE_MAP.get(max_scale_num, "不明")
                mag = hypocenter.get("magnitude", -1)
                mag_str = f"M{mag}" if mag != -1 else "不明"

                field_value = (
                    f"📍 **震源地:** {place}\n"
                    f"🕒 **日時:** {time_str}\n"
                    f"📊 **最大震度:** {shindo_str}\n"
                    f"🌐 **マグニチュード:** {mag_str}"
                )

                embed.add_field(
                    name=f"地震情報 - {time_str}",
                    value=field_value,
                    inline=False
                )

            embed.set_footer(text="データ提供: P2P地震情報 API")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(EEWCog(bot))