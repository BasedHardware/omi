"""Bounded live-chain and windowed TDT metrics, collected by the listen scrape."""

import logging
import threading
from typing import Any, NamedTuple

from prometheus_client import Counter, Gauge, Histogram

from config.live_stt_recovery import recovery_enabled
from utils.observability.demand_cohort import DEMAND_COHORTS, initialize_metric

DEMAND_LANE_SECONDS = Counter(
    'omi_listen_live_lane_seconds_total',
    'Listen wall time on the actual serving lane',
    ['lane', 'reason', 'demand_cohort'],
)
DEMAND_SWITCHES = Counter(
    'omi_listen_live_lane_switches_total',
    'Adopted listen lane changes, including demand handovers and fallbacks',
    ['from_lane', 'to_lane', 'reason'],
)

PAID_SPILLOVER_ADMISSIONS = Counter(
    'omi_stt_paid_spillover_admissions_total', 'Fleet paid router spillover budget decisions', ['provider', 'outcome']
)
NO_TEXT_RESCUE_AUDIO = Counter(
    'omi_stt_no_text_rescue_audio_seconds_total', 'Paid audio admitted during bounded progress rescue', ['provider']
)
NO_TEXT_RESCUE_OUTCOME = Counter(
    'omi_stt_no_text_rescue_total', 'Bounded no-text rescue intervals and successor proof', ['outcome']
)

REPLAY_WALL = Histogram(
    'omi_stt_replay_wall_seconds',
    'Elapsed prefix replay time',
    ['source', 'successor'],
    buckets=(0.1, 1, 5, 10, 15, 20, 25),
)
REPLAY_AUDIO = Counter('omi_stt_replay_audio_seconds_total', 'Replay audio admitted', ['source', 'successor'])
REPLAY_QUEUE_HIGH_WATER = Histogram(
    'omi_stt_replay_queue_high_water',
    'Maximum adapter queue items during replay',
    ['source', 'successor'],
    buckets=(1, 2, 4, 8, 16, 32, 64, 256, 2000),
)
REPLAY_SKIPPED = Counter(
    'omi_stt_replay_skipped_seconds_total', 'Unanswered audio skipped by replay wall budget', ['source', 'successor']
)
REPLAY_CLOSED = Counter(
    'omi_stt_replay_successor_closed_total', 'Successor deaths during replay', ['source', 'successor']
)
TAIL_CATCHUP = Counter(
    'omi_stt_live_tail_catchup_seconds_total',
    'Live tail audio delivered above the endpoint sustained rate to drain a held backlog',
    ['successor'],
)
RECOVERY_ATTEMPTS = Counter(
    'omi_stt_recovery_attempts_total',
    'Actual live recovery dials by dead provider family and attempted successor family',
    ['source', 'successor', 'demand_cohort'],
)
LIVE_SESSION_TERMINAL_AFTER_TEXT = Counter(
    'omi_live_session_terminal_after_text_total',
    'Live sessions closed with a terminal STT failure after a transcript was already delivered',
    ['provider', 'demand_cohort'],
)

