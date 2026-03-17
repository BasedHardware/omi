"""
LLM-based purpose detection for fair-use anti-abuse.

Classifies whether a user's recent conversations indicate non-personal-use
patterns (audiobook transcription, podcast transcription, pre-recorded content).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import database.conversations as conversations_db
from utils.llm.clients import llm_mini

logger = logging.getLogger(__name__)

CLASSIFIER_MODEL = os.getenv('FAIR_USE_CLASSIFIER_MODEL', 'gpt-4.1-mini')
CLASSIFIER_LOOKBACK_DAYS = int(os.getenv('FAIR_USE_CLASSIFIER_LOOKBACK_DAYS', '7'))
CLASSIFIER_MAX_CONVERSATIONS = 30

# ---------------------------------------------------------------------------
# Prompt recipes for different abuse scenarios
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a fair-use policy analyst for Omi, a personal AI wearable device designed for recording personal conversations and meetings.

Your job is to analyze a user's recent conversation metadata and determine if their usage matches the intended personal-use purpose, or if they are misusing the device for non-personal content transcription.

IMPORTANT RULES:
- You must be CONSERVATIVE. Only flag usage that clearly indicates misuse.
- False positives hurt real users. When in doubt, classify as legitimate.
- A single suspicious conversation is NOT enough to flag abuse. Look for PATTERNS.
- High usage alone is NOT abuse. Someone can have back-to-back meetings all day.

LEGITIMATE USE (do NOT flag):
- Personal conversations of any length
- Work meetings, standups, brainstorms
- Live lectures or classes the user attends in person
- Phone calls, video calls
- Conferences or all-day events
- Group discussions, interviews
- Any real-time human conversation

MISUSE PATTERNS (flag these):
- Audiobook transcription: long single-speaker sessions with book-like titles/content
- Podcast transcription: sessions matching known podcast formats/names
- TV/movie transcription: entertainment content titles, episode patterns
- Pre-recorded content: uniform session lengths (e.g., all ~30min), media-like titles
- Commercial transcription service: extremely high volume with no personal engagement (zero or near-zero memories created vs hundreds of conversations)

OUTPUT FORMAT (strict JSON):
{
  "abuse_score": <float 0.0-1.0>,
  "abuse_type": "<none|audiobook|podcast|prerecorded|tv_movie|commercial|unknown>",
  "confidence": <float 0.0-1.0>,
  "evidence": [
    {"conversation_id": "...", "title": "...", "reason": "..."}
  ],
  "reasoning": "<brief explanation of your analysis>"
}

SCORING GUIDE:
- 0.0-0.3: Clearly legitimate personal use
- 0.3-0.5: Some unusual patterns but insufficient evidence
- 0.5-0.7: Suspicious but not conclusive
- 0.7-0.9: Strong evidence of misuse
- 0.9-1.0: Unambiguous misuse (e.g., "Harry Potter Chapter 12" titles)
"""

RECIPE_AUDIOBOOK = """ADDITIONAL FOCUS: Audiobook Detection
Look specifically for:
- Titles containing book names, chapter numbers, author names
- Very long sessions (>1 hour) with single speaker
- Sequential chapter patterns across sessions
- Literary/narrative content in overviews
"""

RECIPE_PODCAST = """ADDITIONAL FOCUS: Podcast Detection
Look specifically for:
- Titles matching known podcast formats ("Episode XX", "EP.", show names)
- Consistent session durations (~30-90 min, matching episode lengths)
- Interview/show format descriptions in overviews
- Media/entertainment categories
"""

RECIPE_PRERECORDED = """ADDITIONAL FOCUS: Pre-recorded Content Detection
Look specifically for:
- Highly uniform session durations (low variance)
- No real interaction or memory creation
- TV show, movie, or lecture titles
- Media consumption patterns (binge-watching transcription)
"""

RECIPE_COMMERCIAL = """ADDITIONAL FOCUS: Commercial Use Detection
Look specifically for:
- Extremely high conversation count with very few memories
- Conversations that look like customer service calls or business dictation
- No personal engagement patterns
- Usage patterns suggesting a transcription service
"""


