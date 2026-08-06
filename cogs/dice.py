from collections import defaultdict
import random
import re
import discord
from discord import app_commands
from discord.ext import commands


class Dice(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.enabled_guilds = defaultdict(lambda: False)

    @app_commands.command(name="roll", description="このサーバーのダイス機能の有効/無効を切り替えます")
    @app_commands.describe(status="有効にするか無効にするかを選択してください")
    @app_commands.choices(status=[
        app_commands.Choice(name="有効", value="enable"),
        app_commands.Choice(name="無効", value="disable"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def roll_setting(self, interaction: discord.Interaction, status: str):
        guild_id = interaction.guild_id

        if status == "enable":
            self.enabled_guilds[guild_id] = True
            await interaction.response.send_message("✅ このサーバーでダイス機能を**有効**にしました", ephemeral=True)
        else:
            self.enabled_guilds[guild_id] = False
            await interaction.response.send_message("❌ このサーバーでダイス機能を**無効**にしました", ephemeral=True)

    @roll_setting.error
    async def roll_setting_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ このコマンドを実行するには**サーバー管理者**の権限が必要です。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if not self.enabled_guilds[message.guild.id]:
            return
            
        match = re.search(r"\b(\d+)d(\d+)\b", message.content.lower())
        if not match:
            return

        count = int(match.group(1))
        sides = int(match.group(2))
        dice_str = f"{count}d{sides}"

        if count <= 0 or sides <= 0 or count > 100 or sides > 100000:
            return
        
        results = [random.randint(1, sides) for _ in range(count)]
        total = sum(results)

        # 画像のようなシンプル表示用のテキストを作成
        if count > 1:
            results_str = ", ".join(map(str, results))
            if len(results_str) > 1900:
                results_str = " (出目が多すぎるため省略されました) "
            content_str = f"{dice_str}\n[{results_str}] > {total}"
        else:
            content_str = f"{dice_str}\n[{results[0]}] > {total}"

        await message.reply(content_str, mention_author=False)


async def setup(bot):
    await bot.add_cog(Dice(bot))