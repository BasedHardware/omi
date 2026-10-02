"""Closed-vocabulary relocation outcomes. No account, text or source labels."""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
OUTCOMES = frozenset(
    {
        'relocated',
        'ambiguous',
        'not_found',
        'budget_exhausted',
        'verified_at_stored_position',
        'disabled',
        'not_authorized',
        'short_or_generic',
        'invalid_timing',
        'unsupported_source',
        'source_changed',
        'incomplete_audio',
        'verification_rejected',
        'transcription_failed',
        'cache_unavailable',
        'busy',
        'timeout',
        'error',
    }
)
CLIP_LOCATION_TOTAL = Counter(
    'omi_speaker_clip_location_total', 'Manual teaching audio location outcomes.', ['outcome']
)


def record_location(outcome: str) -> None:
    outcome = outcome if outcome in OUTCOMES else 'error'
    CLIP_LOCATION_TOTAL.labels(outcome=outcome).inc()
    logger.info('speaker_clip_location outcome=%s', outcome)
