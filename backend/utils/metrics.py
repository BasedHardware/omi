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
