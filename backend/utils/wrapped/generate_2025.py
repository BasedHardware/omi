"""
Wrapped 2025 generation logic.

Computes analytics from user's 2025 data and generates LLM-based insights.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import database.wrapped as wrapped_db
import database.conversations as conversations_db
import database.action_items as action_items_db
from database.wrapped import WrappedStatus
from models.conversation import Conversation, CategoryEnum
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


def _get_month_name(month_num: int) -> str:
    """Get month name from number."""
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return months[month_num - 1] if 1 <= month_num <= 12 else "Unknown"


def _get_time_window(hour: int) -> str:
    """Get time window description from hour."""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


def _compute_conversation_duration(conv: Conversation) -> float:
    """Compute conversation duration in seconds."""
    # Try to get duration from transcript segments
    if conv.transcript_segments:
        max_end = max((seg.end for seg in conv.transcript_segments), default=0)
        if max_end > 0:
            return max_end

    # Fallback: estimate from created_at to finished_at or use a default
    return 300  # 5 minutes default


def _count_words_in_transcript(conv: Conversation) -> int:
    """Count total words in conversation transcript."""
    total = 0
    for seg in conv.transcript_segments:
        if seg.text:
            total += len(seg.text.split())
    return total


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


def _determine_conversation_style(conversations: List[Conversation]) -> str:
    """Determine if conversations are 'long & exploratory' or 'short & decisive'."""
    if not conversations:
        return "balanced"

    durations = [_compute_conversation_duration(conv) for conv in conversations]
    word_counts = [_count_words_in_transcript(conv) for conv in conversations]

    avg_duration = sum(durations) / len(durations) if durations else 0
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0

    # Thresholds (in seconds for duration, words for word count)
    if avg_duration > 600 or avg_words > 500:  # > 10 min avg or > 500 words
        return "Long & exploratory"
    elif avg_duration < 180 or avg_words < 150:  # < 3 min avg or < 150 words
        return "Short & decisive"
    else:
        return "Balanced & focused"


def _get_hour_histogram(conversations: List[Conversation]) -> Dict[int, int]:
    """Get histogram of conversation hours."""
    hour_counts = Counter()
    for conv in conversations:
        if conv.created_at:
            hour_counts[conv.created_at.hour] += 1
    return dict(hour_counts)


def _determine_archetype(stats: Dict[str, Any]) -> Dict[str, str]:
    """Determine decision style archetype based on stats."""
    # Simple heuristic-based selection
    completion_rate = stats.get("action_items_completion_rate", 0)
    conv_count = stats.get("total_conversations", 0)
    avg_duration = stats.get("avg_conversation_duration_seconds", 300)
    top_category = stats.get("dominant_category", "other")

    # Score each archetype
    scores = {}

    for archetype in DECISION_ARCHETYPES:
        score = 0
        traits = archetype["traits"]

        if "high_completion_rate" in traits and completion_rate > 0.6:
            score += 2
        if "high_conversation_count" in traits and conv_count > 100:
            score += 2
        if "short_conversations" in traits and avg_duration < 300:
            score += 1
        if "long_conversations" in traits and avg_duration > 600:
            score += 1
        if "high_action_items" in traits and stats.get("total_action_items", 0) > 50:
            score += 1
        if "work_or_business_focus" in traits and top_category in ["work", "business"]:
            score += 1
        if "technology_or_business_focus" in traits and top_category in ["technology", "business"]:
            score += 1
        if "diverse_categories" in traits and len(stats.get("top_categories", [])) >= 4:
            score += 1

        scores[archetype["name"]] = score

    # Pick the highest scoring archetype
    best = max(scores.items(), key=lambda x: x[1])
    selected = next(a for a in DECISION_ARCHETYPES if a["name"] == best[0])

    return {
        "name": selected["name"],
        "description": selected["description"],
    }


def _find_what_mattered_most_with_llm(conversations: List[Conversation]) -> Dict[str, str]:
    """Use Gemini to find the single word that captures what mattered most to this person in 2025."""
    print(f"[Wrapped]   - Starting 'what mattered most' analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars from {len(conversations)} conversations")

        prompt = f"""Analyze these conversation summaries from someone's entire 2025 year and determine the ONE WORD that best captures what mattered most to them.

CONVERSATIONS:
{context}

