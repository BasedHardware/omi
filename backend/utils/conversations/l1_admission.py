"""Why a conversation cannot yield a durable memory, or None to extract.

Pure: no IO, no environment read beyond the kill switch, no mutation. The
verdicts mirror the deterministic noise decision the Home row contract already
makes (``utils.conversations.home_step``): a server minimum, a media/noise
content kind, or content the relevance rules settled as content-free. The
presentation-only parts of that contract (processing age, stand-in titles) are
not repeated here.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from prometheus_client import Counter
from utils.observability.reasons import MemoryL1Reason, ReasonFamily, reason_label

from config.memory_l1_admission import L1_MIN_OWNER_WORDS, noise_skip_enabled
from utils.conversations.minimum_derived import is_server_minimum
from utils.conversations.owner_attribution import speaker_role_projection
from utils.conversations.relevance_rules import transcript_word_count

logger = logging.getLogger(__name__)

NOISE = 'noise'
SHORT_OWNER_SPEECH = 'short_owner_speech'

SKIPPED = Counter(
    'omi_memory_l1_skipped_total',
    'L1 memory extraction skipped before the model call',
    ['reason'],
)

# A user action protects the row: never skip a conversation the owner kept.
_CURATED_FIELDS = ('sync_relevance_user_kept', 'has_photos', 'photos', 'user_title', 'starred', 'folder_user_set')


def _field(row: Any, name: str, default: Any = None) -> Any:
    return row.get(name, default) if isinstance(row, Mapping) else getattr(row, name, default)


def _value(value: Any) -> Any:
    return getattr(value, 'value', value)


def _curated(conversation: Any) -> bool:
    return any(bool(_field(conversation, name)) for name in _CURATED_FIELDS)


def _text(row: Any) -> str:
    return str(_field(row, 'text', '') or '')


def total_word_count(segments: Sequence[Any] | None) -> int:
    return sum(transcript_word_count(_text(row)) for row in segments or ())


def owner_word_count(segments: Sequence[Any] | None) -> int | None:
    """Words the owner spoke, or None when no owner is positively identified.

    None is unknown, never zero: a transcript without owner evidence must not be
    read as "the owner said nothing".
    """
    rows = list(segments or ())
    if not rows:
        return 0
    roles = speaker_role_projection(rows)
    if roles is None:
        return None
    total = 0
    identified = False
    for row in rows:
        if roles.for_segment(row).role != 'primary_user':
            continue
        identified = True
        total += transcript_word_count(_text(row))
    return total if identified else None


def skip_reason(conversation: Any) -> str | None:
    """The reason to skip this conversation's L1 call, or None to extract."""
    if not noise_skip_enabled():
        return None
    if _curated(conversation):
        return None
    if is_server_minimum(conversation):
        return NOISE
    if _value(_field(conversation, 'content_kind')) in ('media', 'noise'):
        return NOISE
    if _value(_field(conversation, 'source')) == 'external_integration':
        # Imported text has no owner speech to measure; its own admission runs
        # on the external path.
        return None
    segments = _field(conversation, 'transcript_segments')
    words = owner_word_count(segments)
    if words is None:
        # The owner cannot have spoken more than the whole transcript, so a
        # short total is a sound upper bound even without owner attribution.
        words = total_word_count(segments)
    if words < L1_MIN_OWNER_WORDS:
        return SHORT_OWNER_SPEECH
    return None


def skip(uid: str, conversation: Any) -> bool:
    """Count, log and report whether this conversation's L1 call must be skipped."""
    reason = skip_reason(conversation)
    if reason is None:
        return False
    SKIPPED.labels(reason=reason_label(ReasonFamily.MEMORY_L1, reason, MemoryL1Reason)).inc()
    logger.info(
        'memory extraction skipped: reason=%s uid=%s conv=%s',
        reason,
        uid,
        _field(conversation, 'id'),
    )
    return True