def _select_recipes(conversation_summaries: list) -> str:
    """Select which additional detection recipes to apply based on conversation patterns."""
    recipes = []

    if not conversation_summaries:
        return ""

    # Check for signs that suggest specific recipes
    titles = [c.get('title', '') for c in conversation_summaries]
    durations = [c.get('duration_minutes', 0) for c in conversation_summaries]
    categories = [c.get('category', '') for c in conversation_summaries]

    # Long sessions suggest audiobook/podcast
    long_sessions = sum(1 for d in durations if d > 60)
    if long_sessions >= 3:
        recipes.append(RECIPE_AUDIOBOOK)

    # Consistent durations suggest pre-recorded
    if len(durations) >= 5:
        avg_dur = sum(durations) / len(durations)
        if avg_dur > 0:
            variance = sum((d - avg_dur) ** 2 for d in durations) / len(durations)
            cv = (variance**0.5) / avg_dur if avg_dur > 0 else 0
            if cv < 0.3:  # Low coefficient of variation = uniform durations
                recipes.append(RECIPE_PRERECORDED)

    # Very high count with few unique categories
    if len(conversation_summaries) >= 20:
        unique_cats = len(set(categories))
        if unique_cats <= 3:
            recipes.append(RECIPE_COMMERCIAL)

    # Medium-duration sessions suggest podcast
    medium_sessions = sum(1 for d in durations if 25 <= d <= 90)
    if medium_sessions >= 5:
        recipes.append(RECIPE_PODCAST)

    return '\n'.join(recipes)


def _prepare_conversation_summaries(uid: str) -> list:
    """Fetch recent conversations and extract metadata for classification."""
    start_date = datetime.utcnow() - timedelta(days=CLASSIFIER_LOOKBACK_DAYS)

    conversations = conversations_db.get_conversations(
        uid,
        limit=CLASSIFIER_MAX_CONVERSATIONS,
        start_date=start_date,
    )

    summaries = []
    for conv in conversations:
        structured = conv.get('structured', {}) or {}
        started = conv.get('started_at')
        ended = conv.get('finished_at') or conv.get('ended_at')

        duration_minutes = 0
        if started and ended:
            try:
                if isinstance(started, datetime) and isinstance(ended, datetime):
                    duration_minutes = (ended - started).total_seconds() / 60
            except Exception:
                pass

        summaries.append(
            {
                'conversation_id': conv.get('id', ''),
                'title': structured.get('title', '') or '',
                'overview': (structured.get('overview', '') or '')[:200],  # Truncate for token efficiency
                'category': structured.get('category', '') or '',
                'duration_minutes': round(duration_minutes, 1),
                'source': conv.get('source', ''),
                'created_at': str(conv.get('created_at', '')),
            }
        )

    return summaries


async def classify_user_purpose(uid: str) -> dict:
    """Run LLM classification on a user's recent conversations.

    Returns a dict matching the ClassifierResult model:
      {abuse_score, abuse_type, confidence, evidence, model, prompt_version}
    """
    default_result = {
        'abuse_score': 0.0,
        'abuse_type': 'none',
        'confidence': 0.0,
        'evidence': [],
        'model': CLASSIFIER_MODEL,
        'prompt_version': 'v1',
    }

    try:
        summaries = _prepare_conversation_summaries(uid)
        if not summaries:
            logger.info(f'fair_use: no conversations to classify for {uid}')
            return default_result

        additional_recipes = _select_recipes(summaries)

        user_message = f"""Analyze the following {len(summaries)} recent conversations from user and determine if their usage is legitimate personal use or potential misuse.

{additional_recipes}

CONVERSATIONS:
{json.dumps(summaries, indent=2, default=str)}

Respond with ONLY the JSON output, no other text."""

        response = await llm_mini.ainvoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
        )

        content = response.content if hasattr(response, 'content') else str(response)

        # Parse JSON from response
        # Handle potential markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        result = json.loads(content.strip())

        # Validate and clamp
        result['abuse_score'] = max(0.0, min(1.0, float(result.get('abuse_score', 0.0))))
        result['confidence'] = max(0.0, min(1.0, float(result.get('confidence', 0.0))))
        result['abuse_type'] = result.get('abuse_type', 'none')
        result['evidence'] = result.get('evidence', [])[:10]  # Cap evidence entries
        result['model'] = CLASSIFIER_MODEL
        result['prompt_version'] = 'v1'

        return result

    except json.JSONDecodeError as e:
        logger.error(f'fair_use: classifier JSON parse error for {uid}: {e}')
        return default_result
    except Exception as e:
        logger.error(f'fair_use: classifier error for {uid}: {e}')
        return default_result
