"""Small label alphabet used only by utils.speakers.display.display_participants.

Originally introduced by the live-speaker-names lane. Renderers must use the
participants authority so identity evidence and count sanity cannot be bypassed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Hashable, Optional


def _column(index: int) -> str:
    """0 -> A ... 25 -> Z, 26 -> AA (spreadsheet columns keep labels small past 26 voices)."""
    if index < 26:
        return chr(ord('A') + index)
    return _column(index // 26 - 1) + chr(ord('A') + index % 26)


def voice_key(segment: Any) -> tuple[Optional[Any], Optional[Any]]:
    """Legacy scoped wire-identity helper; renderers use display_participants."""
    if isinstance(segment, Mapping):
        return (segment.get('speaker_id_scope'), segment.get('speaker_id'))
    return (getattr(segment, 'speaker_id_scope', None), getattr(segment, 'speaker_id', None))


class SpeakerLabeler:
    """Assigns dense "Speaker A/B/..." labels to unnamed voice keys, first appearance order."""

    def __init__(self) -> None:
        self._labels: dict[Hashable, str] = {}

    def label(self, key: Hashable) -> str:
        label = self._labels.get(key)
        if label is None:
            label = f'Speaker {_column(len(self._labels))}'
            self._labels[key] = label
        return label


__all__ = ['SpeakerLabeler', 'voice_key']
