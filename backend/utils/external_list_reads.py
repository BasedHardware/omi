"""Authorized external list caching, normalized queries, and bounded read seams."""

import hashlib
import json
import logging
import os
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import BoundedSemaphore
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Request, Response
from fastapi.routing import APIRoute
from pydantic import ValidationError

from database import redis_db, action_item_versions
from utils.encryption import derive_key
from utils.executors import db_executor, submit_with_context
from utils.mcp_server.cursors import decode_cursor
from utils.mcp_server.errors import ToolExecutionError
from utils.observability.external_lists import EXTERNAL_LIST_CACHE_TOTAL, observe_action_items_rows
from utils.other.list_budget import ListReadBudget, list_read_budget_for_request
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
TTL_SECONDS = 10
VERSIONED_TTL_SECONDS = 900
MAX_BODY_BYTES = 256 * 1024
MAX_ENTRY_BYTES = MAX_BODY_BYTES + 8192
MAX_CACHE_POPULATIONS = 32
_population_slots = BoundedSemaphore(MAX_CACHE_POPULATIONS)
_client: Any = None
_HEADERS = frozenset(
    {
        'x-omi-effective-limit',
        'x-omi-has-more',
        'x-omi-next-offset',
        'x-omi-next-cursor',
        'x-next-cursor',
        'x-pagination-guidance',
    }
)


def lever_enabled(name: str) -> bool:
    """Each lever ships on; only the literal value false disables it."""
    return os.getenv(name, '').strip().lower() != 'false'


def _redis() -> Any:
    global _client
    if _client is None:
        _client = redis_db.create_bounded_redis_client(0.2)
    return _client


def _fail_open(mode: str) -> None:
    # Never log exceptions, keys, query values, or plaintext/ciphertext.
    record_fallback(
        component='redis_cache', from_mode=mode, to_mode='none', reason='other', outcome='recovered', log=logger
    )


@dataclass
class _Entry:
    uid: str
    key: str
    route: str
    expires_at: float
    started: float
    ttl: int = TTL_SECONDS
    version: str | None = None

    def event(self, outcome: str) -> None:
        EXTERNAL_LIST_CACHE_TOTAL.labels(route=self.route, outcome=outcome).inc()

    def eligible(self, response: Response) -> bool:
        reason = None
        if response.status_code != 200:
            reason = 'skip_status'
        elif any(
            response.headers.get(header, '').lower() == 'true'
            for header in ('x-omi-list-truncated', 'x-scan-truncated')
        ):
            reason = 'skip_truncated'
        elif len(response.body) > MAX_BODY_BYTES:
            reason = 'skip_body_size'
        elif time.monotonic() - self.started >= self.ttl or time.time() >= self.expires_at:
            reason = 'skip_expired'
        elif not lever_enabled('OMI_EXTERNAL_LIST_CACHE_ENABLED'):
            reason = 'skip_disabled'
        if reason:
            self.event(reason)
        return reason is None

    def store(self, response: Response) -> None:
        # Recheck after queue delay; the deadline still belongs to query start.
        if not self.eligible(response):
            return
        if self.version is not None and action_item_versions.version(self.uid) != self.version:
            self.event('skip_version_changed')
            return
        body = bytes(response.body)
        try:
            envelope = json.dumps(
                {
                    'expires_at': self.expires_at,
                    'body': body.decode('utf-8'),
                    'headers': {k: v for k, v in response.headers.items() if k.lower() in _HEADERS},
                },
                separators=(',', ':'),
            ).encode('utf-8')
            nonce = os.urandom(12)
            ciphertext = nonce + AESGCM(derive_key(self.uid)).encrypt(nonce, envelope, self.key.encode())
            if len(ciphertext) > MAX_ENTRY_BYTES or time.monotonic() - self.started >= self.ttl:
                return
            # Deduct query/serialization time using the existing Redis SET PX
            # surface. The encrypted absolute deadline also rejects late gets
            # if socket delay makes Redis retain the bytes slightly longer.
            remaining_ms = int(1000 * min(self.expires_at - time.time(), self.ttl - (time.monotonic() - self.started)))
            if remaining_ms <= 0:
                return
            _redis().set(self.key, ciphertext, px=remaining_ms)
            EXTERNAL_LIST_CACHE_TOTAL.labels(route=self.route, outcome='stored').inc()
        except Exception:
            _fail_open('cache_write')


