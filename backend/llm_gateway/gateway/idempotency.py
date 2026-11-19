"""HTTP contract for opted-in chat completion idempotency."""

from collections.abc import Awaitable, Callable
import json
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter

from config.refactor_modes import default_on
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import CredentialContext
from llm_gateway.gateway.idempotency_store import IdempotencyError, Operation, Store, StoredResponse
from utils.executors import ExecutorSaturatedError, gateway_idempotency_executor, run_blocking

HEADER = 'idempotency-key'
ACK_HEADER = 'X-Omi-Idempotency-Key'
MAX_REQUEST_BYTES = 1024 * 1024
PROVIDERS = frozenset({'openai', 'openrouter', 'anthropic'})

KEYED_POSTS = Counter('llm_gateway_keyed_posts_total', 'Authenticated chat POSTs using the keyed protocol')
OUTCOMES = Counter('llm_gateway_idempotency_outcomes_total', 'Keyed chat outcomes', ['method', 'outcome'])
P = ParamSpec('P')
T = TypeVar('T')


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


async def _storage(fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return await run_blocking(gateway_idempotency_executor, fn, *args, **kwargs)
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
    invoke: Callable[[dict[str, Any], str, str], Awaitable[JSONResponse]],
) -> Response:
    KEYED_POSTS.inc()
    try:
        values = request.headers.getlist(HEADER)
        if len(values) != 1:
            raise IdempotencyError(400, 'idempotency_invalid_key')
        key = _key(values[0])
        if (caller.usage_feature or '').startswith('proactivity_v2_') or any(
            header.startswith('x-omi-proactivity-') for header in request.headers
        ):
            raise IdempotencyError(400, 'idempotency_proactivity_unsupported')
        operation = Operation.for_caller(caller, key)
        body = await _request_body(request)
        store, replay = await _storage(_claim, operation, body, credentials)
        if replay is not None:
            OUTCOMES.labels('post', 'replay').inc()
            return _replay(key, replay)

        # If canceled or killed here, the claim stays fenced and ages to indeterminate.
        response = await invoke(body, key, operation.document_id)
        if response.status_code >= 500:
            await _storage(store.finish, None)
            OUTCOMES.labels('post', 'indeterminate').inc()
        else:
            saved = StoredResponse(response.status_code, bytes(response.body))
            await _storage(store.finish, saved)
            OUTCOMES.labels('post', 'committed').inc()
            response.headers[ACK_HEADER] = key
        response.headers['Cache-Control'] = 'no-store'
        return response
    except IdempotencyError as exc:
        return _error(exc, 'post')


def _lookup(operation: Operation) -> StoredResponse:
    return Store(operation).lookup()


async def lookup(caller: ServiceCaller, value: str) -> Response:
    try:
        key = _key(value)
        response = await _storage(_lookup, Operation.for_caller(caller, key))
        if response.status != 200:
            # A deterministic error can be replayed by POST, but has no completion.
            raise IdempotencyError(404, 'idempotency_not_found')
        OUTCOMES.labels('lookup', 'hit').inc()
        return _replay(key, response)
    except IdempotencyError as exc:
        return _error(exc, 'lookup')