WINDOW_ACTIVE = Gauge('omi_stt_window_sessions_active', 'Admitted windowed TDT sessions')
WINDOW_CAP = Gauge('omi_stt_window_sessions_capacity', 'Process windowed TDT session cap')
WINDOW_ADMISSION = Counter('omi_stt_window_admissions_total', 'Window admission decisions', ['outcome'])
WINDOW_PRESSURE_REFRESH = Counter(
    'omi_stt_window_batch_pressure_refresh_total', 'Batch pressure fleet refresh outcomes', ['outcome']
)
WINDOW_PRESSURE_REPLICAS = Gauge(
    'omi_stt_window_batch_pressure_replicas', 'Fresh and DNS-ready GPU replicas for window admission', ['state']
)
WINDOW_PRESSURE_REFUSAL = Counter(
    'omi_stt_window_batch_pressure_refusals_total', 'Window batch pressure refusals', ['reason']
)
WINDOW_POSTS = Counter('omi_stt_window_posts_total', 'Window POST outcomes', ['outcome'])
WINDOW_LATENCY = Histogram('omi_stt_window_post_seconds', 'Window POST latency', buckets=(0.1, 0.5, 1, 2, 4, 8, 15))
WINDOW_FIRST_TEXT = Histogram(
    'omi_stt_window_first_text_seconds',
    'Wall seconds from first VAD speech sent to first nonempty windowed transcript',
    ['demand_cohort'],
    buckets=(2, 5, 10, 15, 20, 25, 30, 45, 60),
)
WINDOW_SESSION_OUTCOME = Counter(
    'omi_stt_window_session_outcome_total', 'Windowed sessions with VAD speech', ['outcome', 'reason']
)
WINDOW_REPLAY_SAFE_TRIMS = Counter(
    'omi_stt_window_replay_safe_trims_total',
    'Window replay ring trims through emitted anchors or speech-free capture',
)
NONWINDOW_REPLAY_SETTLES = Counter(
    'omi_stt_nonwindow_replay_settles_total',
    'Non-window replacement legs that settled horizon-aged quiet replay capture instead of failing over',
    ['provider'],
)
SESSION_LOCAL_EXCLUSION_RELEASES = Counter(
    'omi_stt_session_local_exclusion_releases_total',
    'Providers re-admitted to a session after a successor was adopted; they had left only for replay overflow',
    ['provider'],
)
SAME_TARGET_RETRIES = Counter(
    'omi_stt_same_target_retries_total',
    'One jittered same-target retry after a connection-level failure (path=connect|death)',
    ['provider', 'path', 'outcome'],
)
COST_ESCAPE_VOTES = Counter(
    'omi_stt_cost_routing_escape_votes_total',
    'Trial votes admitted from outside the re-entry cohort because no stage-100 target served the user',
    ['target'],
)
WINDOW_REPLAY_CUT_REQUESTS = Counter(
    'omi_stt_window_replay_cut_requests_total', 'Coalesced requests to cut a held TDT tail under capture-ring pressure'
)
WINDOW_REPLAY_CUT_PERFORMED = Counter(
    'omi_stt_window_replay_cut_performed_total', 'Requested cuts that emit a forced tail and advance the replay anchor'
)
WINDOW_REPLAY_CUT_SKIPPED = Counter(
    'omi_stt_window_replay_cut_skipped_total',
    'Requested cuts deferred at request time or not performed on a POST result',
    ['reason'],
)
WINDOW_STRANDED_FLUSHES = Counter(
    'omi_stt_window_stranded_flushes_total',
    'Long-silence fragment flush attempts and answers',
    ['outcome'],
)
WINDOW_CANARY_OUTCOME = Counter(
    'omi_stt_window_canary_transcript_outcome_total',
    'Listen transcript outcome by stable window allocation arm',
    ['arm', 'outcome', 'demand_cohort'],
)
COST_CANARY_OUTCOME = Counter(
    'omi_stt_cost_routing_canary_outcome_total',
    'Managed listen transcript outcome by router allocation at initialization',
    ['arm', 'outcome', 'demand_cohort'],
)
for _arm in ('on', 'control'):
    for _outcome in ('transcribed', 'no_transcript', 'too_short'):
        for _cohort in DEMAND_COHORTS:
            initialize_metric(COST_CANARY_OUTCOME, arm=_arm, outcome=_outcome, demand_cohort=_cohort)
WINDOW_CONTEXT = Histogram(
    'omi_stt_window_context_seconds',
    'Posted TDT context duration',
    buckets=(3, 6, 9, 12, 18, 24, 30),
)
WINDOW_FORCED_CUTS = Counter(
    'omi_stt_window_forced_cuts_total',
    'Window POSTs that cut an unfinished segment at max context or replay-ring pressure',
)
WINDOW_HEAD_RECOVERIES = Counter(
    'omi_stt_window_head_recoveries_total',
    'Window POSTs whose skipped leading speech was re-posted on its own',
    ['outcome'],
)
WINDOW_DECODER_LOOPS = Counter(
    'omi_stt_window_decoder_loops_total',
    'Repeated-phrase decoder loops collapsed out of windowed TDT segments',
)
WINDOW_EMISSION_DROPS = Counter(
    'omi_stt_window_emission_drops_total',
    'Windowed TDT segments dropped instead of emitted at a fabricated position',
    ['reason'],
)
CONNECT_BACKOFF = Counter(
    'omi_stt_connect_backoff_total',
    'Per-target connect-refusal backoff decisions at the configured live chain connect seam',
    ['provider', 'event'],
)
CHAIN_EXHAUSTED = Counter(
    'omi_stt_chain_exhausted_total', 'Configured live chains that could not serve', ['demand_cohort']
)
for _cohort in DEMAND_COHORTS:
    initialize_metric(CHAIN_EXHAUSTED, demand_cohort=_cohort)
    initialize_metric(WINDOW_FIRST_TEXT, demand_cohort=_cohort)

