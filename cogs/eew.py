import asyncio
import json
import logging
import re
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import websockets

logger = logging.getLogger(__name__)

WOLFX_EEW_WS = "wss://ws-api.wolfx.jp/jma_eew"

SCALE_MAP = {
    10: "震度1",
    20: "震度2",
    30: "震度3",
    40: "震度4",
    45: "震度5弱",
    50: "震度5強",
    55: "震度6弱",
    60: "震度6強",
    70: "震度7",
}


def parse_shindo(shindo_str: str) -> float:
    """震度文字列（"5弱", "5-", "6+", 60 等）を float の値に変換"""
    if not shindo_str or str(shindo_str) in ["不明", "0", "None"]:
        return 0.0

    mapping = {
        "1": 1.0,
        "2": 2.0,
        "3": 3.0,
        "4": 4.0,
        "5-": 5.0,
        "5弱": 5.0,
        "5+": 5.5,
        "5強": 5.5,
        "6-": 6.0,
        "6弱": 6.0,
        "6+": 6.5,
        "6強": 6.5,
        "7": 7.0,
    }

    clean_str = str(shindo_str).strip()
    if clean_str in mapping:
        return mapping[clean_str]

    # 数値形式（P2P等の 10, 20... 80）や直接の数字抽出
    match = re.search(r"\d+", clean_str)
    if match:
        val = float(match.group())
        if val >= 10:
            return val / 10.0
        return val
    return 0.0


class EEWCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bg_task: asyncio.Task | None = None
        # 重複防止用の状態管理 {EventID: last_serial_number}
        self.processed_events: dict[str, int] = {}

    async def cog_load(self):
        # バックグラウンドタスク開始
        self.bg_task = self.bot.loop.create_task(self.listen_eew())

    async def cog_unload(self):
        if self.bg_task:
            self.bg_task.cancel()

    # ==========================================
    # 🗄️ SettingsCog から通知先チャンネルを取得
    # ==========================================
    async def get_all_eew_targets(self) -> list[int]:
        """SettingsCog 経由で全サーバーの EEW 通知先 channel_id を取得"""
        settings_cog = self.bot.get_cog("SettingsCog")
        if not settings_cog:
            logger.warning("[EEWCog] SettingsCog がロードされていません。")
            return []

        # SettingsCog 側で定義した取得メソッドを呼び出し
        if hasattr(settings_cog, "get_all_eew_targets"):
            return await settings_cog.get_all_eew_targets()
        
        logger.warning("[EEWCog] SettingsCog に get_all_eew_targets メソッドが見つかりません。")
        return []

    # ==========================================
    # 📡 リアルタイム緊急地震速報ループ
    # ==========================================
    async def listen_eew(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                async with websockets.connect(
                    WOLFX_EEW_WS, ping_interval=20, ping_timeout=10
                ) as ws:
                    logger.info("[EEWCog] WebSocket 接続成功")
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        # 心拍(heartbeat)ログまたは判定不可能なデータのスキップ
                        msg_type = data.get("type")
                        if msg_type in ["heartbeat", "ping"]:
                            continue

                        # Cancel 報の判定
                        if (
                            data.get("isCancel")
                            or data.get("Title") == "緊急地震速報（キャンセル）"
                        ):
                            continue

                        # Wolfx APIの震度取得
                        max_shindo_raw = (
                            data.get("max_intensity")
                            or data.get("Shindo1")
                            or "0"
                        )
                        shindo_value = parse_shindo(max_shindo_raw)

                        # 震度4未満はスキップ
                        # ※テストで今すぐ確認したい場合は一時的に 1.0 などに下げてください
                        if shindo_value < 4.0:
                            continue

                        # 重複通知防止チェック（同じEventIDで同じ電文番号であればスキップ）
                        event_id = str(
                            data.get("EventID")
                            or data.get("EventID_Raw")
                            or ""
                        )
                        serial_num = int(data.get("Serial", 0))

                        if event_id:
                            if (
                                self.processed_events.get(event_id)
                                == serial_num
                            ):
                                continue
                            self.processed_events[event_id] = serial_num

                            # メモリリーク防止（履歴が100件を超えたら古いものを削除）
                            if len(self.processed_events) > 100:
                                self.processed_events.pop(
                                    next(iter(self.processed_events))
                                )

                        # SettingsCog 経由で通知対象チャンネルIDのリストを取得
                        target_channels = await self.get_all_eew_targets()
                        
                        # 💡 チャンネルが正しく取得できているかログで確認できるように追加
                        logger.info(f"[EEWCog] 取得した通知先チャンネル一覧: {target_channels}")

                        if not target_channels:
                            logger.info("[EEWCog] 通知先チャンネルが設定されていないためスキップします。")
                            continue

                        # 情報の抽出
                        hypocenter = data.get("Hypocenter") or data.get(
                            "Title", "不明"
                        )
                        mag = data.get("Magunitude") or data.get(
                            "Magnitude", "不明"
                        )
                        is_warn = data.get("isWarn", False) or data.get(
                            "is_warn", False
                        )
                        is_final = data.get("isFinal", False)

                        title_type = (
                            "🚨 **【緊急地震速報（警報）】**"
                            if is_warn
                            else "⚠️ **【緊急地震速報（予報）】**"
                        )
                        if is_final:
                            title_type += " (最終報)"

                        embed = discord.Embed(
                            title=f"{title_type} (最大震度 {max_shindo_raw})",
                            description=f"**{hypocenter}** 付近で地震が発生しました。",
                            color=(
                                discord.Color.red()
                                if is_warn
                                else discord.Color.gold()
                            ),
                        )
                        embed.add_field(
                            name="予想最大震度",
                            value=str(max_shindo_raw),
                            inline=True,
                        )
                        embed.add_field(
                            name="マグニチュード",
                            value=f"M{mag}" if str(mag) != "不明" else "不明",
                            inline=True,
                        )
                        embed.add_field(
                            name="震源地",
                            value=str(hypocenter),
                            inline=False,
                        )

                        if serial_num:
                            embed.set_footer(
                                text=f"第 {serial_num} 報 | データ提供: Wolfx API"
                            )
                        else:
                            embed.set_footer(text="データ提供: Wolfx API")

                        # 取得した全チャンネルに送信
                        for channel_id in target_channels:
                            channel = self.bot.get_channel(int(channel_id))
                            if channel and isinstance(
                                channel, discord.TextChannel
                            ):
                                try:
                                    await channel.send(embed=embed)
                                    logger.info(f"[EEWCog] チャンネル {channel_id} に地震速報を送信しました。")
                                except discord.Forbidden:
                                    logger.warning(
                                        f"[EEWCog] チャンネル {channel_id} への送信権限がありません。"
                                    )
                                except Exception as send_error:
                                    logger.error(
                                        f"[EEWCog] メッセージ送信失敗 ({channel_id}): {send_error}"
                                    )

            except asyncio.CancelledError:
                logger.info("[EEWCog] WebSocket タスクが終了しました")
                break
            except Exception as e:
                logger.error(
                    f"[EEWCog] WebSocketエラー発生: {e}. 5秒後に再接続します..."
                )
                await asyncio.sleep(5)

    # ==========================================
    # 📜 /eew_history コマンド（直近の震度4以上・10件）
    # ==========================================
    @app_commands.command(
        name="eew_history",
        description="直近の最大震度4以上の地震履歴（10件）を取得します",
    )
    @app_commands.guild_only()
    async def eew_history(self, interaction: discord.Interaction):
        await interaction.response.defer()

        url = "https://api.p2pquake.net/v2/history?codes=551&limit=100"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers={"User-Agent": "DiscordBot/1.0"}
                ) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            "❌ 地震情報の取得に失敗しました。"
                        )
                        return

                    data = await resp.json()

            filtered_earthquakes = []
            for item in data:
                earthquake = item.get("earthquake", {})
                max_scale_num = earthquake.get("maxScale", 0)

                if max_scale_num >= 40:
                    filtered_earthquakes.append(item)
                    if len(filtered_earthquakes) >= 10:
                        break

            if not filtered_earthquakes:
                await interaction.followup.send(
                    "ℹ️ 直近で観測された震度4以上の地震はありません。"
                )
                return

            embed = discord.Embed(
                title="🌋 直近の地震履歴（最大震度4以上）",
                description="直近で発生した最大震度4以上の地震情報（最大10件）です。",
                color=discord.Color.red(),
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
                    inline=False,
                )

            embed.set_footer(text="データ提供: P2P地震情報 API")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"⚠️ エラーが発生しました: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(EEWCog(bot))