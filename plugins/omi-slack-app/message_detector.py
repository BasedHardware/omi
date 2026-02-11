import re
from typing import Optional, Tuple
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class MessageDetector:
    """Detects Slack message commands and extracts message content + channel intelligently."""
    
    TRIGGER_PHRASES = [
        "send slack message",
        "post slack message",
        "post in slack"
    ]
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        return text.lower().strip()
    
    @classmethod
    def detect_trigger(cls, text: str) -> bool:
        """Check if text contains a Slack message trigger phrase."""
        normalized = cls.normalize_text(text)
        return any(trigger in normalized for trigger in cls.TRIGGER_PHRASES)
    
    @classmethod
    def extract_message_content(cls, text: str) -> Optional[str]:
        """Extract message content after trigger phrase."""
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
        
        return content if content else None
    
    @classmethod
    async def ai_extract_message_and_channel(cls, all_segments_text: str, available_channels: list) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract message content and target channel from voice segments.
        Uses AI to intelligently parse "send X message to/in Y channel"
        
        Returns: (channel_id, channel_name, message_content) or (None, None, None)
        """
        # Create channel list for AI
        channel_names = [ch["name"] for ch in available_channels]
        channel_map = {ch["name"]: ch["id"] for ch in available_channels}
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a Slack message parser. Extract the channel name and message content from voice commands.

Available channels: {', '.join(channel_names)}

The user said something like "send message to [channel] saying [message]" or "post in [channel] that [message]"

Your job:
1. Identify which channel name the user mentioned (fuzzy match from available channels)
2. Extract the message content they want to send
3. Clean up the message (remove filler words, fix grammar)

Important:
- Channel names might be said imperfectly (e.g., "general" for "#general", "random stuff" for "#random")
- Match to the CLOSEST available channel name
- If no clear channel mentioned, return "UNKNOWN" for channel
- Message should be clean and natural

Respond in this EXACT format:
CHANNEL: <channel_name or UNKNOWN>
MESSAGE: <cleaned message content>

Examples:

Input: "to general saying hello team how are you doing today"
Output:
CHANNEL: general
MESSAGE: Hello team, how are you doing today?

Input: "in the marketing channel that the new campaign is live"
Output:
CHANNEL: marketing
MESSAGE: The new campaign is live

Input: "to random saying just had an amazing idea about this"
Output:
CHANNEL: random
MESSAGE: Just had an amazing idea about this

Input: "hello everyone this is a test message"
Output:
CHANNEL: UNKNOWN
MESSAGE: Hello everyone, this is a test message"""
                    },
                    {
                        "role": "user",
                        "content": f"Voice command after trigger: {all_segments_text}\n\nExtract channel and message:"
                    }
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse response
            channel_name = None
            message = None
            
            for line in result.split('\n'):
                if line.startswith("CHANNEL:"):
                    channel_name = line.replace("CHANNEL:", "").strip()
                elif line.startswith("MESSAGE:"):
                    message = line.replace("MESSAGE:", "").strip()
            
            # Handle unknown channel
            if not channel_name or channel_name.upper() == "UNKNOWN":
                print(f"⚠️  No channel identified in message", flush=True)
                return None, None, message
            
            # Remove # if present
            channel_name = channel_name.lstrip('#')
            
            # Get channel ID from map (case insensitive)
            channel_id = None
            for name, id in channel_map.items():
                if name.lower() == channel_name.lower():
                    channel_id = id
                    channel_name = name  # Use exact name from map
                    break
            
            if not channel_id:
                # Try fuzzy match
                for name, id in channel_map.items():
                    if channel_name.lower() in name.lower() or name.lower() in channel_name.lower():
                        channel_id = id
                        channel_name = name
                        print(f"🔍 Fuzzy matched '{channel_name}' to '{name}'", flush=True)
                        break
            
            if not channel_id:
                print(f"⚠️  Channel '{channel_name}' not found in workspace", flush=True)
                return None, channel_name, message
            
            print(f"✅ Extracted - Channel: #{channel_name}, Message: '{message}'", flush=True)
            return channel_id, channel_name, message
            
        except Exception as e:
            print(f"⚠️  AI extraction failed: {e}", flush=True)
            return None, None, all_segments_text
    
    @classmethod
    async def ai_match_channel(cls, spoken_channel: str, available_channels: list) -> Optional[dict]:
        """
        Use AI to fuzzy match a spoken channel name to available channels.
        Returns best matching channel dict or None
        """
        if not available_channels:
            return None
        
        channel_names = [ch["name"] for ch in available_channels]
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You match spoken channel names to actual Slack channel names.

Available channels: {', '.join(channel_names)}

The user said a channel name that might be:
- Incomplete (e.g., "gen" for "general")
- Imperfect pronunciation transcription
- With/without # symbol
- Slightly different wording

Find the BEST matching channel from the available list.
If no good match exists, respond with "NONE"

Respond with ONLY the exact channel name from the available list, or "NONE"

Examples:
User said: "general" → general
User said: "the marketing channel" → marketing
User said: "random stuff" → random
User said: "engineering team" → engineering
User said: "xyz123" (not in list) → NONE"""
                    },
                    {
                        "role": "user", 
                        "content": f"User said channel: '{spoken_channel}'\n\nBest match from available channels:"
                    }
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            matched = response.choices[0].message.content.strip().lstrip('#')
            
            if matched.upper() == "NONE":
                return None
            
            # Find the channel with this name
            for ch in available_channels:
                if ch["name"].lower() == matched.lower():
                    print(f"🎯 AI matched '{spoken_channel}' → #{ch['name']}", flush=True)
                    return ch
            
            return None
            
        except Exception as e:
            print(f"⚠️  AI channel matching failed: {e}", flush=True)
            # Fallback to simple matching
            spoken_lower = spoken_channel.lower().lstrip('#')
            for ch in available_channels:
                if ch["name"].lower() == spoken_lower:
                    return ch
            return None
    
    @classmethod
    def clean_content(cls, content: str) -> str:
        """Basic cleaning of content (fallback)."""
        # Remove multiple spaces
        content = re.sub(r'\s+', ' ', content)
        
        # Remove common filler words
        filler_words = ["um", "uh", "like", "you know", "so", "yeah"]
        words = content.split()
        cleaned_words = [w for w in words if w.lower().rstrip('.,!?') not in filler_words]
        
        content = ' '.join(cleaned_words).strip()
        
        # Ensure proper capitalization of first letter
        if content and content[0].islower():
            content = content[0].upper() + content[1:]
        
        return content

