import os
import threading
from typing import Any

from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest, start_http_server

from utils.journey_metrics_contract import (
    CLIENT_JOURNEY_ISSUE_CLASSES,
    CLIENT_JOURNEY_OUTCOMES,
    CLIENT_JOURNEYS,
    CLIENT_KINDS,
)

BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS = Gauge(
    'backend_listen_active_ws_connections',
    'Number of currently active WebSocket connections in backend-listen',
)

PUSHER_ACTIVE_WS_CONNECTIONS = Gauge(
    'pusher_active_ws_connections',
    'Number of currently active WebSocket connections in pusher',
)

PUSHER_QUEUE_DROPS = Counter(
    'pusher_queue_drops_total',
    'Pusher queue items dropped by bounded queue name',
    ['queue'],
)

PUSHER_QUEUE_DROPPED_BYTES = Counter(
    'pusher_queue_dropped_bytes_total',
    'Pusher queue bytes dropped by bounded queue name',
    ['queue'],
)

PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS = Counter(
    'pusher_private_cloud_upload_drops_total',
    'Private cloud audio batches dropped after exhausting upload attempts',
)

PUSHER_CIRCUIT_BREAKER_STATE = Gauge(
    'pusher_circuit_breaker_state',
    'Pusher circuit breaker state (0=closed, 1=open, 2=half_open)',
)

PUSHER_CIRCUIT_BREAKER_REJECTIONS = Counter(
    'pusher_circuit_breaker_rejections_total',
    'Total pusher connection attempts rejected by circuit breaker',
)

PUSHER_SESSION_DEGRADED = Gauge(
    'pusher_sessions_degraded',
    'Number of sessions currently in degraded mode (pusher unavailable)',
)

OMI_JOURNEY_ACCEPTED_TOTAL = Counter(
    'omi_journey_accepted_total',
    'Accepted real-traffic product journeys by closed journey name',
    ['journey'],
)

OMI_JOURNEY_TERMINAL_TOTAL = Counter(
    'omi_journey_terminal_total',
    'Terminal real-traffic product journey outcomes by closed journey and outcome names',
    ['journey', 'outcome'],
)

OMI_JOURNEY_LATENCY_SECONDS = Histogram(
    'omi_journey_latency_seconds',
    'Elapsed time from accepted real-traffic journey to terminal outcome',
    ['journey', 'outcome'],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900, 3600, 21600, 86400),
)

OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL = Counter(
    'omi_capture_finalization_reconciliations_total',
    'Reconciliation attempts for stale nonterminal capture finalization jobs',
    ['outcome'],
)

# Export zero-valued children from a healthy but idle process. This lets
# Prometheus/Grafana distinguish no user traffic from an absent scrape target.
for _journey in ('chat_response', 'pusher_session', 'capture_finalization'):
    OMI_JOURNEY_ACCEPTED_TOTAL.labels(journey=_journey)
    for _outcome in ('success', 'failure', 'cancelled', 'stale'):
        OMI_JOURNEY_TERMINAL_TOTAL.labels(journey=_journey, outcome=_outcome)
        OMI_JOURNEY_LATENCY_SECONDS.labels(journey=_journey, outcome=_outcome)
for _outcome in ('requeued', 'enqueue_failed'):
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL.labels(outcome=_outcome)

JIT_ROLLOUT_DECISION_TOTAL = Counter(
    'jit_rollout_decision_total',
    'JIT admission decisions by bounded labels; never labeled by UID',
    ['effective', 'reason', 'stage', 'error_class'],
)

