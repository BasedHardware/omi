"""Row-local, counts-only telemetry. Inactive outside the isolated repair child."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time

STAGES = ('startup', 'clients', 'proof', 'list', 'walk', 'apply')
_current: ContextVar[RowProfile | None] = ContextVar('record_seal_profile', default=None)


class RowProfile:
    def __init__(self, started, progress=lambda _: None, clock=time.monotonic):
        self.clock, self.progress = clock, progress
        self.stage, self.since = 'startup', started
        self.timings: dict[str, float] = dict.fromkeys(STAGES, 0)
        self.chunks = self.bytes = self.metadata_reloads = 0

    def snapshot(self):
        timings = dict(self.timings)
        timings[self.stage] += max(0, self.clock() - self.since)
        return {
            'stage': self.stage,
            'stage_ms': {key: min(3600000, round(value * 1000)) for key, value in timings.items()},
            'chunks': self.chunks,
            'bytes': self.bytes,
            'metadata_reloads': self.metadata_reloads,
        }

    def enter(self, stage):
        now = self.clock()
        self.timings[self.stage] += max(0, now - self.since)
        self.stage, self.since = stage, now
        self.progress(self.snapshot())

    @contextmanager
    def install(self):
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)


def enter(stage):
    profile = _current.get()
    if profile is not None:
        profile.enter(stage)


def received(size):
    profile = _current.get()
    if profile is not None:
        profile.chunks += 1
        profile.bytes += size


def metadata_reload():
    profile = _current.get()
    if profile is not None:
        profile.metadata_reloads += 1
