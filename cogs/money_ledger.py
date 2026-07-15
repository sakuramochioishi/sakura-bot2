from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands
import json
import os

class MoneyLedger(commands.GroupCog, name="money"):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "money_ledger.json"
        self.balances = self._load_data()
        # ★ 履歴を送信したいテキストチャンネルのID（数値）をここに貼り付けてください
        self.log_channel_id = 1510453677461082112
        self.my_discord_id = 1048754537051193364

    
    def _load_data(self):
        """JSONファイルからデータを読み込む(ファイルがない場合は新規作成)"""
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
            return {}
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def _save_data(self):
        """データをJSONファイルに書き出す"""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.balances, f, ensure_ascii=False, indent=4)

    def _get_user_balance(self, user_id_str):
        """ユーザーの残高を取得(未登録なら初期値を作成)"""
        if user_id_str not in self.balances:
            self.balances[user_id_str] = {"bank": 0, "paypay": 0, "wallet": 0}
            self._save_data()
        return self.balances[user_id_str]

    def _update_balance(self, user_id, bank_diff=0, paypay_diff=0, wallet_diff=0):
        """残高を更新して保存"""
        user_id_str = str(user_id)
        user_data = self._get_user_balance(user_id_str)

        user_data["bank"] += bank_diff
        user_data["paypay"] += paypay_diff
        user_data["wallet"] += wallet_diff

        self.balances[user_id_str] = user_data
        self._save_data()

    async def _send_log(self, user, action_title, description):
        """指定されたチャンネルに履歴を埋め込み(Embed)で送信する"""
        if user.id != self.my_discord_id:
            return
       
        channel = self.bot.get_channel(self.log_channel_id)
        if channel is None:
            # もしキャッシュになければAPIから取得を試みる
            try:
                channel = await self.bot.fetch_channel(self.log_channel_id)
            except Exception:
                print(f"❌ 履歴用チャンネル(ID: {self.log_channel_id}) が見つかりません。")
                return

        # 履歴用の埋め込み（Embed）を作成
        embed = discord.Embed(
            title=f"📝 残高変動履歴 - {action_title}",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        # 変動後の最新残高も一緒に載せる
        user_balance = self._get_user_balance(str(user.id))
        embed.add_field(name="🏦 Bank", value=f"{user_balance['bank']:,}円", inline=True)
        embed.add_field(name="📱 PayPay", value=f"{user_balance['paypay']:,}円", inline=True)
        embed.add_field(name="🪙 Wallet", value=f"{user_balance['wallet']:,}円", inline=True)
        
        await channel.send(embed=embed)

    # =========== スラッシュコマンド定義 =============

    @app_commands.command(name="show", description="現在のお小遣い帳の残高を表示します")
    async def show(self, interaction: discord.Interaction):
        user_balance = self._get_user_balance(str(interaction.user.id))

        embed = discord.Embed(
            title=f"👛 {interaction.user.display_name} のお小遣い帳",
            color=discord.Color.green()
        )
        embed.add_field(name="🏦 Bank(銀行)", value=f"{user_balance['bank']:,}円", inline=False)
        embed.add_field(name="📱 PayPay", value=f"{user_balance['paypay']:,}円", inline=False)
        embed.add_field(name="🪙 Wallet(財布)", value=f"{user_balance['wallet']:,}円", inline=False)

        total = sum(user_balance.values())
        embed.set_footer(text=f"合計総資産: {total:,}円")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bank", description="銀行の残高を操作します")
    @app_commands.choices(action=[
        app_commands.Choice(name="in(入金)", value="in"),
        app_commands.Choice(name="out(出金)", value="out")
    ])
    async def bank(self, interaction: discord.Interaction, action: app_commands.Choice[str], amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ 金額は1以上の数値を入力してください。", ephemeral=True)
            return
        
        if action.value == "in":
            self._update_balance(interaction.user.id, bank_diff=amount)
            await interaction.response.send_message(f"🏦 銀行に **{amount:,}円** 入金しました。", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "銀行入金", f"銀行に **{amount:,}円** 入金しました。")
        else:
            self._update_balance(interaction.user.id, bank_diff=-amount, wallet_diff=amount)
            await interaction.response.send_message(f"🏦 銀行から **{amount:,}円** 出金しました。(財布に自動的にお金が入りました)", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "銀行出金", f"銀行から **{amount:,}円** 出金しました。（財布へ移動）")

    @app_commands.command(name="paypay", description="PayPayの残高を操作します (inは銀行から自動的に引かれます)")
    @app_commands.choices(action=[    
        app_commands.Choice(name="in(チャージ)", value="in"),
        app_commands.Choice(name="out(支払う)", value="out")
    ])
    async def paypay(self, interaction: discord.Interaction, action: app_commands.Choice[str], amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ 金額は1以上の数値を入力してください。", ephemeral=True)
            return
         
        if action.value == "in":
            self._update_balance(interaction.user.id, bank_diff=-amount, paypay_diff=amount)
            await interaction.response.send_message(f"📱 PayPayに **{amount:,}円** チャージしました。(🏦 銀行から自動出金されました)", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "PayPayチャージ", f"PayPayに **{amount:,}円** チャージしました。（銀行から引き落とし）")
        else:
            self._update_balance(interaction.user.id, paypay_diff=-amount)
            await interaction.response.send_message(f"📱 PayPayから **{amount:,}円** 支払いました。", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "PayPay支払", f"PayPayで **{amount:,}円** 支払いました。")
    
    @app_commands.command(name="wallet", description="財布の残高を操作します (inは銀行から自動的に引かれます)")
    @app_commands.choices(action=[    
        app_commands.Choice(name="in(お金を入れる)", value="in"),
        app_commands.Choice(name="out(支払う)", value="out")
    ])
    async def wallet(self, interaction: discord.Interaction, action: app_commands.Choice[str], amount: int):
        if amount <= 0:
            await interaction.response.send_message("❌ 金額は1以上の数値を入力してください。", ephemeral=True)
            return
         
        if action.value == "in":
            self._update_balance(interaction.user.id, bank_diff=-amount, wallet_diff=amount)
            await interaction.response.send_message(f"🪙 財布に **{amount:,}円** お金を入れました。(🏦 銀行から自動出金されました)", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "財布へ入金", f"財布に **{amount:,}円** 入れました。（銀行から引き出し）")
        else:
            self._update_balance(interaction.user.id, wallet_diff=-amount)
            await interaction.response.send_message(f"🪙 財布から **{amount:,}円** 支払いました。", ephemeral=True)
            # ★ ログ送信を追加
            await self._send_log(interaction.user, "財布から支払", f"財布から **{amount:,}円** 支払いました。")

async def setup(bot: commands.Bot):
    await bot.add_cog(MoneyLedger(bot))