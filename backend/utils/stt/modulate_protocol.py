"""Bounded pending previews for Modulate's nullable, interleaved utterances."""

from __future__ import annotations

import logging
import re
from typing import Any, Final, Optional

from utils.stt.stream_close import PROVIDER_AUTH_REJECTED, PROVIDER_BUDGET_EXHAUSTED, PROVIDER_RATE_LIMITED

logger = logging.getLogger(__name__)
MAX_PENDING_UTTERANCES = 64


def _key(message: dict[str, Any]) -> str:
    identifier = message.get('utterance_uuid')
    # The documented partial shape has no UUID: keep one anonymous preview.
    return identifier if isinstance(identifier, str) and identifier else ''


def _timestamp(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _normalized_text(value: Any) -> str:
    return ' '.join(re.findall(r'\w+', value.casefold())) if isinstance(value, str) else ''


MODULATE_DEATH_SERVE_ERROR: Final = 'modulate_serve_error'

# Velma's in-stream error frames are free text, so the fault boundary is
# matched on normalized text. Budget/quota is never transient and is the
# same class as Soniox monthly-budget / Deepgram HTTP 402. 5xx wording is a
# provider serve fault. Everything else — invalid audio we sent, rate limits
# — is either our fault or this session's, and must not bench the provider.
_MODULATE_BUDGET_MARKERS: Final = (
    'monthly usage limit',
    'usage limit reached',
    'quota exceeded',
)
_MODULATE_SERVER_FAULT_MARKERS: Final = (
    'internal server error',
    'internal error',
    'unable to complete the request',
    'server error',
)


def modulate_death_reason(err: Any, *, protocol_guard: bool = False) -> Optional[str]:
    """Bound a Velma in-stream error frame to a typed death reason.

    Returns ``PROVIDER_BUDGET_EXHAUSTED`` for quota/monthly-cap text,
    ``MODULATE_DEATH_SERVE_ERROR`` when the text says the provider failed to
    serve the stream it accepted, else ``None`` (untyped — the raw text stays
    on the death latch for logs). New provider wordings degrade to untyped
    rather than growing a new bounded token per message.
    """
    normalized = str(err or '').strip().lower().rstrip('.')
    if not normalized:
        return None
    if any(marker in normalized for marker in _MODULATE_BUDGET_MARKERS):
        return PROVIDER_BUDGET_EXHAUSTED
    if protocol_guard:
        if 'insufficient credits' in normalized:
            return PROVIDER_BUDGET_EXHAUSTED
        if 'concurrent request limit' in normalized:
            return PROVIDER_RATE_LIMITED
        if any(
            marker in normalized
            for marker in (
                'invalid api key',
                'missing api_key',
                'request is not permitted',
                'does not have access to this model',
            )
        ):
            return PROVIDER_AUTH_REJECTED
    if any(marker in normalized for marker in _MODULATE_SERVER_FAULT_MARKERS):
        return MODULATE_DEATH_SERVE_ERROR
    if any(marker in normalized for marker in ('invalid audio', 'unsupported audio', 'invalid wav', 'invalid input')):
        return 'other'  # Our audio/request shape, never provider availability.
    return None


class ModulatePendingUtterances:
    """Finals retire their UUID and covered anonymous text; never invent time."""

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}

    def __bool__(self) -> bool:
        return bool(self._pending)

    def observe(self, message: dict[str, Any]) -> None:
        key = _key(message)
        previous = self._pending.get(key, {})
        start = _timestamp(message.get('start_ms'))
        # A UUID proves that a nullable update belongs to the same utterance.
        # The documented UUID-less partial cannot prove that association.
        if start is None and key:
            start = previous.get('start_ms')
        speaker = message.get('speaker')
        if type(speaker) is not int or speaker < 1:
            speaker = previous.get('speaker') if key else None
        text = message.get('text')
        if not isinstance(text, str):
            return
        if not text.strip():
            # Every preview supersedes its predecessor, including retractions.
            self._pending.pop(key, None)
            return
        if key not in self._pending and len(self._pending) >= MAX_PENDING_UTTERANCES:
            # These are previews only; final utterances still pass through.
            self._pending.pop(next(iter(self._pending)))
            logger.warning('Modulate pending preview capacity reached')
        self._pending[key] = {'text': text.strip(), 'start_ms': start, 'speaker': speaker}

    def finalized(self, message: dict[str, Any]) -> None:
        key = _key(message)
        if key:
            self._pending.pop(key, None)
        preview = self._pending.get('')
        if preview is None:
            return
        # A UUID-less start has no duration, so overlap cannot prove coverage.
        # Keep uncertain previews, preferring a duplicate to lost pending text.
        preview_text = _normalized_text(preview['text'])
        final_text = _normalized_text(message.get('text'))
        if preview_text and f' {preview_text} ' in f' {final_text} ':
            self._pending.pop('', None)

    def flush(self, preseconds: int = 0) -> list[dict[str, Any]]:
        pending, self._pending = self._pending, {}
        segments: list[dict[str, Any]] = []
        for preview in pending.values():
            start_ms = preview['start_ms']
            if start_ms is None:
                logger.warning('Modulate terminal preview has no timestamp; retaining finalized text only')
                continue
            start = start_ms / 1000.0
            if preseconds and start < preseconds:
                continue
            speaker = preview['speaker']
            segments.append(
                {
                    'speaker': f'SPEAKER_{speaker - 1:02d}' if speaker is not None else 'SPEAKER_00',
                    'start': start,
                    # Preserve the existing tail representation: previews have
                    # no duration, so this is not a measured speech interval.
                    'end': (start_ms + 1) / 1000.0,
                    'text': preview['text'],
                    'is_user': False,
                    'person_id': None,
                }
            )
        return sorted(segments, key=lambda segment: segment['start'])
