from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS = Gauge(
    'backend_listen_active_ws_connections',
    'Number of currently active WebSocket connections in backend-listen',
)

PUSHER_ACTIVE_WS_CONNECTIONS = Gauge(
    'pusher_active_ws_connections',
    'Number of currently active WebSocket connections in pusher',
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
for _journey in ('chat_response', 'pusher_session', 'live_transcription', 'capture_finalization'):
    OMI_JOURNEY_ACCEPTED_TOTAL.labels(journey=_journey)
    for _outcome in ('success', 'failure', 'cancelled', 'stale'):
        OMI_JOURNEY_TERMINAL_TOTAL.labels(journey=_journey, outcome=_outcome)
        OMI_JOURNEY_LATENCY_SECONDS.labels(journey=_journey, outcome=_outcome)
for _outcome in ('requeued', 'enqueue_failed'):
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL.labels(outcome=_outcome)

LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS = Gauge(
    'listen_finalization_oldest_nonterminal_age_seconds',
    'Age of the oldest queued, leased, or blocked listen finalization job',
)

LISTEN_FINALIZATION_JOB_STATUS = Gauge(
    'listen_finalization_jobs',
    'Current durable listen finalization job count by non-success status',
    ['status'],
)

LISTEN_FINALIZATION_RETRIES_TOTAL = Counter(
    'listen_finalization_retries_total',
    'Durable listen finalization jobs replayed by the reconciler',
)

LISTEN_FINALIZATION_DEAD_LETTER_TOTAL = Counter(
    'listen_finalization_dead_letter_total',
    'Listen finalization jobs terminalized after their final Cloud Tasks attempt',
)

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
    'Terminal live-STT failures by bounded provider, outcome, client platform, revision, and phase',
    ['provider', 'outcome', 'client_platform', 'deployment_version', 'phase'],
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
    ['event', 'source'],
)

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


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
