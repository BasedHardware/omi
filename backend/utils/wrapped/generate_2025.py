"""
Wrapped 2025 generation logic.

Computes analytics from user's 2025 data and generates LLM-based insights.
"""

from collections import Counter
from datetime import datetime, timezone
from typing import List, Dict, Any

import database.wrapped as wrapped_db
import database.conversations as conversations_db
import database.action_items as action_items_db
from database.wrapped import WrappedStatus
from models.conversation import Conversation
from utils.llm.clients import llm_gemini_flash
from utils.notifications import send_notification
import json


# Date range for 2025
YEAR_2025_START = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
YEAR_2025_END = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# Common phrases to look for (safe, non-sensitive)
SIGNATURE_PHRASES = [
    "let's do this",
    "sounds good",
    "makes sense",
    "i think",
    "we should",
    "let me",
    "i need to",
    "we need to",
    "that's interesting",
    "exactly",
    "absolutely",
    "definitely",
    "basically",
    "actually",
    "honestly",
    "you know",
    "i mean",
    "right",
    "okay",
    "got it",
]

# Decision style archetypes
DECISION_ARCHETYPES = [
    {
        "name": "Reflective Executor",
        "description": "You think deeply, then move decisively.",
        "traits": ["high_completion_rate", "moderate_conversation_length", "balanced_categories"],
    },
    {
        "name": "Fast Iterative Thinker",
        "description": "You process quickly through many short conversations.",
        "traits": ["high_conversation_count", "short_conversations", "high_action_items"],
    },
    {
        "name": "Collaborative Planner",
        "description": "You work through ideas with others before acting.",
        "traits": ["long_conversations", "work_or_business_focus", "moderate_action_items"],
    },
    {
        "name": "Independent Builder",
        "description": "You work autonomously, focusing on execution.",
        "traits": ["high_completion_rate", "technology_or_business_focus", "consistent_timing"],
    },
    {
        "name": "Strategic Questioner",
        "description": "You ask the right questions before committing.",
        "traits": ["diverse_categories", "thoughtful_pacing", "quality_over_quantity"],
    },
]


def _update_progress(uid: str, year: int, step: str, pct: float):
    """Update generation progress."""
    wrapped_db.update_wrapped_progress(uid, year, {"step": step, "pct": pct})


def _compute_conversation_duration(conv: Conversation) -> float:
    """Compute conversation duration in seconds."""
    # Try to get duration from transcript segments
    if conv.transcript_segments:
        max_end = max((seg.end for seg in conv.transcript_segments), default=0)
        if max_end > 0:
            return max_end

    # Fallback: estimate from created_at to finished_at or use a default
    return 300  # 5 minutes default


def _find_signature_phrases(conversations: List[Conversation], sample_size: int = 50) -> Dict[str, int]:
    """Find signature phrases in user's conversations (sample for performance)."""
    phrase_counts = Counter()

    # Sample conversations
    sampled = conversations[:sample_size] if len(conversations) > sample_size else conversations

    for conv in sampled:
        # Only look at user segments
        user_text = " ".join(seg.text.lower() for seg in conv.transcript_segments if seg.is_user and seg.text)

        for phrase in SIGNATURE_PHRASES:
            count = user_text.count(phrase)
            if count > 0:
                phrase_counts[phrase] += count

    return dict(phrase_counts)