JIT_ROLLOUT_DECISION_LATENCY_SECONDS = Histogram(
    'jit_rollout_decision_latency_seconds',
    'Wall time to resolve a JIT admission decision',
    ['stage'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

JIT_WRITER_MODE_TRANSITION_TOTAL = Counter(
    'jit_writer_mode_transition_total',
    'Canonical writer-mode transitions; never labeled by UID',
    ['from_mode', 'to_mode'],
)

JIT_FIRST_OPEN_TOTAL = Counter(
    'jit_first_open_total',
    'First-open obligation claim, complete, and fail events; never labeled by UID',
    ['event', 'effect'],
)


def record_jit_rollout_decision(
    *,
    effective: str,
    reason: str,
    stage: str,
    error_class: str,
    latency_ms: int,
) -> None:
    JIT_ROLLOUT_DECISION_TOTAL.labels(
        effective=effective,
        reason=reason,
        stage=stage,
        error_class=error_class,
    ).inc()
    JIT_ROLLOUT_DECISION_LATENCY_SECONDS.labels(stage=stage).observe(max(0, latency_ms) / 1000.0)


def record_jit_writer_mode_transition(*, from_mode: str, to_mode: str) -> None:
    JIT_WRITER_MODE_TRANSITION_TOTAL.labels(from_mode=from_mode, to_mode=to_mode).inc()


def record_jit_first_open(*, event: str, effect: str) -> None:
    JIT_FIRST_OPEN_TOTAL.labels(event=event, effect=effect).inc()


OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL = Counter(
    'omi_client_journey_accepted_total',
    'Accepted client-segmented product journeys by bounded journey and client kind',
    ['journey', 'client_kind'],
)

OMI_CLIENT_JOURNEY_TERMINAL_TOTAL = Counter(
    'omi_client_journey_terminal_total',
    'Terminal client-segmented product journey outcomes by bounded labels',
    ['journey', 'client_kind', 'outcome'],
)

OMI_CLIENT_JOURNEY_ISSUES_TOTAL = Counter(
    'omi_client_journey_issues_total',
    'Bounded issue detail for failed or degraded client-segmented product journeys',
    ['journey', 'client_kind', 'issue_class'],
)

OMI_CLIENT_JOURNEY_DURATION_SECONDS = Histogram(
    'omi_client_journey_duration_seconds',
    'Elapsed time from acceptance to terminal client-segmented journey outcome',
    ['journey', 'outcome'],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900, 3600, 21600, 86400),
)

# This is a separate, versioned contract from the legacy omi_journey_* family
# above. Keep client_kind off the histogram: its 16 bucket series per child
# would multiply the most expensive metric without helping outcome segmentation.
# Initialize the complete bounded product so healthy-but-idle exporters expose
# zeros instead of making an idle process indistinguishable from a missing one.
for _journey in CLIENT_JOURNEYS:
    for _client_kind in CLIENT_KINDS:
        OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL.labels(journey=_journey, client_kind=_client_kind)
        for _outcome in CLIENT_JOURNEY_OUTCOMES:
            OMI_CLIENT_JOURNEY_TERMINAL_TOTAL.labels(
                journey=_journey,
                client_kind=_client_kind,
                outcome=_outcome,
            )
        for _issue_class in CLIENT_JOURNEY_ISSUE_CLASSES:
            OMI_CLIENT_JOURNEY_ISSUES_TOTAL.labels(
                journey=_journey,
                client_kind=_client_kind,
                issue_class=_issue_class,
            )
    for _outcome in CLIENT_JOURNEY_OUTCOMES:
        OMI_CLIENT_JOURNEY_DURATION_SECONDS.labels(journey=_journey, outcome=_outcome)

# The gauges below report one GLOBAL Firestore-derived quantity, and every
# replica publishes the same value. Aggregate them with max(), never sum(): a
# sum() multiplies the real number by the replica count and, while replicas run
# different images, mixes two different answers to the same question.
LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS = Gauge(
    'listen_finalization_oldest_nonterminal_age_seconds',
    'Global age of the oldest queued, leased, or blocked listen finalization job; '
    'replicated per process, aggregate with max() not sum()',
)

# Durable-queue substrate age. Every replica publishes the same Firestore-derived
# value for a given queue name; aggregate with max(), never sum(). Do not
# zero-initialize: absent() means the periodic publisher has not run.
OMI_QUEUE_OLDEST_READY_AGE_SECONDS = Gauge(
    'omi_queue_oldest_ready_age_seconds',
    'Age in seconds of the oldest ready durable-queue item; replicated per process, ' 'aggregate with max() not sum()',
    ['queue'],
)

OMI_QUEUE_NAMES = (
    'memory_outbox',
    'candidate_integration_outbox',
    'chat_first_proactive_intents',
    'conversation_finalization_jobs',
    'daily_summary_hour_groups',
    'daily_memory_sweep',
    'vector_repair_outbox',
    'task_recurrence_inbox',
    'frame_deletion_outbox',
    'projection_repairs',
)

LISTEN_FINALIZATION_JOB_STATUS = Gauge(
    'listen_finalization_jobs',
    'Global durable listen finalization job count by non-success status; replicated '
    'per process, aggregate with max() not sum(). dead_letter is cumulative and only '
    'ever rises: it is an all-time terminal total, not a backlog',
    ['status'],
)

LISTEN_FINALIZATION_DURABLE_JOBS = Gauge(
    'listen_finalization_durable_jobs',
    'Global authoritative Firestore finalization jobs by closed durable lifecycle '
    'state; replicated per process, aggregate with max() not sum()',
    ['state'],
)

LISTEN_FINALIZATION_RETRIES_TOTAL = Counter(
    'listen_finalization_retries_total',
    'Durable listen finalization jobs replayed by the reconciler',
)

LISTEN_FINALIZATION_DEAD_LETTER_TOTAL = Counter(
    'listen_finalization_dead_letter_total',
    'Listen finalization jobs terminalized after their final Cloud Tasks attempt',
)

LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL = Counter(
    'listen_finalization_stale_processing_reconciliations_total',
    'Stale bare-processing conversation reconciliation outcomes by the crash-orphan sweep',
    ['outcome'],
)

# Zero-initialize the closed outcome set so an idle process exports every
# series, distinguishing no stranded rows from a missing scrape target.
for _outcome in ('completed', 'migrated', 'skipped', 'error'):
    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome=_outcome)

LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL = Counter(
    'listen_finalization_byok_abandonments_total',
    'Stranded BYOK finalization job dispositions by the abandonment sweep',
    ['outcome'],
)

# Zero-initialize the closed outcome set so an idle process exports every
# series, distinguishing no stranded rows from a missing scrape target.
for _outcome in ('abandoned_conversation_closed', 'abandoned_bookkeeping', 'skipped', 'error'):
    LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome=_outcome)

LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS = Counter(
    'llm_gateway_chat_extraction_requests_total',
    'LLM gateway routing outcomes by feature (serving, fallback, direct_exception, shadow)',
    ['feature', 'mode', 'outcome', 'reason'],
)

LLM_GATEWAY_DIRECT_EXCEPTION_REQUESTS = Counter(
    'llm_gateway_direct_exception_requests_total',
    'Inventoried direct-provider surfaces used while gateway feature mode is active',
    ['surface', 'reason'],
)

LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS = Counter(
    'llm_gateway_chat_extraction_comparisons_total',
    'Privacy-safe comparison buckets between shadow gateway output and legacy extraction output',
    ['feature', 'field', 'outcome'],
)

LLM_GATEWAY_CIRCUIT_OPEN = Gauge(
    'llm_gateway_circuit_open',
    'Whether this backend process is bypassing the LLM gateway after transport failures',
)

LLM_GATEWAY_CLIENT_FIRST_BYTE_SECONDS = Histogram(
    'llm_gateway_client_first_byte_seconds',
    'Client time until the gateway returns a non-streaming response, first stream event, or transport failure',
    ['feature', 'outcome'],
    buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 15, 30),
)

OMI_FALLBACK_TOTAL = Counter(
    'omi_fallback_total',
    'Fallback / resilience transitions by component, path, reason, and outcome',
    ['component', 'from_mode', 'to_mode', 'reason', 'outcome'],
)

DESKTOP_UPDATE_RESOLUTION_TOTAL = Counter(
    'desktop_update_resolution_total',
    'Desktop update channel resolutions by platform, channel, and source',
    ['platform', 'channel', 'source'],
)

DESKTOP_UPDATE_POINTER_MISMATCH_TOTAL = Counter(
    'desktop_update_pointer_mismatch_total',
    'Desktop update pointer and legacy release mismatches',
    ['platform', 'channel', 'field'],
)

DESKTOP_UPDATE_POINTER_AGE_SECONDS = Gauge(
    'desktop_update_pointer_age_seconds',
    'Age of the selected desktop update pointer',
    ['platform', 'channel'],
)