LEG_ATTEMPTS = Counter('omi_stt_leg_attempts_total', 'Configured-chain connection results', ['to_mode', 'outcome'])
RECONNECT = Counter(
    'omi_stt_reconnect_total', 'Bounded live STT reconnect decisions', ['provider', 'reason', 'outcome']
)
REPLAY_SECONDS = Counter('omi_stt_replay_seconds_total', 'Live STT audio replayed after reconnect', ['provider'])
LANGUAGE_CONSTRAINT = Counter(
    'omi_stt_language_constraint_total',
    'Language information sent on live STT connections',
    ['provider', 'constraint', 'primary_group', 'arm'],
)
OUTPUT_LANGUAGE_SEGMENTS = Counter(
    'omi_stt_output_language_segments_total',
    'Finalized live STT segment language conformance',
    ['provider', 'primary_group', 'arm', 'conformance', 'profile_source'],
)
LEG_TRANSCRIPT_OUTCOME = Counter(
    'omi_stt_leg_transcript_outcome_total',
    'Provider leg outcome after VAD speech; text must arrive within the configured deadline',
    ['provider', 'language', 'outcome'],
)
ROUTING_DECISION = Counter('omi_stt_routing_decisions_total', 'Health-weighted routing decisions', ['outcome'])
FLEET_HEALTH_WRITE_DROPPED = Counter(
    'omi_stt_fleet_health_write_dropped_total',
    'Fleet-health Redis writes dropped before persistence by bounded path, kind, and reason',
    ['write_path', 'kind', 'reason'],
)
FLEET_HEALTH_WRITE_ATTEMPTED = Counter(
    'omi_stt_fleet_health_write_attempted_total',
    'Fleet-health Redis write attempts by bounded path and kind',
    ['write_path', 'kind'],
)
FLEET_HEALTH_WRITE_WRITTEN = Counter(
    'omi_stt_fleet_health_write_written_total',
    'Fleet-health writes acknowledged by Redis by bounded path and kind',
    ['write_path', 'kind'],
)

_logger = logging.getLogger(__name__)


def safe_counter_increment(counter: Any, *, metric_name: str, **labels: str) -> None:
    """Record best-effort telemetry without allowing instrumentation to affect serving."""
    try:
        counter.labels(**labels).inc()
    except Exception:
        try:
            _logger.debug('Unable to increment metric %s', metric_name, exc_info=True)
        except Exception:
            # A logging handler failure must not turn a metrics failure into a request failure.
            pass


def record_fleet_health_write_attempted(*, write_path: str, kind: str) -> None:
    safe_counter_increment(
        FLEET_HEALTH_WRITE_ATTEMPTED,
        metric_name='omi_stt_fleet_health_write_attempted_total',
        write_path=write_path,
        kind=kind,
    )


def record_fleet_health_write_written(*, write_path: str, kind: str) -> None:
    safe_counter_increment(
        FLEET_HEALTH_WRITE_WRITTEN,
        metric_name='omi_stt_fleet_health_write_written_total',
        write_path=write_path,
        kind=kind,
    )


def record_fleet_health_write_dropped(*, write_path: str, kind: str, reason: str) -> None:
    safe_counter_increment(
        FLEET_HEALTH_WRITE_DROPPED,
        metric_name='omi_stt_fleet_health_write_dropped_total',
        write_path=write_path,
        kind=kind,
        reason=reason,
    )


ROUTING_DECISION_LATENCY = Histogram(
    'omi_stt_routing_decision_seconds',
    'Time spent choosing the eligible live STT order without network operations',
    buckets=(0.0001, 0.0005, 0.001, 0.002, 0.005, 0.01, 0.05),
)

