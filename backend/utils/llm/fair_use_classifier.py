"""
LLM-based purpose detection for fair-use fair-use.

Classifies whether a user's recent conversations indicate non-personal-use
patterns (audiobook transcription, podcast transcription, pre-recorded content).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import database.conversations as conversations_db
from langchain_openai import ChatOpenAI
from utils.llm.usage_tracker import get_usage_callback

logger = logging.getLogger(__name__)

CLASSIFIER_MODEL = os.getenv('FAIR_USE_CLASSIFIER_MODEL', 'gpt-5.1')
_classifier_llm = ChatOpenAI(model=CLASSIFIER_MODEL, callbacks=[get_usage_callback()])
CLASSIFIER_LOOKBACK_DAYS = int(os.getenv('FAIR_USE_CLASSIFIER_LOOKBACK_DAYS', '7'))
CLASSIFIER_MAX_CONVERSATIONS = 30

# ---------------------------------------------------------------------------
# Prompt recipes for different non-personal usage scenarios
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a fair-use cost-protection analyst for Omi, a personal AI wearable device.

OBJECTIVE: Protect against abuse that causes excessive Deepgram transcription costs. The concern is users who BOTH use the device for the wrong purpose AND consume disproportionate resources. Wrong purpose alone at low volume is NOT a concern.

This classifier is ONLY called when a user has already exceeded speech-hour soft caps. Your job is to determine whether that high usage is legitimate (heavy personal use) or abusive (non-personal bulk transcription).

CRITICAL RULES:
- Be EXTREMELY CONSERVATIVE. False positives restrict real users. When in doubt, score LOW.
- A single suspicious conversation is NOT enough. Require a clear PATTERN across many sessions.
- High usage of personal conversations is 100% LEGITIMATE — never flag this.
- Someone recording 10 hours of work meetings per day is a power user, NOT an abuser.
- Only flag patterns where the user is clearly using Omi as a bulk transcription tool for pre-recorded or non-live content.

LEGITIMATE USE (score 0.0-0.3, do NOT flag regardless of volume):
- Personal conversations (any length, any frequency)
- Work meetings, standups, brainstorms, 1-on-1s
- Live lectures or classes the user physically attends
- Phone calls, video calls, FaceTime
- Conferences, all-day events, workshops
- Group discussions, interviews, therapy sessions
- Any real-time live human interaction
- Mixed usage with some long sessions

ABUSE = HIGH VOLUME + WRONG PURPOSE (score 0.7+ only when BOTH conditions):
- Audiobook transcription: long single-speaker sessions with book-like titles, chapter numbers
- Podcast feed transcription: sessions matching known podcast formats/names at scale
- TV/movie transcription: entertainment content at scale
- Pre-recorded content farm: uniform session lengths, media-like titles, no personal engagement
- Commercial transcription service: massive volume, zero personal context, API-like patterns

NOT ABUSE (even if wrong purpose):
- Someone who transcribed one podcast episode → low volume, not a cost concern
- A few audiobook chapters → not enough volume to matter
- Occasional non-personal use mixed with personal → normal usage

OUTPUT FORMAT (strict JSON):
{
  "misuse_score": <float 0.0-1.0>,
  "usage_type": "<none|audiobook|podcast|prerecorded|tv_movie|commercial|unknown>",
  "confidence": <float 0.0-1.0>,
  "evidence": [
    {"conversation_id": "...", "title": "...", "reason": "..."}
  ],
  "reasoning": "<brief explanation: what pattern you see and why it's a cost concern>"
}

SCORING GUIDE:
- 0.0-0.2: Clearly legitimate — personal conversations, meetings, live events
- 0.2-0.4: High usage but looks personal — power user with lots of meetings/calls
- 0.4-0.6: Some non-personal patterns but mixed with personal use — lean toward legitimate
- 0.6-0.7: Majority non-personal content at high volume — borderline, gather more evidence
- 0.7-0.85: Strong pattern of bulk non-personal transcription driving high costs
- 0.85-1.0: Unambiguous bulk abuse (e.g., sequential "Chapter 1, 2, 3..." audiobook titles)
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
      {misuse_score, usage_type, confidence, evidence, model, prompt_version}
    """
    default_result = {
        'misuse_score': 0.0,
        'usage_type': 'none',
        'confidence': 0.0,
        'evidence': [],
        'model': CLASSIFIER_MODEL,
        'prompt_version': 'v2',
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

        response = await _classifier_llm.ainvoke(
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
        result['misuse_score'] = max(0.0, min(1.0, float(result.get('misuse_score', 0.0))))
        result['confidence'] = max(0.0, min(1.0, float(result.get('confidence', 0.0))))
        result['usage_type'] = result.get('usage_type', 'none')
        result['evidence'] = result.get('evidence', [])[:10]  # Cap evidence entries
        result['model'] = CLASSIFIER_MODEL
        result['prompt_version'] = 'v2'

        return result

    except json.JSONDecodeError as e:
        logger.error(f'fair_use: classifier JSON parse error for {uid}: {e}')
        return default_result
    except Exception as e:
        logger.error(f'fair_use: classifier error for {uid}: {e}')
        return default_result
