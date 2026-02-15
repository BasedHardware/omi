import re
from typing import Optional, Tuple
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env file
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TweetDetector:
    """Detects 'Tweet Now' commands and extracts tweet content intelligently."""
    
    TRIGGER_PHRASES = [
        "tweet now",
        "post tweet",
        "send tweet",
        "tweet this",
        "post this tweet"
    ]
    
    END_PHRASES = [
        "end tweet",
        "stop tweet",
        "that's it",
        "that's the tweet",
        "done tweeting",
        "finish tweet"
    ]
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        return text.lower().strip()
    
    @classmethod
    def detect_trigger(cls, text: str) -> bool:
        """Check if text contains a tweet trigger phrase."""
        normalized = cls.normalize_text(text)
        return any(trigger in normalized for trigger in cls.TRIGGER_PHRASES)
    
    @classmethod
    def detect_end(cls, text: str) -> bool:
        """Check if text contains an explicit end phrase."""
        normalized = cls.normalize_text(text)
        return any(end_phrase in normalized for end_phrase in cls.END_PHRASES)
    
    @classmethod
    def extract_tweet_content(cls, text: str) -> Optional[str]:
        """Extract tweet content after trigger phrase."""
        normalized = cls.normalize_text(text)
        
        # Find the trigger phrase
        trigger_index = -1
        matched_trigger = None
        for trigger in cls.TRIGGER_PHRASES:
            idx = normalized.find(trigger)
            if idx != -1:
                trigger_index = idx
                matched_trigger = trigger
                break
        
        if trigger_index == -1:
            return None
        
        # Extract content after trigger
        start_index = trigger_index + len(matched_trigger)
        content = text[start_index:].strip()
        
        # Remove explicit end phrases if present
        for end_phrase in cls.END_PHRASES:
            if content.lower().endswith(end_phrase):
                content = content[:-(len(end_phrase))].strip()
                break
        
        return content if content else None
    
    @classmethod
    async def ai_check_completeness(cls, accumulated_text: str) -> float:
        """
        Use AI to check if tweet sounds complete.
        Returns a score from 0.0 to 1.0:
        - 0.0 = definitely incomplete, wait for more
        - 1.0 = definitely complete, post now
        - 0.5+ = probably complete enough
        """
        # If explicit end phrase, it's complete
        if cls.detect_end(accumulated_text):
            return 1.0
        
        # Very short tweets might still be complete
        cleaned = accumulated_text.strip().lstrip('.,!?;: ')
        if len(cleaned) < 3:
            return 0.0
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You check if a tweet/statement is complete or needs more content.

COMPLETE (score 0.8-1.0):
✓ Expresses a complete thought or feeling
✓ Can stand alone as a valid tweet
✓ Examples:
  - "that this is amazing" → 0.9
  - "This is incredible" → 1.0
  - "Just had the best day" → 0.95
  - "Love this" → 0.9

INCOMPLETE (score 0.0-0.4):
✗ Ends mid-sentence/mid-thought
✗ Obviously needs more words
✗ Examples:
  - "I think that" → 0.2
  - "This is" → 0.1
  - "Just had a great idea and" → 0.15
  - "Going to" → 0.1

Be GENEROUS with completeness scores. Short tweets are often intentionally brief.
If it could be a tweet, score it 0.7+

