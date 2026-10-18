"""Count all four list routes, including dependency/validation rejections."""

import os
from typing import Any

from prometheus_client import Counter

EXTERNAL_LIST_HTTP_TOTAL = Counter(
    'omi_external_list_http_requests_total',
    'External list GETs including auth, rate-limit and validation failures',
    ['route', 'outcome'],
)
EXTERNAL_LIST_CACHE_TOTAL = Counter(
    'omi_external_list_cache_total', 'External list response cache activity', ['route', 'outcome']
)

ROUTES = frozenset(
    {'/v1/dev/user/conversations', '/v1/dev/user/memories', '/v1/dev/user/action-items', '/v1/mcp/memories'}
)


def _outcome(status: int, truncated: bool) -> str:
    if status == 429:
        return 'rate_limited'
    if status in (401, 403):
        return 'auth_error'
    if status in (400, 413, 422):
        return 'validation_error'
    if status >= 500:
        return 'server_error'
    if truncated:
        return 'truncated'
    return 'success' if 200 <= status < 300 else 'other'


class ExternalListMetricsMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if (
            scope['type'] != 'http'
            or scope.get('method') != 'GET'
            or scope.get('path') not in ROUTES
            or os.getenv('OMI_EXTERNAL_LIST_METRICS_ENABLED', '').strip().lower() == 'false'
        ):
            await self.app(scope, receive, send)
            return
        status = 500
        truncated = False

        async def observe_send(message: Any) -> None:
            nonlocal status, truncated
            if message['type'] == 'http.response.start':
                status = message['status']
                truncated = any(
                    k.lower() in (b'x-omi-list-truncated', b'x-scan-truncated') and v.lower() == b'true'
                    for k, v in message.get('headers', [])
                )
            await send(message)

        try:
            await self.app(scope, receive, observe_send)
        finally:
            EXTERNAL_LIST_HTTP_TOTAL.labels(route=scope['path'], outcome=_outcome(status, truncated)).inc()
