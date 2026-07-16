import discord
from discord.ext import commands
from discord import app_commands
import random
import traceback

HANDS = {"rock": "✊", "scissors": "✌️", "paper": "🖐️"}
HAND_NAMES = {"rock": "グー", "scissors": "チョキ", "paper": "パー"}

class JankenView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, is_bot: bool, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.opponent = opponent
        self.is_bot = is_bot
        
        self.choices = {challenger.id: None, opponent.id: None}
        if is_bot:
            self.choices[opponent.id] = random.choice(list(HANDS.keys()))

    @discord.ui.button(label="✊ グー", style=discord.ButtonStyle.primary, custom_id="rock")
    async def rock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "rock")

    @discord.ui.button(label="✌️ チョキ", style=discord.ButtonStyle.success, custom_id="scissors")
    async def scissors_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "scissors")

    @discord.ui.button(label="🖐️ パー", style=discord.ButtonStyle.danger, custom_id="paper")
    async def paper_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "paper")

    async def process_choice(self, interaction: discord.Interaction, hand: str):
        try:
            user = interaction.user

            if user.id not in self.choices:
                await interaction.response.send_message("❌ あなたはこの対戦のプレイヤーではありません！", ephemeral=True)
                return

            if self.choices[user.id] is not None:
                await interaction.response.send_message("❌ 既に手を選んでいます！", ephemeral=True)
                return

            self.choices[user.id] = hand

            if None in self.choices.values():
                await interaction.response.send_message(f"選択完了！相手が選ぶのを待っています...", ephemeral=True)
                return

            await self.judge(interaction)
            
        except Exception as e:
            traceback.print_exc()

    async def judge(self, interaction: discord.Interaction):
        try:
            p1_hand = self.choices[self.challenger.id]
            p2_hand = self.choices[self.opponent.id]

            p1_emoji = HANDS[p1_hand]
            p2_emoji = HANDS[p2_hand]

            embed = discord.Embed(title="じゃんけん ポン！", color=discord.Color.blue())
            embed.add_field(name=f"{self.challenger.display_name} (あなた)", value=f"{p1_emoji} {HAND_NAMES[p1_hand]}", inline=True)
            embed.add_field(name=f"{self.opponent.display_name}", value=f"{p2_emoji} {HAND_NAMES[p2_hand]}", inline=True)

            # ── あいこの判定 ──
            if p1_hand == p2_hand:
                embed.description = "🤔 **「あいこでしょ！」**\n\n引き分けです！勝負を続ける場合は、もう一度 `/janken` コマンドを実行してください！"
                embed.color = discord.Color.orange()
                
                if not interaction.response.is_done():
                    await interaction.response.edit_message(content="引き分け！", embed=embed, view=None)
                else:
                    await interaction.message.edit(content="引き分け！", embed=embed, view=None)
                self.stop()
                return

            # ── 勝敗判定 ──
            win_conditions = [("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")]
            if (p1_hand, p2_hand) in win_conditions:
                winner = self.challenger
                embed.color = discord.Color.green()
            else:
                winner = self.opponent
                embed.color = discord.Color.red()

            embed.description = f"🎉 **勝者: {winner.mention} !!**"
            
            # 🧼 データベースへの記録処理（db_manager）を完全に消去しました
            
            if not interaction.response.is_done():
                await interaction.response.edit_message(content="対戦終了！", embed=embed, view=None)
            else:
                await interaction.message.edit(content="対戦終了！", embed=embed, view=None)
                
            self.stop()
            
        except Exception as e:
            traceback.print_exc()


class JankenCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="janken", description="サーバーの誰か、またはBotとじゃんけん対決をします！")
    @app_commands.describe(相手="対戦したいメンバーを選んでね（選ばないとBotと対戦になります）")
    async def janken(self, interaction: discord.Interaction, 相手: discord.Member = None):
        try:
            challenger = interaction.user
            
            if 相手 is not None and 相手.bot and 相手.id != self.bot.user.id:
                await interaction.response.send_message("❌ 他のbotとじゃんけんすることはできません!", ephemeral=True)
                return
            
            if 相手 is None or 相手.id == self.bot.user.id:
                opponent = self.bot.user
                is_bot = True
            elif 相手.id == challenger.id:
                await interaction.response.send_message("❌ 自分自身とじゃんけんはできません！", ephemeral=True)
                return
            else:
                opponent = 相手
                is_bot = False

            embed = discord.Embed(
                title="⚔️ じゃんけん勝負勃発！",
                description=f"{challenger.mention} **vs** {opponent.mention}\n下のボタンを押して手を選んでください!",
                color=discord.Color.blurple()
            )
            
            view = JankenView(challenger, opponent, is_bot)
            await interaction.response.send_message(content=f"{challenger.mention} vs {opponent.mention}", embed=embed, view=view)
            
        except Exception as e:
            traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(JankenCog(bot))
    await bot.tree.sync()   