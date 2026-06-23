import os
import discord
from discord.ext import commands, tasks
import urllib.request
import xml.etree.ElementTree as ET

class TasksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_video_id = None
        self.last_tweet_url = None
        self.check_youtube_update.start()
        self.check_x_update.start()

    def cog_unload(self):
        self.check_youtube_update.cancel()
        self.check_x_update.cancel()

    @tasks.loop(seconds=300)
    async def check_youtube_update(self):
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
                return
            if video_id != self.last_video_id:
                self.last_video_id = video_id
                await channel.send(f"🌟 **YouTube 新着動画通知** 🌟\nチャンネルに新しい動画が投稿されました！\n\n🎥 **{video_title}**\n🔗 {video_url}")
                print(f"📺 新着動画を通知しました: {video_title}")
        except Exception as e:
            print(f"⚠️ YouTubeチェック中にエラーが発生しました: {e}")

    @tasks.loop(seconds=60)
    async def check_x_update(self):
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
                return
            if tweet_url != self.last_tweet_url:
                self.last_tweet_url = tweet_url
                await channel.send(f"📢 **X（旧Twitter）新着ポスト通知** 📢\nアカウントが新しくポストしました！\n\n📝 **内容:**\n{tweet_title}\n\n🔗 **リンク:** {tweet_url}")
                print(f"🐦 新着ポストを通知しました: {tweet_title[:15]}...")
        except Exception as e:
            print(f"⚠️ Xチェック中にエラーが発生しました: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(TasksCog(bot))