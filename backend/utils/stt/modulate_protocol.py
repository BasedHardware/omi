"""Bounded pending previews for Modulate's nullable, interleaved utterances."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
MAX_PENDING_UTTERANCES = 64


def _key(message: dict[str, Any]) -> str:
    identifier = message.get('utterance_uuid')
    return identifier if isinstance(identifier, str) and identifier else ''


def _timestamp(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


class ModulatePendingUtterances:
    """Finals retire only their own preview; unanchored text cannot invent time."""

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}

    def __bool__(self) -> bool:
        return bool(self._pending)

    def observe(self, message: dict[str, Any]) -> None:
        key = _key(message)
        previous = self._pending.get(key, {})
        start = _timestamp(message.get('start_ms'))
        # A UUID proves that a nullable update belongs to the same utterance.
        # An older server without UUIDs cannot prove that association.
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
        self._pending.pop(_key(message), None)

    def flush(self, preseconds: int = 0) -> list[dict[str, Any]]:
        pending, self._pending = self._pending, {}
        segments = []
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
