"""Bounded, observational collapse signal; never an input to speaker decisions."""

from collections import deque
from dataclasses import dataclass, field

COLLAPSE_SEGMENT_THRESHOLD = 10
COLLAPSE_REJECTION_THRESHOLD = 3


@dataclass
class LiveSpeakerCollapseMonitor:
    voice: tuple[int, str] | None = None
    consecutive_segments: int = 0
    rejected_matches: int = 0
    emitted: bool = False
    recent_segments: deque[str] = field(default_factory=lambda: deque(maxlen=128))
    recent_matches: deque[str] = field(default_factory=lambda: deque(maxlen=128))

    def observe(self, speaker_id: int, scope: str, segment_id: str) -> bool:
        if not segment_id or segment_id in self.recent_segments:
            return False
        self.recent_segments.append(segment_id)
        voice = (speaker_id, scope)
        if voice != self.voice:
            self.voice = voice
            self.consecutive_segments = self.rejected_matches = 0
            self.emitted = False
            self.recent_matches.clear()
        self.consecutive_segments += 1
        return self._signal()

    def match(self, speaker_id: int, scope: str, segment_id: str, *, accepted: bool) -> bool:
        if self.voice != (speaker_id, scope) or segment_id in self.recent_matches:
            return False
        self.recent_matches.append(segment_id)
        if accepted:
            self.rejected_matches = 0
        else:
            self.rejected_matches += 1
        return self._signal()

    def _signal(self) -> bool:
        if (
            not self.emitted
            and self.consecutive_segments >= COLLAPSE_SEGMENT_THRESHOLD
            and self.rejected_matches >= COLLAPSE_REJECTION_THRESHOLD
        ):
            self.emitted = True
            return True
        return False
