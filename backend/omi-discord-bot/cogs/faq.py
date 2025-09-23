import discord
from discord.ext import commands
import joblib
import os
import re
from difflib import SequenceMatcher

# Get the absolute path to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Faq(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kb_data = None
        self.bm25 = None
        self.questions_lower = []  # Store lowercase questions for matching
        self.load_index()
        
    def load_index(self):
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "bm25_index.joblib"), "rb") as f:
                data = joblib.load(f)
                self.kb_data = data["kb"]
                self.bm25 = data["bm25"]
                # Create lowercase question list for fuzzy matching
                self.questions_lower = [q["question"].lower() for q in self.kb_data]
        except FileNotFoundError:
            print("BM25 index not found. Please run the !index command.")
    
    def clean_text(self, text):
        """Clean and normalize text for better matching"""
        # Convert to lowercase
        text = text.lower()
        # Remove multiple spaces and punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def find_best_match(self, query):
        """Find the best matching FAQ entry using multiple strategies"""
        cleaned_query = self.clean_text(query)
        
        # Check for exact or near-exact question matches
        best_exact_score = 0
        best_exact_idx = -1
        
        for idx, question in enumerate(self.questions_lower):
            # Check if query is contained in question or vice versa
            if cleaned_query in self.clean_text(question) or self.clean_text(question) in cleaned_query:
                similarity = SequenceMatcher(None, cleaned_query, self.clean_text(question)).ratio()
                if similarity > best_exact_score:
                    best_exact_score = similarity
                    best_exact_idx = idx
        
        # If we have a good exact match (>60% similarity), use it
        if best_exact_score > 0.6:
            return best_exact_idx, best_exact_score * 10  # Scale score for consistency
        
        # Use BM25 for semantic matching
        if self.bm25:
            tokenized_query = cleaned_query.split()
            doc_scores = self.bm25.get_scores(tokenized_query)
            best_bm25_idx = doc_scores.argmax()
            best_bm25_score = doc_scores[best_bm25_idx]
            
            # Return BM25 result if score is reasonable
            if best_bm25_score > 0.5:
                return best_bm25_idx, best_bm25_score
        
        return -1, 0
    
    @commands.command()
    @commands.is_owner()
    async def reload_index(self, ctx):
        self.load_index()
        await ctx.send("✅ BM25 index reloaded successfully.")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
            
        if self.bot.user.mentioned_in(message):
            # Extract question from message
            question = message.content
            for mention in [f'<@{self.bot.user.id}>', f'<@!{self.bot.user.id}>']:
                question = question.replace(mention, '')
            
            question = question.strip()
            
            # If no question in message, check reply
            if not question and message.reference:
                try:
                    tagged_message = await message.channel.fetch_message(message.reference.message_id)
                    question = tagged_message.content
                except:
                    pass
            
            if question and self.kb_data:
                # Find best match using multiple strategies
                best_idx, best_score = self.find_best_match(question)
                
                print(f"Query: '{question}'")
                if best_idx >= 0:
                    print(f"Matched: '{self.kb_data[best_idx]['question']}' with score {best_score:.2f}")
                
                # Use lower threshold since we have better matching
                if best_idx >= 0 and best_score > 0.5:
                    answer = self.kb_data[best_idx]["answer"]
                    matched_question = self.kb_data[best_idx]["question"]
                    
                    # Create a nice embed
                    embed = discord.Embed(
                        title="💡 Answer",
                        description=answer,
                        color=self._get_confidence_color(best_score)
                    )
                    
                    # Add matched question if it's significantly different from query
                    if not (question.lower() in matched_question.lower() or matched_question.lower() in question.lower()):
                        embed.add_field(
                            name="Matched Question",
                            value=matched_question,
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Confidence: {best_score:.2f}")
                    
                    await message.reply(embed=embed)
                else:
                    embed = discord.Embed(
                        title="❓ No Answer Found",
                        description="I couldn't find a relevant answer to your question. Please try rephrasing or ask a different question.",
                        color=discord.Color.orange()
                    )
                    embed.set_footer(text="Tip: Try using different keywords or be more specific.")
                    await message.reply(embed=embed)
            elif not self.kb_data:
                await message.reply("⚠️ The FAQ index is not loaded. Please ask an admin to run the `!index` command.")
    
    def _get_confidence_color(self, score):
        """Get color based on confidence score"""
        if score > 8:
            return discord.Color.green()
        elif score > 4:
            return discord.Color.blue()
        else:
            return discord.Color.yellow()
    
    @commands.command(name="faq")
    async def faq_search(self, ctx, *, query: str = None):
        """Search the FAQ database"""
        if not query:
            await ctx.send("Please provide a search query. Example: `!faq what is omi`")
            return
            
        if not self.kb_data:
            await ctx.send("⚠️ The FAQ index is not loaded. Please run the `!index` command first.")
            return
        
        # Find best match
        best_idx, best_score = self.find_best_match(query)
        
        if best_idx >= 0 and best_score > 0.5:
            answer = self.kb_data[best_idx]["answer"]
            question = self.kb_data[best_idx]["question"]
            
            embed = discord.Embed(
                title="🔍 FAQ Result",
                color=self._get_confidence_color(best_score)
            )
            embed.add_field(name="Question", value=question, inline=False)
            embed.add_field(name="Answer", value=answer[:1024], inline=False)  # Discord field limit
            embed.set_footer(text=f"Confidence: {best_score:.2f}")
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❓ No matching FAQ entry found. Try different keywords!")

async def setup(bot):
    await bot.add_cog(Faq(bot))