"""Connection/provider-scoped speaker identity for live transcript segments."""

from __future__ import annotations

import re
import uuid
from typing import Any, Iterable, Mapping, MutableMapping, Optional

# Onboarding reserves this ID for Omi's own question segments (canonical value:
# OnboardingHandler.OMI_SPEAKER_ID in utils/onboarding.py; a unit test pins the
# two together). The allocator never hands it to a real speaker, so a long
# session with many provider transitions cannot collide with it.
OMI_SPEAKER_ID_SENTINEL = 99

_SPEAKER_NUMBER = re.compile(r'^SPEAKER_(\d+)$')


def _read(record: Any, field: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field)
    return getattr(record, field, None)


def _canonical_speaker_label(label: str) -> str:
    """Fold ``SPEAKER_02`` and ``SPEAKER_2`` into one allocator key.

    Providers disagree on zero padding (Deepgram/Modulate emit ``SPEAKER_02``,
    Parakeet paths emit ``SPEAKER_2``), and a custom-STT client may send a bare
    ``speaker_id`` with no label at all. hydrate() and assign() must agree on
    one spelling or the same (scope, speaker) pair splits into two identities.
    """
    match = _SPEAKER_NUMBER.match(label)
    if match:
        return f'SPEAKER_{int(match.group(1))}'
    return label


class SpeakerProviderEpoch:
    """Stamp provider numbering with a new epoch on every provider transition."""

    def __init__(self, connection_scope: Optional[str] = None) -> None:
        self._connection_scope = connection_scope or uuid.uuid4().hex
        self._provider: Optional[str] = None
        self._epoch = -1

    def stamp(self, segments: Iterable[MutableMapping[str, Any]], provider: Optional[str]) -> None:
        """Scope each segment by the provider that actually served it.

        A socket that knows its serving peer stamps ``stt_provider`` on the segment
        itself, and that value is authoritative: the caller-supplied name is the
        host's configured selection, which stays the same across a fallback to a
        different peer. Overwriting it would erase the very transition the epoch
        exists to separate. The epoch therefore advances per segment, so a provider
        change inside one batch opens a new scope rather than being flattened.
        """
        fallback = provider or 'unknown'
        for segment in segments:
            provider_name = segment.get('stt_provider') or fallback
            if provider_name != self._provider:
                self._provider = provider_name
                self._epoch += 1
            segment['stt_provider'] = provider_name
            segment['speaker_id_scope'] = f'{self._connection_scope}:{self._epoch}'


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
                self._speaker_ids.setdefault((str(scope), _canonical_speaker_label(str(speaker))), speaker_id)

    def _allocate(self) -> int:
        speaker_id = self._next_id
        if speaker_id == OMI_SPEAKER_ID_SENTINEL:
            speaker_id += 1
        self._next_id = speaker_id + 1
        return speaker_id

    def assign(self, segment: MutableMapping[str, Any]) -> None:
        """Replace a provider-local number with its conversation-local integer."""
        scope = segment.get('speaker_id_scope')
        if not scope:
            return
        speaker = segment.get('speaker')
        if not speaker and isinstance(segment.get('speaker_id'), int):
            speaker = f'SPEAKER_{segment["speaker_id"]}'
        speaker = _canonical_speaker_label(str(speaker or 'SPEAKER_00'))
        key = (str(scope), speaker)
        speaker_id = self._speaker_ids.get(key)
        if speaker_id is None:
            speaker_id = self._allocate()
            self._speaker_ids[key] = speaker_id
        segment['speaker_id'] = speaker_id
