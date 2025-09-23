import discord
from discord.ext import commands

class TestCommand(commands.Cog):
    def __init__(self, bot):
        self.index = 0 
        self.bot = bot

    @commands.command()
    async def run(self, ctx):
        """Mentions the user provided as an argument."""
        await ctx.reply(f"Hello!")


    @commands.command()
    async def called(self, ctx):
        await ctx.reply(f"hello!")


async def setup(bot):
    await bot.add_cog(TestCommand(bot))