DESKTOP_UPDATE_LKG_AGE_SECONDS = Gauge(
    'desktop_update_lkg_age_seconds',
    'Age of the selected desktop update last-known-good cache entry',
    ['platform', 'channel'],
)

DESKTOP_UPDATE_FEED_VALID = Gauge(
    'desktop_update_feed_valid',
    'Whether a valid desktop update was resolved for a channel',
    ['platform', 'channel'],
)

OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL = Counter(
    'omi_sync_dispatch_attempts_total',
    'Sync v2 dispatch attempts by selected mode (denominator for fallback rates)',
    ['mode'],
)

OMI_SYNC_LANE_JOBS_TOTAL = Counter(
    'omi_sync_lane_jobs_total',
    'Sync jobs admitted by lane, capture-time trust, and outcome',
    ['lane', 'trust', 'outcome'],
)

OMI_SYNC_LANE_SPEECH_MS_TOTAL = Counter(
    'omi_sync_lane_speech_ms_total',
    'Successfully reserved sync speech milliseconds by lane',
    ['lane'],
)

OMI_SYNC_RECORDING_AGE_SECONDS = Histogram(
    'omi_sync_recording_age_seconds',
    'Oldest recording age at sync admission by lane',
    ['lane'],
    buckets=(300, 1800, 3600, 21600, 86400, 259200, 604800, 1209600, 2592000),
)

OMI_SYNC_QUEUE_WAIT_SECONDS = Histogram(
    'omi_sync_queue_wait_seconds',
    'Cloud Tasks queue wait before sync processing by lane',
    ['lane'],
    buckets=(1, 5, 15, 30, 60, 300, 900, 3600, 21600, 86400),
)

OMI_SYNC_BACKFILL_DAILY_USED_MS = Gauge(
    'omi_sync_backfill_daily_used_ms',
    'Current UTC-day processed speech milliseconds reserved by historical sync',
)

OMI_TRANSCRIPTION_ACCEPTED_TOTAL = Counter(
    'omi_voice_transcription_accepted_total',
    'Accepted prerecorded transcription journeys by bounded route and runtime identity',
    ['route', 'provider', 'client_platform', 'deployment_version'],
)

OMI_TRANSCRIPTION_COMPLETED_TOTAL = Counter(
    'omi_voice_transcription_completed_total',
    'Terminal semantic outcomes for accepted prerecorded transcription journeys',
    ['route', 'provider', 'outcome', 'client_platform', 'deployment_version'],
)

OMI_TRANSCRIPTION_LATENCY_SECONDS = Histogram(
    'omi_voice_transcription_latency_seconds',
    'End-to-end latency for accepted prerecorded transcription journeys',
    ['route', 'provider', 'outcome', 'client_platform', 'deployment_version'],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)

OMI_SYNC_TRANSCRIPTION_SEGMENTS_TOTAL = Counter(
    'omi_sync_transcription_segments_total',
    'Terminal semantic outcomes for sync transcription segments',
    ['provider', 'model', 'lane', 'outcome', 'deployment_version'],
)

OMI_SYNC_TRANSCRIPTION_JOBS_TOTAL = Counter(
    'omi_sync_transcription_job_total',
    'Terminal semantic outcomes for sync transcription jobs',
    ['provider', 'model', 'lane', 'outcome', 'deployment_version'],
)

OMI_LIVE_STT_TERMINAL_FAILURES_TOTAL = Counter(
    'omi_live_stt_terminal_failures_total',
    'Terminal live-STT failures by bounded provider, outcome, client platform, environment, and phase',
    ['provider', 'outcome', 'client_platform', 'deployment_environment', 'phase'],
)

OMI_LIVE_STT_ACCEPTED_TOTAL = Counter(
    'omi_live_stt_accepted_total',
    'Accepted live-STT attempts by bounded provider, client platform, and deployment environment',
    ['provider', 'client_platform', 'deployment_environment'],
)

# Whether misaligned frames actually occur in production is unmeasured; Velma rejects
# them outright, so this counter is what tells a Velma canary if that was the cause.
OMI_LIVE_STT_MISALIGNED_FRAMES_TOTAL = Counter(
    'omi_live_stt_misaligned_frames_total',
    'Live-STT frames that were not a whole number of 16-bit samples, by provider and pipeline stage',
    ['provider', 'stage'],
)