def cached_list_response(
    request: Request | None,
    response: Response | None,
    *,
    uid: str,
    context: Any,
    query: dict[str, Any],
    max_documents: int | None = None,
) -> Response | None:
    """Call AFTER all auth/grant/rate/validation gates, with parsed effective query.

    The route adapter stores the final response-model bytes. Authorization tokens
    are hashed only in-memory as extra isolation for legacy keys lacking IDs.
    No token, uid, app/key ID, or query text is stored in Redis key names.
    """
    if request is None or not lever_enabled('OMI_EXTERNAL_LIST_CACHE_ENABLED'):
        return None
    route = request.url.path
    version = None
    ttl = TTL_SECONDS
    if route == '/v1/dev/user/action-items' and lever_enabled('OMI_DEV_ACTION_ITEMS_VERSION_CACHE_ENABLED'):
        version = action_item_versions.version(uid)
        if version is None:
            EXTERNAL_LIST_CACHE_TOTAL.labels(route=route, outcome='version_bypass').inc()
            return None  # Busy or unavailable: origin only, never a short-cache fallback.
        ttl = VERSIONED_TTL_SECONDS
    identity = {
        'collection_version': version,
        'uid': uid,
        'app': getattr(context, 'app_id', None),
        'key': getattr(context, 'key_id', None),
        'credential': hashlib.sha256(request.headers.get('authorization', '').encode()).hexdigest(),
        'route': route,
        'query': query,
        'max_documents': max_documents,
        'mcp_budget': lever_enabled('OMI_MCP_MEMORY_LIST_BUDGET_ENABLED'),
        'conversation_budget': lever_enabled('OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED'),
    }
    key = (
        'external-list:v2:'
        + hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    )
    entry = _Entry(uid, key, route, time.time() + ttl, time.monotonic(), ttl, version)
    request.state.external_list_cache_entry = entry
    try:
        raw = _redis().get(key)
        if raw and len(raw) <= MAX_ENTRY_BYTES:
            payload = json.loads(AESGCM(derive_key(uid)).decrypt(raw[:12], raw[12:], key.encode()))
            if time.time() < payload['expires_at'] <= time.time() + ttl and (
                version is None or action_item_versions.version(uid) == version
            ):
                headers = {k: v for k, v in payload['headers'].items() if k.lower() in _HEADERS}
                if response is not None:
                    headers.update(response.headers)
                EXTERNAL_LIST_CACHE_TOTAL.labels(route=route, outcome='hit').inc()
                request.state.external_list_cache_entry = None
                return Response(content=payload['body'].encode(), media_type='application/json', headers=headers)
    except Exception:
        _fail_open('cache_read')
    EXTERNAL_LIST_CACHE_TOTAL.labels(route=route, outcome='miss').inc()
    return None


def _queue_population(entry: _Entry, response: Response) -> None:
    # Never let optional population queue unbounded response bodies on the
    # shared db pool: 32 running/queued bodies retain at most 8 MiB per process.
    if not entry.eligible(response):
        return
    slots = _population_slots
    if not slots.acquire(blocking=False):
        _fail_open('cache_write_saturated')
        return
    try:
        future = submit_with_context(db_executor, entry.store, response)
    except Exception:
        slots.release()
        _fail_open('cache_write_submit')
        return

    def completed(done: Future) -> None:
        slots.release()
        if not done.cancelled() and done.exception() is not None:
            _fail_open('cache_write')

    future.add_done_callback(completed)


