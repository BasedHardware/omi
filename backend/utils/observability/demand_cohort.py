"""Listen intent-to-treat telemetry. Only closed labels; pinned before provider selection."""

from contextvars import ContextVar
from time import monotonic

from prometheus_client import Counter, Histogram

DEMAND_COHORTS = ('admitted', 'eligible_control', 'ineligible')
current_demand: ContextVar['DemandTelemetry | None'] = ContextVar('listen_demand', default=None)
WIRE_AUDIO = Counter(
    'omi_stt_provider_wire_audio_seconds_total',
    'Listen PCM seconds successfully written to paid transports, including each replay write',
    ['provider', 'demand_cohort'],
)
SONIOX_CONNECTED = Counter(
    'omi_soniox_connected_seconds_total',
    'Wall seconds a Soniox real-time websocket was open (the vendor bills this, keepalive silence included)',
    ['demand_cohort'],
)
BATCH_WIRE_AUDIO = Counter(
    'omi_batch_live_stt_provider_wire_audio_seconds_total',
    'Successful paid transport PCM seconds including replay, pinned to batch preview admission',
    ['provider', 'batch_cohort'],
)
BATCH_CAPTURE_AUDIO = Counter(
    'omi_batch_live_stt_capture_audio_seconds_total',
    'Decoded capture seconds before VAD/replay, pinned to batch preview admission',
    ['batch_cohort'],
)
CAPTURE_AUDIO = Counter(
    'omi_listen_demand_capture_audio_seconds_total',
    'Decoded listen capture seconds before VAD or replay',
    ['demand_cohort'],
)
# Why a session was ineligible: the first failing admission condition, in the
# order capture_demand_admission checks them. ~300/10m ineligible sessions were
# the only cohort hitting chain_exhausted (2026-10-21, lead ruling f12e4a) and
# the cohort alone could not say which exclusion they share. 'none' for the
# eligible cohorts.
INELIGIBLE_REASONS = (
    'recovery_off',
    'unmanaged_chain',  # byok, multichannel or custom STT
    'onboarding',
    'phone_call',
    'language_unqualified',
    'no_profile',
)
EXHAUSTED_SESSIONS = Counter(
    'omi_listen_demand_exhausted_sessions_total',
    'Completed backend-STT sessions with or without an exhausted selection/recovery hop',
    ['demand_cohort', 'outcome', 'ineligible_reason'],
)
FAILURE_DETAIL = Counter(
    'omi_listen_demand_failure_detail_total',
    'Listen fallback hops by bounded ramp-watch reason and capacity detail; not distinct sessions',
    ['demand_cohort', 'reason', 'capacity_subtype', 'outcome'],
)
OUTPUT_EVENTS = Counter(
    'omi_listen_demand_output_events_total',
    'Output waits started, delivered, or ended without output; unfinished waits remain in flight',
    ['demand_cohort', 'trigger', 'outcome'],
)
OUTPUT_LATENCY = Histogram(
    'omi_listen_demand_output_seconds',
    'Time to delivered text from first decoded audio or a hidden-to-visible report',
    ['demand_cohort', 'trigger'],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60),
)


def record_metric(metric, labels: dict, value: float = 1, *, observe: bool = False) -> None:
    """Metric lookup, label binding and mutation are outside the serving failure domain."""
    try:
        child = metric.labels(**labels) if labels else metric
        if observe:
            child.observe(value)
        else:
            child.inc(value)
    except Exception:
        pass


def telemetry_call(owner, attribute: str, method: str, *args, **kwargs) -> None:
    """An absent or broken optional attachment must never interrupt the caller."""
    try:
        target = getattr(owner, attribute, None)
        if target is not None:
            getattr(target, method)(*args, **kwargs)
    except Exception:
        pass


def cohort_label(telemetry) -> str:
    try:
        cohort = getattr(telemetry, 'cohort', 'ineligible')
        return cohort if cohort in DEMAND_COHORTS else 'ineligible'
    except Exception:
        return 'ineligible'


def host_telemetry(host):
    try:
        return getattr(host, 'demand_telemetry', None)
    except Exception:
        return None


def host_cohort(host) -> str:
    return cohort_label(host_telemetry(host))


