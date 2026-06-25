import os
import discord
from discord.ext import commands, tasks
import urllib.request
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import websockets
import json
import os
from urllib.parse import urlparse, parse_qs
import db_manager
import asyncio

# 🌟 db_manager をインポート
import db_manager

load_dotenv()

# 📡 接続中のあなたのダッシュボードを管理するセット
connected_clients = set()

async def ws_handler(websocket):
    """WebSocketの接続要求を処理する関数"""
    query = parse_qs(urlparse(websocket.path).query)
    token = query.get("token", [None])[0]

    if token != os.getenv("DASHBOARD_SECRET_TOKEN"):
        await websocket.close(code=4003)
        return

    connected_clients.add(websocket)
    print(f"📡 聡人さんのダッシュボードが接続しました！ ({websocket.remote_address})")

    try:
        g_count, u_count = db_manager.get_bot_counts()
        labels, counts = db_manager.get_command_stats()
        
        init_payload = {
            "type": "init",
            "guild_count": g_count,
            "user_count": u_count,
            "chart_labels": labels,
            "chart_data": counts,
            "logs": db_manager.get_recent_logs_list(20)
        }
        await websocket.send(json.dumps(init_payload, ensure_ascii=False))

        async for message in websocket:
            pass
            
    except websockets.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        print("🔌 ダッシュボードが切断されました")

class TasksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_video_id = None
        self.last_tweet_url = None
        self.bot.loop.create_task(self.start_ws_server())
        
        # ⏰ YouTubeとXの通知タスクだけをスタート（Pingタスクは削除！）
        self.check_youtube_update.start()
        self.check_x_update.start()

    def cog_unload(self):
        self.check_youtube_update.cancel()
        self.check_x_update.cancel()

    @commands.Cog.listener()
    async def on_app_command_completion(self, INTERACTION: discord.Interaction, command: discord.app_commands.Command):
        """📊 コマンド完了時の処理を非同期タスクとして裏で安全に実行する（3秒制限を回避）"""
        
        async def background_logging():
            cmd_name = command.name
            # db_managerに登録されている名前（help, skr_help）以外はその他にする
            if cmd_name not in ['help', 'skr_help']:
                db_manager.increment_command('other')
            else:
                db_manager.increment_command(cmd_name)
                
            db_manager.add_log(f"💻 コマンド実行: /{cmd_name} (ユーザー: {INTERACTION.user.name})")

        # 💡 Discordへの返答を邪魔しないように、ログ書き込み処理を別ルート（バックグラウンド）に放り投げる
        self.bot.loop.create_task(background_logging())
        
    @tasks.loop(seconds=300)
    async def check_youtube_update(self):
        """📺 YouTubeの新着動画チェック"""
        await self.bot.wait_until_ready()
        
        notify_channel = os.getenv("cid12")
        yt_channel_id = os.getenv("youtubeid")
        
        if not notify_channel or not yt_channel_id:
            return
        channel = self.bot.get_channel(int(notify_channel))
        if not channel:
            return
            
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_channel_id}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            ns = {'ns': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
            entry = root.find('ns:entry', ns)
            if entry is None:
                return
            video_id = entry.find('yt:videoId', ns).text
            video_title = entry.find('ns:title', ns).text
            video_url = entry.find('ns:link', ns).attrib['href']
            
            if self.last_video_id is None:
                self.last_video_id = video_id
                print(f"📺 YouTube初期化: 現在の最新動画は「{video_title}」です。")
                db_manager.add_log(f"📺 YouTube連携システムを初期化（最新動画: {video_title[:15]}...）")
                db_manager.increment_command('youtube_check') # カウントも増やす
                return
                
            if video_id != self.last_video_id:
                self.last_video_id = video_id
                await channel.send(f"🌟 **YouTube 新着動画通知** 🌟\nチャンネルに新しい動画が投稿されました！\n\n🎥 **{video_title}**\n🔗 {video_url}")
                
                db_manager.add_log(f"🔔 【YouTube】新着動画を通知しました: {video_title[:20]}...")
                print(f"📺 新着動画を通知しました: {video_title}")
        except Exception as e:
            print(f"⚠️ YouTubeチェック中にエラーが発生しました: {e}")

    @tasks.loop(seconds=60)
    async def check_x_update(self):
        """🐦 X（旧Twitter）の新着ポストチェック"""
        await self.bot.wait_until_ready()
        
        x_notify_channel = os.getenv("chid1")
        x_rss_url = os.getenv("xid")
        
        if not x_notify_channel or not x_rss_url:
            return
        channel = self.bot.get_channel(int(x_notify_channel))
        if not channel:
            return
            
        try:
            req = urllib.request.Request(x_rss_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            item = root.find('.//item')
            if item is None:
                return
            tweet_title = item.find('title').text
            tweet_url = item.find('link').text
            
            if self.last_tweet_url is None:
                self.last_tweet_url = tweet_url
                print(f"🐦 X初期化: 現在の最新ポストは「{tweet_title[:15]}...」です。")
                db_manager.add_log(f"🐦 X(Twitter)連携システムを初期化しました")
                db_manager.increment_command('x_check') # カウントも増やす
                return
                
            if tweet_url != self.last_tweet_url:
                self.last_tweet_url = tweet_url
                await channel.send(f"📢 **X（旧Twitter）新着ポスト通知** 📢\nアカウントが新しくポストしました！\n\n📝 **内容:**\n{tweet_title}\n\n🔗 **リンク:** {tweet_url}")
                
                db_manager.add_log(f"🔔 【X】新着ポストを通知しました")
                print(f"🐦 新着ポストを通知しました: {tweet_title[:15]}...")
        except Exception as e:
            print(f"⚠️ Xチェック中にエラーが発生しました: {e}")
    async def start_ws_server(self):
        """Ubuntu Serverのポート8080でWebSocket待ち受けを開始"""
        async with websockets.serve(ws_handler, "127.0.0.1", 7001):
            await asyncio.Future()

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: discord.app_commands.Command):
        """📊 スラッシュコマンドが正常に完了したときに動くトリガー"""
        cmd_name = command.name
        log_msg = f"💻 コマンド実行: /{cmd_name} (ユーザー: {interaction.user.name})"
        
        # 1️⃣ 友人のUbuntu側のSQLiteに保存
        if cmd_name not in ['help', 'skr_help', 'youtube_check', 'x_check']:
            db_manager.increment_command('other')
        else:
            db_manager.increment_command(cmd_name)
        db_manager.add_log(log_msg)

        # 2️⃣ 今まさに画面を開いている聡人さんのダッシュボードへリアルタイムで速達
        if connected_clients:
            g_count = len(self.bot.guilds)
            u_count = sum(g.member_count for g in self.bot.guilds if g.member_count)
            labels, counts = db_manager.get_command_stats()
            
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            update_payload = {
                "type": "update",
                "log": f"[{now_str}] {log_msg}",
                "guild_count": g_count,
                "user_count": u_count,
                "chart_labels": labels,
                "chart_data": counts
            }
            await asyncio.gather(*[client.send(json.dumps(update_payload, ensure_ascii=False)) for client in connected_clients])



async def setup(bot: commands.Bot):
    await bot.add_cog(TasksCog(bot))