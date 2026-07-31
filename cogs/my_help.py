import discord
from discord import app_commands
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Botのコマンド一覧と使い方を表示します")
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📚 sakura-bot2 コマンド一覧",
            description="このBotで利用可能なコマンドの一覧です。\n`/` から始まるコマンドは全員が使用できます。",
            color=discord.Color.blurple()
        )

        user_cmds_list = []
        admin_cmds_list = []

        # 💡 bot.tree から登録されている全スラッシュコマンドをすべて自動取得
        for cmd in self.bot.tree.get_commands():
            if isinstance(cmd, app_commands.Command):
                cmd_name = f"**/{cmd.name}**"
                cmd_desc = cmd.description or "説明なし"

                # 管理者権限が設定されているかどうかで分類
                if cmd.default_permissions and cmd.default_permissions.administrator:
                    admin_cmds_list.append(f"🔘 {cmd_name}\n└ {cmd_desc}\n")
                else:
                    user_cmds_list.append(f"🔹 {cmd_name}\n└ {cmd_desc}\n")

            elif isinstance(cmd, app_commands.Group):
                for sub_cmd in cmd.commands:
                    cmd_name = f"**/{cmd.name} {sub_cmd.name}**"
                    cmd_desc = sub_cmd.description or "説明なし"
                    user_cmds_list.append(f"🔹 {cmd_name}\n└ {cmd_desc}\n")

        # 一般コマンドの追加
        if user_cmds_list:
            embed.add_field(
                name="👥 利用可能な一般コマンド",
                value="\n".join(user_cmds_list),
                inline=False
            )
        else:
            embed.add_field(name="👥 利用可能な一般コマンド", value="コマンドはありません", inline=False)

        # 実行者が管理者権限を持っている場合のみ表示
        if interaction.permissions.administrator and admin_cmds_list:
            embed.add_field(
                name="🔒 管理者専用コマンド",
                value="\n".join(admin_cmds_list),
                inline=False
            )

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @commands.command(name="skr_help")
    @commands.is_owner()
    async def skr_help_command(self, ctx):
        embed = discord.Embed(
            title="👑 sakura-bot2 オーナー限定コマンド一覧 👑",
            description="Botの所有者（あなた）のみが実行できる、ダイレクトなテキスト管理コマンドです。",
            color=discord.Color.red()
        )
        
        owner_cmds_list = []

        # 💡 bot.commands から登録されているテキスト（Prefix）コマンドをスキップせず全て自動取得
        for cmd in self.bot.commands:
            prefix = ctx.clean_prefix  # 設定中のプレフィックス（! など）
            cmd_name = f"⚡ **{prefix}{cmd.name}**"
            
            # コマンドの help 引数、または関数の Docstring ("""〜""") から説明を取得
            cmd_desc = cmd.help or (cmd.callback.__doc__.strip() if cmd.callback.__doc__ else "説明文が設定されていません。")
            
            owner_cmds_list.append(f"{cmd_name}\n└ {cmd_desc}\n")

        # 取得したコマンド一覧を Embed に追加
        if owner_cmds_list:
            embed.add_field(
                name="🛠️ システム管理コマンド",
                value="\n".join(owner_cmds_list),
                inline=False
            )
        else:
            embed.add_field(name="🛠️ システム管理コマンド", value="利用可能なコマンドがありません。", inline=False)

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)

        # 送信元メッセージの削除を行わず、そのまま全員（※オーナーのみ実行可能）に見える形で送信
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))