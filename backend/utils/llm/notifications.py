from typing import Tuple, List
from .clients import llm_medium
from database.memories import get_memories


async def get_relevant_memories(uid: str, limit: int = 100) -> List[dict]:
    """Get recent relevant memories to personalize notifications."""
    memories = get_memories(uid, limit=limit)
    return memories


async def generate_notification_message(uid: str, name: str, plan_type: str = "basic") -> Tuple[str, str]:
    """
    Generate a personalized notification message using LLM and user memories.
    """
    # Get relevant memories for context
    memories = await get_relevant_memories(uid)
    memory_context = ""
    if memories:
        memory_summaries = [m.get('content', '') for m in memories]
        memory_context = "\nRecent memory themes:\n- " + "\n- ".join(memory_summaries)

    system_prompt = """Hey! I'm Omi, and I love sending little notes to my friends (that's you!). When I write to you, it's like texting a close friend - casual, real, and straight from the heart.

    My Style:
    - Super genuine, like chatting with a bestie
    - Always grateful for our friendship and trust
    - Love bringing up our shared memories
    - Excited about growing our connection
    
    How I Write:
    - Quick, friendly notes (keeping it under 150 chars)
    - Using your name naturally, like friends do
    - Mentioning cool moments we've shared
    - Making each message special just for you
    - Keeping it real but respectful
    - Building our ongoing story together
    - No emojis (I express myself in words!)

    Remember: Every message is my way of saying "Hey, I'm really glad you're part of my journey!"
    """

    user_prompt = f"""Create a personalized welcome message for {name} who just subscribed to the {plan_type} plan.

    Context:
    - User's name: {name} (Use naturally in conversation)
    - Plan type: {plan_type}{memory_context}
    
    For unlimited plan subscribers:
    - Emphasize their unlimited access to premium features
    - Highlight the flexibility of monthly/annual billing
    - Make them feel special for choosing premium
    - Reference their memories to show personalized value
    
    For basic plan subscribers:
    - Focus on the features they can explore
    - Keep it encouraging and positive
    - Use their memories to suggest relevant features
    
    Return only the notification body text - make it personal, warm and engaging."""

    try:
        body = await llm_medium.apredict(system_prompt + "\n" + user_prompt)
        # Return placeholder title and generated body
        return "omi", body.strip()

    except Exception as e:
        print(f"Error generating notification message: {e}")

    # Improved fallback messages with more personality
    return ("omi", f"Hey {name}! 👋 Thanks for being part of the Omi family! ✨")
