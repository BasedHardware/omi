"""Bounded, measurement-only raw-socket evidence; never grants capture placement."""

import logging
import math
import os
import time
from typing import Any, Callable, Iterable

from prometheus_client import REGISTRY, Counter, Histogram
from prometheus_client.metrics_core import Metric
from prometheus_client.registry import Collector

logger = logging.getLogger(__name__)
_last_sample_log = float('-inf')


def enabled() -> bool:
    return os.getenv('SONIOX_CAPTURE_AXIS_DIAGNOSTICS', 'false').strip().lower() == 'true'


AXIS_DELTA = Histogram(
    'omi_soniox_capture_axis_delta_seconds',
    'Raw original final-token/processing clocks minus socket-local reference clocks; response events',
    ['reference', 'phase', 'write_state', 'queue'],
    registry=None,
    buckets=(-60, -30, -10, -3, -1, -0.1, 0, 0.1, 1, 3, 10, 30, 60),
)
AXIS_EVENTS = Counter(
    'omi_soniox_capture_axis_events_total',
    'Successful raw Soniox wire frames and bounded diagnostic failures',
    ['event'],
    registry=None,
)
AXIS_COMPARISON = Counter(
    'omi_soniox_capture_axis_comparison_total',
    'Joint raw final-token overshoot and compact ledger conservation per response',
    ['wire', 'ledger', 'phase', 'write_state', 'queue'],
    registry=None,
)
VALIDATION_DETAIL = Counter(
    'omi_audio_timeline_elapsed_validation_detail_total',
    'Elapsed validation events separated by candidate/gate availability',
    ['provider', 'reason'],
    registry=None,
)


class _EnabledCollectors(Collector):
    """Reserve names once, but expose neither metadata nor samples while OFF."""

    metrics = (AXIS_DELTA, AXIS_EVENTS, AXIS_COMPARISON, VALIDATION_DETAIL)

    def describe(self) -> Iterable[Metric]:
        for metric in self.metrics:
            yield from metric.describe()

    def collect(self) -> Iterable[Metric]:
        if enabled():
            for metric in self.metrics:
                yield from metric.collect()


REGISTRY.register(_EnabledCollectors())


def diagnostic_error() -> None:
    """One static event label; telemetry failure must never affect transport."""
    try:
        AXIS_EVENTS.labels(event='diagnostic_error').inc()
    except Exception:
        pass


def disable_socket_diagnostics(socket: Any) -> None:
    """Setup callers stay outside the transport failure domain, even for wrappers."""
    try:
        socket.disable_capture_axis_diagnostics()
    except Exception:
        diagnostic_error()