class ExternalListCacheRoute(APIRoute):
    """Capture bytes only after FastAPI has applied response-model validation."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            response = await original(request)
            entry = getattr(request.state, 'external_list_cache_entry', None)
            if entry is not None:
                _queue_population(entry, response)
            return response

        return handler


# Only parsed, effective parameters from the handler are admitted to cache keys.
# New list filters must be added here alongside their route and isolation tests.
_QUERY_FIELDS = {
    '/v1/dev/user/conversations': (
        'limit',
        'offset',
        'start_date',
        'end_date',
        'categories',
        'include_transcript',
        'folder_id',
        'starred',
        'cursor',
    ),
    '/v1/dev/user/memories': ('limit', 'offset', 'categories'),
    '/v1/dev/user/action-items': ('conversation_id', 'completed', 'start_date', 'end_date', 'limit', 'offset'),
    '/v1/mcp/memories': (
        'limit',
        'offset',
        'categories',
        'sort',
        'reviewed',
        'manually_added',
        'updated_after',
        'include_activity',
        'include_sensitive',
        'cursor',
    ),
}


def cached_external_list(
    request: Request | None, response: Response | None, context: Any, parameters: dict[str, Any]
) -> Response | None:
    """Select a fixed allowlist from handler locals; never serialize arbitrary locals."""
    if request is None or not lever_enabled('OMI_EXTERNAL_LIST_CACHE_ENABLED'):
        return None
    fields = _QUERY_FIELDS.get(request.url.path)
    if fields is None:
        return None
    query = {key: parameters[key] for key in fields}
    if request.url.path == '/v1/dev/user/action-items' and lever_enabled(
        'OMI_DEV_ACTION_ITEMS_CACHE_NORMALIZE_ENABLED'
    ):
        for key in ('start_date', 'end_date'):
            value = query[key]
            if isinstance(value, datetime):
                # Firestore treats naive datetimes as UTC. Only the key changes.
                query[key] = value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    if 'categories' in query:
        query['categories'] = sorted(category.value for category in parameters['category_list'])
    if 'parsed_updated_after' in parameters:
        query['updated_after'] = parameters['parsed_updated_after']
    if request.url.path == '/v1/mcp/memories' and query['cursor'] is not None:
        filters = {
            key: query[key]
            for key in (
                'categories',
                'sort',
                'reviewed',
                'manually_added',
                'include_activity',
                'include_sensitive',
            )
        }
        filters['updated_after'] = query['updated_after'].isoformat() if query['updated_after'] else None
        try:
            position = decode_cursor(query['cursor'], kind='rest_get_memories', uid=context.uid, filters=filters)
        except ToolExecutionError:
            return None  # Let the original handler report the same validation error.
        if 'uml' in position:
            # Signed inner cursors have expiry/snapshot authority checked by
            # read_page. Never reuse a response past those independent gates.
            return None
    budget = parameters.get('budget')
    return cached_list_response(
        request,
        response,
        uid=context.uid,
        context=context,
        query=query,
        max_documents=budget.max_documents if budget is not None else None,
    )


def developer_conversation_offset_budget(
    request: Request | None, response: Response | None, offset: int, context: Any = None
) -> ListReadBudget | None:
    if offset <= 0 or not lever_enabled('OMI_DEV_CONVERSATION_LIST_BUDGET_ENABLED'):
        return None
    budget = list_read_budget_for_request(
        request, route='developer-conversations', owner_uid=getattr(context, 'uid', None), context=context
    )
    if response is not None:
        response.headers['X-Pagination-Guidance'] = (
            'Prefer cursor with offset=0, include_transcript=false and no folder/starred filter; '
            'use date windows for transcript/folder/starred reads. Truncated pages are incomplete.'
        )
    return budget


def validate_developer_action_items(action_items: list[Any], response_model: Any, uid: str, log: Any) -> list[Any]:
    """Preserve per-row validation and locked-item filtering before cache serialization."""
    valid_action_items = []
    for item in action_items:
        if not isinstance(item, dict) or not item.get('id'):
            observe_action_items_rows('invalid')
            log.warning('Skipping malformed action item in Developer API action-item list')
            continue
        if item.get('is_locked', False):
            observe_action_items_rows('locked')
            continue
        try:
            valid_action_items.append(response_model.model_validate(item))
        except ValidationError as e:
            observe_action_items_rows('invalid')
            invalid_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            log.warning(
                f"Skipping invalid action item doc {item.get('id', 'unknown')} for uid {uid}: "
                f"missing/invalid fields {invalid_fields}"
            )
            continue
    return valid_action_items


def clamp_list_page(offset: int, limit: int, maximum: int) -> tuple[int, int]:
    return max(0, offset), max(1, min(limit, maximum))
