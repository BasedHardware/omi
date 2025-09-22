import discord
import os
from dotenv import load_dotenv
from discord.ext import commands
import asyncio
import logging
from typing import Literal, Optional


load_dotenv()
token = os.getenv('TOKEN')
if not token:
    logging.error("TOKEN not found in .env file.")
    exit()

from core.bot  import OmiDiscordBot

bot = OmiDiscordBot()

async def load():
    for f in os.listdir("./cogs"):
        if f.endswith(".py"):
            try:
                await bot.load_extension(f'cogs.{f[:-3]}')

            except:
                logging.warning(f"PROBLEM WITH A COG FILE <<<{f[:-3]}>>>")
                


#https://about.abstractumbra.dev/discord.py/2023/01/29/sync-command-example.html
@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")


bot.remove_command('help')  
async def main():
    await load()
    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bm25_index.joblib")):
        logging.warning("BM25 index not found. Please run the !index command.")
    await bot.start(token)

asyncio.run(main())