import ast
import re
import discord
from discord.ext import commands


class Calculator(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  def _eval_node(self, node):
    operators = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
        ast.USub: lambda a: -a,
        ast.UAdd: lambda a: +a,
    }

    if isinstance(node, ast.Constant):
      if isinstance(node.value, (int, float)):
        return node.value
      raise TypeError("サポートされていない型です")
    elif isinstance(node, ast.BinOp):
      op_type = type(node.op)
      if op_type in operators:
        return operators[op_type](
            self._eval_node(node.left), self._eval_node(node.right)
        )
    elif isinstance(node, ast.UnaryOp):
      op_type = type(node.op)
      if op_type in operators:
        return operators[op_type](self._eval_node(node.operand))

    raise TypeError("安全ではない数式、または無効な数式です")

  def safe_eval(self, expr_str: str):
    node = ast.parse(expr_str, mode="eval")
    return self._eval_node(node.body)

  @commands.Cog.listener()
  async def on_message(self, message: discord.Message):
    if message.author.bot or not message.guild:
      return

    content = message.content
    calc_match = re.search(r"([0-9\.\s\+\-\*\/\(\)\^%]+)", content)
    if calc_match:
      expr = calc_match.group(1).strip()
      has_operator = any(
          op in expr for op in ["+", "-", "*", "/", "^", "%", "(", ")"]
      )
      if has_operator:
        try:
          clean_expr = expr.replace("^", "**")
          result = self.safe_eval(clean_expr)

          if isinstance(result, float) and result.is_integer():
            result = int(result)

          embed = discord.Embed(title="🧮 計算結果", color=discord.Color.green())
          embed.add_field(
              name="数式", value=f"`{expr.replace('**', '^')}`", inline=False
          )
          embed.add_field(name="答え", value=f"**{result}**", inline=False)

          embed.set_footer(
              text=f"Calculated by {message.author.display_name}",
              icon_url=message.author.display_avatar.url,
          )
          await message.reply(embed=embed, mention_author=False)
        except Exception:
          pass


async def setup(bot):
  await bot.add_cog(Calculator(bot))