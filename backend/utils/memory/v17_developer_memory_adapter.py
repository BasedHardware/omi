from datetime import datetime
from typing import Any, Callable, Optional

from config.v17_memory import V17Capabilities
from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_default_read_rollout import V17DefaultReadRolloutDecision, read_v17_default_read_rollout
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search
from utils.memory.v17_vector_search_service import fetch_default_v17_vector_memory_search

V17DeveloperDefaultMemoryRolloutDecision = V17DefaultReadRolloutDecision


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


def _format_developer_memory(item: dict, policy: MemoryAccessPolicy) -> dict:
    updated_at = _parse_datetime(item.get('date') or item.get('updated_at') or item.get('captured_at'))
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': 'other',
        'visibility': 'private',
        'tags': ['v17_default_memory', f"tier:{item.get('tier')}"] if item.get('tier') else ['v17_default_memory'],
        'created_at': updated_at,
        'updated_at': updated_at,
        'manually_added': False,
        'scoring': None,
        'reviewed': True,
        'user_review': None,
        'edited': False,
        'v17_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def search_v17_default_developer_memories(
    *,
    uid: str,
    query: str = '',
    limit: int,
    offset: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities],
    app_has_default_memory_grant: bool,
    now: Optional[datetime] = None,
) -> Optional[list[dict]]:
    """Return default-visible V17 product memories for the developer memory caller.

    Returns `None` when the concrete developer route should keep using the legacy
    `users/{uid}/memories` path. Firestore `memory_items` are touched only after
    persisted V17 read capability and developer default-memory grant both pass.
    """

    if not rollout_capabilities or not rollout_capabilities.v17_reads_enabled:
        return None
    if not app_has_default_memory_grant:
        return None

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
    return [_format_developer_memory(item, policy) for item in response['items']]


def search_v17_default_developer_memories_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities],
    app_has_default_memory_grant: bool,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
) -> Optional[list[dict]]:
    """Return hydrated V17 vector memories for the developer API caller.

    Returns `None` before vector lookup or `users/{uid}/memory_items` reads when
    persisted V17 read rollout or the developer default-memory grant is missing.
    Archive is deliberately default-disabled here; explicit Archive routes remain
    separate and capability-gated.
    """

    if not rollout_capabilities or not rollout_capabilities.v17_reads_enabled:
        return None
    if not app_has_default_memory_grant:
        return None

    bounded_limit = max(1, min(limit, 100))
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
        required_projection_commit_id=required_projection_commit_id,
    )

    scores_by_memory_id = response.get('scores_by_memory_id', {})
    formatted = []
    for item in response['items']:
        memory = _format_developer_memory(item, policy)
        memory_id = item['memory_id']
        memory['relevance_score'] = round(float(scores_by_memory_id.get(memory_id, 0)), 4)
        memory['vector_search'] = True
        formatted.append(memory)
    return formatted
