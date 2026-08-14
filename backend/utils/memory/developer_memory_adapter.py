"""Canonical developer memory adapter module (WS-G8a).

Neutral ``developer_memory_adapter`` is the source of truth. Canonical developer memory adapter.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from config.memory_rollout import MemoryRolloutCapabilities
from models.product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.default_read_rollout import (
    DefaultReadRolloutDecision,
    MemoryReadDecision,
)
from utils.memory.default_read_surface import (
    DefaultReadSearchResult,
    fetch_default_read_list,
    fetch_default_read_vector,
    parse_default_read_datetime,
    rollout_decision_from_legacy_args,
)

MemoryPayload = dict[str, Any]


@dataclass(frozen=True)
class DeveloperMemorySearchResult:
    memories: list[MemoryPayload]
    read_decision: MemoryReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == MemoryReadDecision.USE_LEGACY_SAFE


def _developer_result(result: DefaultReadSearchResult) -> DeveloperMemorySearchResult:
    return DeveloperMemorySearchResult(
        memories=result.items,
        read_decision=result.read_decision,
        fallback_reason=result.fallback_reason,
    )


def _developer_category(item: MemoryPayload) -> str:
    category = item.get('category')
    if isinstance(category, str) and category.strip():
        return category
    return 'other'


def _format_developer_memory(item: MemoryPayload, policy: MemoryAccessPolicy) -> MemoryPayload:
    updated_at = parse_default_read_datetime(item.get('date') or item.get('updated_at') or item.get('captured_at'))
    raw_category = item.get('category')
    category_source = (
        'memory_item.category'
        if isinstance(raw_category, str) and raw_category.strip()
        else 'developer_memory_compatibility_default_no_source_category'
    )
    visibility_source = item.get('visibility_source') or 'memory_item.visibility'
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': _developer_category(item),
        'category_source': category_source,
        'visibility': item.get('visibility') or 'private',
        'visibility_source': visibility_source,
        'tags': (
            ['memory_default_memory', f"tier:{item.get('tier')}"] if item.get('tier') else ['memory_default_memory']
        ),
        'created_at': updated_at,
        'updated_at': updated_at,
        'manually_added': False,
        'manually_added_source': 'developer_memory_compatibility_default_no_manual_state',
        'scoring': None,
        'reviewed': False,
        'reviewed_source': 'developer_memory_compatibility_default_no_review_state',
        'user_review': None,
        'edited': False,
        'edited_source': 'developer_memory_compatibility_default_no_edit_state',
        'memory_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def _attach_developer_vector_score(
    memory: MemoryPayload, item: MemoryPayload, scores_by_memory_id: dict[str, float]
) -> MemoryPayload:
    memory_id = item.get('memory_id')
    score = scores_by_memory_id.get(memory_id, 0.0) if isinstance(memory_id, str) else 0.0
    memory['relevance_score'] = round(float(score), 4)
    memory['vector_search'] = True
    return memory


def search_memory_default_developer_memories(
    *,
    uid: str,
    query: str = '',
    limit: int,
    offset: int,
    db_client: Any,
    rollout_capabilities: Optional[MemoryRolloutCapabilities] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[DefaultReadRolloutDecision] = None,
    now: Optional[datetime] = None,
    categories: Optional[list[str]] = None,
) -> DeveloperMemorySearchResult:
    """Return explicit read-decision semantics for the developer list caller.

    Missing/malformed/no-grant/disabled rollout states are DENY_MEMORY or
    SHADOW_ONLY, not an implicit `None` downgrade to the legacy
    `users/{uid}/memories` path. Legacy fallback is only valid when callers pass
    an explicit USE_LEGACY_SAFE decision. Firestore `memory_items` are touched
    only after USE_MEMORY.
    """

    decision = rollout_decision_from_legacy_args(
        uid=uid,
        consumer='developer_api',
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )

    def _category_filter(memory: MemoryPayload) -> bool:
        if not categories:
            return True
        allowed_categories = {category for category in categories if category}
        return memory.get('category') in allowed_categories

    return _developer_result(
        fetch_default_read_list(
            uid=uid,
            query=query,
            limit=limit,
            offset=offset,
            db_client=db_client,
            decision=decision,
            consumer=MemoryConsumer.developer_api,
            now=now,
            item_filter=_category_filter if categories else None,
            item_formatter=_format_developer_memory,
        )
    )


def search_memory_default_developer_memories_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client: Any,
    rollout_capabilities: Optional[MemoryRolloutCapabilities] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[DefaultReadRolloutDecision] = None,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> DeveloperMemorySearchResult:
    """Return explicit read-decision semantics for the developer vector caller.

    Missing/malformed/no-grant/disabled rollout states are DENY_MEMORY or
    SHADOW_ONLY before vector lookup or `users/{uid}/memory_items` reads. Legacy
    fallback is only valid when callers pass an explicit USE_LEGACY_SAFE decision.
    Archive is deliberately default-disabled here; explicit Archive routes remain
    separate and capability-gated.
    """

    decision = rollout_decision_from_legacy_args(
        uid=uid,
        consumer='developer_api',
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )
    return _developer_result(
        fetch_default_read_vector(
            uid=uid,
            query=query,
            limit=limit,
            db_client=db_client,
            decision=decision,
            consumer=MemoryConsumer.developer_api,
            vector_query=vector_query,
            required_projection_commit_id=required_projection_commit_id,
            now=now,
            item_formatter=_format_developer_memory,
            score_attacher=_attach_developer_vector_score,
        )
    )
