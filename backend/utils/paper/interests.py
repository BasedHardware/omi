"""What the reader cares about, learned from their own record.

Every personalization system reads stated preference — topics you typed, links
you clicked. This reads lived context instead: what was actually discussed, what
was actually on screen, what was actually decided. The output is the scoring
rubric for everything external the edition prints.

The profile is cached for a day. It is derived from a fortnight of record, so
recomputing it per request would burn a model call to produce the same answer.

**Evidence is mandatory.** Every interest carries the line from the record that
demonstrates it. An interest the model cannot ground is dropped, because a
rubric built on invented preferences quietly makes every downstream section
wrong in a way nobody can see.
"""

import json
import logging
import re
from datetime import date, timedelta

import database.conversations as conversations_db
import database.daily_summaries as daily_summaries_db
from database import redis_db
from models.paper import Interest, InterestProfile
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import Features, track_usage
from utils.log_sanitizer import sanitize

from .context import DayContext, day_bounds

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r'^\s*```(?:json)?\s*|\s*```\s*$')

# A fortnight is long enough for a real interest to repeat and short enough that
# last month's finished project stops ranking today's reading.
PROFILE_WINDOW_DAYS = 14

CACHE_TTL_SECONDS = 24 * 60 * 60

MAX_INTERESTS = 8

_PROMPT = """You are building a reading profile for one person from their own captured record.

THE RECORD (last {days} days of their conversations, screen activity and day summaries):
{record}

HARD RULE: every interest must be grounded in the record above. The `evidence` field must \
quote or closely paraphrase something actually in it. If you cannot ground an interest, \
leave it out. Do not add interests that merely seem plausible for someone in their field.

Return only JSON, no fences:
{{
  "thesis": "<one sentence: what this person is actually working on right now>",
  "interests": [
    {{
      "topic": "<specific enough to rank against. 'memory retrieval at scale', not 'AI'>",
      "evidence": "<what in the record shows this>",
      "weight": <0.0-1.0, how central it is>
    }}
  ],
  "exclusions": ["<kinds of content to drop even when topically close, inferred from what they skip or dismiss>"],
  "people": ["<names that recur in their record>"]
}}

At most {max_interests} interests, most central first."""


def _cache_key(uid: str, day: date) -> str:
    return f'paper:interests:{uid}:{day.isoformat()}'


def _parse(raw: str) -> dict:
    cleaned = _FENCE_RE.sub('', raw or '').strip()
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _window_record(uid: str, day: date) -> tuple[list[str], int]:
    """Flatten the profile window into grounding lines.

    Returns the lines and how many days actually carried data, so the caller can
    report a thin profile rather than presenting it as confident.
    """
    start = day - timedelta(days=PROFILE_WINDOW_DAYS)
    lines: list[str] = []
    days_with_data = 0

    try:
        summaries = daily_summaries_db.get_daily_summaries(
            uid,
            limit=PROFILE_WINDOW_DAYS + 1,
            start_date=start.isoformat(),
            end_date=day.isoformat(),
        )
    except Exception as e:  # noqa: BLE001 — a thin profile beats no edition.
        logger.warning('paper: interest window summaries failed: %s', sanitize(str(e)))
        summaries = []

    for summary in summaries or []:
        had_content = False
        if summary.get('headline'):
            lines.append(f"[{summary.get('date')}] {summary['headline']}")
            had_content = True
        for highlight in (summary.get('highlights') or [])[:4]:
            topic = (highlight or {}).get('topic') or ''
            detail = (highlight or {}).get('summary') or ''
            if topic or detail:
                lines.append(f"  - {topic}: {detail}".rstrip(': '))
                had_content = True
        for decision in (summary.get('decisions_made') or [])[:3]:
            if (decision or {}).get('decision'):
                lines.append(f"  - Decided: {decision['decision']}")
                had_content = True
        for question in (summary.get('unresolved_questions') or [])[:3]:
            if (question or {}).get('question'):
                lines.append(f"  - Asked: {question['question']}")
                had_content = True
        if had_content:
            days_with_data += 1

    start_dt, _ = day_bounds(start)
    _, end_dt = day_bounds(day)
    try:
        conversations = conversations_db.get_conversations(uid, limit=80, start_date=start_dt, end_date=end_dt)
    except Exception as e:  # noqa: BLE001
        logger.warning('paper: interest window conversations failed: %s', sanitize(str(e)))
        conversations = []

    for conversation in conversations or []:
        structured = conversation.get('structured') or {}
        title = structured.get('title') or ''
        overview = structured.get('overview') or ''
        if title or overview:
            lines.append(f"  - Conversation: {title}. {overview}".strip())

    return lines[:220], days_with_data


