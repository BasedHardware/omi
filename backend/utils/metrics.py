from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS = Gauge(
    'backend_listen_active_ws_connections',
    'Number of currently active WebSocket connections in backend-listen',
)

PUSHER_ACTIVE_WS_CONNECTIONS = Gauge(
    'pusher_active_ws_connections',
    'Number of currently active WebSocket connections in pusher',
)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