COST_DECISION = Counter(
    'omi_stt_cost_routing_decisions_total', 'Cost routing selections and skips', ['target', 'reason']
)
COST_BENCH = Gauge('omi_stt_cost_routing_benched', 'Fleet target health bench', ['target'])
COST_STAGE = Gauge(
    'omi_stt_cost_routing_stage', 'Pod view of global target stage: 0, 5, 25, 100; NaN unknown', ['target']
)
COST_SNAPSHOT_AT = Gauge(
    'omi_stt_cost_routing_snapshot_timestamp_seconds', 'Last complete Redis cost snapshot on this pod'
)
# A never-refreshed pod is unknown, not a Unix-epoch/stale snapshot.
COST_SNAPSHOT_AT.set(float('nan'))
COST_STATE_KNOWN = Gauge(
    'omi_stt_cost_routing_state_known', 'Whether this pod has evidence about global target health', ['target']
)
COST_EVENTS = Counter(
    'omi_stt_cost_routing_events_total', 'CAS health transitions by state scope', ['target', 'event', 'scope']
)
COST_ALL_DEGRADED = Counter(
    'omi_stt_cost_routing_all_degraded_total', 'Selections with every eligible target unhealthy', ['target']
)
COST_IGNORED_DEATHS = Counter(
    'omi_stt_cost_routing_ignored_deaths_total',
    'Claimed socket deaths excluded by client departure, owner teardown or pod drain',
    ['target', 'reason', 'boundary'],
)
COST_OBSERVATIONS = Counter(
    'omi_stt_cost_routing_observations_total', 'Classified cost health outcomes', ['target', 'outcome', 'reason']
)
COST_SETTLEMENTS = Counter(
    'omi_stt_cost_routing_settlements_total',
    'Serving decisions requiring matching health observations',
    ['target', 'outcome', 'reason', 'path'],
)
COST_EVIDENCE_ERRORS = Counter(
    'omi_stt_cost_routing_evidence_errors_total', 'Serving settlements whose health emission failed'
)
COST_EMISSION_ACK_ERRORS = Counter(
    'omi_stt_cost_routing_emission_ack_errors_total',
    'Emission acknowledgement errors only; does not validate classification, lifecycle coverage or Redis persistence',
)
MANAGED_LEGS_OPENED = Counter(
    'omi_stt_managed_legs_opened_total', 'Managed connected legs handed off by the chain', ['target']
)
MANAGED_LEGS_SETTLED = Counter(
    'omi_stt_managed_legs_settled_total', 'Handed-off managed legs reaching terminal settlement', ['target']
)
MANAGED_LEGS_OPEN = Gauge(
    'omi_stt_managed_legs_open', 'Handed-off managed transports not yet released, independent of settlement', ['target']
)
COST_VOTES = Counter(
    'omi_stt_cost_routing_votes_total',
    'Settled evidence applied or excluded by the shared gate',
    ['target', 'scope', 'result'],
)
COST_SHADOW = Counter(
    'omi_stt_cost_routing_shadow_total',
    'Proposed vs static primary',
    ['agreement', 'static_primary', 'proposed_primary'],
)
COST_FAIL_OPEN = Counter('omi_stt_cost_routing_fail_open_total', 'Configured-order router recovery', ['reason'])
COST_NO_PERMITTED_TARGET = Counter(
    'omi_stt_cost_routing_no_permitted_target_total',
    'Routing decisions with no permitted live STT target',
)
COST_LANGUAGE_STATE = Counter(
    'omi_stt_cost_routing_language_state_total',
    'Global vs language target health disagreements observed at selection',
    ['target', 'comparison'],
)

PROVIDER_FAMILIES = ('parakeet', 'modulate', 'soniox', 'deepgram', 'unknown')


def provider_family(name: object) -> str:
    text = str(name or '').lower()
    for fam in PROVIDER_FAMILIES[:-1]:
        if fam in text:
            return fam
    return 'unknown'


# Zero-fill recovery series only on pods running recovery, so flag-off scrapes match main.
if recovery_enabled():
    for _source in PROVIDER_FAMILIES:
        for _successor in PROVIDER_FAMILIES:
            REPLAY_WALL.labels(source=_source, successor=_successor)
            REPLAY_AUDIO.labels(source=_source, successor=_successor)
            REPLAY_QUEUE_HIGH_WATER.labels(source=_source, successor=_successor)
            REPLAY_SKIPPED.labels(source=_source, successor=_successor)
            REPLAY_CLOSED.labels(source=_source, successor=_successor)
            for _cohort in DEMAND_COHORTS:
                initialize_metric(RECOVERY_ATTEMPTS, source=_source, successor=_successor, demand_cohort=_cohort)
    for _provider in PROVIDER_FAMILIES:
        TAIL_CATCHUP.labels(successor=_provider)
        for _cohort in DEMAND_COHORTS:
            initialize_metric(LIVE_SESSION_TERMINAL_AFTER_TEXT, provider=_provider, demand_cohort=_cohort)
        for _event in ('opened', 'probe', 'skipped', 'reset', 'escape'):
            CONNECT_BACKOFF.labels(provider=_provider, event=_event)


