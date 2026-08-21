"""Connection/provider-scoped speaker identity for live transcript segments."""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping, MutableMapping, Optional


def _read(record: Any, field: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field)
    return getattr(record, field, None)


class SpeakerProviderEpoch:
    """Stamp provider numbering with a new epoch on every provider transition."""

    def __init__(self, connection_scope: Optional[str] = None) -> None:
        self._connection_scope = connection_scope or uuid.uuid4().hex
        self._provider: Optional[str] = None
        self._epoch = -1

    def stamp(self, segments: Iterable[MutableMapping[str, Any]], provider: Optional[str]) -> None:
        provider_name = provider or 'unknown'
        if provider_name != self._provider:
            self._provider = provider_name
            self._epoch += 1
        scope = f'{self._connection_scope}:{self._epoch}'
        for segment in segments:
            segment['stt_provider'] = provider_name
            segment['speaker_id_scope'] = scope


class ConversationSpeakerIdAllocator:
    """Allocate small conversation-local integer IDs for scoped provider labels."""

    def __init__(self) -> None:
        self._speaker_ids: dict[tuple[str, str], int] = {}
        self._next_id = 0

    def hydrate(self, segments: Iterable[Any]) -> None:
        """Learn persisted assignments before allocating IDs after a reconnect."""
        for segment in segments:
            speaker_id = _read(segment, 'speaker_id')
            if isinstance(speaker_id, int):
                self._next_id = max(self._next_id, speaker_id + 1)
            scope = _read(segment, 'speaker_id_scope')
            speaker = _read(segment, 'speaker')
            if scope and speaker and isinstance(speaker_id, int):
                self._speaker_ids.setdefault((str(scope), str(speaker)), speaker_id)

    def assign(self, segment: MutableMapping[str, Any]) -> None:
        """Replace a provider-local number with its conversation-local integer."""
        scope = segment.get('speaker_id_scope')
        if not scope:
            return
        speaker = segment.get('speaker')
        if not speaker and isinstance(segment.get('speaker_id'), int):
            speaker = f'SPEAKER_{segment["speaker_id"]}'
        speaker = str(speaker or 'SPEAKER_00')
        key = (str(scope), speaker)
        speaker_id = self._speaker_ids.get(key)
        if speaker_id is None:
            speaker_id = self._next_id
            self._next_id += 1
            self._speaker_ids[key] = speaker_id
        segment['speaker_id'] = speaker_id
