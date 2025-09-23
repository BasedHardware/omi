import discord
from discord.ext import commands
import json
import joblib
from rank_bm25 import BM25Okapi
import os
import re

# Get the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Indexing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def clean_text(self, text):
        """Clean and normalize text for better matching"""
        # Convert to lowercase
        text = text.lower()
        # Remove punctuation but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        # Normalize multiple spaces to single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    @commands.command()
    @commands.is_owner()
    async def index(self, ctx):
        """Indexes the FAQ data using BM25 with improved text processing."""
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "faq.json"), "r") as f:
                kb = json.load(f)
            
            # Create documents combining question and partial answer for better matching
            documents = []
            for entry in kb:
                # Combine question with first 100 chars of answer for context
                doc = f"{entry['question']} {entry['answer'][:100]}"
                # Clean the document
                doc = self.clean_text(doc)
                documents.append(doc)
            
            # Tokenize corpus
            tokenized_corpus = [doc.split() for doc in documents]
            
            # Create BM25 with tuned parameters
            # k1=1.2 (term frequency saturation)
            # b=0.75 (length normalization)
            bm25 = BM25Okapi(tokenized_corpus, k1=1.2, b=0.75)
            
            # Save index with the knowledge base
            with open(os.path.join(PROJECT_ROOT, "data", "bm25_index.joblib"), "wb") as f:
                joblib.dump({
                    "kb": kb,
                    "bm25": bm25,
                    "documents": documents  # Save processed documents for debugging
                }, f)
            
            # Create a nice embed response
            embed = discord.Embed(
                title="✅ Indexing Complete",
                description=f"Successfully indexed {len(kb)} FAQ entries with BM25!",
                color=discord.Color.green()
            )
            embed.add_field(name="Documents", value=len(kb), inline=True)
            embed.add_field(name="Algorithm", value="BM25Okapi", inline=True)
            embed.set_footer(text="Ready to answer questions!")
            
            await ctx.send(embed=embed)
            
        except FileNotFoundError:
            await ctx.send("❌ Error: `faq.json` file not found in the data directory.")
        except json.JSONDecodeError:
            await ctx.send("❌ Error: `faq.json` file contains invalid JSON.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred during indexing: {str(e)}")
    
    @commands.command()
    @commands.is_owner()
    async def test_index(self, ctx, *, query: str = None):
        """Test the index with a sample query"""
        if not query:
            await ctx.send("Please provide a query to test. Example: `!test_index what is omi`")
            return
        
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "bm25_index.joblib"), "rb") as f:
                data = joblib.load(f)
            
            bm25 = data["bm25"]
            kb = data["kb"]
            
            # Clean query
            cleaned_query = self.clean_text(query)
            tokenized_query = cleaned_query.split()
            
            # Get scores
            scores = bm25.get_scores(tokenized_query)
            
            # Get top 3 results
            top_indices = scores.argsort()[-3:][::-1]
            
            embed = discord.Embed(
                title="🔍 Index Test Results",
                description=f"Query: **{query}**\nCleaned: **{cleaned_query}**",
                color=discord.Color.blue()
            )
            
            for i, idx in enumerate(top_indices, 1):
                score = scores[idx]
                question = kb[idx]["question"]
                answer_preview = kb[idx]["answer"][:100] + "..."
                
                embed.add_field(
                    name=f"{i}. Score: {score:.2f}",
                    value=f"**Q:** {question}\n**A:** {answer_preview}",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except FileNotFoundError:
            await ctx.send("❌ Index not found. Please run `!index` first.")
        except Exception as e:
            await ctx.send(f"❌ Error testing index: {str(e)}")

async def setup(bot):
    await bot.add_cog(Indexing(bot))