class SonioxIdleMetrics(NamedTuple):
    closes: Counter
    reopens: Counter
    latency: Histogram
    failures: Counter
    avoided: Counter
    closes_by_trigger: Counter
    cohort_closes: Counter
    cohort_reopens: Counter
    cohort_latency: Histogram
    cohort_failures: Counter
    cohort_avoided: Counter
    cohort_closes_by_trigger: Counter


_soniox_idle_metrics: SonioxIdleMetrics | None = None
_soniox_idle_lock = threading.Lock()

SONIOX_IDLE_COHORT_ARMS = ('control', 'treatment')


def soniox_idle_metrics() -> SonioxIdleMetrics:
    """Register only when an enabled Soniox socket is constructed; no off series.

    The ``omi_soniox_idle_cohort_*`` companions carry the session's treatment
    arm (``config.soniox_idle`` uid-hash cohort) so a percent rollout compares
    arms without relabelling the existing unlabeled family.
    """
    global _soniox_idle_metrics
    with _soniox_idle_lock:
        if _soniox_idle_metrics is None:
            _soniox_idle_metrics = SonioxIdleMetrics(
                Counter('omi_soniox_idle_closes_total', 'Planned paid transport closes'),
                Counter('omi_soniox_idle_reopens_total', 'Speech-triggered paid transport dials'),
                Histogram(
                    'omi_soniox_idle_reopen_seconds',
                    'Onset to replacement audio admission',
                    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
                ),
                Counter('omi_soniox_idle_reopen_failures_total', 'Failed speech-triggered transport dials'),
                Counter(
                    'omi_soniox_idle_connected_seconds_avoided_total', 'Estimated wall seconds with transport closed'
                ),
                Counter(
                    'omi_soniox_idle_closes_by_trigger_total',
                    'Planned paid transport closes by trigger (vad silence or no client frames)',
                    ['trigger'],
                ),
                Counter(
                    'omi_soniox_idle_cohort_closes_total',
                    'Planned paid transport closes by treatment arm',
                    ['arm'],
                ),
                Counter(
                    'omi_soniox_idle_cohort_reopens_total',
                    'Speech-triggered paid transport dials by treatment arm',
                    ['arm'],
                ),
                Histogram(
                    'omi_soniox_idle_cohort_reopen_seconds',
                    'Onset to replacement audio admission by treatment arm',
                    ['arm'],
                    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
                ),
                Counter(
                    'omi_soniox_idle_cohort_reopen_failures_total',
                    'Failed speech-triggered transport dials by treatment arm',
                    ['arm'],
                ),
                Counter(
                    'omi_soniox_idle_cohort_connected_seconds_avoided_total',
                    'Estimated wall seconds with transport closed by treatment arm',
                    ['arm'],
                ),
                Counter(
                    'omi_soniox_idle_cohort_closes_by_trigger_total',
                    'Planned paid transport closes by trigger and treatment arm',
                    ['arm', 'trigger'],
                ),
            )
            for _trigger in ('vad', 'no_frames'):
                _soniox_idle_metrics.closes_by_trigger.labels(trigger=_trigger)
                for _arm in SONIOX_IDLE_COHORT_ARMS:
                    _soniox_idle_metrics.cohort_closes_by_trigger.labels(arm=_arm, trigger=_trigger)
            for _arm in SONIOX_IDLE_COHORT_ARMS:
                _soniox_idle_metrics.cohort_closes.labels(arm=_arm)
                _soniox_idle_metrics.cohort_reopens.labels(arm=_arm)
                _soniox_idle_metrics.cohort_latency.labels(arm=_arm)
                _soniox_idle_metrics.cohort_failures.labels(arm=_arm)
                _soniox_idle_metrics.cohort_avoided.labels(arm=_arm)
    return _soniox_idle_metrics
