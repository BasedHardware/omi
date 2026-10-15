"""GPU-independent batch protocol. No provider imports or import-time IO."""

from dataclasses import dataclass
import math
from typing import Protocol, Sequence


from config.batch_pipeline import Priority
from utils.batch_pipeline.capacity import PoolCapacity as PoolCapacity


@dataclass(frozen=True)
class WorkItem:
    segment_id: str
    owner_id: str
    capture_at: float
    audio_uri: str
    duration_seconds: float
    priority: Priority

    def __post_init__(self):
        if not self.segment_id or len(self.segment_id) > 128 or '/' in self.segment_id:
            raise ValueError('segment_id must be a bounded opaque document ID')
        if not self.owner_id or len(self.owner_id.encode()) > 256:
            raise ValueError('owner_id must be bounded')
        if not self.audio_uri or len(self.audio_uri.encode()) > 2048:
            raise ValueError('audio_uri must be a bounded durable reference')
        if not math.isfinite(self.capture_at) or self.capture_at < 0:
            raise ValueError('capture_at must be a UTC epoch timestamp')
        if not math.isfinite(self.duration_seconds) or not 0 < self.duration_seconds <= 7200:
            raise ValueError('audio duration must be in (0, 7200]')
        Priority(self.priority)


@dataclass(frozen=True)
class LeasedWork:
    item: WorkItem
    token: str
    attempt: int
    lease_until: float


@dataclass(frozen=True)
class WorkResult:
    segment_id: str
    result_uri: str
    outcome: str = 'success'

    def __post_init__(self):
        if self.outcome not in {'success', 'silence'}:
            raise ValueError('failed items must retry, never become silence')
        if not self.result_uri or len(self.result_uri.encode()) > 2048:
            raise ValueError('result_uri must be a bounded durable encrypted reference')


class BatchWorker(Protocol):
    def process_batch(self, items: Sequence[WorkItem]) -> Sequence[WorkResult]: ...
