"""Bounded FIFO speaker work, with a tail only for proven rejectors."""

from __future__ import annotations

import asyncio
from collections import deque
from math import isfinite
from typing import Any, Callable

from utils.observability.speaker_embedding_budget import REJECTOR_DEMOTIONS

MAX_QUEUED_SEGMENTS = 100


def pending_audio_ranges(
    segment: dict[str, Any], pending: list[tuple[float, float]], buffer_start: float, buffer_end: float
) -> list[tuple[float, float]]:
    """Clamp and union queued timing metadata without pooling ordinary updates."""
    incoming = segment.get(
        '_speaker_audio_ranges',
        [(segment['abs_start'], min(segment['abs_end'], segment['abs_start'] + max(0.0, segment['duration'])))],
    )
    fresh: list[tuple[float, float]] = []
    for start, end in sorted(pending + incoming):
        start, end = max(start, buffer_start), min(end, buffer_end)
        if end <= start:
            continue
        if fresh and start <= fresh[-1][1]:
            fresh[-1] = (fresh[-1][0], max(fresh[-1][1], end))
        else:
            fresh.append((start, end))
    return fresh


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
    """Keep ordinary provider updates separate and in arrival order.

    Generation is captured at enqueue so old work cannot match after a rollover.
    Only a proven rejector collapses into one pending entry behind ordinary work.
    Per-voice serialization and the task ceiling remain the matcher's concern.
    """

    # asyncio.Queue's Python 3.11 storage/waiter fields are absent from typeshed.
    # Coalescing adjusts unfinished work and wakes a blocked producer when a
    # pending slot is released; the inherited get/put cancellation rules remain.
    _queue: deque[dict[str, Any]]
    _unfinished_tasks: int
    _putters: deque[asyncio.Future[None]]

    def __init__(self, *, generation: Callable[[], int], rejector: Callable[[int], bool] = lambda _: False) -> None:
        super().__init__(maxsize=MAX_QUEUED_SEGMENTS)
        self._generation = generation
        self._rejector = rejector

    def _is_rejector(self, work: dict[str, Any]) -> bool:
        return work['_matcher_generation'] == self._generation() and self._rejector(work['speaker_id'])

    @staticmethod
    def _key(work: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(
            work.get(field) for field in ('_matcher_generation', 'conversation_id', 'speaker_id_scope', 'speaker_id')
        )

    @staticmethod
    def _ranges(work: dict[str, Any]) -> list[tuple[float, float]]:
        return work.get(
            '_speaker_audio_ranges',
            [(work['abs_start'], min(work['abs_end'], work['abs_start'] + max(0.0, work['duration'])))],
        )

    def _merge(self, pending: dict[str, Any], latest: dict[str, Any]) -> None:
        ranges: list[tuple[float, float]] = []
        for start, end in sorted(self._ranges(pending) + self._ranges(latest)):
            if not isfinite(start) or not isfinite(end) or end <= start:
                continue
            if ranges and start <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        pending.update(latest)
        pending['_speaker_audio_ranges'] = ranges[-128:]
        if ranges:
            pending['abs_start'] = ranges[-128:][0][0]
            pending['abs_end'] = ranges[-1][1]
            pending['duration'] = sum(end - start for start, end in ranges[-128:])
        pending['_rejector_pending'] = True
        REJECTOR_DEMOTIONS.labels(action='coalesced').inc()

    def _normalize(self) -> None:
        # Recheck at dequeue too: queued FIFO work may become proven while
        # earlier tasks finish. Never merge across conversation/scope fences.
        ordinary: list[dict[str, Any]] = []
        rejectors: dict[tuple[Any, ...], dict[str, Any]] = {}
        removed = 0
        for work in self._queue:
            if not self._is_rejector(work):
                ordinary.append(work)
                continue
            key = self._key(work)
            if key in rejectors:
                self._merge(rejectors[key], work)
                removed += 1
            else:
                if not work.get('_rejector_pending'):
                    work['_rejector_pending'] = True
                    REJECTOR_DEMOTIONS.labels(action='deferred').inc()
                rejectors[key] = work
        self._queue.clear()
        self._queue.extend([*ordinary, *rejectors.values()])
        self._unfinished_tasks -= removed
        if removed:
            while self._putters:
                waiter = self._putters.popleft()
                if not waiter.done():
                    waiter.set_result(None)
                    break

    def _get(self) -> dict[str, Any]:
        self._normalize()
        return super()._get()

    def put_nowait(self, item: dict[str, Any]) -> None:
        # Timing/identity metadata only; queued work never carries PCM or text.
        work = {
            field: item[field]
            for field in ('id', 'conversation_id', 'speaker_id', 'speaker_id_scope', 'abs_start', 'abs_end', 'duration')
            if field in item
        }
        work['_matcher_generation'] = self._generation()
        self._normalize()
        if self._is_rejector(work):
            for pending in self._queue:
                if self._is_rejector(pending) and self._key(pending) == self._key(work):
                    self._merge(pending, work)
                    return
        super().put_nowait(work)
        self._normalize()
