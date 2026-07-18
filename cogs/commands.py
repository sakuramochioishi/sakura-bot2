import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import time
import sys
import json
import os
from typing import List, Tuple, Optional

# 設定を保存するJSONファイルのパス
CONFIG_FILE = "role_panels.json"

def load_panels() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"設定の読み込み中にエラーが発生しました: {e}")
        return {}

def save_panel(channel_id: int, message_id: int, role_settings: List[dict]):
    panels = load_panels()
    panels[str(message_id)] = {
        "channel_id": channel_id,
        "roles": role_settings  # [{"id": 123, "name": "ロール名"}, ...] の形式で保存
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(panels, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"設定の保存中にエラーが発生しました: {e}")

class RolePanelView(discord.ui.View):
    def __init__(self, role_settings: List[dict]):
        super().__init__(timeout=None)
        
        for index, role_info in enumerate(role_settings):
            if index >= 6:
                break
                
            role_id = role_info["id"]
            role_name = role_info["name"]
            
            # 永続化（再起動対策）のため、custom_id に一意のロールIDを含めます
            custom_id = f"persistent_role_toggle:{role_id}"
            
            # ロール名をそのままボタンのラベル（表示名）にします
            button = discord.ui.Button(
                label=role_name, 
                style=discord.ButtonStyle.primary, 
                custom_id=custom_id
            )
            button.callback = self.make_callback(role_id)
            self.add_item(button)

    def make_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction):
            guild = interaction.guild
            if not guild: return
            
            role = guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("⚠️ 設定されたロールが見つかりませんでした。", ephemeral=True)
                return
                
            member = interaction.user
            if role in member.roles:
                await member.remove_roles(role)
                await interaction.response.send_message(f"✅ {role.mention} を外しました。", ephemeral=True)
            else:
                await member.add_roles(role)
                await interaction.response.send_message(f"✅ {role.mention} を付与しました！", ephemeral=True)
        return callback

class RoleBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # ロール操作に必須
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # 過去のView（ボタン）の復活処理
        panels = load_panels()
        print(f"【永続化】{len(panels)}件のロールパネル設定を読み込んでいます...")
        for message_id, data in panels.items():
            self.add_view(RolePanelView(data["roles"]))

bot = RoleBot()

@bot.event
async def on_ready():
    print(f"ログイン完了: {bot.user.name}")
    try:
        # スラッシュコマンドを強制同期
        synced = await bot.tree.sync()
        print(f"【同期完了】{len(synced)} 個のスラッシュコマンドを同期しました！")
    except Exception as e:
        print(f"コマンドの同期中にエラーが発生しました: {e}")

# コマンド名を「/role_panel」に変更
@bot.tree.command(name="role_panel", description="カスタムロール付与パネルを設置します（最大6個）")
@app_commands.describe(
    role1="1つ目のロール",
    role2="2つ目のロール（任意）",
    role3="3つ目のロール（任意）",
    role4="4つ目のロール（任意）",
    role5="5つ目のロール（任意）",
    role6="6つ目のロール（任意）",
)
async def role_panel(
    interaction: discord.Interaction,
    role1: discord.Role,
    role2: Optional[discord.Role] = None,
    role3: Optional[discord.Role] = None,
    role4: Optional[discord.Role] = None,
    role5: Optional[discord.Role] = None,
    role6: Optional[discord.Role] = None,
):
    # 権限チェック
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("❌ このコマンドを実行するには「ロールの管理」権限が必要です。", ephemeral=True)
        return

    raw_roles = [role1, role2, role3, role4, role5, role6]
    role_settings: List[dict] = []
    
    # 選択されたロールから、IDと名前を抽出してリスト化
    for r in raw_roles:
        if r is not None:
            role_settings.append({"id": r.id, "name": r.name})

    # 一度応答を保留
    await interaction.response.defer(ephemeral=True)
    
    channel = interaction.channel
    if not channel:
        await interaction.followup.send("❌ チャンネルの取得に失敗しました。", ephemeral=True)
        return

    # パネルを送信（Viewを適用）
    view = RolePanelView(role_settings)
    panel_message = await channel.send(content="以下のボタンを押すと、対応するロールを付け外しできます！", view=view)

    # JSONファイルに保存
    save_panel(channel_id=channel.id, message_id=panel_message.id, role_settings=role_settings)
    await interaction.followup.send(f"✅ ロールパネルを設置し、設定を `{CONFIG_FILE}` に保存しました！", ephemeral=True)


