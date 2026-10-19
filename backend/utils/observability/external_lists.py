"""Count four list GETs and staged promote POSTs, including dependency/validation rejections."""

import os
from typing import Any

from prometheus_client import Counter, Histogram

from utils.observability.firestore_request_reads import (
    RequestReadTrace,
    ReadComponent,
    bind_request_read_trace,
    read_component,
    reset_request_read_trace,
)

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

ACTION_ITEMS_READ_COMPONENTS = Histogram(
    'omi_dev_action_items_firestore_reads_by_component',
    'SDK billed-equivalent reads per Developer action-item request; components partition the request total',
    ['component'],
    buckets=(0, 1, 5, 10, 25, 50, 100, 200, 400, 800, 1600, 3200, 6400, 25000),
)
ACTION_ITEMS_PAGE_PARAMETERS = Histogram(
    'omi_dev_action_items_page_parameter',
    'Effective Developer action-item pagination; offsets above 25000 recorded as 25001, including cache hits',
    ['parameter'],
    buckets=(0, 1, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 25000),
)
ACTION_ITEMS_PAGE_ROWS = Counter(
    'omi_dev_action_items_page_rows_total',
    'Developer action-item rows filtered or discarded at fixed list stages; not additional billed reads',
    ['stage'],
)
ACTION_ITEMS_REQUEST_SHAPES = Counter(
    'omi_dev_action_items_request_shapes_total',
    'Fixed filter/completion shapes and response cache outcomes for Developer action-item requests',
    ['filters', 'completion', 'cache'],
)


def action_items_details_enabled() -> bool:
    return os.getenv('OMI_DEV_ACTION_ITEMS_READ_DETAILS_ENABLED', '').strip().lower() != 'false'


def observe_action_items_page(limit: int, offset: int) -> None:
    if action_items_details_enabled():
        ACTION_ITEMS_PAGE_PARAMETERS.labels(parameter='limit').observe(limit)
        # HTTP accepts arbitrary Python ints. Cap only telemetry above its last
        # finite bucket, so float conversion cannot turn a valid offset into 500.
        ACTION_ITEMS_PAGE_PARAMETERS.labels(parameter='offset').observe(min(offset, 25001))


def observe_action_items_rows(stage: str, amount: int = 1) -> None:
    if stage in {'deleted', 'locked', 'invalid', 'slack', 'offset', 'returned'} and action_items_details_enabled():
        ACTION_ITEMS_PAGE_ROWS.labels(stage=stage).inc(amount)


def observe_action_items_shape(conversation: bool, dated: bool, completed: bool | None, hit: bool) -> None:
    if action_items_details_enabled():
        filters = ('conversation_date' if dated else 'conversation') if conversation else ('date' if dated else 'none')
        completion = 'default' if completed is None else ('completed' if completed else 'incomplete')
        ACTION_ITEMS_REQUEST_SHAPES.labels(filters=filters, completion=completion, cache='hit' if hit else 'miss').inc()


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
        details = scope['path'] == '/v1/dev/user/action-items' and action_items_details_enabled()

        def finish_trace() -> None:
            nonlocal observed
            if not observed:
                with trace.lock:
                    trace.closed = True
                    reads = trace.reads
                    components = dict(trace.components)
                observed = True
                EXTERNAL_LIST_READS.labels(route=scope['path']).observe(reads)
                if details:
                    for component in ReadComponent:
                        ACTION_ITEMS_READ_COMPONENTS.labels(component=component.value).observe(
                            components.get(component.value, 0)
                        )

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
            # Dependencies run before the sync handler, which switches to OTHER.
            with read_component(ReadComponent.AUTH):
                await self.app(scope, receive, observe_send)
        finally:
            finish_trace()
            reset_request_read_trace(token)
            EXTERNAL_LIST_HTTP_TOTAL.labels(route=scope['path'], outcome=_outcome(status, truncated)).inc()