def build_profile(uid: str, day: date) -> InterestProfile:
    """Derive the reader's interest profile for ``day``.

    Returns an empty (unusable) profile rather than a guessed one when the
    record is too thin or the model call fails. Callers check ``is_usable``
    before ranking anything against it.
    """
    lines, days_with_data = _window_record(uid, day)
    if not lines:
        logger.info('paper: no record in the interest window, profile unusable')
        return InterestProfile(generated_at=day.isoformat(), covers_days=0)

    prompt = _PROMPT.format(
        days=PROFILE_WINDOW_DAYS,
        record='\n'.join(lines),
        max_interests=MAX_INTERESTS,
    )

    try:
        with track_usage(uid, Features.PAPER):
            response = get_llm('paper', cache_key='omi-paper-interests').invoke(prompt)
        content = getattr(response, 'content', response)
        payload = _parse(content if isinstance(content, str) else str(content))
    except Exception as e:  # noqa: BLE001 — an unusable profile is handled; a raise is not.
        logger.warning('paper: interest profile generation failed: %s', sanitize(str(e)))
        return InterestProfile(generated_at=day.isoformat(), covers_days=days_with_data)

    interests: list[Interest] = []
    for raw in (payload.get('interests') or [])[:MAX_INTERESTS]:
        if not isinstance(raw, dict):
            continue
        topic = str(raw.get('topic') or '').strip()
        evidence = str(raw.get('evidence') or '').strip()
        # Ungrounded interests are the failure mode this whole file exists to avoid.
        if not topic or not evidence:
            continue
        try:
            weight = float(raw.get('weight', 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        interests.append(Interest(topic=topic, evidence=evidence, weight=max(0.0, min(1.0, weight))))

    return InterestProfile(
        generated_at=day.isoformat(),
        covers_days=days_with_data,
        thesis=str(payload.get('thesis') or '').strip(),
        interests=interests,
        exclusions=[str(x).strip() for x in (payload.get('exclusions') or []) if str(x).strip()][:10],
        people=[str(x).strip() for x in (payload.get('people') or []) if str(x).strip()][:20],
    )


def get_profile(uid: str, day: date, context: DayContext | None = None) -> InterestProfile:
    """Cached read of the interest profile for ``day``.

    ``context`` is accepted so a caller that already gathered the day does not
    force a second set of reads; it is unused when the cache hits.
    """
    key = _cache_key(uid, day)
    try:
        cached = redis_db.r.get(key)
        if cached:
            return InterestProfile.model_validate_json(cached)
    except Exception as e:  # noqa: BLE001 — a cold cache is not an error.
        logger.info('paper: interest cache read skipped: %s', sanitize(str(e)))

    profile = build_profile(uid, day)

    if profile.is_usable:
        try:
            redis_db.r.setex(key, CACHE_TTL_SECONDS, profile.model_dump_json())
        except Exception as e:  # noqa: BLE001
            logger.info('paper: interest cache write skipped: %s', sanitize(str(e)))

    return profile


def rubric_text(profile: InterestProfile) -> str:
    """The profile as prompt text, for ranking candidates against it."""
    if not profile.is_usable:
        return ''
    lines = []
    if profile.thesis:
        lines.append(f"What they are working on: {profile.thesis}")
    lines.append('What they care about, most central first:')
    for interest in profile.interests:
        lines.append(f"  - {interest.topic} (weight {interest.weight:.1f}) — because: {interest.evidence}")
    if profile.exclusions:
        lines.append('Do not surface: ' + '; '.join(profile.exclusions))
    return '\n'.join(lines)
