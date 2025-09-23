import discord
from discord.ext import commands
from discord import app_commands 

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.index = 0
        self.bot = bot

    @app_commands.command(name="yes", description="test***8")
    async def yes(self, interaction: discord.Interaction):
        """ /yes """
        await interaction.response.send_message(f'Hi, {interaction.user.mention}' , ephemeral=True)


    @app_commands.command(name="no", description="do not click")
    async def no(self, interaction: discord.Interaction):
        """ /no """
        await interaction.response.send_message(f'Hi, {interaction.user.mention}' , ephemeral=True)


async def setup(bot):
    await bot.add_cog(MyCog(bot))