# LIFECYCLE: permanent
"""Receiver-observed provenance carried through the managed Soniox queue.

No provenance is inferred from duration, VAD, wall time or adjacent packets.
Unknown sends still consume compact provider time at the wire boundary.
"""

from contextvars import ContextVar
from collections import deque
from typing import Any

from utils.observability.fallback import record_fallback

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
    """Reported padding anchors, with irreversible per-transport association loss.

    A normal single acknowledgment racing PCM may leave the cursor uncertain.
    Ambiguous acknowledgments cannot identify a future control, even if that
    control is the only pending one and its report conserves emitted PCM.
    """

    mode = 'reported'

    def __init__(self, sample_rate: int) -> None:
        from utils.stt.soniox_wire_metrics import wire_metrics, finalize_gate_metrics

        self._metrics = wire_metrics()
        self._gate = finalize_gate_metrics()
        self.sample_rate = sample_rate
        self.samples = 0
        self._pending = 0
        self._audio_inflight = 0
        self._audio_after_finalize = False
        self._uncertain = False
        self._association_lost = False
        self._last_ack_position: int | None = None
        self._checkpoints_closed = False
        # Telemetry counts successful writes only. Receive can settle a control
        # inside its send await; defer that outcome until write completion.
        self._gate_pending = 0
        self._control_inflight = False
        self._control_outcome: str | None = None
        self._state = 'placeable'
        self._gate.sockets.labels(mode=self.mode, state=self._state).inc()

    @property
    def placeable(self) -> bool:
        return not self._uncertain

    @property
    def pending_from(self) -> int | None:
        return None

    def _update_state(self) -> None:
        if self._checkpoints_closed:
            return
        state = 'association_lost' if self._association_lost else 'uncertain' if self._uncertain else 'placeable'
        if state == 'placeable' and self.pending_from is not None:
            state = 'pending'
        if state != self._state:
            self._gate.sockets.labels(mode=self.mode, state=self._state).dec()
            self._gate.sockets.labels(mode=self.mode, state=state).inc()
            self._state = state

    def _record_settled(self, outcome: str, count: int) -> None:
        self._gate.controls.labels(mode=self.mode, outcome=outcome).inc(count)

    def _settle_controls(self, outcome: str, count: int | None = None) -> None:
        available = self._gate_pending + int(self._control_inflight and self._control_outcome is None)
        count = available if count is None else min(count, available)
        completed = min(count, self._gate_pending)
        self._gate_pending -= completed
        self._record_settled(outcome, completed)
        if count > completed:
            self._control_outcome = outcome

    def finalize_written(self) -> None:
        self._gate.controls.labels(mode=self.mode, outcome='sent').inc()
        outcome = self._control_outcome
        self._control_inflight = False
        self._control_outcome = None
        if outcome is not None or self._association_lost or self._checkpoints_closed:
            self._record_settled(outcome or 'unverified', 1)
        else:
            self._gate_pending += 1

    def write_failed(self) -> None:
        # No sent/settled count for the failed write. Any preceding successful
        # controls are now unverified and cannot authorize future sends.
        self._control_inflight = False
        self._control_outcome = None
        self._lose_association('unverified')

    def _lose_association(self, outcome: str = 'mismatch') -> None:
        if not self._association_lost:
            self._association_lost = True
            self._gate.association_lost.labels(mode=self.mode).inc()
            record_fallback(
                component='stt_live_session',
                from_mode='soniox',
                to_mode='soniox',
                reason='other',
                outcome='degraded',
            )
        self._uncertain = True
        self._settle_controls(outcome)
        self._update_state()

    def begin_audio(self) -> bool:
        self._audio_inflight += 1
        if self._pending:
            self._audio_after_finalize = True
            self._uncertain = True
            self._update_state()
        return self.placeable

    def end_audio(self, length: int) -> None:
        self._audio_inflight -= 1
        self.samples += length

    def begin_finalize(self) -> int:
        self._pending += 1
        self._audio_after_finalize = False
        self._control_inflight = True
        self._control_outcome = 'unverified' if self._association_lost or self._checkpoints_closed else None
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
        single = self._pending == acknowledgments == 1
        uncontested = single and not (self._audio_after_finalize or self._audio_inflight)
        self._pending = max(0, self._pending - acknowledgments)
        self._uncertain = True
        total, final = message.get('total_audio_proc_ms'), message.get('final_audio_proc_ms')
        position = None
        if type(total) is int and type(final) is int and total == final and total >= 0:
            numerator = total * self.sample_rate
            if numerator % 1000 == 0:
                position = numerator // 1000
        if self._association_lost or self._checkpoints_closed:
            self._settle_controls('unverified', settled)
            self._update_state()
            self._raced(settled)
            # Preserve the reported-only display/reopen cursor used on main.
            # This bookkeeping is never capture authorization: uncertainty
            # stays latched and every subsequent send lacks capture spans.
            if self.mode == 'reported' and not self._checkpoints_closed and uncontested:
                if position is not None and position >= self.samples:
                    hole = position - self.samples
                    self.samples = position
                    return hole
            return 0
        repeated = position is not None and self._last_ack_position is not None and position <= self._last_ack_position
        if not single or position is None or repeated or (uncontested and position < self.samples):
            self._lose_association()
            return self._raced(settled)
        self._last_ack_position = position
        if not uncontested:
            self._settle_controls('unverified', settled)
            self._update_state()
            return self._raced(settled)
        hole = position - self.samples
        self.samples = position
        self._uncertain = False
        self._settle_controls('verified', settled)
        if self._state == 'uncertain':
            self._gate.recoveries.labels(mode=self.mode).inc()
        self._update_state()
        self._metrics.checkpoints.labels(outcome='clean').inc()
        return hole

    def _raced(self, settled: int) -> int:
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='raced').inc(settled)
        return 0

    def close(self) -> None:
        """Settle successful controls and release occupancy once at receive end."""
        if not self._checkpoints_closed:
            self._settle_controls('unverified')
            self._metrics.checkpoints.labels(outcome='missing_ack').inc(self._pending)
            self._gate.sockets.labels(mode=self.mode, state=self._state).dec()
            self._checkpoints_closed = True
        # Telemetry closure never clears pending controls or grants capture.


