# LIFECYCLE: permanent
"""Receiver-observed provenance carried through the managed Soniox queue.

No provenance is inferred from duration, VAD, wall time or adjacent packets.
Unknown sends still consume compact provider time at the wire boundary.
"""

from contextvars import ContextVar
from collections import deque
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


class SonioxProviderClock:
    """Local provider cursor, separate from emitted PCM, with no transport waits.

    A finalize report is an anchor only while it is the sole outstanding control
    and no subsequent audio write has begun. Raced audio stays unplaceable until
    a later uncontested finalize reports an exact position. The measured 120ms
    quantum is deliberately not a runtime assumption.
    """

    def __init__(self, sample_rate: int) -> None:
        from utils.stt.soniox_wire_metrics import wire_metrics

        self._metrics = wire_metrics()
        self.sample_rate = sample_rate
        self.samples = 0
        self._pending = 0
        self._audio_inflight = 0
        self._audio_after_finalize = False
        self._uncertain = False
        self._checkpoints_closed = False

    def begin_audio(self) -> bool:
        self._audio_inflight += 1
        if self._pending:
            self._audio_after_finalize = True
            self._uncertain = True
        return not self._uncertain

    def end_audio(self, length: int) -> None:
        self._audio_inflight -= 1
        self.samples += length

    def begin_finalize(self) -> int:
        self._pending += 1
        self._audio_after_finalize = False
        if self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='missing_ack').inc()
        return 0

    def response(self, message: dict[str, Any]) -> int:
        acknowledgments = sum(
            isinstance(token, dict) and token.get('is_final') is True and token.get('text') == '<fin>'
            for token in message.get('tokens') or []
        )
        if not acknowledgments:
            return 0
        settled = min(self._pending, acknowledgments)
        uncontested = self._pending == acknowledgments == 1 and not (self._audio_after_finalize or self._audio_inflight)
        self._pending = max(0, self._pending - acknowledgments)
        self._uncertain = True
        if not uncontested:
            return self._raced(settled)
        total, final = message.get('total_audio_proc_ms'), message.get('final_audio_proc_ms')
        # Full finalize acknowledgment must carry one exact, non-regressing
        # position. A token endpoint, lagging progress report or missing field
        # cannot establish padding. Reject bools, strings and fractional samples.
        if type(total) is not int or type(final) is not int or total != final or total < 0:
            return self._raced(settled)
        numerator = total * self.sample_rate
        if numerator % 1000 or numerator // 1000 < self.samples:
            return self._raced(settled)
        position = numerator // 1000
        hole = position - self.samples
        self.samples = position
        self._uncertain = False
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='clean').inc()
        return hole

    def _raced(self, settled: int) -> int:
        # Invalid/missing positions and overlapping controls also cannot prove
        # ordering. Unsolicited/duplicate acks settle no finalize controls.
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='raced').inc(settled)
        return 0

    def close(self) -> None:
        """Settle unmatched controls once, on receive-loop termination."""
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='missing_ack').inc(self._pending)
            self._checkpoints_closed = True
        # This is telemetry settlement, never a provider-clock reset. Writes
        # already queued may still begin after receive termination; a pending
        # finalize must keep those writes unplaceable just as before metrics.


class OrderedSonioxProviderClock(SonioxProviderClock):
    """FIFO padding predictions, verified before downstream capture admission.

    Only the production 16 kHz PCM configuration has been probed. A bounded
    prediction queue cannot grant capture while its checkpoint is unverified.
    A failed prediction falls back to the original clean-checkpoint recovery.
    """

    def __init__(self, sample_rate: int) -> None:
        super().__init__(sample_rate)
        from utils.stt.soniox_wire_metrics import ordered_finalize_metrics

        self._ordered_metrics = ordered_finalize_metrics()
        self._predictions: deque[tuple[int, int, int]] = deque()
        self._modeled = True
        self.invalid_from: int | None = None
        self.reanchor: int | None = None
        self._emitted = 0
        self._verified_position = 0
        self._verified_audio = 0

    @property
    def pending_from(self) -> int | None:
        return self._predictions[0][0] if self._predictions else None

    @property
    def placeable(self) -> bool:
        return not self._uncertain

    def begin_audio(self) -> bool:
        if not self._modeled:
            return super().begin_audio()
        self._audio_inflight += 1
        if self._pending:
            self._audio_after_finalize = True
        return not self._uncertain

    def end_audio(self, length: int) -> None:
        super().end_audio(length)
        self._emitted += length

    def begin_finalize(self) -> int:
        super().begin_finalize()
        if self._checkpoints_closed:
            self.invalidate()
            return 0
        if not self._modeled:
            return 0
        if len(self._predictions) >= 64:
            self.invalidate()
            self._ordered_metrics.labels(outcome='unverified').inc()
            return 0
        before = self.samples
        quantum = 1920  # Probed stt-rt-v5 mono pcm_s16le / 16 kHz only.
        self.samples = (before // quantum + 1) * quantum
        self._predictions.append((before, self.samples, self._emitted))
        return self.samples - before

    def invalidate(self) -> None:
        self.invalid_from = self.pending_from if self.pending_from is not None else self.samples
        self._predictions.clear()
        self._modeled = False
        self._uncertain = True

    def response(self, message: dict[str, Any]) -> int:
        acknowledgments = sum(
            isinstance(token, dict) and token.get('is_final') is True and token.get('text') == '<fin>'
            for token in message.get('tokens') or []
        )
        if not acknowledgments:
            return 0
        if not self._modeled:
            previous = self.samples
            # A disproven padding model may overestimate the cursor. The next
            # uncontested report needs only conserve PCM after the last verified
            # checkpoint; its position need not exceed the rejected prediction.
            if self._pending == acknowledgments == 1 and not (self._audio_after_finalize or self._audio_inflight):
                self.samples = self._verified_position + self._emitted - self._verified_audio
            super().response(message)
            if not self._uncertain:
                self._modeled = self.samples % 1920 == 0
                self.reanchor = self.samples
                self._verified_position, self._verified_audio = self.samples, self._emitted
                return max(0, self.samples - previous)
            self.samples = previous
            return 0
        # Multiple <fin>s in one response have only one progress position.
        # Missing, duplicate or unsolicited acks cannot prove FIFO association.
        total, final = message.get('total_audio_proc_ms'), message.get('final_audio_proc_ms')
        valid = (
            acknowledgments == 1
            and bool(self._predictions)
            and type(total) is int
            and type(final) is int
            and total == final
            and total * self.sample_rate == self._predictions[0][1] * 1000
        )
        if not valid:
            settled = min(self._pending, acknowledgments)
            self.invalidate()
            self._pending = max(0, self._pending - acknowledgments)
            self._ordered_metrics.labels(outcome='mismatch').inc()
            return self._raced(settled)
        uncontested = self._pending == 1 and not (self._audio_after_finalize or self._audio_inflight)
        _, self._verified_position, self._verified_audio = self._predictions.popleft()
        self._pending -= 1
        self._ordered_metrics.labels(outcome='verified').inc()
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='clean' if uncontested else 'raced').inc()
        return 0  # Hole already reserved at the ordered wire boundary.

    def close(self) -> None:
        if self._predictions:
            self._ordered_metrics.labels(outcome='unverified').inc(len(self._predictions))
            self.invalidate()
        super().close()
