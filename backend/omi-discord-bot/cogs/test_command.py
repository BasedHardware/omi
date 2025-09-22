import discord
from discord.ext import commands

class TestCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def mention_test(self, ctx, member: discord.Member):
        """Mentions the user provided as an argument."""
        await ctx.send(f"Hello {member.mention}!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message) and not message.content.startswith(self.bot.command_prefix):
            await message.channel.send("hello")

async def setup(bot):
    await bot.add_cog(TestCommand(bot))
