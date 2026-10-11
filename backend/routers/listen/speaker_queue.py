"""Bounded metadata-only speaker work, coalesced before fair admission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

MAX_QUEUED_VOICES = 100
MAX_QUEUED_INTERVALS = 128
SPEAKER_QUEUE_MAX_WAIT_SECONDS = 5.0
VoiceKey = tuple[int, Optional[str], str, int]


@dataclass
class _QueuedVoice:
    segment: dict[str, Any]
    arrived_at: float


class SpeakerMatchQueue:
    """One pending slot per generation/conversation/scoped voice, at most 100.

    Work aged five monotonic seconds wins oldest-first; otherwise untried
    voices win, then acoustic near-owner candidates and longer pooled clips.
    Active voices stay queued until completion instead of occupying task slots
    waiting on the same speaker lock. Nothing here reserves model budget.
    """

    def __init__(
        self,
        *,
        generation: Callable[[], int],
        attempts: Callable[[int], int],
        near_owner: Callable[[int], bool],
        clock: Callable[[], float],
    ) -> None:
        self._generation = generation
        self._attempts = attempts
        self._near_owner = near_owner
        self._clock = clock
        self._items: dict[VoiceKey, _QueuedVoice] = {}
        self._active: set[VoiceKey] = set()
        self._changed = asyncio.Event()
        self.maxsize = MAX_QUEUED_VOICES

    @staticmethod
    def _key(segment: dict[str, Any]) -> VoiceKey:
        return (
            segment['_matcher_generation'],
            segment.get('conversation_id'),
            segment.get('speaker_id_scope') or '',
            segment['speaker_id'],
        )

    def qsize(self) -> int:
        return len(self._items)

    def empty(self) -> bool:
        return not self._items

    def full(self) -> bool:
        return self.qsize() >= self.maxsize

    def put_nowait(self, segment: dict[str, Any]) -> None:
        # Only timing and identity metadata enter this queue, never PCM or text.
        work = {
            field: segment[field]
            for field in ('id', 'conversation_id', 'speaker_id', 'speaker_id_scope', 'abs_start', 'abs_end', 'duration')
            if field in segment
        }
        work['_matcher_generation'] = self._generation()
        key = self._key(work)
        previous = self._items.get(key)
        if previous is None and self.full():
            raise asyncio.QueueFull
        intervals = list(previous.segment['_speaker_audio_ranges']) if previous is not None else []
        intervals.append((work['abs_start'], min(work['abs_end'], work['abs_start'] + max(0.0, work['duration']))))
        merged: list[tuple[float, float]] = []
        for start, end in sorted(intervals):
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        work['_speaker_audio_ranges'] = merged[-MAX_QUEUED_INTERVALS:]
        self._items[key] = _QueuedVoice(work, previous.arrived_at if previous is not None else self._clock())
        self._changed.set()

    def get_nowait(self) -> dict[str, Any]:
        ready = [(key, item) for key, item in self._items.items() if key not in self._active]
        if not ready:
            raise asyncio.QueueEmpty
        now = self._clock()
        aged = [(key, item) for key, item in ready if now - item.arrived_at >= SPEAKER_QUEUE_MAX_WAIT_SECONDS]
        if aged:
            key, item = min(aged, key=lambda entry: entry[1].arrived_at)
        else:
            key, item = min(
                ready,
                key=lambda entry: (
                    self._attempts(entry[0][3]) > 0,
                    not self._near_owner(entry[0][3]),
                    -min(10.0, sum(end - start for start, end in entry[1].segment['_speaker_audio_ranges'])),
                    entry[1].arrived_at,
                ),
            )
        del self._items[key]
        self._active.add(key)
        return item.segment

    async def get(self) -> dict[str, Any]:
        while True:
            self._changed.clear()
            try:
                return self.get_nowait()
            except asyncio.QueueEmpty:
                await self._changed.wait()

    def complete(self, segment: dict[str, Any]) -> None:
        self._active.discard(self._key(segment))
        self._changed.set()
