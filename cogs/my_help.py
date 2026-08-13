import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

class HelpPaginator(View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=180)  # 3分でボタンが無効化されます
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        # 最初のページなら「前へ」を無効化
        self.prev_button.disabled = self.current_page == 0
        # 最後のページなら「次へ」を無効化
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
        # ページ番号の表示を更新
        self.page_counter.label = f"{self.current_page + 1} / {len(self.embeds)}"

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.blurple)
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_counter(self, interaction: discord.Interaction, button: Button):
        pass

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Botのコマンド一覧と使い方を表示します")
    async def help_command(self, interaction: discord.Interaction):
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

        # 1024文字オーバーを防ぐためのチャンク（分割）関数
        def create_chunks(commands_list):
            chunks = []
            current_chunk = []
            current_length = 0

            for cmd_str in commands_list:
                if current_length + len(cmd_str) + 1 > 900:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [cmd_str]
                    current_length = len(cmd_str)
                else:
                    current_chunk.append(cmd_str)
                    current_length += len(cmd_str) + 1
            
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            return chunks

        user_chunks = create_chunks(user_cmds_list) if user_cmds_list else ["コマンドはありません"]
        admin_chunks = create_chunks(admin_cmds_list) if (interaction.permissions.administrator and admin_cmds_list) else []

        embeds = []
        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None

        # 一般コマンドのページを作成
        for i, chunk in enumerate(user_chunks):
            embed = discord.Embed(
                title="📚 sakura-bot2 コマンド一覧",
                description=f"このBotで利用可能なコマンドの一覧です。\n`/` から始まるコマンドは全員が使用できます。",
                color=discord.Color.blurple()
            )
            embed.add_field(name="👥 利用可能な一般コマンド", value=chunk, inline=False)
            embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)
            embeds.append(embed)

        # 管理者コマンドがある場合は専用ページを追加
        if interaction.permissions.administrator and admin_chunks:
            for i, chunk in enumerate(admin_chunks):
                embed = discord.Embed(
                    title="📚 sakura-bot2 管理者コマンド一覧",
                    description="管理者権限を持つユーザーのみ実行できるコマンドです。",
                    color=discord.Color.orange()
                )
                embed.add_field(name="🔒 管理者専用コマンド", value=chunk, inline=False)
                embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)
                embeds.append(embed)

        if not embeds:
            embed = discord.Embed(
                title="📚 sakura-bot2 コマンド一覧",
                description="表示できるコマンドがありません。",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="SAKURA-BOT System", icon_url=bot_avatar)
            embeds.append(embed)

        view = HelpPaginator(embeds)
        message = await interaction.response.send_message(embed=embeds[0], view=view)
        view.message = message


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