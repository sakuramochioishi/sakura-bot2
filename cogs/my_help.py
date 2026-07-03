import discord
from discord import app_commands
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Botのコマンド一覧と使い方を表示します")
    async def help_command(self, interaction: discord.Interaction):
        # 💡 【重要】データベース処理の遅延対策として、まず3秒の返答制限を15分に引き伸ばす
        await interaction.response.defer()

        embed = discord.Embed(
            title="📚 sakura-bot2 コマンド一覧",
            description="このBotで利用可能なコマンドの一覧です。\n`/` から始まるコマンドは全員が使用できます。",
            color=discord.Color.blurple()
        )
        user_cmds = (
            "🎲 **/roulette**\n└ サーバー内の全メンバーからランダムに1人選んでメンションします。\n\n"
            "🔮 **/omikuji**\n└ 今日のおみくじを引いて運勢を占います。\n\n"
            "📝 **/quiz [問題] [正解]**\n└ 早押しクイズを出題します（お手付き・制限時間付き）。\n\n"
            "⏰ **/timer [分]**\n└ 指定した分数が経過した後にメンションで通知。\n\n"
            "🤡 **/koubun [言葉1] [言葉2]**\n└ ふたつの言葉からコウメ太夫のネタを生成します。"
        )
        embed.add_field(name="👥 利用可能な一般コマンド", value=user_cmds, inline=False)

        if interaction.permissions.administrator:
            admin_cmds = (
                "🔘 **/role_panel [タイトル] [説明] [役職1] [ラベル1]...**\n"
                "└ ボタンを押すだけで役職を自動で付け外しできるパネルを設置します。"
            )
            embed.add_field(name="🔒 管理者専用コマンド", value=admin_cmds, inline=False)

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user.avatar else None
        embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)
        
        # 💡 deferした後は send_message ではなく followup.send で送信する
        await interaction.followup.send(embed=embed)

    @commands.command(name="help")
    async def skr_help_command(self, ctx):
        embed = discord.Embed(
            title="👑 sakura-bot2 オーナー限定コマンド一覧 👑",
            description="Botの所有者（あなた）のみが実行できる、ダイレクトなテキスト管理コマンドです。",
            color=discord.Color.red()
        )
        secret_cmds = (
            "🧹 **!skr_clear [件数]**\n└ 指定した件数のチャットメッセージを一括削除。\n\n"
            "📢 **!skr_say [#チャンネル] [メッセージ]**\n└ 指定したチャンネルにBotとしてメッセージを代弁投稿。\n\n"
            "🎭 **!skr_status [テキスト]**\n└ Botのステータス（〜をプレイ中）を動的に変更。\n\n"
            "📶 **!skr_ping**\n└ Botの通信速度（レイテンシ）を確認。\n\n"
            "🌐 **!skr_servers**\n└ Botが現在参加しているサーバーの一覧とIDを確認。\n\n"
            "🔄 **!skr_restart**\n└ Botを安全に終了してプログラムを停止します。"
        )
        embed.add_field(name="🛠️ システム管理コマンド", value=secret_cmds, inline=False)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))