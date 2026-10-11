"""Bounded fresh-PCM recovery of an exhausted live voice allowance."""

from dataclasses import dataclass
from typing import Optional
from weakref import ref, ReferenceType

from utils.audio import AudioRingBuffer

RECOVERY_ATTEMPTS_PER_TRANCHE = 3
RECOVERY_MAX_TRANCHES = 2
RECOVERY_FRESH_SECONDS = 10
RECOVERY_COOLDOWN_SECONDS = 30
MAX_RECOVERED_VOICE_ATTEMPTS = 18


@dataclass
class VoiceRecovery:
    ring_ref: Optional[ReferenceType[AudioRingBuffer]]
    watermark: int
    audio_watermark: float
    next_grant_at: float
    fresh_bytes: int = 0
    tranches: int = 0
    has_evidence: bool = False
    accepted: bool = False

    @classmethod
    def checkpoint(cls, ring: Optional[AudioRingBuffer], now: float) -> 'VoiceRecovery':
        # Legacy test doubles or unavailable provenance fail closed.
        proven = ring if isinstance(ring, AudioRingBuffer) else None
        bounds = proven.get_time_range() if proven else None
        return cls(
            ref(proven) if proven else None,
            proven.total_bytes_written if proven else 0,
            bounds[1] if bounds else 0,
            now + RECOVERY_COOLDOWN_SECONDS,
        )

    def observe(self, ring: object, ranges: list[tuple[float, float]]) -> None:
        current = self.ring_ref() if self.ring_ref else None
        if ring is not current:
            proven = ring if isinstance(ring, AudioRingBuffer) else None
            self.ring_ref = ref(proven) if proven else None
            self.watermark = proven.total_bytes_written if proven else 0
            bounds = proven.get_time_range() if proven else None
            self.audio_watermark = bounds[1] if bounds else 0
            self.fresh_bytes = 0
            return
        if current is None or self.tranches >= RECOVERY_MAX_TRANCHES:
            return
        ring = current
        bounds = ring.get_time_range()
        if bounds is None:
            return
        for lo, hi in sorted(ranges):
            positions = ring.proven_byte_ranges(max(lo, self.audio_watermark), hi)
            before = self.watermark
            for start, end in positions:
                # Physical and capture-axis high-watermarks exclude both window
                # repeats and PCM re-appended onto overlapping timestamp spans.
                self.fresh_bytes += max(0, end - max(start, self.watermark))
                self.watermark = max(self.watermark, end)
            if self.watermark > before:
                self.audio_watermark = max(self.audio_watermark, min(hi, bounds[1]))
        self.fresh_bytes = min(self.fresh_bytes, RECOVERY_FRESH_SECONDS * ring.bytes_per_second)

    def grant(self, now: float) -> bool:
        ring = self.ring_ref() if self.ring_ref else None
        if (
            ring is None
            or self.tranches >= RECOVERY_MAX_TRANCHES
            or now < self.next_grant_at
            or self.fresh_bytes < RECOVERY_FRESH_SECONDS * ring.bytes_per_second
        ):
            return False
        self.tranches += 1
        self.fresh_bytes = 0
        self.watermark = ring.total_bytes_written
        bounds = ring.get_time_range()
        self.audio_watermark = bounds[1] if bounds else self.audio_watermark
        self.next_grant_at = now + RECOVERY_COOLDOWN_SECONDS
        return True

    def attempt_limit(self, base: int) -> int:
        return min(MAX_RECOVERED_VOICE_ATTEMPTS, base + self.tranches * RECOVERY_ATTEMPTS_PER_TRANCHE)