def initialize_metric(metric, **labels) -> None:
    try:
        metric.labels(**labels)
    except Exception:
        pass


def current_telemetry():
    try:
        return current_demand.get()
    except Exception:
        return None


def demand_cohort() -> str:
    return cohort_label(current_telemetry())


try:
    for _cohort in DEMAND_COHORTS:
        BATCH_CAPTURE_AUDIO.labels(batch_cohort=_cohort)
        CAPTURE_AUDIO.labels(demand_cohort=_cohort)
        SONIOX_CONNECTED.labels(demand_cohort=_cohort)
        for _provider in ('soniox', 'modulate', 'deepgram'):
            BATCH_WIRE_AUDIO.labels(provider=_provider, batch_cohort=_cohort)
            WIRE_AUDIO.labels(provider=_provider, demand_cohort=_cohort)
        for _reason in (
            'first_text_deadline',
            'capacity_full',
            'replay_ring_overflow',
            'gate_unavailable',
            'send_queue_full',
            'replay_send_stalled',
            'delivery_expired',
            'other',
        ):
            _subtypes = (
                ('buffer_cap', 'span_cap', 'admission', 'queue_timeout', 'unknown')
                if _reason == 'capacity_full'
                else ('none',)
            )
            for _subtype in _subtypes:
                for _outcome in ('recovered', 'degraded', 'exhausted'):
                    FAILURE_DETAIL.labels(
                        demand_cohort=_cohort, reason=_reason, capacity_subtype=_subtype, outcome=_outcome
                    )
        for _outcome in ('yes', 'no'):
            # A batch preview can move an admitted session into the ineligible
            # cohort after admission, with no exclusion reason: that series
            # reads 'none' too, so it needs its zero child.
            for _reason in (*INELIGIBLE_REASONS, 'none') if _cohort == 'ineligible' else ('none',):
                EXHAUSTED_SESSIONS.labels(demand_cohort=_cohort, outcome=_outcome, ineligible_reason=_reason)
        for _trigger in ('first_output', 'visible_return'):
            OUTPUT_LATENCY.labels(demand_cohort=_cohort, trigger=_trigger)
            for _outcome in ('started', 'delivered', 'no_output'):
                OUTPUT_EVENTS.labels(demand_cohort=_cohort, trigger=_trigger, outcome=_outcome)
except Exception:
    pass  # Missing zero children are a telemetry HOLD, never a startup failure.


class DemandTelemetry:
    def __init__(self, cohort: str, ineligible_reason: str | None = None):
        if cohort not in DEMAND_COHORTS:
            raise ValueError('invalid demand cohort')
        self.cohort = cohort
        # Bounded: a reason only exists for the ineligible cohort, and only from
        # the closed set; anything else reads 'none'.
        self.ineligible_reason = (
            ineligible_reason if cohort == 'ineligible' and ineligible_reason in INELIGIBLE_REASONS else 'none'
        )
        self.batch_cohort = 'ineligible'
        self.exhausted = False
        self.finished = False
        self.first_audio_at: float | None = None
        self.first_output = False
        self.visible_at: float | None = None
        self.visibility: str | None = None

    def capture(self, seconds: float) -> None:
        if seconds > 0:
            if self.first_audio_at is None:
                self.first_audio_at = monotonic()
                self.output_event('first_output', 'started')
            record_metric(CAPTURE_AUDIO, {'demand_cohort': self.cohort}, seconds)
            record_metric(BATCH_CAPTURE_AUDIO, {'batch_cohort': self.batch_cohort}, seconds)

    def observe_visibility(self, payload) -> None:
        foreground, visible = payload.get('foreground'), payload.get('transcript_visible')
        state = None
        if type(foreground) is bool and type(visible) is bool and (foreground or not visible):
            state = 'visible' if visible else 'hidden'
        state = self.visibility if state is None else state
        if state == 'visible' and self.visibility == 'hidden':
            self.visible_at = monotonic()
            self.output_event('visible_return', 'started')
        elif state != 'visible':
            if self.visible_at is not None:
                self.output_event('visible_return', 'no_output')
            self.visible_at = None
        self.visibility = state

    def delivered(self) -> None:
        now = monotonic()
        if not self.first_output and self.first_audio_at is not None:
            record_metric(
                OUTPUT_LATENCY,
                {'demand_cohort': self.cohort, 'trigger': 'first_output'},
                max(0, now - self.first_audio_at),
                observe=True,
            )
            self.first_output = True
            self.output_event('first_output', 'delivered')
        if self.visible_at is not None:
            record_metric(
                OUTPUT_LATENCY,
                {'demand_cohort': self.cohort, 'trigger': 'visible_return'},
                max(0, now - self.visible_at),
                observe=True,
            )
            self.visible_at = None
            self.output_event('visible_return', 'delivered')

    def output_event(self, trigger: str, outcome: str) -> None:
        record_metric(OUTPUT_EVENTS, {'demand_cohort': self.cohort, 'trigger': trigger, 'outcome': outcome}, 1)

    def finish(self) -> None:
        if not self.finished:
            self.finished = True
            if self.first_audio_at is not None and not self.first_output:
                self.output_event('first_output', 'no_output')
            if self.visible_at is not None:
                self.output_event('visible_return', 'no_output')
                self.visible_at = None
            record_metric(
                EXHAUSTED_SESSIONS,
                {
                    'demand_cohort': self.cohort,
                    'outcome': 'yes' if self.exhausted else 'no',
                    'ineligible_reason': self.ineligible_reason,
                },
                1,
            )


