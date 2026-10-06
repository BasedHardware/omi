"""One bounded paid progress-rescue interval per managed listen session.

No text is ambiguous. A paid successor may decode the interval, but must not
inherit the rest of an arbitrarily long recording. At lease expiry the owner
replays unanswered capture into Parakeet using the ordinary recovery fences.
"""

import math
import os
import time
from typing import Any, Callable

from utils.stt.live_metrics import NO_TEXT_RESCUE_AUDIO, NO_TEXT_RESCUE_OUTCOME


class NoTextRescue:
    def __init__(self, *, recovery_enabled: bool, clock: Callable[[], float] | None = None) -> None:
        self.enabled = recovery_enabled and os.getenv('STT_NO_TEXT_RESCUE_ENABLED', 'false').lower() == 'true'
        try:
            seconds = float(os.getenv('STT_NO_TEXT_RESCUE_SECONDS', '60'))
        except ValueError:
            seconds = 60.0
        self.seconds = min(120.0, max(5.0, seconds)) if math.isfinite(seconds) else 60.0
        self.clock = clock or time.monotonic
        self.deadline: float | None = None
        self.completed = False
        self.returning = False
        self.text = False
        self.capture_interval: tuple[int, int] | None = None
        self.admitted_seconds = 0.0

    def start(self, reason: str, *, capture_interval: tuple[int, int] | None = None) -> None:
        if self.enabled and self.deadline is None and reason in {'first_text_deadline', 'empty_streak'}:
            self.capture_interval = capture_interval
            self.deadline = self.clock() + self.seconds
            NO_TEXT_RESCUE_OUTCOME.labels(outcome='started').inc()

    def note_transcript(self, segments: list[dict[str, Any]]) -> None:
        """Only capture-mapped text overlapping the stalled interval is evidence."""
        if not self.active or self.capture_interval is None:
            return
        first, end = self.capture_interval
        for segment in segments:
            start_sample = segment.get('_capture_start_sample')
            end_sample = segment.get('_capture_end_sample')
            if (
                str(segment.get('text') or '').strip()
                and isinstance(start_sample, int)
                and isinstance(end_sample, int)
                and first < end
                and start_sample < end_sample
                and start_sample < end
                and end_sample > first
            ):
                self.text = True

    @property
    def active(self) -> bool:
        return self.deadline is not None and not self.completed

    def remaining(self) -> float:
        return max(0.0, self.deadline - self.clock()) if self.deadline is not None else 0.0

    def audio(self, provider: str, seconds: float) -> None:
        if self.active:
            self.admitted_seconds += seconds
            NO_TEXT_RESCUE_AUDIO.labels(provider=provider).inc(seconds)

    def can_admit(self, seconds: float) -> bool:
        return not self.active or (self.remaining() > 0 and self.admitted_seconds + seconds <= self.seconds)

    def complete(self) -> None:
        if not self.active:
            return
        self.completed = True
        self.returning = True
        NO_TEXT_RESCUE_OUTCOME.labels(outcome='interval_text' if self.text else 'unproven').inc()

    def allow_window_rescue(self) -> bool:
        return not self.completed
