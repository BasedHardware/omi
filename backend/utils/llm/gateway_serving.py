"""Gateway-only serving transport-failure classification."""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover - stubbed test environments
    httpx = None  # type: ignore[assignment]

try:
    from langchain_core.language_models import BaseChatModel  # noqa: F401
except ImportError:
    BaseChatModel = Any  # type: ignore[misc,assignment]

from utils.llm.gateway_client import GATEWAY_TRANSPORT_STATUS_CODES


def is_gateway_transport_failure(exc: BaseException) -> bool:
    """Return True for gateway unreachable / hard HTTP failures."""
    if httpx is not None:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response is not None and exc.response.status_code in GATEWAY_TRANSPORT_STATUS_CODES

    status_code = getattr(exc, 'status_code', None)
    if isinstance(status_code, int) and status_code in GATEWAY_TRANSPORT_STATUS_CODES:
        return True

    response = getattr(exc, 'response', None)
    response_status = getattr(response, 'status_code', None)
    if isinstance(response_status, int) and response_status in GATEWAY_TRANSPORT_STATUS_CODES:
        return True

    message = str(exc).casefold()
    transport_markers = (
        'timeout',
        'timed out',
        'connection refused',
        'connection reset',
        'connecterror',
        'network error',
        'bad gateway',
        'gateway timeout',
        '502',
        '504',
    )
    return any(marker in message for marker in transport_markers)
