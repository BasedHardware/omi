"""Recorded coordinates and their provenance, independent of server arrival."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, model_validator


class RecordedClock(str, Enum):
    device = 'device'
    estimated_device = 'estimated_device'
    frame = 'frame'
    live_capture = 'live_capture'
    imported = 'imported'
    legacy = 'legacy'


class RecordedSpan(BaseModel):
    recorded_start: datetime
    recorded_end: datetime
    arrival_at: datetime | None = None
    clock: RecordedClock

    @model_validator(mode='after')
    def ordered(self):
        if self.recorded_end < self.recorded_start:
            raise ValueError('recorded end precedes start')
        return self
