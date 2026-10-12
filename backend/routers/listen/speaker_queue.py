"""Bounded metadata-only FIFO speaker work with generation fencing."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

MAX_QUEUED_SEGMENTS = 100


def subtract_audio_ranges(
    ranges: list[tuple[float, float]], used: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Retain only unconsumed speech intervals, preserving gaps and partial clips."""
    for used_start, used_end in used:
        remaining = []
        for start, end in ranges:
            if used_end <= start or used_start >= end:
                remaining.append((start, end))
            else:
                if start < used_start:
                    remaining.append((start, used_start))
                if used_end < end:
                    remaining.append((used_end, end))
        ranges = remaining
    return ranges


class SpeakerMatchQueue(asyncio.Queue[dict[str, Any]]):
    """Keep each provider update separate and in arrival order.

    Generation is captured at enqueue so old work cannot match after a rollover.
    Per-voice serialization and the task ceiling remain the matcher's concern.
    """

    def __init__(self, *, generation: Callable[[], int]) -> None:
        super().__init__(maxsize=MAX_QUEUED_SEGMENTS)
        self._generation = generation

    def put_nowait(self, item: dict[str, Any]) -> None:
        # Timing/identity metadata only; queued work never carries PCM or text.
        work = {
            field: item[field]
            for field in ('id', 'conversation_id', 'speaker_id', 'speaker_id_scope', 'abs_start', 'abs_end', 'duration')
            if field in item
        }
        work['_matcher_generation'] = self._generation()
        super().put_nowait(work)
