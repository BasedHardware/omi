"""Dense speaker display labels shared by every transcript renderer.

A ``speaker_id`` is a per-conversation diarization counter, not a person: it
reaches the hundreds in a long conversation, and LLMs copy ``Speaker 379``-
style dialogue labels verbatim into user-visible notes (#23381). Renderers that
need a label for an unnamed voice use :class:`SpeakerLabeler` instead: named
people keep their names, and each unnamed voice gets a small stable label
("Speaker A", "Speaker B", ...) in order of first appearance within the
rendered transcript. One labeler instance per rendered transcript keeps the
labels consistent across its lines.
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
    """(speaker_id_scope, speaker_id): merged multi-source transcripts reuse ids across scopes."""
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