class OrderedSonioxProviderClock(SonioxProviderClock):
    """Bounded FIFO predictions; association loss locks this transport forever."""

    mode = 'ordered'

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

    def _record_settled(self, outcome: str, count: int) -> None:
        super()._record_settled(outcome, count)
        self._ordered_metrics.labels(outcome=outcome).inc(count)

    @property
    def pending_from(self) -> int | None:
        return self._predictions[0][0] if self._predictions else None

    def begin_audio(self) -> bool:
        if not self._modeled:
            return super().begin_audio()
        self._audio_inflight += 1
        if self._pending:
            self._audio_after_finalize = True
        return self.placeable

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
            return 0
        before = self.samples
        quantum = 1920  # Probed stt-rt-v5 mono pcm_s16le / 16 kHz only.
        self.samples = (before // quantum + 1) * quantum
        self._predictions.append((before, self.samples, self._emitted))
        self._update_state()
        return self.samples - before

    def invalidate(self, outcome: str = 'unverified', *, association_lost: bool = True) -> None:
        first = self.pending_from if self.pending_from is not None else self.samples
        self.invalid_from = first if self.invalid_from is None else min(first, self.invalid_from)
        self._predictions.clear()
        self._modeled = False
        if association_lost:
            self._lose_association(outcome)
        else:
            self._uncertain = True
            self._settle_controls(outcome)
            self._update_state()

    def write_failed(self) -> None:
        super().write_failed()
        self.invalidate()

    def response(self, message: dict[str, Any]) -> int:
        acknowledgments = sum(
            isinstance(token, dict) and token.get('is_final') is True and token.get('text') == '<fin>'
            for token in message.get('tokens') or []
        )
        if not acknowledgments:
            return 0
        if not self._modeled:
            return super().response(message)
        # Multiple <fin>s share one position; they cannot identify controls.
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
            self.invalidate('mismatch')
            self._pending = max(0, self._pending - acknowledgments)
            return self._raced(settled)
        uncontested = self._pending == 1 and not (self._audio_after_finalize or self._audio_inflight)
        _, self._verified_position, self._verified_audio = self._predictions.popleft()
        self._pending -= 1
        self._settle_controls('verified', 1)
        if not self._predictions and self._state == 'pending':
            self._gate.recoveries.labels(mode=self.mode).inc()
        self._update_state()
        if not self._checkpoints_closed:
            self._metrics.checkpoints.labels(outcome='clean' if uncontested else 'raced').inc()
        return 0  # Hole already reserved at the ordered wire boundary.

    def close(self) -> None:
        if self._predictions:
            self.invalidate(association_lost=False)
        super().close()
