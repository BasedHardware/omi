import random
from typing import Tuple, List
from .clients import llm_medium
from .usage_tracker import track_usage, Features
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
        with track_usage(uid, Features.SUBSCRIPTION_NOTIFICATION):
            response = await llm_medium.ainvoke(system_prompt + "\n" + user_prompt)
        body = response.content
        # Return placeholder title and generated body
        return "omi", body.strip()

    except Exception as e:
        print(f"Error generating notification message: {e}")

    # Improved fallback messages with more personality
    return ("omi", f"Hey {name}! 👋 Thanks for being part of the Omi family! ✨")


async def generate_credit_limit_notification(uid: str, name: str) -> Tuple[str, str]:
    """
    Generate a personalized notification when user hits transcription credit limits.
    """
    # Get relevant memories for context
    memories = await get_relevant_memories(uid, limit=50)
    memory_context = ""
    if memories:
        memory_summaries = [m.get('content', '') for m in memories]  # Use all memories for context
        memory_context = f"\nRecent conversations include: {', '.join(memory_summaries[:100])}..."

    system_prompt = """You're Omi, and you need to gently let a user know they've hit their transcription limits while encouraging them to upgrade to unlimited. 

    Your Style:
    - Warm and understanding, not pushy
    - Show genuine care for their journey with you
    - Make the upgrade feel like a natural next step
    - Reference their usage to show value
    - Keep it conversational and friendly
    - No emojis (express yourself in words!)
    - Under 150 characters total

    Key Points to Include:
    - They've been actively using transcription (show appreciation)
    - Unlimited plan removes all limits
    - Can check usage/plans in the app under Settings > Plan & Usages
    - Make it feel like you're helping them, not selling to them
    """

    user_prompt = f"""Create a credit limit notification for {name} who has reached their transcription limits.

    Context:
    - User's name: {name}
    - They've been actively transcribing conversations
    - Need to encourage unlimited plan subscription{memory_context}

    The message should:
    - Acknowledge their active usage positively
    - Suggest checking plans in the app under Settings > Plan & Usages
    - Feel helpful, not sales-y
    - Be warm and personal to {name}
    
    Return only the notification body text."""

    try:
        with track_usage(uid, Features.SUBSCRIPTION_NOTIFICATION):
            response = await llm_medium.ainvoke(system_prompt + "\n" + user_prompt)
        body = response.content
        return "omi", body.strip()

    except Exception as e:
        print(f"Error generating credit limit notification: {e}")

    # Fallback message
    return (
        "omi",
        f"Hey {name}! You've been actively using transcription - that's awesome! You've hit your limit, but unlimited plans remove all restrictions. You can check your usage and upgrade in the app under Settings > Plan & Usages.",
    )


def generate_silent_user_notification(name: str) -> Tuple[str, str]:
    """
    Generate a funny notification for a user who has been silent for a while.
    """
    messages = [
        f"Hey {name}, just checking in! My ears are open if you've got something to say.",
        f"Is this thing on? Tapping my mic here, {name}. Let me know when you're ready to chat!",
        f"Quiet on the set! {name}, are we rolling? Just waiting for your cue.",
        f"The sound of silence... is nice, but I'm here for the words, {name}! What's on your mind?",
        f"{name}, you've gone quiet! Just a heads up, I'm still here listening and using up your free minutes.",
        f"Psst, {name}... My virtual ears are getting a little lonely. Anything to share?",
        f"Enjoying the quiet time, {name}? Just remember, I'm on the clock, ready to transcribe!",
        f"Hello from the other side... of silence! {name}, ready to talk again?",
        f"I'm all ears, {name}! Just letting you know the recording is still live.",
        f"Silence is golden, but words are what I live for, {name}! Let's chat when you're ready.",
    ]
    body = random.choice(messages)
    return "omi", body
