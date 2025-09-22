import discord
from discord.ext import commands
import json
import joblib
from rank_bm25 import BM25Okapi

import os

# Get the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Indexing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def index(self, ctx):
        """Indexes the FAQ data using BM25."""
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "faq.json"), "r") as f:
                kb = json.load(f)

            questions = [entry["question"] for entry in kb]
            tokenized_corpus = [doc.split(" ") for doc in questions]
            bm25 = BM25Okapi(tokenized_corpus)

            with open(os.path.join(PROJECT_ROOT, "data", "bm25_index.joblib"), "wb") as f:
                joblib.dump({"kb": kb, "bm25": bm25}, f)

            await ctx.send("Knowledge base indexed with BM25!")
        except Exception as e:
            await ctx.send(f"An error occurred during indexing: {e}")

async def setup(bot):
    await bot.add_cog(Indexing(bot))