def _determine_archetype_with_llm(conversations: List[Conversation], stats: Dict[str, Any]) -> Dict[str, str]:
    """Use Gemini to determine decision style archetype based on conversation patterns."""
    print(f"[Wrapped]   - Starting decision style analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations, max_chars=300000)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        archetypes_str = "\n".join([f"- {a['name']}: {a['description']}" for a in DECISION_ARCHETYPES])

        prompt = f"""Analyze these conversation summaries and determine this person's DECISION STYLE and PERSONALITY archetype.

CONVERSATIONS:
{context}

STATS:
- Total conversations: {stats.get('total_conversations', 0)}
- Total hours: {stats.get('total_time_hours', 0)}
- Action item completion rate: {round(stats.get('action_items_completion_rate', 0) * 100)}%
- Top categories: {', '.join(stats.get('top_categories', [])[:3])}

Based on HOW they talk, WHAT they discuss, and their patterns, pick ONE archetype that fits best:
{archetypes_str}

Return as JSON (no markdown):
{{
    "name": "Archetype Name",
    "description": "A personalized 1-sentence description of their style based on actual conversation patterns"
}}

Make the description specific to THIS person based on what you see in their conversations, not generic."""

        print(f"[Wrapped]     - Calling Gemini for decision style...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        print(f"[Wrapped]     - Decision style: {result.get('name')}")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in decision style analysis: {e}")
        import traceback

        traceback.print_exc()
        return {"name": "Reflective Executor", "description": "You think deeply, then move decisively."}


def _find_top_phrases_with_llm(conversations: List[Conversation]) -> List[Dict[str, Any]]:
    """Use Gemini to find the user's top 5 most used phrases."""
    print(f"[Wrapped]   - Starting top phrases analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations, max_chars=400000)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries and identify this person's TOP 5 MOST USED PHRASES or expressions.

CONVERSATIONS:
{context}

Look for:
- Repeated phrases they use often
- Catchphrases or verbal habits
- Common expressions in their speech
- Things they say frequently when making points
- Signature ways they start or end statements

Return as JSON (no markdown):
{{
    "phrases": [
        {{"phrase": "the phrase", "context": "when/how they use it"}},
        {{"phrase": "another phrase", "context": "when/how they use it"}},
        {{"phrase": "third phrase", "context": "when/how they use it"}},
        {{"phrase": "fourth phrase", "context": "when/how they use it"}},
        {{"phrase": "fifth phrase", "context": "when/how they use it"}}
    ]
}}

Be specific with actual phrases from their conversations. Avoid generic filler words like "um", "like", "you know"."""

        print(f"[Wrapped]     - Calling Gemini for top phrases...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        phrases = result.get("phrases", []) if isinstance(result, dict) else result

        print(f"[Wrapped]     - Found {len(phrases)} top phrases")
        return phrases[:5]

    except Exception as e:
        print(f"[Wrapped]     - ERROR in top phrases analysis: {e}")
        import traceback

        traceback.print_exc()
        return [
            {"phrase": "Let's do this", "context": "When starting something new"},
            {"phrase": "Makes sense", "context": "When agreeing with ideas"},
            {"phrase": "I think", "context": "When sharing opinions"},
            {"phrase": "We should", "context": "When suggesting actions"},
            {"phrase": "Sounds good", "context": "When approving plans"},
        ]


def _build_conversations_context(conversations: List[Conversation], max_chars: int = 800000) -> str:
    """Build a context string from conversations for Gemini analysis (title + overview for broad coverage)."""
    context_parts = []
    total_chars = 0

    for conv in conversations:
        if not conv.created_at:
            continue

        date_str = conv.created_at.strftime("%Y-%m-%d %H:%M")
        title = conv.structured.title if conv.structured else "Untitled"
        overview = conv.structured.overview if conv.structured else ""

        # Use only title and overview for broader coverage (no transcript)
        entry = f"[{date_str}] {title}: {overview}\n"

        if total_chars + len(entry) > max_chars:
            break

        context_parts.append(entry)
        total_chars += len(entry)

    return "\n".join(context_parts)


def _analyze_memorable_days_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Use Gemini to analyze and find the most memorable days of the year."""
    print(f"[Wrapped]   - Starting memorable days analysis with Gemini...")

    try:
        # Build context from all conversations
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars from {len(conversations)} conversations")

        prompt = f"""Analyze these conversation transcripts from someone's year and identify the most memorable days.

CONVERSATIONS:
{context}

Based on the emotional content, topics, and events discussed, identify:

1. **MOST FUN DAY**: A day where the conversations show joy, excitement, celebration, laughter, or fun activities (parties, games, trips, achievements celebrated, etc.)

2. **MOST PRODUCTIVE DAY**: A day with conversations about accomplishments, completing tasks, making progress, closing deals, shipping features, finishing projects, etc.

3. **MOST STRESSFUL DAY**: A day where conversations reveal stress, pressure, deadlines, problems, conflicts, or challenging situations.

Return your analysis as JSON (no markdown):
{{
    "most_fun_day": {{
        "date": "Month Day" (e.g. "March 15"),
        "title": "Short catchy title for this day (3-5 words)",
        "description": "Brief description - MUST be 15-20 words max",
        "emoji": "Single relevant emoji"
    }},
    "most_productive_day": {{
        "date": "Month Day",
        "title": "Short catchy title (3-5 words)",
        "description": "Brief description - MUST be 15-20 words max",
        "emoji": "Single relevant emoji"
    }},
    "most_stressful_day": {{
        "date": "Month Day",
        "title": "Short catchy title (3-5 words)",
        "description": "Brief description (keep it light/empathetic) - MUST be 15-20 words max",
        "emoji": "Single relevant emoji"
    }}
}}

IMPORTANT: Each description MUST be exactly 15-20 words. No more, no less.
Be specific and reference actual events from the conversations. Make titles catchy and memorable."""

        print(f"[Wrapped]     - Calling Gemini for memorable days...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        # Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        print(f"[Wrapped]     - Successfully parsed memorable days")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in memorable days analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "most_fun_day": {
                "date": "Unknown",
                "title": "A Great Day",
                "description": "You had some memorable moments this year!",
                "emoji": "🎉",
            },
            "most_productive_day": {
                "date": "Unknown",
                "title": "Getting Things Done",
                "description": "You crushed it on productivity!",
                "emoji": "💪",
            },
            "most_stressful_day": {
                "date": "Unknown",
                "title": "A Challenging Day",
                "description": "You pushed through some tough moments.",
                "emoji": "😤",
            },
        }


def _find_funniest_event_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Use Gemini to find the funniest event/moment from the year."""
    print(f"[Wrapped]   - Starting funniest event analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation transcripts and find the FUNNIEST moment or event from this person's year.

CONVERSATIONS:
{context}

Look for:
- Funny stories they told
- Embarrassing but hilarious situations
- Jokes or witty moments
- Absurd situations
- Unexpected funny outcomes
- Self-deprecating humor
- Amusing mishaps

Return the single funniest event as JSON (no markdown):
{{
    "date": "Month Day" (e.g. "June 22"),
    "title": "Catchy funny title (3-6 words)",
    "story": "Brief retelling of the funny moment - MUST be 20-30 words max",
    "emoji": "Single funny emoji"
}}

IMPORTANT: The story MUST be exactly 20-30 words. No more, no less.
Pick something genuinely funny and retell it in an entertaining way. Make the user smile when they read it!"""

        print(f"[Wrapped]     - Calling Gemini for funniest event...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        print(f"[Wrapped]     - Successfully parsed funniest event: {result.get('title', 'Unknown')}")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in funniest event analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "date": "Unknown",
            "title": "A Hilarious Moment",
            "story": "You had some funny moments this year that made you laugh!",
            "emoji": "😂",
        }


def _find_most_embarrassing_event_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Use Gemini to find the most embarrassing moment from the year."""
    print(f"[Wrapped]   - Starting most embarrassing event analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation transcripts and find the MOST EMBARRASSING moment or event from this person's year.

CONVERSATIONS:
{context}

Look for:
- Awkward social situations
- Mistakes or blunders they made
- Cringeworthy moments they mentioned
- Times they felt embarrassed
- Foot-in-mouth moments
- Funny fails
- Moments of "I can't believe I did that"

Return the most embarrassing event as JSON (no markdown):
{{
    "date": "Month Day" (e.g. "August 5"),
    "title": "Catchy empathetic title (3-6 words)",
    "story": "Brief retelling of the embarrassing moment - MUST be 20-30 words max, keep it light and relatable",
    "emoji": "Single appropriate emoji"
}}

IMPORTANT: The story MUST be exactly 20-30 words. No more, no less.
Frame it in a lighthearted, relatable way - we've all been there! Make it funny rather than cruel."""

        print(f"[Wrapped]     - Calling Gemini for most embarrassing event...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        print(f"[Wrapped]     - Successfully parsed embarrassing event: {result.get('title', 'Unknown')}")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in embarrassing event analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "date": "Unknown",
            "title": "That Awkward Moment",
            "story": "We've all had those moments - you handled it like a champ!",
            "emoji": "😅",
        }


def _find_top_buddies_with_llm(conversations: List[Conversation]) -> List[Dict[str, Any]]:
    """Use Gemini to find the top 5 people the user interacted with most."""
    print(f"[Wrapped]   - Starting top buddies analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation transcripts and identify the TOP 5 PEOPLE this person interacted with, talked about, or mentioned most frequently throughout the year.

CONVERSATIONS:
{context}

Look for:
- People they had conversations with or about
- Friends, family members, colleagues, partners
- People mentioned by name or relationship (mom, dad, best friend, etc.)
- Recurring people in their stories and daily life

Return the top 5 people as JSON array (no markdown):
[
    {{
        "name": "First name or relationship (e.g. 'Sarah', 'Mom', 'Best Friend Jake')",
        "relationship": "Brief relationship descriptor (e.g. 'Best Friend', 'Colleague', 'Partner', 'Family')",
        "context": "One fun/memorable thing about their interactions - 10-15 words max",
        "emoji": "Single emoji that represents this relationship"
    }},
    ...
]

IMPORTANT: 
- Return exactly 5 people, ranked by how frequently/meaningfully they appear
- Use first names when available, otherwise use relationship titles
- The context should be specific and memorable, not generic
- Each context MUST be 10-15 words max"""

        print(f"[Wrapped]     - Calling Gemini for top buddies...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        if not isinstance(result, list):
            result = [result]

        # Ensure we have exactly 5
        result = result[:5]

        print(f"[Wrapped]     - Successfully parsed {len(result)} buddies")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in top buddies analysis: {e}")
        import traceback

        traceback.print_exc()
        return [
            {
                "name": "Your #1",
                "relationship": "Close Friend",
                "context": "Always there when you needed them!",
                "emoji": "👋",
            },
            {
                "name": "Your Confidant",
                "relationship": "Best Friend",
                "context": "Shared your best moments together.",
                "emoji": "🤝",
            },
            {"name": "Work Buddy", "relationship": "Colleague", "context": "Made work days more fun.", "emoji": "💼"},
            {"name": "Family", "relationship": "Family", "context": "Your support system all year.", "emoji": "❤️"},
            {"name": "The Fun One", "relationship": "Friend", "context": "Always up for an adventure.", "emoji": "🎉"},
        ]


def _find_obsessions_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Find what shows, movies, books, celebrities, and food the user couldn't stop talking about."""
    print(f"[Wrapped]   - Starting obsessions analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries and find what this person COULDN'T STOP TALKING ABOUT in 2025.

CONVERSATIONS:
{context}

Identify specific things they mentioned multiple times or with enthusiasm:

1. **SHOW**: A TV show or series they talked about (Netflix, HBO, etc.)
2. **MOVIE**: A movie they discussed or recommended
3. **BOOK**: A book they read or mentioned
4. **CELEBRITY**: Any famous person - actor, entrepreneur, athlete, musician, influencer, etc.
5. **FOOD**: A food, drink, cuisine, or restaurant they mentioned enjoying or craving

Return as JSON (no markdown):
{{
    "show": "Name of the show",
    "movie": "Name of the movie", 
    "book": "Name of the book",
    "celebrity": "Name of the celebrity",
    "food": "Name of the food/drink/cuisine"
}}

Be specific with actual names. If something isn't clearly mentioned, make your best inference or use "Not mentioned"."""

        print(f"[Wrapped]     - Calling Gemini for obsessions...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        print(f"[Wrapped]     - Obsessions found: {result}")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in obsessions analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "show": "Not mentioned",
            "movie": "Not mentioned",
            "book": "Not mentioned",
            "celebrity": "Not mentioned",
            "food": "Not mentioned",
        }


def _find_movie_recommendations_with_llm(conversations: List[Conversation]) -> List[str]:
    """Find 5 movies the user would recommend to friends based on their conversations."""
    print(f"[Wrapped]   - Starting movie recommendations analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries and determine 5 MOVIES this person would recommend to friends.

CONVERSATIONS:
{context}

Based on:
- Movies they explicitly mentioned liking or recommending
- Their interests, tastes, and personality
- Topics they care about

Return as JSON (no markdown):
{{
    "movies": ["Movie 1", "Movie 2", "Movie 3", "Movie 4", "Movie 5"]
}}

Include a mix of movies they mentioned AND movies that match their vibe/interests. Use actual movie titles."""

        print(f"[Wrapped]     - Calling Gemini for movie recommendations...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        if isinstance(result, list):
            return result[:5]

        movies = result.get("movies", [])
        print(f"[Wrapped]     - Movie recommendations: {movies}")
        return movies[:5]

    except Exception as e:
        print(f"[Wrapped]     - ERROR in movie recommendations: {e}")
        import traceback

        traceback.print_exc()
        return [
            "The Social Network",
            "Inception",
            "Interstellar",
            "The Pursuit of Happyness",
            "The Shawshank Redemption",
        ]


def _find_struggles_and_wins_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Find the biggest struggle and personal win of the year."""
    print(f"[Wrapped]   - Starting struggles and wins analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries and identify the most significant STRUGGLE and WIN from this person's year.

CONVERSATIONS:
{context}

Identify:

1. **BIGGEST STRUGGLE**: The thing they struggled with most - could be health, relationships, work, mental health, a project, a decision, etc. What kept coming up as difficult?

2. **BIGGEST PERSONAL WIN**: A personal achievement or positive life event - relationship milestone, health goal, personal growth, family moment, hobby achievement, career milestone, etc.

Return as JSON (no markdown):
{{
    "struggle": {{
        "title": "Short title (3-5 words)",
        "description": "One sentence describing the struggle"
    }},
    "personal_win": {{
        "title": "Short title (3-5 words)",
        "description": "One sentence describing the win"
    }}
}}

Be specific and empathetic. These should feel personal and meaningful."""

        print(f"[Wrapped]     - Calling Gemini for struggles and wins...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        print(f"[Wrapped]     - Struggles and wins found")
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in struggles and wins analysis: {e}")
        import traceback

        traceback.print_exc()
        return {
            "struggle": {"title": "Balancing Everything", "description": "Finding time for everything that matters"},
            "personal_win": {"title": "Growth Mindset", "description": "You became more self-aware and intentional"},
        }


def generate_wrapped_2025(uid: str, year: int = 2025):
    """
    Generate Wrapped 2025 for a user.

    This fetches all 2025 data, computes analytics, generates LLM insights,
    and stores the result in Firestore.
    """
    import time

    start_time = time.time()

    try:
        print(f"[Wrapped] ========== Starting Wrapped 2025 generation for user {uid} ==========")
        print(f"[Wrapped] Date range: {YEAR_2025_START} to {YEAR_2025_END}")

        # Step 1: Fetch conversations
        step_start = time.time()
        _update_progress(uid, year, "Fetching conversations...", 0.1)
        print(f"[Wrapped] Step 1: Fetching conversations...")

        conversations_data = conversations_db.get_conversations_without_photos(
            uid=uid,
            limit=10000,  # Get all conversations for the year
            offset=0,
            include_discarded=False,
            statuses=["completed"],
            start_date=YEAR_2025_START,
            end_date=YEAR_2025_END,
        )

        conversations = [Conversation(**c) for c in conversations_data]
        print(
            f"[Wrapped] Step 1 complete: Found {len(conversations)} conversations for 2025 (took {time.time() - step_start:.2f}s)"
        )

        if conversations:
            print(f"[Wrapped]   - First conversation date: {conversations[0].created_at}")
            print(f"[Wrapped]   - Last conversation date: {conversations[-1].created_at}")

        # Step 2: Fetch action items
        step_start = time.time()
        _update_progress(uid, year, "Fetching action items...", 0.2)
        print(f"[Wrapped] Step 2: Fetching action items...")

        action_items = action_items_db.get_action_items(
            uid=uid,
            start_date=YEAR_2025_START,
            end_date=YEAR_2025_END,
            limit=10000,
        )
        print(
            f"[Wrapped] Step 2 complete: Found {len(action_items)} action items for 2025 (took {time.time() - step_start:.2f}s)"
        )

        completed_count = sum(1 for item in action_items if item.get("completed", False))
        print(f"[Wrapped]   - Completed: {completed_count}, Pending: {len(action_items) - completed_count}")

        # Step 3: Compute basic stats
        step_start = time.time()
        _update_progress(uid, year, "Computing statistics...", 0.3)
        print(f"[Wrapped] Step 3: Computing statistics...")

        result = _compute_all_stats(conversations, action_items)
        print(f"[Wrapped] Step 3 complete: Statistics computed (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Total hours: {result.get('total_time_hours', 0)}")
        print(f"[Wrapped]   - Top categories: {result.get('top_categories', [])}")
        print(f"[Wrapped]   - Signature phrase: {result.get('signature_phrase', {})}")

        # Step 4: Determine decision style with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Analyzing your personality...", 0.50)
        print(f"[Wrapped] Step 4: Analyzing decision style with Gemini...")

        decision_style = _determine_archetype_with_llm(conversations, result)
        result["decision_style"] = decision_style
        print(f"[Wrapped] Step 4 complete: Decision style analyzed (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Archetype: {decision_style.get('name')}")

        # Step 5: Find top phrases with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your catchphrases...", 0.58)
        print(f"[Wrapped] Step 5: Finding top phrases with Gemini...")

        top_phrases = _find_top_phrases_with_llm(conversations)
        result["top_phrases"] = top_phrases
        print(f"[Wrapped] Step 5 complete: Top phrases found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Top phrases: {len(top_phrases)} found")

        # Step 6: Analyze memorable days with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your memorable days...", 0.65)
        print(f"[Wrapped] Step 6: Analyzing memorable days with Gemini...")

        memorable_days = _analyze_memorable_days_with_llm(conversations)
        result["memorable_days"] = memorable_days
        print(f"[Wrapped] Step 6 complete: Memorable days analyzed (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Most fun day: {memorable_days.get('most_fun_day', {}).get('title', 'N/A')}")
        print(f"[Wrapped]   - Most productive day: {memorable_days.get('most_productive_day', {}).get('title', 'N/A')}")
        print(f"[Wrapped]   - Most stressful day: {memorable_days.get('most_stressful_day', {}).get('title', 'N/A')}")

        # Step 7: Find funniest event with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your funniest moment...", 0.72)
        print(f"[Wrapped] Step 7: Finding funniest event with Gemini...")

        funniest_event = _find_funniest_event_with_llm(conversations)
        result["funniest_event"] = funniest_event
        print(f"[Wrapped] Step 7 complete: Funniest event found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Funniest: {funniest_event.get('title', 'N/A')}")

        # Step 8: Find most embarrassing event with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your most cringe moment...", 0.78)
        print(f"[Wrapped] Step 8: Finding most embarrassing event with Gemini...")

        embarrassing_event = _find_most_embarrassing_event_with_llm(conversations)
        result["most_embarrassing_event"] = embarrassing_event
        print(f"[Wrapped] Step 8 complete: Embarrassing event found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Most embarrassing: {embarrassing_event.get('title', 'N/A')}")

        # Step 9: Find top buddies with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your top buddies...", 0.80)
        print(f"[Wrapped] Step 9: Finding top buddies with Gemini...")

        top_buddies = _find_top_buddies_with_llm(conversations)
        result["top_buddies"] = top_buddies
        print(f"[Wrapped] Step 9 complete: Top buddies found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Top buddies: {len(top_buddies)} found")

        # Step 10: Find obsessions (shows, movies, books, celebrities, food)
        step_start = time.time()
        _update_progress(uid, year, "Finding your obsessions...", 0.86)
        print(f"[Wrapped] Step 10: Finding obsessions with Gemini...")

        obsessions = _find_obsessions_with_llm(conversations)
        result["obsessions"] = obsessions
        print(f"[Wrapped] Step 10 complete: Obsessions found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Obsessions: {obsessions}")

        # Step 11: Find movie recommendations
        step_start = time.time()
        _update_progress(uid, year, "Generating movie recommendations...", 0.90)
        print(f"[Wrapped] Step 11: Finding movie recommendations with Gemini...")

        movie_recs = _find_movie_recommendations_with_llm(conversations)
        result["movie_recommendations"] = movie_recs
        print(f"[Wrapped] Step 11 complete: Movie recommendations found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Movies: {movie_recs}")

        # Step 12: Find struggles and wins
        step_start = time.time()
        _update_progress(uid, year, "Finding your wins and struggles...", 0.94)
        print(f"[Wrapped] Step 12: Finding struggles and wins with Gemini...")

        struggles_wins = _find_struggles_and_wins_with_llm(conversations)
        result["struggle"] = struggles_wins.get("struggle", {})
        result["personal_win"] = struggles_wins.get("personal_win", {})
        print(f"[Wrapped] Step 12 complete: Struggles and wins found (took {time.time() - step_start:.2f}s)")

        # Step 13: Save result
        step_start = time.time()
        _update_progress(uid, year, "Saving your Wrapped...", 0.98)
        print(f"[Wrapped] Step 13: Saving result to Firestore...")

        wrapped_db.update_wrapped_status(uid, year, WrappedStatus.DONE, result=result)
        print(f"[Wrapped] Step 13 complete: Result saved (took {time.time() - step_start:.2f}s)")

        # Step 14: Send notification
        step_start = time.time()
        print(f"[Wrapped] Step 14: Sending notification...")
        _send_wrapped_ready_notification(uid)
        print(f"[Wrapped] Step 14 complete: Notification sent (took {time.time() - step_start:.2f}s)")

        total_time = time.time() - start_time
        print(f"[Wrapped] ========== Wrapped 2025 generation completed for user {uid} ==========")
        print(f"[Wrapped] Total generation time: {total_time:.2f}s")

    except Exception as e:
        total_time = time.time() - start_time
        print(f"[Wrapped] ========== ERROR generating Wrapped 2025 for user {uid} ==========")
        print(f"[Wrapped] Error after {total_time:.2f}s: {e}")
        import traceback

        traceback.print_exc()
        wrapped_db.update_wrapped_status(uid, year, WrappedStatus.ERROR, error=str(e))


def _compute_all_stats(conversations: List[Conversation], action_items: List[dict]) -> Dict[str, Any]:
    """Compute all analytics stats from conversations and action items."""
    print(f"[Wrapped]   - Computing stats from {len(conversations)} conversations, {len(action_items)} action items")
    result = {}

    # === Section 1: Your Year in Numbers ===
    print(f"[Wrapped]   - Section 1: Year in Numbers...")
    total_conversations = len(conversations)
    result["total_conversations"] = total_conversations

    # Days active (unique days with conversations)
    active_days = set()
    for conv in conversations:
        if conv.created_at:
            active_days.add(conv.created_at.date())
    result["days_active"] = len(active_days)
    print(f"[Wrapped]     - Days active: {len(active_days)}")

    # Total time
    total_seconds = sum(_compute_conversation_duration(c) for c in conversations)
    result["total_time_hours"] = round(total_seconds / 3600, 1)
    print(f"[Wrapped]     - Total time: {result['total_time_hours']} hours across {total_conversations} conversations")

    # === Section 2: What You Talked About ===
    print(f"[Wrapped]   - Section 2: Topics & Categories...")
    category_counts = Counter()

    for conv in conversations:
        cat = conv.structured.category.value if conv.structured and conv.structured.category else "other"
        category_counts[cat] += 1

    # Top categories
    top_cats = category_counts.most_common(5)
    result["top_categories"] = [cat for cat, _ in top_cats]
    result["category_breakdown"] = [{"category": cat, "count": count} for cat, count in top_cats]

    # === Section 3: Conversations → Actions ===
    print(f"[Wrapped]   - Section 3: Action Items...")
    total_action_items = len(action_items)
    completed_items = sum(1 for item in action_items if item.get("completed", False))
    print(f"[Wrapped]     - {completed_items}/{total_action_items} action items completed")

    result["total_action_items"] = total_action_items
    result["completed_action_items"] = completed_items
    result["action_items_completion_rate"] = completed_items / total_action_items if total_action_items > 0 else 0

    # === Section 4: Voice Patterns ===
    print(f"[Wrapped]   - Section 4: Voice Patterns...")
    # Signature phrases
    phrase_counts = _find_signature_phrases(conversations)
    print(f"[Wrapped]     - Found {len(phrase_counts)} signature phrases")
    if phrase_counts:
        top_phrase = max(phrase_counts.items(), key=lambda x: x[1])
        result["signature_phrase"] = {
            "phrase": top_phrase[0],
            "count": top_phrase[1],
        }
    else:
        result["signature_phrase"] = None

    # Note: Decision style and top phrases computed via LLM in main function

    print(f"[Wrapped]   - All stats computed successfully")
    return result


def _send_wrapped_ready_notification(uid: str):
    """Send push notification that Wrapped is ready."""
    try:
        send_notification(
            user_id=uid,
            title="omi",
            body="Your Wrapped 2025 is ready! 🎁",
            data={
                "type": "wrapped_ready",
                "year": "2025",
                "navigate_to": "/wrapped/2025",
            },
        )
        print(f"[Wrapped] Notification sent successfully to user {uid}")
    except Exception as e:
        print(f"[Wrapped] ERROR: Failed to send notification to user {uid}: {e}")
