"""Left ASR context from a unit's capture predecessor. Model-free; no IO.

Parakeet TDT v3 decodes nothing when a clip starts mid-utterance: from the
decoder start state blank beats every token on every frame (KB
projects/parakeet-primary/evidence/2026-09-21-tdt-empty-output-root-cause.md).
Capture units are cut at fixed upload boundaries, so a unit whose speech starts
at sample 0 usually starts mid-utterance and comes back empty.

When the same owner's immediately preceding capture span is known to this
worker (same flight, or a bounded recent-tail cache), the unit's first ASR
window is prefixed with that predecessor's audio from the onset of the speech
run crossing the seam. Words whose midpoint falls in the prefix are never
owned by the unit (window core ownership), so nothing is double-counted.
"""

from collections import OrderedDict
from dataclasses import dataclass
import time
from typing import Any, Callable

import numpy as np

SAMPLE_RATE = 16000
# A gap larger than this is not one continuous capture stream.
MAX_SEAM_GAP_SECONDS = 1.0
# Overlap tolerated between timestamped neighbours (clock rounding).
MAX_SEAM_OVERLAP_SECONDS = 0.5
# Speech ending this close to the seam is treated as running across it.
SEAM_SPEECH_SECONDS = 0.3
# Audio kept before the onset of the crossing speech run.
ONSET_MARGIN_SECONDS = 0.5
# Non-speech tail used when the predecessor ended in silence.
SILENT_TAIL_SECONDS = 1.0


@dataclass(frozen=True)
class _Tail:
    end_at: float
    pcm: np.ndarray  # int16, the selected context
    stored_at: float


def select_context(samples, spans, max_seconds: float) -> tuple[int, int] | None:
    """Sample range of the predecessor to prepend, or None.

    Starts at the onset of the speech run touching the seam (minus a margin),
    bounded to ``max_seconds``; a predecessor ending in silence contributes a
    short non-speech tail only.
    """
    total = len(samples)
    if total == 0 or max_seconds <= 0:
        return None
    seam = total / SAMPLE_RATE
    floor = max(0.0, seam - max_seconds)
    crossing = [s for s, e in spans if e >= seam - SEAM_SPEECH_SECONDS]
    start = max(floor, min(crossing) - ONSET_MARGIN_SECONDS) if crossing else max(floor, seam - SILENT_TAIL_SECONDS)
    first = max(0, min(total - 1, int(start * SAMPLE_RATE)))
    return first, total


class LeftContextIndex:
    """Bounded, process-local predecessor tails of one capture stream.

    Keyed by owner, privacy generation and conversation (the capture stream),
    so another device's simultaneous audio never matches. Entries hold at most
    ``max_seconds`` of int16 PCM each and expire after ``ttl_seconds``. Seeing a
    unit of a newer (or older) generation drops that owner's other-generation
    tails.
    """

    def __init__(
        self,
        *,
        max_seconds: float,
        max_units: int,
        ttl_seconds: float = 600,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_seconds = float(max_seconds)
        self.max_units = int(max_units)
        self.ttl_seconds = float(ttl_seconds)
        self.clock = clock
        self._tails: OrderedDict[tuple[str, Any, str, float], _Tail] = OrderedDict()

    @staticmethod
    def _key(item, end_at: float):
        return (item.owner_id, item.privacy_generation, item.conversation_id, round(end_at, 3))

    def _drop_other_generations(self, item) -> None:
        for key in [k for k in self._tails if k[0] == item.owner_id and k[1] != item.privacy_generation]:
            del self._tails[key]

    def remember(self, item, samples, spans) -> None:
        if self.max_units <= 0 or not isinstance(samples, np.ndarray) or not item.conversation_id:
            return
        self._drop_other_generations(item)
        selected = select_context(samples, spans, self.max_seconds)
        if selected is None:
            return
        first, last = selected
        pcm = np.clip(np.round(np.asarray(samples[first:last], dtype=np.float32) * 32768), -32768, 32767)
        end_at = item.capture_at + len(samples) / SAMPLE_RATE
        key = self._key(item, end_at)
        self._tails[key] = _Tail(end_at, pcm.astype(np.int16), self.clock())
        self._tails.move_to_end(key)
        while len(self._tails) > self.max_units:
            self._tails.popitem(last=False)

    def lookup(self, item, duration: float) -> np.ndarray | None:
        """float32 context for ``item`` from a contiguous same-owner predecessor."""
        if not item.conversation_id:
            return None
        self._drop_other_generations(item)
        now = self.clock()
        own_end = item.capture_at + duration
        best = None
        for key, tail in list(self._tails.items()):
            if now - tail.stored_at > self.ttl_seconds:
                del self._tails[key]
                continue
            if (
                key[:3] != (item.owner_id, item.privacy_generation, item.conversation_id)
                or abs(tail.end_at - own_end) < 1e-3
            ):
                continue
            gap = item.capture_at - tail.end_at
            if -MAX_SEAM_OVERLAP_SECONDS <= gap <= MAX_SEAM_GAP_SECONDS and (
                best is None or abs(gap) < abs(item.capture_at - best.end_at)
            ):
                best = tail
        if best is None:
            return None
        pcm = best.pcm
        overlap = item.capture_at - best.end_at
        if overlap < 0:
            # Never replay audio the unit itself contains: end the prefix where
            # the unit starts.
            pcm = pcm[: max(0, len(pcm) - int(round(-overlap * SAMPLE_RATE)))]
            if not len(pcm):
                return None
        return pcm.astype(np.float32) / 32768


# VAD speech starting this close to sample 0 is treated as mid-utterance.
START_IN_SPEECH_SECONDS = 0.5


def starts_in_speech(spans) -> bool:
    """VAD speech begins at the capture's first samples (likely mid-utterance)."""
    return bool(spans) and min(start for start, _ in spans) <= START_IN_SPEECH_SECONDS