OMI_VAD_GATE_AUDIO_SECONDS_TOTAL = Counter(
    'omi_vad_gate_audio_seconds_total',
    'Live VAD gate audio seconds by gate outcome and mode',
    ['outcome', 'mode'],
)

OMI_VAD_GATE_SESSIONS_TOTAL = Counter(
    'omi_vad_gate_sessions_total',
    'Live VAD gate sessions by mode',
    ['mode'],
)

OMI_LIVE_STT_TERMINAL_TOTAL = Counter(
    'omi_live_stt_terminal_total',
    'Terminal live-STT outcomes for accepted attempts by bounded labels',
    ['provider', 'outcome', 'client_platform', 'deployment_environment', 'phase'],
)

# /v4/listen funnel for sources the client cannot self-report (phone_call today):
# accepted socket -> first decoded audio -> transcript delivery. Sources and outcomes
# are closed enums; no user, call, or session identifiers appear as labels.
OMI_LISTEN_ACCEPTED_TOTAL = Counter(
    'omi_listen_accepted_total',
    'Accepted /v4/listen WebSocket sessions by bounded transcription source and client platform',
    ['transcription_source', 'client_platform'],
)

OMI_LISTEN_AUDIO_OUTCOME_TOTAL = Counter(
    'omi_listen_audio_outcome_total',
    'Per-session listen audio outcomes by bounded transcription source, outcome, and client platform',
    ['transcription_source', 'outcome', 'client_platform'],
)

OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL = Counter(
    'omi_listen_unknown_channel_prefix_total',
    'Multi-channel frames dropped for an unknown channel prefix, by bounded source and client platform',
    ['transcription_source', 'client_platform'],
)

TASK_WORKSTREAM_ASSOCIATION_TOTAL = Counter(
    'task_workstream_association_total',
    'Canonical evidence association outcomes with bounded adjudication reasons',
    ['outcome', 'reason'],
)

TASK_INTELLIGENCE_ATTRIBUTION_TOTAL = Counter(
    'task_intelligence_attribution_total',
    'Privacy-safe task intervention, feedback, and outcome events',
    ['event', 'subject_kind', 'code'],
)

CHAT_FIRST_PROACTIVE_TOTAL = Counter(
    'chat_first_proactive_total',
    'Chat-first proactive engine activity with no user content',
    ['event', 'source', 'reason'],
)

MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL = Counter(
    'memory_universal_read_origin_total',
    'Logical memory rows considered by the universal repository by physical origin',
    ['origin'],
)

MEMORY_HISTORICAL_SUPPRESSION_TOTAL = Counter(
    'memory_historical_suppression_total',
    'Historical rows suppressed by canonical identity or canonical state',
    ['reason'],
)

LIST_READ_REQUEST_TOTAL = Counter(
    'list_read_requests_total',
    'Bounded list GET read outcomes by route',
    ['route', 'outcome'],
)

LIST_READ_DOCUMENTS_TOTAL = Counter(
    'list_read_documents_total',
    'Documents scanned by bounded list GET reads by route',
    ['route'],
)

LIST_READ_SECONDS = Histogram(
    'list_read_seconds',
    'Wall-clock seconds spent in bounded list GET reads by route',
    ['route'],
)

for _list_route in ('action-items', 'conversations', 'memories'):
    LIST_READ_DOCUMENTS_TOTAL.labels(route=_list_route)
    LIST_READ_SECONDS.labels(route=_list_route)
    for _list_outcome in ('complete', 'truncated'):
        LIST_READ_REQUEST_TOTAL.labels(route=_list_route, outcome=_list_outcome)

MEMORY_HISTORICAL_MATERIALIZATION_TOTAL = Counter(
    'memory_historical_materialization_total',
    'Lazy historical-memory materialization outcomes',
    ['outcome'],
)

for _origin in ('canonical', 'historical'):
    MEMORY_UNIVERSAL_READ_ORIGIN_TOTAL.labels(origin=_origin)
for _reason in ('canonical_identity', 'canonical_state'):
    MEMORY_HISTORICAL_SUPPRESSION_TOTAL.labels(reason=_reason)