class CaptureAxisDiagnostics:
    """Constant state per actual socket; offsets do not survive raw-socket replacement."""

    def __init__(self, rate: int):
        self.rate = rate
        self.queued = 0
        self.written = 0
        self.inflight = False
        self.connected_at = time.monotonic()
        self.first_write_at: float | None = None
        self.ledger: Callable[[], int | None] | None = None
        self.origin = 0
        self.phase = 'initial'
        self.sample_logs = 0
        self.keepalives = 0
        self.finalizes = 0

    def bind(self, ledger: Callable[[], int | None], origin: int = 0, phase: str = 'initial') -> None:
        self.ledger, self.origin, self.phase = ledger, origin, phase

    def sent(self, data: bytes | str) -> None:
        """Count actual binary frames, including unknown-provenance PCM.

        Provider-internal finalize padding is not a wire byte and must never
        inflate written PCM or acquire a synthetic capture origin.
        """
        if isinstance(data, bytes):
            self.written += len(data) // 2
            if self.first_write_at is None:
                self.first_write_at = time.monotonic()
            event = 'audio'
        else:
            event = 'end' if not data else 'keepalive' if 'keepalive' in data else 'finalize'
            self.keepalives += int(event == 'keepalive')
            self.finalizes += int(event == 'finalize')
        AXIS_EVENTS.labels(event=event).inc()

    def response(self, msg: dict[str, Any]) -> None:
        """Observe before preseconds subtraction, idle offsets, VAD remap or leg rebase."""
        global _last_sample_log
        ends = [
            float(token['end_ms']) / 1000
            for token in msg.get('tokens') or ()
            if isinstance(token, dict)
            and token.get('is_final')
            and token.get('translation_status') != 'translation'
            and token.get('text') not in ('<fin>', '<end>', '', None)
            and token.get('end_ms') is not None
        ]
        state = 'inflight' if self.inflight else 'settled'
        queue = 'drained' if self.written == self.queued else 'backlogged'

        def observe(reference: str, delta: float) -> None:
            if math.isfinite(delta):
                AXIS_DELTA.labels(reference=reference, phase=self.phase, write_state=state, queue=queue).observe(delta)

        if ends:
            end = max(ends)
            now = time.monotonic()
            observe('token_minus_written', end - self.written / self.rate)
            observe('token_minus_queued', end - self.queued / self.rate)
            observe('token_minus_connected_elapsed', end - (now - self.connected_at))
            if self.first_write_at is not None:
                observe('token_minus_first_write_elapsed', end - (now - self.first_write_at))
            ledger = self.ledger() if self.ledger is not None else None
            if ledger is not None:
                observe('queued_minus_ledger', (self.queued - (ledger - self.origin)) / self.rate)
            else:
                AXIS_EVENTS.labels(event='ledger_unavailable').inc()
            wire_result = (
                'no_audio' if not self.written else 'past' if end > self.written / self.rate + 0.1 else 'within'
            )
            ledger_delta = self.queued - (ledger - self.origin) if ledger is not None else None
            ledger_result = (
                'unavailable'
                if ledger_delta is None
                else 'equal' if ledger_delta == 0 else 'queue_ahead' if ledger_delta > 0 else 'ledger_ahead'
            )
            AXIS_COMPARISON.labels(
                wire=wire_result, ledger=ledger_result, phase=self.phase, write_state=state, queue=queue
            ).inc()
            if wire_result == 'past' and not self.inflight and self.sample_logs < 4 and now - _last_sample_log >= 60:
                self.sample_logs += 1
                _last_sample_log = now
                # All numeric, same-response evidence; no audio/text/identity.
                logger.info(
                    'soniox_capture_axis_sample phase=%s rate=%d token_end=%.6f queued=%d written=%d '
                    'ledger=%s origin=%d connected_elapsed=%.6f first_write_elapsed=%s keepalives=%d finalizes=%d '
                    'total_audio_proc_ms=%s final_audio_proc_ms=%s',
                    self.phase,
                    self.rate,
                    end,
                    self.queued,
                    self.written,
                    ledger,
                    self.origin,
                    now - self.connected_at,
                    None if self.first_write_at is None else now - self.first_write_at,
                    self.keepalives,
                    self.finalizes,
                    None if msg.get('total_audio_proc_ms') is None else float(msg['total_audio_proc_ms']),
                    None if msg.get('final_audio_proc_ms') is None else float(msg['final_audio_proc_ms']),
                )
        for key in ('total_audio_proc_ms', 'final_audio_proc_ms'):
            if msg.get(key) is not None:
                observe(key + '_minus_written', float(msg[key]) / 1000 - self.written / self.rate)


def validation_detail(provider: str, interval: Any, gate: Any, outcome: str) -> None:
    if not enabled():
        return
    reason = (
        'map_refused'
        if interval is None
        else (
            'no_gate'
            if gate is None
            else (
                'invalid_interval'
                if interval[1] <= interval[0]
                else 'vad_uncovered' if outcome == 'unknown' else 'classified'
            )
        )
    )
    try:
        VALIDATION_DETAIL.labels(provider=provider, reason=reason).inc()
    except Exception:
        pass