class WireAudioMeter:
    """Pin at transport creation; call only after a successful binary audio write."""

    def __init__(self, provider: str, sample_rate: int, channels: int = 1):
        self.telemetry = current_telemetry()
        self.batch_cohort = getattr(self.telemetry, 'batch_cohort', 'ineligible')
        self.provider = provider
        self.bytes_per_second = 2 * sample_rate * channels

    def written(self, data: bytes | str) -> None:
        if self.telemetry is not None and isinstance(data, bytes) and data and self.bytes_per_second > 0:
            record_metric(
                BATCH_WIRE_AUDIO,
                {'provider': self.provider, 'batch_cohort': self.batch_cohort},
                len(data) / self.bytes_per_second,
            )
            record_metric(
                WIRE_AUDIO,
                {'provider': self.provider, 'demand_cohort': cohort_label(self.telemetry)},
                len(data) / self.bytes_per_second,
            )


class ConnectedSecondsMeter:
    """Billed stream time for one paid transport, flushed incrementally so rates stay smooth.

    Pin at transport creation; ``flush`` from the writer's wake-ups and once with
    ``close=True`` when the websocket ends. Seconds are counted exactly once.
    """

    FLUSH_SECONDS = 5.0

    def __init__(self, metric=None):
        self.metric = SONIOX_CONNECTED if metric is None else metric
        self.cohort = cohort_label(current_telemetry())
        self.accounted_at = monotonic()
        self.closed = False

    def flush(self, *, close: bool = False) -> None:
        if self.closed:
            return
        now = monotonic()
        elapsed = now - self.accounted_at
        if not close and elapsed < self.FLUSH_SECONDS:
            return
        self.accounted_at = now
        self.closed = close
        if elapsed > 0:
            record_metric(self.metric, {'demand_cohort': self.cohort}, elapsed)


class MeteredSyncTransport:
    """Observe the Deepgram SDK's synchronous websocket write, below its error handling."""

    def __init__(self, transport, meter: WireAudioMeter):
        self.transport = transport
        self.meter = meter

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def send(self, data, *args, **kwargs):
        result = self.transport.send(data, *args, **kwargs)
        telemetry_call(self, 'meter', 'written', data)
        return result


def create_connected_meter():
    try:
        return ConnectedSecondsMeter()
    except Exception:
        return None


def create_wire_meter(provider: str, sample_rate: int, channels: int = 1):
    try:
        return WireAudioMeter(provider, sample_rate, channels)
    except Exception:
        return None


def attach_demand_telemetry(host, cohort: str, ineligible_reason: str | None = None):
    try:
        telemetry = DemandTelemetry(cohort, ineligible_reason)
        host.demand_telemetry = telemetry
        current_demand.set(telemetry)
        return telemetry
    except Exception:
        return None
