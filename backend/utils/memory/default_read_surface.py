"""Shared default-read rollout list/search skeleton for product surface adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from config.memory_rollout import MemoryRolloutCapabilities
from models.product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.default_read_rollout import (
    DefaultReadRolloutDecision,
    MemoryReadDecision,
    disabled_default_read_rollout_decision,
)
from utils.memory.product_memory_read_service import fetch_default_product_memory_search
from utils.memory.vector_search_service import fetch_default_vector_memory_search

T = TypeVar('T')
MemoryPayload = dict[str, Any]


@dataclass(frozen=True)
class DefaultReadSearchResult:
    """Shared read-decision envelope for default-memory surface adapters."""

    items: list[Any]
    read_decision: MemoryReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == MemoryReadDecision.USE_LEGACY_SAFE


def parse_default_read_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    raise ValueError('missing memory timestamp')


def parse_optional_default_read_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return None


def rollout_decision_from_legacy_args(
    *,
    uid: str,
    consumer: str,
    rollout_decision: Optional[DefaultReadRolloutDecision],
    rollout_capabilities: Optional[MemoryRolloutCapabilities],
    app_has_default_memory_grant: bool,
) -> DefaultReadRolloutDecision:
    if rollout_decision is not None:
        return rollout_decision
    if rollout_capabilities is None:
        return disabled_default_read_rollout_decision(
            uid=uid,
            source_path=f'users/{uid}/memory_control/state',
            consumer=consumer,
            reason='missing_rollout_state',
        )
    return DefaultReadRolloutDecision(
        uid=uid,
        source_path=f'users/{uid}/memory_control/state',
        consumer=consumer,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
        archive_capability=False,
    )


def deny_default_read_search(
    decision: DefaultReadRolloutDecision,
) -> DefaultReadSearchResult:
    return DefaultReadSearchResult(
        items=[],
        read_decision=decision.read_decision,
        fallback_reason=decision.fallback_reason,
    )


def fetch_default_read_list(
    *,
    uid: str,
    query: str,
    limit: int,
    offset: int,
    db_client: Any,
    decision: DefaultReadRolloutDecision,
    consumer: MemoryConsumer,
    now: Optional[datetime] = None,
    item_filter: Optional[Callable[[Any], bool]] = None,
    item_formatter: Callable[[MemoryPayload, MemoryAccessPolicy], Any],
    max_limit: int = 500,
) -> DefaultReadSearchResult:
    if decision.read_decision != MemoryReadDecision.USE_MEMORY:
        return deny_default_read_search(decision)

    bounded_limit = max(1, min(limit, max_limit))
    bounded_offset = max(0, offset)
    policy = MemoryAccessPolicy(
        consumer=consumer,
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    response = fetch_default_product_memory_search(
        uid=uid,
        query=query,
        db_client=db_client,
        policy=policy,
        now=now,
        limit=bounded_limit,
        offset=bounded_offset,
    )
    formatted: list[Any] = []
    for item in response['items']:
        memory = item_formatter(item, policy)
        if item_filter is not None and not item_filter(memory):
            continue
        formatted.append(memory)
    return DefaultReadSearchResult(items=formatted, read_decision=MemoryReadDecision.USE_MEMORY)


def fetch_default_read_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client: Any,
    decision: DefaultReadRolloutDecision,
    consumer: MemoryConsumer,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
    item_formatter: Callable[[MemoryPayload, MemoryAccessPolicy], Any],
    now: Optional[datetime] = None,
    score_attacher: Optional[Callable[[Any, MemoryPayload, dict[str, float]], Any]] = None,
) -> DefaultReadSearchResult:
    if decision.read_decision != MemoryReadDecision.USE_MEMORY:
        return deny_default_read_search(decision)

    bounded_limit = max(1, min(limit, 100 if consumer == MemoryConsumer.developer_api else 20))
    projection_commit_id = required_projection_commit_id or decision.vector_projection_commit_id
    if not projection_commit_id:
        return DefaultReadSearchResult(
            items=[],
            read_decision=MemoryReadDecision.DENY_MEMORY,
            fallback_reason='missing_vector_projection_commit_id',
        )

    policy = MemoryAccessPolicy(
        consumer=consumer,
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    response = fetch_default_vector_memory_search(
        uid=uid,
        query=query,
        db_client=db_client,
        policy=policy,
        vector_query=vector_query,
        limit=bounded_limit,
        required_projection_commit_id=projection_commit_id,
        required_account_generation=decision.rollout_capabilities.account_generation,
        now=now,
    )
    scores_by_memory_id = response.get('scores_by_memory_id', {})
    formatted: list[Any] = []
    for item in response['items']:
        memory = item_formatter(item, policy)
        if score_attacher is not None:
            memory = score_attacher(memory, item, scores_by_memory_id)
        formatted.append(memory)
    return DefaultReadSearchResult(items=formatted, read_decision=MemoryReadDecision.USE_MEMORY)
