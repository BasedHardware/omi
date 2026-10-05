# LIFECYCLE: permanent
"""Receiver-observed provenance carried through the managed Soniox queue.

No provenance is inferred from duration, VAD, wall time or adjacent packets.
Unknown sends still consume compact provider time at the wire boundary.
"""

from contextvars import ContextVar
from typing import Any

capture_spans: ContextVar[tuple[tuple[int, int], ...]] = ContextVar('soniox_capture_spans', default=())


class LedgerAudio(bytes):
    spans: tuple[tuple[int, int], ...]

    def __new__(cls, data: bytes, spans: tuple[tuple[int, int], ...]) -> 'LedgerAudio':
        audio = super().__new__(cls, data)
        audio.spans = spans
        return audio


def observed_audio(data: bytes, epoch: Any, spans: tuple[tuple[int, int], ...]) -> LedgerAudio:
    length = len(data) // 2
    observed = (
        len(data) % 2 == 0
        and sum(n for _, n in spans) == length
        and all(n > 0 and 0 <= first < first + n <= epoch.timeline.next_sample for first, n in spans)
    )
    return LedgerAudio(data, spans if observed else ())
