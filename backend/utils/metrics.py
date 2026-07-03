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
    'Chat extraction requests routed through or around the LLM gateway',
    ['feature', 'outcome', 'reason'],
)

LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS = Counter(
    'llm_gateway_chat_extraction_comparisons_total',
    'Privacy-safe comparison buckets between shadow gateway output and legacy extraction output',
    ['feature', 'field', 'outcome'],
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