# --- ルーレット用のView ---
class MemberRouletteView(discord.ui.View):
    def __init__(self, target_members):
        super().__init__(timeout=60)
        self.target_members = target_members

    @discord.ui.button(label="もう一度引く 🔁", style=discord.ButtonStyle.green)
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🎰 **サーバーメンバー全員から選出中... ドラムロールスタート！**", embed=None)
        await asyncio.sleep(2.0)
        chosen_member = random.choice(self.target_members)
        embed = discord.Embed(
            title="🎯 ルーレット結果",
            description=f"選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=self)


# --- メインのCogクラス ---
class CommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- エラーハンドリング (テキストコマンド用) ---
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ このコマンドを実行する権限がありません。", delete_after=5)
        elif isinstance(error, commands.NotOwner):
            await ctx.send("❌ このコマンドはBot開発者のみ実行可能です。", delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ 引数が不足しています。使用方法を確認してください。", delete_after=5)

    # --- スラッシュコマンド (一般向け) ---

    @app_commands.command(name="omikuji", description="今日のおみくじを引きます")
    async def omikuji(self, interaction: discord.Interaction):
        fortunes = ["大吉 🌟", "吉 🎯", "中吉 😊", "小吉 👍", "末吉 🌿", "凶 👻", "半吉", "元凶", "大凶", "半凶", "大狂", "狂"]
        result = random.choice(fortunes)
        await interaction.response.send_message(f"{interaction.user.mention} さんの今日の運勢は... **{result}** です！")

    @app_commands.command(name="timer", description="指定した分数後にメンションで通知します（最大180分）")
    @app_commands.describe(minutes="タイマーの分数 (1〜180分)")
    async def timer(self, interaction: discord.Interaction, minutes: int):
        if minutes < 1 or minutes > 180:
            await interaction.response.send_message("❌ 1分から180分（3時間）の間で指定してください。", ephemeral=True)
            return
        await interaction.response.send_message(f"🔔 {minutes}分間のタイマーを開始しました。時間が来たらお知らせします！")
        await asyncio.sleep(minutes * 60)
        await interaction.channel.send(f"⏰ {interaction.user.mention} さん、{minutes}分が経過しました！")

    @app_commands.command(name="roulette", description="サーバー内の全メンバーからランダムに1人選んでメンションします")
    async def roulette(self, interaction: discord.Interaction):
        guild = interaction.guild
        candidates = [m for m in guild.members if not m.bot]
        if not candidates:
            await interaction.response.send_message("❌ 抽選対象となるメンバーが見つかりませんでした。", ephemeral=True)
            return
        await interaction.response.send_message(f"🎰 **全サーバーメンバーから選出中... ドラムロールスタート！**")
        await asyncio.sleep(2.0)
        chosen_member = random.choice(candidates)
        embed = discord.Embed(title="🎯 ルーレット結果", description=f"対象: 全サーバーメンバー ({len(candidates)}人)\n\n選ばれたのは... 🎉 {chosen_member.mention} 🎉 です！", color=discord.Color.red())
        view = MemberRouletteView(candidates)
        await interaction.edit_original_response(content=f"🎯 {chosen_member.mention} ロックオン！", embed=embed, view=view)

    @app_commands.command(name="koubun", description="ふたつの言葉からコウメ太夫のネタを生成します")
    @app_commands.describe(word1="〜かと思ったら", word2="〜でした")
    async def koubun(self, interaction: discord.Interaction, word1: str, word2: str):
        if len(word1) > 500 or len(word2) > 500:
            await interaction.response.send_message("❌ 文字数が長すぎます（各500文字以内にしてね）。", ephemeral=True)
            return
        joke = f"チャンチャカチャンチャン チャチャンチャチャンチャン♪\n\n**{word1}** かと思ったら〜〜〜\n\n**{word2}** でした〜〜〜\n\n**チクショーー！！** 😭"
        await interaction.response.send_message(joke)

    # --- スラッシュコマンド (管理者限定) ---

    @app_commands.command(name="role_panel", description="【管理者用】ロール付与用のパネルを作成します")
    @app_commands.describe(title="パネルのタイトル", description="説明文")
    @app_commands.default_permissions(administrator=True)
    async def create_role_panel(self, interaction: discord.Interaction, title: str, description: str):
        embed = discord.Embed(title=title, description=description, color=discord.Color.green())
        view = RolePanelView() # 永続ビューの呼び出し
        await interaction.response.send_message("📢 ロールパネルを作成しました！", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)


    # --- テキストコマンド ---

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def msg_clear(self, ctx, amount: int):
        if amount < 1 or amount > 100:
            await ctx.send("❌ 1から100の間の数値を指定してください。", delete_after=5)
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 正常に {len(deleted) - 1} 件のメッセージを削除しました！", delete_after=5)

    @commands.command(name="servers")
    @commands.is_owner()
    async def list_servers(self, ctx):
        guild_count = len(self.bot.guilds)
        server_list = ""
        for guild in self.bot.guilds:
            server_list += f"• **{guild.name}** (メンバー数: {guild.member_count}人, ID: `{guild.id}`)\n"
            if len(server_list) > 1800:
                server_list += "• ...他多数"
                break
        embed = discord.Embed(title="🤖 Bot所属サーバー一覧", description=f"現在 **{guild_count}** 個のサーバーに参加しています。\n\n{server_list}", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name="say")
    @commands.has_permissions(administrator=True)
    async def say_message(self, ctx, channel: discord.TextChannel, *, message: str):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await channel.send(message)

    @commands.command(name="status")
    @commands.is_owner()
    async def change_status(self, ctx, *, text: str):
        await self.bot.change_presence(activity=discord.Game(name=text))
        await ctx.send(f"🤖 Botのステータスを「**{text} をプレイ中**」に変更しました！")

    @commands.command(name="ping")
    async def ping_check(self, ctx):
        raw_ping = self.bot.latency * 1000
        start_time = time.time()
        message = await ctx.send("⚡ Ping測定中...")
        end_time = time.time()
        msg_ping = (end_time - start_time) * 1000
        embed = discord.Embed(title="📶 Bot回線状態（レイテンシ）", color=discord.Color.green())
        embed.add_field(name="WebSocket Ping (APIとの通信)", value=f"`{raw_ping:.2f} ms`", inline=False)
        embed.add_field(name="Message Ping (メッセージ送信速度)", value=f"`{msg_ping:.2f} ms`", inline=False)
        status_text = "🟢 非常に快適" if raw_ping < 50 else "🟡 普通" if raw_ping < 150 else "🔴 遅延気味"
        embed.set_footer(text=f"稼働状況: {status_text}")
        await message.edit(content=None, embed=embed)

    @commands.command(name="restart")
    @commands.is_owner()
    async def restart_bot(self, ctx):
        await ctx.send("**再起動処理を実行中 (プロセスを終了します)**")
        await self.bot.close()
        sys.exit(0)


# ⚙️ スラッシュコマンドと永続Viewのセットアップ
async def setup(bot: commands.Bot):
    # ロールパネルのViewを永続化（再起動後も動作させる）
    bot.add_view(RolePanelView())
    await bot.add_cog(CommandsCog(bot))