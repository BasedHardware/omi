"""Owner-isolated Vertex cachedContents lifecycle; caching never gates inference.

Only hashes and resource handles survive a request. Cache I/O is bounded, local
entries expire, and misses are retried once before using the original payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from contextvars import ContextVar
from typing import Any

import httpx

from llm_gateway.gateway.accounting import ProviderResponseMetadata
from llm_gateway.gateway.provider_types import ProviderFailure
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.cache_policy import INTERNAL_POLICY, estimated_prefix_tokens, split_prefix
from llm_gateway.gateway.vertex_wire import _vertex_request  # pyright: ignore[reportPrivateUsage]

EXPLICIT_MINIMUM_TOKENS = 4096
IMPLICIT_MINIMUM_TOKENS = 6144


@dataclass
class CacheReceipt:
    lane: str = 'unknown'
    resolved_model: str | None = None
    traffic_type: str | None = None
    mode: str = 'implicit'
    prefix_tokens: int = 0
    write_tokens: int = 0
    storage_token_seconds: int = 0
    operation_usage_complete: bool = True

    def accounting(self, base: ProviderResponseMetadata | None = None) -> ProviderResponseMetadata:
        metadata = base or ProviderResponseMetadata()
        return replace(
            metadata,
            lane_id=self.lane,
            resolved_model=self.resolved_model,
            traffic_type=metadata.traffic_type or self.traffic_type,
            cache_mode=self.mode,
            cacheable_prefix_tokens=self.prefix_tokens,
            cache_write_tokens=self.write_tokens,
            cache_storage_token_seconds=self.storage_token_seconds,
            cache_operation_usage_complete=self.operation_usage_complete,
        )


@dataclass
class CacheEntry:
    name: str
    expires: float
    tokens: int
    usage_complete: bool = True


class VertexContentCache:
    def __init__(self, client: httpx.AsyncClient, *, now: Callable[[], float] = time.monotonic):
        self.client = client
        self.now = now
        self.entries: OrderedDict[str, CacheEntry] = OrderedDict()
        # A bounded number of stripes avoids an unbounded owner-lock registry.
        self.locks = [asyncio.Lock() for _ in range(64)]

    @staticmethod
    def ttl() -> int:
        try:
            return max(1800, min(86400, int(os.getenv('LLM_GATEWAY_VERTEX_CACHE_TTL_SECONDS', '1800'))))
        except ValueError:
            return 1800

    async def prepare(self, payload: Mapping[str, Any], **kwargs: Any) -> tuple[dict[str, Any], str | None]:
        try:
            async with asyncio.timeout(2.0):
                return await self._prepare(payload, **kwargs)
        except TimeoutError:
            kwargs['receipt'].operation_usage_complete = False
            kwargs['receipt'].mode = 'implicit'
            return dict(payload), None

    async def _prepare(
        self,
        payload: Mapping[str, Any],
        *,
        request: Mapping[str, Any],
        owner: str | None,
        endpoint: str,
        model: str,
        headers: Mapping[str, str],
        receipt: CacheReceipt,
        recreate: bool = False,
    ) -> tuple[dict[str, Any], str | None]:
        policy = request.get(INTERNAL_POLICY, {})
        receipt.resolved_model = model
        receipt.lane = policy.get('lane', 'unknown')
        mode = policy.get('mode', 'implicit')
        receipt.mode = 'none' if mode == 'off' else 'implicit'
        receipt.prefix_tokens = policy.get('prefix_tokens', 0)
        if mode != 'explicit' or not owner:
            return dict(payload), None
        prefix_messages, suffix_messages = split_prefix(
            list(request.get('messages', [])), seed=bool(policy.get('seed'))
        )
        if not prefix_messages or not suffix_messages:
            # A generateContent request still needs a noncached continuation.
            return dict(payload), None
        prefix_request = {**request, 'messages': prefix_messages}
        suffix_request = {**request, 'messages': suffix_messages}
        operation_started = False
        try:
            prefix_wire = _vertex_request(prefix_request)
            suffix_wire = _vertex_request(suffix_request)
            if suffix_wire.get('systemInstruction'):
                return dict(payload), None
            stable = {
                key: prefix_wire[key]
                for key in ('systemInstruction', 'tools', 'toolConfig', 'contents')
                if prefix_wire.get(key)
            }
            estimate = estimated_prefix_tokens(stable)
            receipt.prefix_tokens = estimate
            if estimate < EXPLICIT_MINIMUM_TOKENS:
                return dict(payload), None
            collection = endpoint.split('/publishers/google/models/')[0] + '/cachedContents'
            canonical = json.dumps(
                [owner, collection, model, stable], sort_keys=True, separators=(',', ':'), ensure_ascii=False
            )
            key = hashlib.sha256(canonical.encode()).hexdigest()
            async with self.locks[int(key[:8], 16) % len(self.locks)]:
                entry = self.entries.get(key)
                if recreate or (entry is not None and entry.expires <= self.now() + 5):
                    self.entries.pop(key, None)
                    entry = None
                token = headers.get('Authorization', '')
                # Cache management is control plane I/O: never attach a generation
                # capacity header. Inference retains its original dedicated/shared header.
                cache_headers = {'Authorization': token, 'Content-Type': 'application/json'}
                root = endpoint.split('/v1/')[0] + '/v1/'
                if entry and entry.expires - self.now() < self.ttl() / 2:
                    operation_started = True
                    response = await self.client.patch(
                        root + entry.name,
                        params={'updateMask': 'ttl'},
                        json={'ttl': f'{self.ttl()}s'},
                        headers=cache_headers,
                        timeout=1.0,
                    )
                    if response.status_code == 404:
                        self.entries.pop(key, None)
                        entry = None
                    else:
                        response.raise_for_status()
                        extension = max(0, int(self.now() + self.ttl() - entry.expires))
                        receipt.storage_token_seconds += entry.tokens * extension
                        entry.expires = self.now() + self.ttl()
                if entry is None:
                    model_resource = (
                        collection.rsplit('/cachedContents', 1)[0].split('/v1/', 1)[-1]
                        + '/publishers/google/models/'
                        + model
                    )
                    operation_started = True
                    response = await self.client.post(
                        collection,
                        json={'model': model_resource, **stable, 'ttl': f'{self.ttl()}s'},
                        headers=cache_headers,
                        timeout=1.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    name = data.get('name')
                    resource_prefix = collection.split('/v1/', 1)[-1] + '/'
                    if (
                        not isinstance(name, str)
                        or not name.startswith(resource_prefix)
                        or '/' in name[len(resource_prefix) :]
                    ):
                        receipt.operation_usage_complete = False
                        return dict(payload), None
                    count = data.get('usageMetadata', {}).get('totalTokenCount')
                    valid = type(count) is int and count >= 0
                    receipt.operation_usage_complete &= valid
                    count = count if valid else estimate
                    receipt.write_tokens += count
                    receipt.storage_token_seconds += count * self.ttl()
                    entry = CacheEntry(name, self.now() + self.ttl(), count, valid)
                    for old_key, old in list(self.entries.items()):
                        if old.expires <= self.now():
                            self.entries.pop(old_key, None)
                    if len(self.entries) >= 1024:
                        self.entries.popitem(last=False)
                    self.entries[key] = entry
                self.entries.move_to_end(key)
            result = {
                key: value
                for key, value in payload.items()
                if key not in {'contents', 'systemInstruction', 'tools', 'toolConfig'}
            }
            result['contents'] = suffix_wire['contents']
            result['cachedContent'] = entry.name
            receipt.operation_usage_complete &= entry.usage_complete
            receipt.mode = 'explicit'
            return result, key
        except (httpx.TimeoutException, httpx.TransportError):
            receipt.operation_usage_complete = False
            return dict(payload), None
        except httpx.HTTPStatusError as error:
            if error.response.status_code >= 500:
                receipt.operation_usage_complete = False
            return dict(payload), None
        except Exception:
            if operation_started:
                receipt.operation_usage_complete = False
            # Never log response bodies, resource handles, owner IDs or prompt hashes.
            return dict(payload), None

    def invalidate(self, key: str | None) -> None:
        if key:
            self.entries.pop(key, None)

    async def generate(
        self,
        send: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
        payload: Mapping[str, Any],
        *,
        allow_recreate: bool = True,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        from llm_gateway.gateway.provider_types import _VertexHttpError  # pyright: ignore[reportPrivateUsage]

        for retry in range(2):
            adapted, key = await self.prepare(payload, **kwargs, recreate=retry > 0)
            try:
                return await send(adapted)
            except _VertexHttpError as error:
                # Cached-content invalid/expired handles can be reported as 400,
                # 404 or 412. Retry only when a cache was actually attached.
                if not key or error.status_code not in {400, 404, 412}:
                    raise
                self.invalidate(key)
                if not allow_recreate:
                    raise
        kwargs['receipt'].mode = 'implicit'
        return await send(payload)


async def scoped_cache_stream(
    variable: ContextVar[Any], scope: Any, stream: AsyncGenerator[bytes, None]
) -> AsyncIterator[bytes]:
    """Rebind each advancement: Starlette can resume a prepared stream in another task.

    Tokens belong to a context, not a generator. Never hold a token across yield;
    cancellation/close must also release resources under the proper owner scope.
    """
    try:
        while True:
            token = variable.set(scope)
            try:
                chunk = await anext(stream)
            except StopAsyncIteration:
                return
            finally:
                variable.reset(token)
            yield chunk
    finally:
        token = variable.set(scope)
        try:
            await stream.aclose()
        finally:
            variable.reset(token)


async def validated_stream(
    stream: AsyncGenerator[bytes, None], *, enabled: bool, max_bytes: int | Callable[[], int]
) -> AsyncGenerator[bytes, None]:
    """Hold retiring-model output until its final traffic receipt is validated.

    A rejected late ON_DEMAND receipt must not leave generated content already
    visible. Bound retained bytes, and always close the native stream on abort.
    """
    limit = (max_bytes() if callable(max_bytes) else max_bytes) if enabled else 0
    pending: list[bytes] = []
    size = 0
    try:
        async for chunk in stream:
            if enabled:
                size += len(chunk)
                if size > limit:
                    raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
                pending.append(chunk)
            else:
                yield chunk
        for chunk in pending:
            yield chunk
    finally:
        await stream.aclose()
