"""Episode detail budget derived from available speech and recorded duration.

This is a prompt/output bound only. It never becomes a freshness fingerprint.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from config.episodes import (
    COMPOSER_MAX_CHAPTERS,
    COMPOSER_DETAIL_MAX_CHAPTERS,
    COMPOSER_DETAIL_WORDS_PER_CHAPTER,
    COMPOSER_DETAIL_MAX_WORDS,
    COMPOSER_DETAIL_MIN_WORDS,
    COMPOSER_DETAIL_WORD_RATIO,
    COMPOSER_DETAIL_WORDS_PER_MINUTE,
    episode_composer_detail_enabled,
)
from utils.conversations.recorded_time import conversation_span


def detail_budget(members: Sequence[Mapping[str, Any]]) -> tuple[int, str]:
    """A 4h/30k-word episode targets 2550..3450 words with up to 15 chapters."""
    if not episode_composer_detail_enabled():
        return COMPOSER_MAX_CHAPTERS, ''
    words = sum(len(str(s.get('text') or '').split()) for row in members for s in row.get('transcript_segments') or [])
    seconds = 0.0
    for row in members:
        span = conversation_span(row)
        if span is not None:
            seconds += max(0.0, (span.recorded_end - span.recorded_start).total_seconds())
    scale = max(words, seconds / 60 * COMPOSER_DETAIL_WORDS_PER_MINUTE)
    # Sparse/noisy recordings must never buy filler just to satisfy a time-based target.
    target = round(
        max(COMPOSER_DETAIL_MIN_WORDS, min(COMPOSER_DETAIL_MAX_WORDS, scale * COMPOSER_DETAIL_WORD_RATIO, words * 0.2))
    )
    chapters = min(COMPOSER_DETAIL_MAX_CHAPTERS, max(4, math.ceil(scale / COMPOSER_DETAIL_WORDS_PER_CHAPTER)))
    guidance = (
        f'Available transcript: {words} words. Aim for roughly {round(target * .85)}-{round(target * 1.15)} '
        f'summary words across the lede, chapters and follow-ups, with at most {chapters} chapters. '
        'Cover the beginning, middle and end and every substantive topic; preserve decisions, reasoning, '
        'alternatives, exact numbers, constraints, unresolved questions and committed next steps. '
        'Use supporting details to carry substance. This is a budget, not a quota: stay shorter for sparse '
        'or repetitive speech, omit noise and never pad or add facts to reach the target.'
    )
    return chapters, guidance