for _outcome in ('not_needed', 'committed'):
    MEMORY_HISTORICAL_MATERIALIZATION_TOTAL.labels(outcome=_outcome)

AUTH_FLOW_EVENTS = Counter(
    'auth_flow_events_total',
    'Auth flow events by provider, stage, outcome, and sanitized failure class',
    ['provider', 'stage', 'outcome', 'failure_class'],
)

AUTH_FLOW_DURATION_SECONDS = Histogram(
    'auth_flow_duration_seconds',
    'Auth flow duration in seconds by provider and terminal state',
    ['provider', 'terminal_state'],
)

OMI_SUBSCRIPTION_EVENTS = Counter(
    'omi_subscription_events_total',
    'Stripe subscription lifecycle events observed via webhook. Counts webhook '
    'deliveries, which Stripe may retry, so treat these as an operational trend '
    'signal rather than a billing-grade figure; Stripe remains source of truth.',
    ['event', 'plan', 'interval', 'reason'],
)


# Pusher readiness / drain gauges. Label-free (low cardinality) so they scrape
# cheaply. Initialized to serving below so an idle healthy pod reads
# pusher_ready=1 / pusher_drain_in_progress=0 and is distinguishable from a
# missing scrape target (a labelless Gauge defaults to 0, which would wrongly
# read as "draining"). utils.readiness.ReadinessGate flips these on drain.
PUSHER_READY = Gauge(
    'pusher_ready',
    '1 = serving new traffic, 0 = draining',
)
PUSHER_DRAIN_IN_PROGRESS = Gauge(
    'pusher_drain_in_progress',
    '1 = drain initiated, readiness closed',
)
PUSHER_READY.set(1)
PUSHER_DRAIN_IN_PROGRESS.set(0)


# GET /v1/action-items read-cost controls (see database/action_items_cache.py).
# `action_items_list` was 48.8% of every billable Firestore document read before
# the 12/min per-uid cap shipped (#12258); the residual cost is a small number of
# large-backlog accounts re-reading a full backlog on every allowed poll. These
# two counters are how a deploy proves the remaining reads went away, rather than
# inferring it from the billing export a week later.
OMI_ACTION_ITEMS_LIST_THROTTLED_TOTAL = Counter(
    'omi_action_items_list_throttled_total',
    'GET /v1/action-items requests rejected with 429 by a list ceiling',
    ['client', 'policy'],
)

OMI_ACTION_ITEMS_LIST_CACHE_TOTAL = Counter(
    'omi_action_items_list_cache_total',
    'GET /v1/action-items list responses by cache outcome (a hit or not_modified reads zero Firestore documents)',
    ['outcome'],
)


def record_action_items_list_throttled(*, client: str, policy: str) -> None:
    OMI_ACTION_ITEMS_LIST_THROTTLED_TOTAL.labels(client=client, policy=policy).inc()


def record_action_items_list_cache(outcome: str) -> None:
    """outcome: hit | not_modified | miss | bypass | unavailable."""
    OMI_ACTION_ITEMS_LIST_CACHE_TOTAL.labels(outcome=outcome).inc()


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


_sidecar_server_lock = threading.Lock()
_sidecar_server: Any | None = None
_sidecar_server_thread: threading.Thread | None = None


def start_metrics_sidecar_server() -> None:
    """Expose the process registry only on loopback for the Cloud Run sidecar."""
    raw_port = os.environ.get('PROMETHEUS_SIDECAR_PORT', '').strip()
    if not raw_port:
        return
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise RuntimeError('PROMETHEUS_SIDECAR_PORT must be an integer') from exc
    if not 1 <= port <= 65535:
        raise RuntimeError('PROMETHEUS_SIDECAR_PORT must be between 1 and 65535')

    global _sidecar_server, _sidecar_server_thread
    with _sidecar_server_lock:
        if _sidecar_server is not None:
            return
        _sidecar_server, _sidecar_server_thread = start_http_server(port, addr='127.0.0.1')


def stop_metrics_sidecar_server() -> None:
    global _sidecar_server, _sidecar_server_thread
    with _sidecar_server_lock:
        server = _sidecar_server
        thread = _sidecar_server_thread
        _sidecar_server = None
        _sidecar_server_thread = None
    if server is None:
        return
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=5)
