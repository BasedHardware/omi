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
CAPTURE_AUDIO = Counter(
    'omi_listen_demand_capture_audio_seconds_total',
    'Decoded listen capture seconds before VAD or replay',
    ['demand_cohort'],
)
EXHAUSTED_SESSIONS = Counter(
    'omi_listen_demand_exhausted_sessions_total',
    'Completed backend-STT sessions with or without an exhausted selection/recovery hop',
    ['demand_cohort', 'outcome'],
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
for _cohort in DEMAND_COHORTS:
    CAPTURE_AUDIO.labels(demand_cohort=_cohort)
    for _provider in ('soniox', 'modulate', 'deepgram'):
        WIRE_AUDIO.labels(provider=_provider, demand_cohort=_cohort)
    for _reason in ('first_text_deadline', 'capacity_full', 'other'):
        _subtypes = (
            ('buffer_cap', 'span_cap', 'admission', 'replay_ring_cap', 'queue_timeout', 'unknown')
            if _reason == 'capacity_full'
            else ('none',)
        )
        for _subtype in _subtypes:
            for _outcome in ('recovered', 'degraded', 'exhausted'):
                FAILURE_DETAIL.labels(
                    demand_cohort=_cohort, reason=_reason, capacity_subtype=_subtype, outcome=_outcome
                )
    for _outcome in ('yes', 'no'):
        EXHAUSTED_SESSIONS.labels(demand_cohort=_cohort, outcome=_outcome)
    for _trigger in ('first_output', 'visible_return'):
        OUTPUT_LATENCY.labels(demand_cohort=_cohort, trigger=_trigger)
        for _outcome in ('started', 'delivered', 'no_output'):
            OUTPUT_EVENTS.labels(demand_cohort=_cohort, trigger=_trigger, outcome=_outcome)


def demand_cohort() -> str:
    telemetry = current_demand.get()
    return telemetry.cohort if telemetry is not None else 'ineligible'


class DemandTelemetry:
    def __init__(self, cohort: str):
        if cohort not in DEMAND_COHORTS:
            raise ValueError('invalid demand cohort')
        self.cohort = cohort
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
            CAPTURE_AUDIO.labels(demand_cohort=self.cohort).inc(seconds)

    def observe_visibility(self, payload) -> None:
        foreground, visible = payload.get('foreground'), payload.get('transcript_visible')
        state = None
        if type(foreground) is bool and type(visible) is bool and (foreground or not visible):
            state = 'visible' if visible else 'hidden'
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
            OUTPUT_LATENCY.labels(demand_cohort=self.cohort, trigger='first_output').observe(
                max(0, now - self.first_audio_at)
            )
            self.first_output = True
            self.output_event('first_output', 'delivered')
        if self.visible_at is not None:
            OUTPUT_LATENCY.labels(demand_cohort=self.cohort, trigger='visible_return').observe(
                max(0, now - self.visible_at)
            )
            self.visible_at = None
            self.output_event('visible_return', 'delivered')

    def output_event(self, trigger: str, outcome: str) -> None:
        OUTPUT_EVENTS.labels(demand_cohort=self.cohort, trigger=trigger, outcome=outcome).inc()

    def finish(self) -> None:
        if not self.finished:
            self.finished = True
            if self.first_audio_at is not None and not self.first_output:
                self.output_event('first_output', 'no_output')
            if self.visible_at is not None:
                self.output_event('visible_return', 'no_output')
                self.visible_at = None
            EXHAUSTED_SESSIONS.labels(demand_cohort=self.cohort, outcome='yes' if self.exhausted else 'no').inc()


class WireAudioMeter:
    """Pin at transport creation; call only after a successful binary audio write."""

    def __init__(self, provider: str, sample_rate: int, channels: int = 1):
        self.telemetry = current_demand.get()
        self.provider = provider
        self.bytes_per_second = 2 * sample_rate * channels

    def written(self, data: bytes | str) -> None:
        if self.telemetry is not None and isinstance(data, bytes) and data and self.bytes_per_second > 0:
            WIRE_AUDIO.labels(provider=self.provider, demand_cohort=self.telemetry.cohort).inc(
                len(data) / self.bytes_per_second
            )


class MeteredSyncTransport:
    """Observe the Deepgram SDK's synchronous websocket write, below its error handling."""

    def __init__(self, transport, meter: WireAudioMeter):
        self.transport = transport
        self.meter = meter

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def send(self, data, *args, **kwargs):
        result = self.transport.send(data, *args, **kwargs)
        self.meter.written(data)
        return result
