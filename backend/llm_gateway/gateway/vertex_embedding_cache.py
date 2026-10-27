"""Bounded, process-local reuse of successful, exact-input Vertex vectors.

Keys are hashes of the owner, endpoint (project/location/model) and complete
Vertex instance (unmodified text, task type and title). No plaintext owner or
input is retained. The provider uses this synchronously on its event loop;
there are no locks, background tasks, persisted caches or cross-owner reuse.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from prometheus_client import Counter

from config.llm_spend import vertex_embedding_dedupe_enabled
from llm_gateway.gateway.accounting import ProviderResponseMetadata
from llm_gateway.gateway.cache_policy import cache_owner_scope
from llm_gateway.gateway.credentials import CredentialContext, CredentialSource
from llm_gateway.gateway.provider_types import ProviderFailure, ProviderResponse
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.gateway.vertex_wire import (
    _vertex_embedding_predict_request,  # pyright: ignore[reportPrivateUsage]
    _vertex_headers,  # pyright: ignore[reportPrivateUsage]
)
from utils.llm import vertex_pt_routing as ptr

VERTEX_EMBEDDING_CONCURRENCY = 8

INPUTS = Counter('llm_gateway_vertex_embedding_inputs_total', 'Vertex embedding inputs by reuse outcome', ['outcome'])
CHARACTERS = Counter(
    'llm_gateway_vertex_embedding_input_characters_total',
    'Input characters submitted or reused; not provider-reported billable usage',
    ['outcome'],
)


def observe_input(outcome: str, characters: int, *, count: int = 1) -> None:
    # Metrics must never turn a valid embedding into a request failure.
    try:
        INPUTS.labels(outcome).inc(count)
        CHARACTERS.labels(outcome).inc(characters * count)
    except Exception:
        pass


def embedding_key(*, owner: str | None, endpoint: str, instance: Mapping[str, Any]) -> str | None:
    if not owner:
        return None
    return hashlib.sha256(
        json.dumps([owner, endpoint, instance], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()


@dataclass(frozen=True)
class _Entry:
    expires_at: float
    values: tuple[float, ...]


class EmbeddingVectorCache:
    """Hard TTL and LRU bounds; the value budget is about 8 MiB of Python floats."""

    def __init__(
        self,
        *,
        now: Callable[[], float],
        ttl_seconds: float = 600.0,
        max_entries: int = 512,
        max_values: int = 262_144,
    ) -> None:
        self._now = now
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._max_values = max_values
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._values = 0

    def clear(self) -> None:
        self._entries.clear()
        self._values = 0

    def _remove(self, key: str) -> None:
        self._values -= len(self._entries.pop(key).values)

    def get(self, key: str) -> list[float] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            self._remove(key)
            return None
        self._entries.move_to_end(key)
        # Never let a caller mutate a vector retained for later requests.
        return list(entry.values)

    def put(self, key: str, vector: list[float]) -> None:
        if not vector or len(vector) > self._max_values:
            return
        now = self._now()
        for expired in [key for key, entry in self._entries.items() if entry.expires_at <= now]:
            self._remove(expired)
        if key in self._entries:
            self._remove(key)
        self._entries[key] = _Entry(now + self._ttl_seconds, tuple(vector))
        self._values += len(vector)
        while len(self._entries) > self._max_entries or self._values > self._max_values:
            self._remove(next(iter(self._entries)))


class VertexEmbeddingRunner:
    """Single-input Vertex wire calls, bounded batch fan-out and exact reuse."""

    def __init__(
        self,
        *,
        create_instance: Callable[..., Awaitable[list[float]]],
        access_token: Callable[[], Awaitable[str]],
        now: Callable[[], float],
    ) -> None:
        self._create_instance = create_instance
        self._access_token = access_token
        self._now = now
        self._embedding_cache = EmbeddingVectorCache(now=now)

    def clear(self) -> None:
        self._embedding_cache.clear()

    async def create_embedding(
        self,
        request: Mapping[str, Any],
        *,
        endpoint: str,
        model: str,
        credentials: CredentialContext,
        timeout_ms: int,
    ) -> ProviderResponse:
        payload = _vertex_embedding_predict_request(request)
        instances = payload['instances']
        dedupe = vertex_embedding_dedupe_enabled()
        if not dedupe:
            self._embedding_cache.clear()
        owner = (
            cache_owner_scope(credentials.caller)
            if dedupe and credentials.source == CredentialSource.OMI_MANAGED and model == ptr.DESKTOP_EMBEDDING_MODEL
            else None
        )
        keys = [embedding_key(owner=owner, endpoint=endpoint, instance=instance) for instance in instances]
        if len(instances) == 1:
            # A single predict keeps the existing per-request wire timeout.
            # Only batches need to share a shrinking budget across requests.
            headers = _vertex_headers(await self._access_token(), ptr.REQUEST_TYPE_SHARED)
            vector = await self._reusable_embedding_instance(
                endpoint,
                instances[0],
                cache_key=keys[0],
                headers=headers,
                credentials=credentials,
                model=model,
                timeout_ms=timeout_ms,
            )
            return ProviderResponse(
                response={
                    'object': 'list',
                    'data': [{'object': 'embedding', 'embedding': vector, 'index': 0}],
                    'model': model,
                },
                accounting=ProviderResponseMetadata(usage=None),
            )
        deadline = self._now() + max(timeout_ms, 0) / 1000.0
        vectors: list[list[float] | None] = [None] * len(instances)
        # Collapse only exact duplicate instances within this request; separate
        # requests may race on a miss, which merely costs another provider call.
        # No shared in-flight task can outlive a cancelled caller.
        unique: list[tuple[list[int], Mapping[str, Any], str | None]] = []
        by_key: dict[str, list[int]] = {}
        for index, (instance, key) in enumerate(zip(instances, keys, strict=True)):
            if key is not None and key in by_key:
                by_key[key].append(index)
            else:
                indexes = [index]
                unique.append((indexes, instance, key))
                if key is not None:
                    by_key[key] = indexes
        pending = iter(unique)

        async def worker(headers: dict[str, str]) -> None:
            for indexes, instance, key in pending:
                remaining_ms = int((deadline - self._now()) * 1000)
                if remaining_ms <= 0:
                    raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT)
                vector = await self._reusable_embedding_instance(
                    endpoint,
                    instance,
                    cache_key=key,
                    headers=headers,
                    credentials=credentials,
                    model=model,
                    timeout_ms=remaining_ms,
                )
                for index in indexes:
                    vectors[index] = list(vector)
                if len(indexes) > 1:
                    observe_input('batch_reuse', len(instance['content']), count=len(indexes) - 1)

        # gemini-embedding-001 accepts ONE text per :predict, unlike AI Studio
        # batchEmbedContents. Fixed workers bound fan-out (including queued
        # items) without allocating a task for every input. One deadline also
        # covers ADC, pool wait and response reads; httpx timeouts are per IO.
        # https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/text-embeddings-api
        try:
            async with asyncio.timeout(max(timeout_ms, 0) / 1000.0):
                headers = _vertex_headers(await self._access_token(), ptr.REQUEST_TYPE_SHARED)
                try:
                    async with asyncio.TaskGroup() as group:
                        for _ in range(min(VERTEX_EMBEDDING_CONCURRENCY, len(unique))):
                            group.create_task(worker(headers))
                except* ProviderFailure as failures:
                    # TaskGroup cancels and drains siblings before exposing the
                    # first typed error; never return a partially embedded batch.
                    raise failures.exceptions[0] from None
        except TimeoutError as exc:
            raise ProviderFailure(FailureClass.TIMEOUT_BEFORE_OUTPUT) from exc

        data = [{'object': 'embedding', 'embedding': vector, 'index': i} for i, vector in enumerate(vectors)]
        # Vertex reports billable characters rather than tokens. Keep usage
        # NOT_REPORTED rather than fabricating aggregate token counts.
        return ProviderResponse(
            response={'object': 'list', 'data': data, 'model': model},
            accounting=ProviderResponseMetadata(usage=None),
        )

    async def _reusable_embedding_instance(
        self,
        endpoint: str,
        instance: Mapping[str, Any],
        *,
        cache_key: str | None,
        headers: dict[str, str],
        credentials: CredentialContext,
        model: str,
        timeout_ms: int,
    ) -> list[float]:
        characters = len(instance['content'])
        if cache_key is not None:
            vector = self._embedding_cache.get(cache_key)
            if vector is not None:
                observe_input('cache_hit', characters)
                return vector
        observe_input('submitted', characters)
        vector = await self._create_instance(
            endpoint, instance, headers=headers, credentials=credentials, model=model, timeout_ms=timeout_ms
        )
        # Only the successful, finite vector validated by the real adapter is
        # reusable. A mid-request kill also prevents late cache insertion.
        if cache_key is not None and vertex_embedding_dedupe_enabled():
            self._embedding_cache.put(cache_key, vector)
        return vector
