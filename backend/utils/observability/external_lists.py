"""Count four list GETs and staged promote POSTs, including dependency/validation rejections."""

import os
from typing import Any

from prometheus_client import Counter, Histogram

from database.firestore_read_origin import RequestReadTrace, bind_request_read_trace, reset_request_read_trace

EXTERNAL_LIST_HTTP_TOTAL = Counter(
    'omi_external_list_http_requests_total',
    'External list GETs and staged promote POSTs including auth, rate-limit and validation failures',
    ['route', 'outcome'],
)
EXTERNAL_LIST_CACHE_TOTAL = Counter(
    'omi_external_list_cache_total', 'External list response cache activity', ['route', 'outcome']
)

EXTERNAL_LIST_READS = Histogram(
    'omi_external_list_firestore_reads_per_request',
    'SDK billed-equivalent Firestore reads per external list/promote request, including auth and empty query floors',
    ['route'],
    buckets=(0, 1, 5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400, 25000),
)

ROUTES = frozenset(
    {'/v1/dev/user/conversations', '/v1/dev/user/memories', '/v1/dev/user/action-items', '/v1/mcp/memories'}
)

STAGED_PROMOTE_ROUTE = '/v1/staged-tasks/promote'


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
            or not (
                (scope.get('method') == 'GET' and scope.get('path') in ROUTES)
                or (scope.get('method') == 'POST' and scope.get('path') == STAGED_PROMOTE_ROUTE)
            )
            or os.getenv('OMI_EXTERNAL_LIST_METRICS_ENABLED', '').strip().lower() == 'false'
        ):
            await self.app(scope, receive, send)
            return
        status = 500
        truncated = False
        trace = RequestReadTrace()
        token = bind_request_read_trace(trace)
        observed = False

        def finish_trace() -> None:
            nonlocal observed
            if not observed:
                with trace.lock:
                    trace.closed = True
                    reads = trace.reads
                observed = True
                EXTERNAL_LIST_READS.labels(route=scope['path']).observe(reads)

        async def observe_send(message: Any) -> None:
            nonlocal status, truncated
            if message['type'] == 'http.response.start':
                status = message['status']
                truncated = any(
                    k.lower() in (b'x-omi-list-truncated', b'x-scan-truncated') and v.lower() == b'true'
                    for k, v in message.get('headers', [])
                )
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                finish_trace()
            await send(message)

        try:
            await self.app(scope, receive, observe_send)
        finally:
            finish_trace()
            reset_request_read_trace(token)
            EXTERNAL_LIST_HTTP_TOTAL.labels(route=scope['path'], outcome=_outcome(status, truncated)).inc()
