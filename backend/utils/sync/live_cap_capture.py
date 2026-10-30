"""Bounded, sample-ordered custody for out-of-order live admission decisions.

Provider queue callbacks can precede the receiver's decision for older capture.
No source is published until the existing PCM bound/age or an explicit barrier;
only adjacent samples under the same owner, rate, month and wall clock can join.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import time

from utils.observability.held_content import record_transition_tail
from utils.sync.live_cap_tail import TINY_SECONDS


@dataclass
class CaptureSpan:
    first: int
    data: bytearray
    rate: int
    timestamp: float
    owner: str | None
    opened: float

    @property
    def end(self) -> int:
        return self.first + len(self.data) // 2

    @property
    def seconds(self) -> float:
        return len(self.data) / (2 * self.rate)


def _joins(left: CaptureSpan, right: CaptureSpan) -> bool:
    return (
        left.end == right.first
        and left.rate == right.rate
        and left.owner == right.owner
        and datetime.fromtimestamp(left.timestamp, timezone.utc).strftime('%Y-%m')
        == datetime.fromtimestamp(right.timestamp, timezone.utc).strftime('%Y-%m')
        and abs(left.timestamp + left.seconds - right.timestamp) <= 0.1
    )


class OrderedCapture:
    def __init__(self) -> None:
        self.spans: list[CaptureSpan] = []

    @property
    def seconds(self) -> float:
        return sum(span.seconds for span in self.spans)

    def add(self, first: int, data: bytes, rate: int, timestamp: float, owner: str | None) -> None:
        incoming = CaptureSpan(first, bytearray(data), rate, timestamp, owner, time.monotonic())
        self.spans.append(incoming)
        self.spans.sort(key=lambda span: span.first)
        merged: list[CaptureSpan] = []
        for span in self.spans:
            if merged and _joins(merged[-1], span):
                previous = merged[-1]
                for item in (previous, span):
                    if item is not incoming and item.seconds < TINY_SECONDS:
                        record_transition_tail('coalesced')
                previous.data.extend(span.data)
                previous.opened = min(previous.opened, span.opened)
            else:
                merged.append(span)
        self.spans = merged

    def take(self, bound: float, *, force: bool) -> list[CaptureSpan]:
        if not self.spans or (not force and time.monotonic() - min(s.opened for s in self.spans) < bound):
            return []
        spans, self.spans = self.spans, []
        for span in spans:
            if span.seconds < TINY_SECONDS:
                record_transition_tail('sealed')
        return spans
