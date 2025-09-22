import discord
from discord.ext import commands
import joblib

import os

# Get the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Faq(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kb_data = None
        self.bm25 = None
        self.load_index()

    def load_index(self):
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "bm25_index.joblib"), "rb") as f:
                data = joblib.load(f)
                self.kb_data = data["kb"]
                self.bm25 = data["bm25"]
        except FileNotFoundError:
            print("BM25 index not found. Please run the !index command.")

    @commands.command()
    @commands.is_owner()
    async def reload_index(self, ctx):
        self.load_index()
        await ctx.send("BM25 index reloaded.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message):
            question = message.content.replace(f'<@!{self.bot.user.id}>', '').strip()
            if question and self.bm25:
                tokenized_query = question.split(" ")
                doc_scores = self.bm25.get_scores(tokenized_query)
                best_doc_index = doc_scores.argmax()
                best_doc_score = doc_scores[best_doc_index]

                if best_doc_score > 0:
                    answer = self.kb_data[best_doc_index]["answer"]
                    await message.channel.send(answer)
                else:
                    await message.channel.send("I couldn't find an answer to your question. Please try rephrasing it.")

async def setup(bot):
    await bot.add_cog(Faq(bot))
