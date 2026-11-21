"""HTTP contract for opted-in chat completion idempotency."""

import asyncio
from concurrent.futures import Future
from contextvars import copy_context
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
import json
import os
from threading import BoundedSemaphore
from typing import Any, TypeVar
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter

from config.refactor_modes import default_on
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.idempotency_store import IdempotencyError, Operation, Store, StoredResponse
from utils.executors import (
    ExecutorSaturatedError,
    GATEWAY_SETTLEMENT_WORKERS,
    gateway_idempotency_executor,
    gateway_settlement_executor,
    run_blocking,
)

HEADER = 'idempotency-key'
ACK_HEADER = 'X-Omi-Idempotency-Key'
MAX_REQUEST_BYTES = 1024 * 1024
PROVIDERS = frozenset({'openai', 'openrouter', 'anthropic'})

ENVIRONMENT_SETTING = 'LLM_GATEWAY_IDEMPOTENCY_ENVIRONMENT'
ENVIRONMENTS = frozenset({'dev', 'prod', 'local'})
KEYED_POSTS = Counter(
    'llm_gateway_keyed_posts_total', 'Authenticated chat POSTs using the keyed protocol', ['environment']
)
OUTCOMES = Counter('llm_gateway_idempotency_outcomes_total', 'Keyed chat outcomes', ['method', 'outcome'])
T = TypeVar('T')
_settlement_slots = BoundedSemaphore(GATEWAY_SETTLEMENT_WORKERS)


@dataclass(frozen=True)
class KeyedRequest:
    key: str
    scope: str
    environment: str


def _key(value: str) -> str:
    if not default_on('LLM_GATEWAY_IDEMPOTENCY_ENABLED'):
        raise IdempotencyError(503, 'idempotency_disabled')
    try:
        if len(value) == 36 and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise IdempotencyError(400, 'idempotency_invalid_key')


async def _request_body(request: Request) -> dict[str, Any]:
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_REQUEST_BYTES:
            raise IdempotencyError(413, 'idempotency_request_too_large')
        raw.extend(chunk)
    try:
        body = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise IdempotencyError(400, 'idempotency_invalid_body') from exc
    if not isinstance(body, dict) or body.get('stream', False) is not False:
        raise IdempotencyError(400, 'idempotency_nonstreaming_object_required')
    return body


async def _storage(work: Awaitable[T]) -> T:
    try:
        return await work
    except ExecutorSaturatedError as exc:
        raise IdempotencyError(503, 'idempotency_store_busy', retry_after='2') from exc
    except IdempotencyError:
        raise
    except Exception as exc:
        # Client exceptions can contain document paths and service metadata.
        raise IdempotencyError(503, 'idempotency_store_unavailable') from exc


def _claim(
    operation: Operation, body: dict[str, Any], credentials: CredentialContext
) -> tuple[Store, StoredResponse | None]:
    store = Store(operation)
    return store, store.claim_or_replay(Operation.canonical_request(body, credentials))


def _error(exc: IdempotencyError, method: str) -> JSONResponse:
    OUTCOMES.labels(method, exc.code).inc()
    headers = {'Cache-Control': 'no-store'}
    if exc.retry_after:
        headers['Retry-After'] = exc.retry_after
    return JSONResponse({'error': {'code': exc.code, 'message': exc.code}}, status_code=exc.status, headers=headers)


def reject_ordinary_post() -> JSONResponse:
    return _error(IdempotencyError(400, 'idempotency_operations_route_required'), 'post')


def _replay(key: str, response: StoredResponse) -> Response:
    return Response(
        response.body,
        status_code=response.status,
        media_type='application/json',
        headers={ACK_HEADER: key, 'Cache-Control': 'no-store'},
    )


async def complete(
    request: Request,
    caller: ServiceCaller,
    credentials: CredentialContext,
    invoke: Callable[[dict[str, Any], KeyedRequest], Awaitable[JSONResponse]],
) -> Response:
    environment = os.getenv(ENVIRONMENT_SETTING, '').strip()
    KEYED_POSTS.labels(environment if environment in ENVIRONMENTS else 'unknown').inc()
    try:
        values = request.headers.getlist(HEADER)
        if len(values) != 1:
            raise IdempotencyError(400, 'idempotency_invalid_key')
        key = _key(values[0])
        if (caller.usage_feature or '').startswith('proactivity_v2_') or any(
            header.startswith('x-omi-proactivity-') for header in request.headers
        ):
            raise IdempotencyError(400, 'idempotency_proactivity_unsupported')
        if environment not in ENVIRONMENTS:
            raise IdempotencyError(503, 'idempotency_environment_unavailable')
        operation = Operation.for_caller(caller, key, environment)
        if not _settlement_slots.acquire(blocking=False):
            raise IdempotencyError(503, 'idempotency_store_busy', retry_after='2')
        settlement: Future[None] | None = None
        try:
            body = await _request_body(request)
            store, replay = await _storage(
                run_blocking(gateway_idempotency_executor, _claim, operation, body, credentials)
            )
            if replay is not None:
                OUTCOMES.labels('post', 'replay').inc()
                return _replay(key, replay)

            # If canceled before the provider returns, the claim stays fenced.
            response = await invoke(body, KeyedRequest(key, operation.document_id, environment))
            saved = None if response.status_code >= 500 else StoredResponse(response.status_code, bytes(response.body))
            # Only permit holders submit to this executor. Keep the permit until
            # the actual worker exits, even if the HTTP waiter is canceled.
            try:
                settlement = gateway_settlement_executor.submit(copy_context().run, store.finish, saved)
            except RuntimeError as exc:
                raise IdempotencyError(503, 'idempotency_store_unavailable') from exc
            settlement.add_done_callback(lambda _: _settlement_slots.release())
            settled = asyncio.wrap_future(settlement)
            # If the HTTP waiter leaves, still observe errors on the asyncio wrapper.
            settled.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            await _storage(asyncio.shield(settled))
            if saved is None:
                OUTCOMES.labels('post', 'indeterminate').inc()
            else:
                OUTCOMES.labels('post', 'committed').inc()
                response.headers[ACK_HEADER] = key
            response.headers['Cache-Control'] = 'no-store'
            return response
        finally:
            if settlement is None:
                _settlement_slots.release()
    except IdempotencyError as exc:
        return _error(exc, 'post')


def _lookup(operation: Operation) -> StoredResponse:
    return Store(operation).lookup()


async def lookup(caller: ServiceCaller, value: str) -> Response:
    try:
        key = _key(value)
        environment = os.getenv(ENVIRONMENT_SETTING, '').strip()
        if environment not in ENVIRONMENTS:
            raise IdempotencyError(503, 'idempotency_environment_unavailable')
        response = await _storage(
            run_blocking(gateway_idempotency_executor, _lookup, Operation.for_caller(caller, key, environment))
        )
        if response.status != 200:
            # A deterministic error can be replayed by POST, but has no completion.
            raise IdempotencyError(404, 'idempotency_not_found')
        OUTCOMES.labels('lookup', 'hit').inc()
        return _replay(key, response)
    except IdempotencyError as exc:
        return _error(exc, 'lookup')
