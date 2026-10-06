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

    def begin_finalize(self) -> None:
        self._pending += 1
        self._audio_after_finalize = False
        if self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='missing_ack').inc()

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
