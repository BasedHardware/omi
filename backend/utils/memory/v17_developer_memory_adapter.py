from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from config.v17_memory import V17Capabilities
from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_default_read_rollout import (
    V17DefaultReadRolloutDecision,
    V17ReadDecision,
    disabled_v17_default_read_rollout_decision,
    read_v17_default_read_rollout,
)
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search
from utils.memory.v17_vector_search_service import fetch_default_v17_vector_memory_search

V17DeveloperDefaultMemoryRolloutDecision = V17DefaultReadRolloutDecision


@dataclass(frozen=True)
class V17DeveloperMemorySearchResult:
    memories: list[dict]
    read_decision: V17ReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == V17ReadDecision.USE_LEGACY_SAFE


def read_v17_developer_default_memory_rollout(*, uid: str, db_client) -> V17DeveloperDefaultMemoryRolloutDecision:
    """Read server-owned V17 developer default-memory rollout state.

    The authoritative per-user document is `users/{uid}/memory_control/state`.
    Missing, malformed, uid-mismatched, or developer-grant-less docs fail closed
    before any `users/{uid}/memory_items` read. Archive stays default-disabled on
    this developer default-memory path regardless of persisted Archive fields.
    """

    return read_v17_default_read_rollout(uid=uid, db_client=db_client, consumer='developer_api')


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    raise ValueError('missing V17 memory timestamp')


def _developer_category(item: dict) -> str:
    category = item.get('category')
    if isinstance(category, str) and category.strip():
        return category
    return 'other'


def _format_developer_memory(item: dict, policy: MemoryAccessPolicy) -> dict:
    updated_at = _parse_datetime(item.get('date') or item.get('updated_at') or item.get('captured_at'))
    raw_category = item.get('category')
    category_source = (
        'v17_memory_item.category'
        if isinstance(raw_category, str) and raw_category.strip()
        else 'developer_v17_compatibility_default_no_source_category'
    )
    visibility_source = item.get('visibility_source') or 'v17_memory_item.visibility'
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': _developer_category(item),
        'category_source': category_source,
        'visibility': item.get('visibility') or 'private',
        'visibility_source': visibility_source,
        'tags': ['v17_default_memory', f"tier:{item.get('tier')}"] if item.get('tier') else ['v17_default_memory'],
        'created_at': updated_at,
        'updated_at': updated_at,
        'manually_added': False,
        'manually_added_source': 'developer_v17_compatibility_default_no_manual_state',
        'scoring': None,
        'reviewed': False,
        'reviewed_source': 'developer_v17_compatibility_default_no_review_state',
        'user_review': None,
        'edited': False,
        'edited_source': 'developer_v17_compatibility_default_no_edit_state',
        'v17_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def _rollout_decision_from_legacy_args(
    *,
    uid: str,
    rollout_decision: Optional[V17DeveloperDefaultMemoryRolloutDecision],
    rollout_capabilities: Optional[V17Capabilities],
    app_has_default_memory_grant: bool,
) -> V17DeveloperDefaultMemoryRolloutDecision:
    if rollout_decision is not None:
        return rollout_decision
    if rollout_capabilities is None:
        return disabled_v17_default_read_rollout_decision(
            uid=uid,
            source_path=f'users/{uid}/memory_control/state',
            consumer='developer_api',
            reason='missing_rollout_state',
        )
    return V17DefaultReadRolloutDecision(
        uid=uid,
        source_path=f'users/{uid}/memory_control/state',
        consumer='developer_api',
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
        archive_capability=False,
    )


def search_v17_default_developer_memories(
    *,
    uid: str,
    query: str = '',
    limit: int,
    offset: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[V17DeveloperDefaultMemoryRolloutDecision] = None,
    now: Optional[datetime] = None,
    categories: Optional[list[str]] = None,
) -> V17DeveloperMemorySearchResult:
    """Return explicit read-decision semantics for the developer list caller.

    Missing/malformed/no-grant/disabled rollout states are DENY_MEMORY or
    SHADOW_ONLY, not an implicit `None` downgrade to the legacy
    `users/{uid}/memories` path. Legacy fallback is only valid when callers pass
    an explicit USE_LEGACY_SAFE decision. Firestore `memory_items` are touched
    only after USE_V17.
    """

    decision = _rollout_decision_from_legacy_args(
        uid=uid,
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )
    if decision.read_decision != V17ReadDecision.USE_V17:
        return V17DeveloperMemorySearchResult(
            memories=[], read_decision=decision.read_decision, fallback_reason=decision.fallback_reason
        )

    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.developer_api,
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
    formatted = [_format_developer_memory(item, policy) for item in response['items']]
    if categories:
        allowed_categories = {category for category in categories if category}
        formatted = [memory for memory in formatted if memory.get('category') in allowed_categories]
    return V17DeveloperMemorySearchResult(
        memories=formatted,
        read_decision=V17ReadDecision.USE_V17,
    )


def search_v17_default_developer_memories_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[V17DeveloperDefaultMemoryRolloutDecision] = None,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
) -> V17DeveloperMemorySearchResult:
    """Return explicit read-decision semantics for the developer vector caller.

    Missing/malformed/no-grant/disabled rollout states are DENY_MEMORY or
    SHADOW_ONLY before vector lookup or `users/{uid}/memory_items` reads. Legacy
    fallback is only valid when callers pass an explicit USE_LEGACY_SAFE decision.
    Archive is deliberately default-disabled here; explicit Archive routes remain
    separate and capability-gated.
    """

    decision = _rollout_decision_from_legacy_args(
        uid=uid,
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )
    if decision.read_decision != V17ReadDecision.USE_V17:
        return V17DeveloperMemorySearchResult(
            memories=[], read_decision=decision.read_decision, fallback_reason=decision.fallback_reason
        )

    bounded_limit = max(1, min(limit, 100))
    projection_commit_id = required_projection_commit_id or decision.vector_projection_commit_id
    if not projection_commit_id:
        return V17DeveloperMemorySearchResult(
            memories=[],
            read_decision=V17ReadDecision.DENY_MEMORY,
            fallback_reason='missing_vector_projection_commit_id',
        )
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.developer_api,
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    response = fetch_default_v17_vector_memory_search(
        uid=uid,
        query=query,
        db_client=db_client,
        policy=policy,
        vector_query=vector_query,
        limit=bounded_limit,
        required_projection_commit_id=projection_commit_id,
        required_account_generation=decision.rollout_capabilities.account_generation,
    )

    scores_by_memory_id = response.get('scores_by_memory_id', {})
    formatted = []
    for item in response['items']:
        memory = _format_developer_memory(item, policy)
        memory_id = item['memory_id']
        memory['relevance_score'] = round(float(scores_by_memory_id.get(memory_id, 0)), 4)
        memory['vector_search'] = True
        formatted.append(memory)
    return V17DeveloperMemorySearchResult(memories=formatted, read_decision=V17ReadDecision.USE_V17)