Respond with ONLY a number 0.0-1.0"""
                    },
                    {
                        "role": "user",
                        "content": f"Text: \"{cleaned}\"\n\nCompleteness (0.0-1.0):"
                    }
                ],
                temperature=0.2,
                max_tokens=5
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse the score
            try:
                score = float(result)
                score = max(0.0, min(1.0, score))  # Clamp between 0 and 1
                print(f"🤖 Completeness: {score:.2f} for '{cleaned[:50]}...'", flush=True)
                return score
            except:
                # If can't parse, be generous
                print(f"⚠️  Couldn't parse AI score, defaulting to 0.8", flush=True)
                return 0.8
                
        except Exception as e:
            print(f"⚠️  AI check failed: {e}, defaulting to complete", flush=True)
            # On error, assume complete if reasonable length
            return 0.9 if len(cleaned) > 8 else 0.5
    
    @classmethod
    async def ai_extract_tweet_from_segments(cls, all_segments_text: str) -> str:
        """
        Extract the actual tweet from 3 segments of speech.
        AI intelligently determines what's the tweet vs what's not.
        """
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You extract tweets from voice transcripts.

The user said "Tweet Now" and then spoke for a bit. Extract ONLY the tweet content.

Rules:
1. The tweet starts after "Tweet Now" trigger phrase
2. Some speech may NOT be part of the tweet (side comments, corrections, etc.)
3. Extract only what should be tweeted
4. Clean up filler words (um, uh, like, you know)
5. Fix grammar and capitalization
6. Make it sound natural and well-written
7. Keep under 280 characters

Examples:

Input: "that this is amazing and oh wait I also need to buy milk later"
Output: "That this is amazing"

Input: "I just had an incredible idea about AI and creativity this is so cool"
Output: "I just had an incredible idea about AI and creativity. This is so cool!"

Input: "the best day ever no wait scratch that it was pretty good"
Output: "The best day ever"

Respond with ONLY the cleaned tweet text. No quotes, no explanations."""
                    },
                    {
                        "role": "user",
                        "content": f"Voice transcript after 'Tweet Now': {all_segments_text}\n\nExtract the tweet:"
                    }
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            cleaned = response.choices[0].message.content.strip()
            
            # Remove quotes if AI added them
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            if cleaned.startswith("'") and cleaned.endswith("'"):
                cleaned = cleaned[1:-1]
            
            # Ensure proper capitalization
            if cleaned and cleaned[0].islower():
                cleaned = cleaned[0].upper() + cleaned[1:]
            
            # Truncate if too long
            if len(cleaned) > 280:
                cleaned = cleaned[:277] + "..."
            
            return cleaned
            
        except Exception as e:
            print(f"⚠️  AI extraction failed: {e}, using basic cleanup", flush=True)
            # Fallback
            return cls.clean_tweet_content(all_segments_text)
    
    @classmethod
    async def ai_clean_tweet(cls, full_text: str, extracted_content: str) -> str:
        """
        Use OpenAI to intelligently clean and extract the tweet.
        Takes the full transcript and extracted content, returns cleaned tweet.
        """
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a tweet cleanup assistant. Extract and clean up the intended tweet from speech.

Your job:
1. Extract ONLY the tweet content (what comes after "Tweet Now")
2. Remove filler words (um, uh, like, you know, so)
3. Fix capitalization and punctuation
4. Remove leading/trailing punctuation artifacts
5. Make it sound natural and well-written
6. Keep it under 280 characters
7. Preserve the original meaning and tone

Respond with ONLY the cleaned tweet text. No quotes, no explanations, just the tweet."""
                    },
                    {
                        "role": "user",
                        "content": f"Full transcript: {full_text}\n\nExtracted after trigger: {extracted_content}\n\nClean this into a perfect tweet:"
                    }
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            cleaned = response.choices[0].message.content.strip()
            
            # Remove quotes if AI added them
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            if cleaned.startswith("'") and cleaned.endswith("'"):
                cleaned = cleaned[1:-1]
            
            # Ensure proper capitalization
            if cleaned and cleaned[0].islower():
                cleaned = cleaned[0].upper() + cleaned[1:]
            
            # Truncate if too long
            if len(cleaned) > 280:
                cleaned = cleaned[:277] + "..."
            
            return cleaned
            
        except Exception as e:
            print(f"⚠️  AI cleanup failed: {e}, using basic cleanup")
            # Fallback to basic cleaning
            return cls.clean_tweet_content(extracted_content)
    
    @classmethod
    def clean_tweet_content(cls, content: str) -> str:
        """Basic cleaning of tweet content (fallback)."""
        # Remove multiple spaces
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common filler words at the end
        filler_words = ["um", "uh", "like", "you know", "so", "yeah"]
        words = content.split()
        while words and words[-1].lower().rstrip('.,!?') in filler_words:
            words.pop()
        
        content = ' '.join(words).strip()
        
        # Remove leading punctuation
        content = content.lstrip('.,!?;: ')
        
        # Ensure proper capitalization of first letter
        if content and content[0].islower():
            content = content[0].upper() + content[1:]
        
        return content