Based on the themes, emotions, topics, and patterns across ALL these conversations, what is the single most important thing to this person?

Think about:
- What topic comes up most passionately?
- What drives their decisions?
- What do they spend the most emotional energy on?
- What's the underlying theme across their year?

Return your answer as JSON (no markdown):
{{
    "word": "SingleWord",
    "reason": "One sentence explaining why this word captures what mattered most"
}}

The word should be meaningful and specific (not generic like "life" or "things"). Examples: Family, Growth, Career, Health, Creation, Freedom, Connection, Impact, Learning, Building, Love, Adventure, Purpose, Success, Balance, etc.

Pick the ONE word that would resonate most deeply with this person."""

        print(f"[Wrapped]     - Calling Gemini for what mattered most...")
        response = llm_gemini_flash.invoke(prompt)
        content = response.content.strip()
        print(f"[Wrapped]     - Gemini response received: {len(content)} chars")

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)

        # Handle list response
        if isinstance(result, list) and len(result) > 0:
            result = result[0]

        word = result.get("word", "Growth")
        reason = result.get("reason", "This theme appeared throughout your year.")

        print(f"[Wrapped]     - What mattered most: {word}")
        return {"word": word, "reason": reason}

    except Exception as e:
        print(f"[Wrapped]     - ERROR in what mattered most analysis: {e}")
        import traceback

        traceback.print_exc()
        return {"word": "Growth", "reason": "You focused on personal development throughout the year."}


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
        "description": "One sentence describing why this was the most fun day",
        "emoji": "Single relevant emoji"
    }},
    "most_productive_day": {{
        "date": "Month Day",
        "title": "Short catchy title (3-5 words)",
        "description": "One sentence describing the productivity",
        "emoji": "Single relevant emoji"
    }},
    "most_stressful_day": {{
        "date": "Month Day",
        "title": "Short catchy title (3-5 words)",
        "description": "One sentence describing the challenge (keep it light/empathetic)",
        "emoji": "Single relevant emoji"
    }}
}}

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
    "story": "2-3 sentence retelling of the funny moment in an engaging way",
    "emoji": "Single funny emoji"
}}

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
    "story": "2-3 sentence retelling of the embarrassing moment - keep it light and relatable, not mean",
    "emoji": "Single appropriate emoji"
}}

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


def _find_favorites_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Use Gemini to find the user's favorite word, person, and food from the year."""
    print(f"[Wrapped]   - Starting favorites analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries from someone's year and identify their FAVORITES.

CONVERSATIONS:
{context}

Based on positive mentions, enthusiasm, and frequency, identify:

1. **FAVORITE WORD**: A word or short phrase they use positively/enthusiastically often (not a common filler word)
2. **FAVORITE PERSON**: Someone they speak about positively, admire, or enjoy spending time with (use first name only or relationship like "Mom", "best friend")
3. **FAVORITE FOOD**: A food, drink, cuisine, or restaurant they mentioned enjoying

Return as JSON (no markdown):
{{
    "word": "the word or phrase",
    "person": "Name or relationship",
    "food": "food/drink/cuisine name"
}}

Be specific based on actual conversations. If something isn't clearly mentioned, make a reasonable inference from context."""

        print(f"[Wrapped]     - Calling Gemini for favorites...")
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

        print(
            f"[Wrapped]     - Favorites: word={result.get('word')}, person={result.get('person')}, food={result.get('food')}"
        )
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in favorites analysis: {e}")
        import traceback

        traceback.print_exc()
        return {"word": "Amazing", "person": "A close friend", "food": "Coffee"}


def _find_most_hated_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Use Gemini to find what the user disliked most - word, person, food."""
    print(f"[Wrapped]   - Starting most hated analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries from someone's year and identify things they DISLIKED or complained about.

CONVERSATIONS:
{context}

Based on negative mentions, complaints, frustrations, or avoidance, identify:

1. **MOST HATED WORD**: A word, phrase, or concept they complained about or expressed frustration with
2. **MOST HATED PERSON**: Someone they expressed frustration with or complained about (use first name only, or a description like "that coworker", "the neighbor" - keep it anonymous/light)
3. **MOST HATED FOOD**: A food, drink, or cuisine they mentioned disliking or avoiding

Return as JSON (no markdown):
{{
    "word": "the word or concept",
    "person": "Anonymous description or first name",
    "food": "food/drink name"
}}

Keep it lighthearted and fun - this is meant to be humorous, not mean-spirited. If something isn't clearly mentioned, make a reasonable inference."""

        print(f"[Wrapped]     - Calling Gemini for most hated...")
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

        print(
            f"[Wrapped]     - Most hated: word={result.get('word')}, person={result.get('person')}, food={result.get('food')}"
        )
        return result

    except Exception as e:
        print(f"[Wrapped]     - ERROR in most hated analysis: {e}")
        import traceback

        traceback.print_exc()
        return {"word": "Meetings", "person": "That one person", "food": "Cold coffee"}


def _find_obsessions_with_llm(conversations: List[Conversation]) -> Dict[str, Any]:
    """Find what shows, movies, books, and celebrities the user couldn't stop talking about."""
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

Return as JSON (no markdown):
{{
    "show": "Name of the show",
    "movie": "Name of the movie", 
    "book": "Name of the book",
    "celebrity": "Name of the celebrity"
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
    """Find the biggest struggle, personal win, and professional win of the year."""
    print(f"[Wrapped]   - Starting struggles and wins analysis with Gemini...")

    try:
        context = _build_conversations_context(conversations)
        print(f"[Wrapped]     - Built context: {len(context)} chars")

        prompt = f"""Analyze these conversation summaries and identify the most significant STRUGGLE and WINS from this person's year.

CONVERSATIONS:
{context}

Identify:

1. **BIGGEST STRUGGLE**: The thing they struggled with most - could be health, relationships, work, mental health, a project, a decision, etc. What kept coming up as difficult?

2. **BIGGEST PERSONAL WIN**: A personal achievement or positive life event - relationship milestone, health goal, personal growth, family moment, hobby achievement, etc.

3. **BIGGEST PROFESSIONAL WIN**: A work/career achievement - promotion, project success, new job, business milestone, recognition, learning new skill, etc.

Return as JSON (no markdown):
{{
    "struggle": {{
        "title": "Short title (3-5 words)",
        "description": "One sentence describing the struggle"
    }},
    "personal_win": {{
        "title": "Short title (3-5 words)",
        "description": "One sentence describing the win"
    }},
    "professional_win": {{
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
            "professional_win": {"title": "Leveling Up", "description": "You made significant progress in your career"},
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
        print(f"[Wrapped]   - Decision style: {result.get('decision_style', {}).get('name', 'Unknown')}")
        print(f"[Wrapped]   - Signature phrase: {result.get('signature_phrase', {})}")

        # Step 4: Find what mattered most with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding what mattered most...", 0.7)
        print(f"[Wrapped] Step 4: Finding what mattered most with Gemini...")

        what_mattered = _find_what_mattered_most_with_llm(conversations)
        result["what_mattered_most"] = what_mattered
        print(f"[Wrapped] Step 4 complete: What mattered most found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Word: {what_mattered.get('word')}")
        print(f"[Wrapped]   - Reason: {what_mattered.get('reason')}")

        # Step 5: Analyze memorable days with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your memorable days...", 0.75)
        print(f"[Wrapped] Step 5: Analyzing memorable days with Gemini...")

        memorable_days = _analyze_memorable_days_with_llm(conversations)
        result["memorable_days"] = memorable_days
        print(f"[Wrapped] Step 5 complete: Memorable days analyzed (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Most fun day: {memorable_days.get('most_fun_day', {}).get('title', 'N/A')}")
        print(f"[Wrapped]   - Most productive day: {memorable_days.get('most_productive_day', {}).get('title', 'N/A')}")
        print(f"[Wrapped]   - Most stressful day: {memorable_days.get('most_stressful_day', {}).get('title', 'N/A')}")

        # Step 6: Find funniest event with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your funniest moment...", 0.82)
        print(f"[Wrapped] Step 6: Finding funniest event with Gemini...")

        funniest_event = _find_funniest_event_with_llm(conversations)
        result["funniest_event"] = funniest_event
        print(f"[Wrapped] Step 6 complete: Funniest event found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Funniest: {funniest_event.get('title', 'N/A')}")

        # Step 7: Find most embarrassing event with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your most cringe moment...", 0.88)
        print(f"[Wrapped] Step 7: Finding most embarrassing event with Gemini...")

        embarrassing_event = _find_most_embarrassing_event_with_llm(conversations)
        result["most_embarrassing_event"] = embarrassing_event
        print(f"[Wrapped] Step 7 complete: Embarrassing event found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Most embarrassing: {embarrassing_event.get('title', 'N/A')}")

        # Step 8: Find favorites with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding your favorites...", 0.88)
        print(f"[Wrapped] Step 8: Finding favorites with Gemini...")

        favorites = _find_favorites_with_llm(conversations)
        result["favorites"] = favorites
        print(f"[Wrapped] Step 8 complete: Favorites found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Favorites: {favorites}")

        # Step 9: Find most hated with Gemini
        step_start = time.time()
        _update_progress(uid, year, "Finding what you hated...", 0.92)
        print(f"[Wrapped] Step 9: Finding most hated with Gemini...")

        most_hated = _find_most_hated_with_llm(conversations)
        result["most_hated"] = most_hated
        print(f"[Wrapped] Step 9 complete: Most hated found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Most hated: {most_hated}")

        # Step 10: Find obsessions (shows, movies, books, celebrities)
        step_start = time.time()
        _update_progress(uid, year, "Finding your obsessions...", 0.90)
        print(f"[Wrapped] Step 10: Finding obsessions with Gemini...")

        obsessions = _find_obsessions_with_llm(conversations)
        result["obsessions"] = obsessions
        print(f"[Wrapped] Step 10 complete: Obsessions found (took {time.time() - step_start:.2f}s)")
        print(f"[Wrapped]   - Obsessions: {obsessions}")

        # Step 11: Find movie recommendations
        step_start = time.time()
        _update_progress(uid, year, "Generating movie recommendations...", 0.92)
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
        result["professional_win"] = struggles_wins.get("professional_win", {})
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

    # Total time
    total_seconds = sum(_compute_conversation_duration(c) for c in conversations)
    result["total_time_seconds"] = total_seconds
    result["total_time_hours"] = round(total_seconds / 3600, 1)
    print(f"[Wrapped]     - Total time: {result['total_time_hours']} hours across {total_conversations} conversations")

    # First and last conversation
    if conversations:
        # Sort by created_at
        sorted_convs = sorted(conversations, key=lambda c: c.created_at or datetime.min.replace(tzinfo=timezone.utc))

        first = sorted_convs[0]
        last = sorted_convs[-1]

        result["first_conversation"] = {
            "date": first.created_at.strftime("%B %d, %Y") if first.created_at else "Unknown",
            "title": first.structured.title if first.structured else "Untitled",
        }
        result["last_conversation"] = {
            "date": last.created_at.strftime("%B %d, %Y") if last.created_at else "Unknown",
            "title": last.structured.title if last.structured else "Untitled",
        }
    else:
        result["first_conversation"] = None
        result["last_conversation"] = None

    # Monthly breakdown
    monthly_counts = Counter()
    for conv in conversations:
        if conv.created_at:
            monthly_counts[conv.created_at.month] += 1

    if monthly_counts:
        most_active_month = max(monthly_counts.items(), key=lambda x: x[1])
        least_active_month = min(monthly_counts.items(), key=lambda x: x[1])
        result["most_active_month"] = {
            "name": _get_month_name(most_active_month[0]),
            "count": most_active_month[1],
        }
        result["least_active_month"] = {
            "name": _get_month_name(least_active_month[0]),
            "count": least_active_month[1],
        }
    else:
        result["most_active_month"] = None
        result["least_active_month"] = None

    # === Section 2: What You Talked About ===
    print(f"[Wrapped]   - Section 2: Topics & Categories...")
    category_counts = Counter()
    category_durations = defaultdict(list)

    for conv in conversations:
        cat = conv.structured.category.value if conv.structured and conv.structured.category else "other"
        category_counts[cat] += 1
        category_durations[cat].append(_compute_conversation_duration(conv))

    # Top categories
    top_cats = category_counts.most_common(5)
    result["top_categories"] = [cat for cat, _ in top_cats]
    result["category_breakdown"] = [{"category": cat, "count": count} for cat, count in top_cats]

    # Dominant category
    result["dominant_category"] = top_cats[0][0] if top_cats else "other"

    # Longest conversations by category (avg duration)
    if category_durations:
        avg_durations = {cat: sum(durs) / len(durs) for cat, durs in category_durations.items()}
        longest_cat = max(avg_durations.items(), key=lambda x: x[1])
        result["longest_conversations_category"] = {
            "category": longest_cat[0],
            "avg_duration_minutes": round(longest_cat[1] / 60, 1),
        }
    else:
        result["longest_conversations_category"] = None

    # === Section 3: Conversations → Actions ===
    print(f"[Wrapped]   - Section 3: Action Items...")
    total_action_items = len(action_items)
    completed_items = sum(1 for item in action_items if item.get("completed", False))
    print(f"[Wrapped]     - {completed_items}/{total_action_items} action items completed")

    result["total_action_items"] = total_action_items
    result["completed_action_items"] = completed_items
    result["action_items_completion_rate"] = completed_items / total_action_items if total_action_items > 0 else 0

    # Most productive month (by completed action items)
    monthly_completed = Counter()
    monthly_created = Counter()
    for item in action_items:
        created_at = item.get("created_at")
        completed_at = item.get("completed_at")

        if created_at:
            if hasattr(created_at, 'month'):
                monthly_created[created_at.month] += 1
        if completed_at and item.get("completed"):
            if hasattr(completed_at, 'month'):
                monthly_completed[completed_at.month] += 1

    if monthly_completed:
        most_productive = max(monthly_completed.items(), key=lambda x: x[1])
        result["most_productive_month"] = {
            "name": _get_month_name(most_productive[0]),
            "completed_count": most_productive[1],
        }
    elif monthly_created:
        most_created = max(monthly_created.items(), key=lambda x: x[1])
        result["most_productive_month"] = {
            "name": _get_month_name(most_created[0]),
            "completed_count": most_created[1],
        }
    else:
        result["most_productive_month"] = None

    # === Section 4: Emotional & Energy Signals ===
    print(f"[Wrapped]   - Section 4: Energy Signals...")
    # Calm vs intense months (using duration variance as proxy)
    monthly_avg_duration = {}
    monthly_durations = defaultdict(list)
    for conv in conversations:
        if conv.created_at:
            monthly_durations[conv.created_at.month].append(_compute_conversation_duration(conv))

    for month, durs in monthly_durations.items():
        monthly_avg_duration[month] = sum(durs) / len(durs) if durs else 0

    if monthly_avg_duration:
        # Lower avg duration = more intense (many short conversations)
        # Higher avg duration = more calm (fewer, longer conversations)
        calmest = max(monthly_avg_duration.items(), key=lambda x: x[1])
        most_intense = min(monthly_avg_duration.items(), key=lambda x: x[1])
        result["calmest_month"] = _get_month_name(calmest[0])
        result["most_intense_month"] = _get_month_name(most_intense[0])
    else:
        result["calmest_month"] = None
        result["most_intense_month"] = None

    # Late night conversations (10 PM - 4 AM)
    late_night_count = sum(
        1 for conv in conversations if conv.created_at and (conv.created_at.hour >= 22 or conv.created_at.hour < 4)
    )
    result["late_night_conversation_count"] = late_night_count

    # Hour histogram (convert int keys to strings for Firestore compatibility)
    hour_histogram = _get_hour_histogram(conversations)
    result["hour_histogram"] = {str(k): v for k, v in hour_histogram.items()}

    # === Section 5: Voice Patterns ===
    print(f"[Wrapped]   - Section 5: Voice Patterns...")
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

    # Conversation style
    result["conversation_style"] = _determine_conversation_style(conversations)

    # Most common time window
    if hour_histogram:
        most_common_hour = max(hour_histogram.items(), key=lambda x: x[1])[0]
        result["most_common_time_window"] = _get_time_window(most_common_hour)
    else:
        result["most_common_time_window"] = None

    # Average duration for archetype calculation
    result["avg_conversation_duration_seconds"] = total_seconds / total_conversations if total_conversations > 0 else 0

    # === Section 6: Decision Style ===
    print(f"[Wrapped]   - Section 6: Decision Style...")
    result["decision_style"] = _determine_archetype(result)
    print(f"[Wrapped]     - Archetype: {result['decision_style'].get('name', 'Unknown')}")

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
