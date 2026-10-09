"""OFF by default second opinion for R03/R08; no calendar or account reads.

Lifecycle: offline pilot approved 2026-10-09; activation requires separate review.
The score is P(discard), not P(keep). Exactly 0.80 leaves the discard standing.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

FLAG = 'CONVERSATION_RELEVANCE_JEV_RESCUE'
THRESHOLD = 0.80
ELIGIBLE_REASONS = frozenset({'filler_only', 'no_content_words'})


@dataclass(frozen=True)
class RescueDecision:
    rescued: bool
    score: Optional[float]
    outcome: str


def rescue_mode() -> str:
    mode = os.getenv(FLAG, 'off').strip().lower()
    return mode if mode in {'off', 'shadow', 'on'} else 'off'


def should_rescue(segments: Sequence[str], rule_reason: str) -> bool:
    """Admission only; this does not call a provider or imply JEV's verdict."""
    return rule_reason in ELIGIBLE_REASONS and any(text.strip() for text in segments)


def rescue_decision(score_call: Callable[[], Optional[float]]) -> RescueDecision:
    """Pure conservative policy shared by offline and backend adapters."""
    try:
        score = score_call()
        valid = (
            not isinstance(score, bool) and isinstance(score, (int, float)) and math.isfinite(score) and 0 <= score <= 1
        )
    except Exception:
        valid, score = False, None
    if not valid:
        return RescueDecision(True, None, 'error_keep')
    return RescueDecision(score < THRESHOLD, float(score), 'rescue' if score < THRESHOLD else 'discard_stands')


def transcript_for_rescue(segments: Sequence[str]) -> str:
    """Text-only adapter: no invented owner identity; each raw segment has a label."""
    return '\n\n'.join(f'Speaker 0: {text}' for text in segments if text.strip())


def score_segments(segments: Sequence[str]) -> RescueDecision:
    # Lazy imports keep the flag-off deterministic path stdlib-only.
    from utils.conversations.relevance_jev import jev_discard_probability

    return rescue_decision(lambda: jev_discard_probability(transcript_for_rescue(segments)))


def record_rescue(*, mode: str, rule: str, outcome: str) -> None:
    from utils.metrics import record_conversation_relevance_rescue

    record_conversation_relevance_rescue(mode=mode, rule=rule, outcome=outcome)
    if outcome == 'error_keep':
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_relevance',
            from_mode='jev',
            to_mode='keep',
            reason='model_error',
            outcome='recovered',
        )
