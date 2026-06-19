from datetime import datetime
from typing import Any, Callable, Optional

from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_default_read_rollout import V17DefaultReadRolloutDecision, read_v17_default_read_rollout
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search
from utils.memory.v17_vector_search_service import fetch_default_v17_vector_memory_search

V17ChatDefaultMemoryRolloutDecision = V17DefaultReadRolloutDecision


def read_v17_chat_default_memory_rollout(*, uid: str, db_client) -> V17ChatDefaultMemoryRolloutDecision:
    """Read server-owned V17 Omi chat default-memory rollout state.

    Missing, malformed, uid-mismatched, disabled, or grant-less state fails
    closed before any `users/{uid}/memory_items` read. Archive stays default-
    disabled for chat; explicit Archive product routes remain separate.
    """

    return read_v17_default_read_rollout(uid=uid, db_client=db_client, consumer='omi_chat')


def search_v17_default_chat_memories_text(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return LLM-ready default-visible V17 product memories for Omi chat.

    Returns `None` when the mature chat retrieval caller should keep using the
    legacy memory vector path. The authoritative V17 `memory_items` collection is
    touched only after persisted V17 read capability and Omi chat default-memory
    grant both pass.
    """

    decision = read_v17_chat_default_memory_rollout(uid=uid, db_client=db_client)
    if not decision.rollout_capabilities.v17_reads_enabled:
        return None
    if not decision.app_has_default_memory_grant:
        return None

    bounded_limit = max(1, min(limit, 20))
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.omi_chat,
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
        offset=0,
    )
    items = response['items']
    if not items:
        return f"No V17 default memories found matching '{query}'."

    lines = [f"Found {len(items)} V17 default memories matching '{query}':", '']
    for item in items:
        updated_at = _parse_datetime(item.get('date'))
        date_str = updated_at.strftime('%Y-%m-%d') if updated_at else 'Unknown'
        lines.append(f"- {item.get('content') or ''} (tier: {item.get('tier')}, date: {date_str})")
    lines.append('')
    lines.append('archive_default_visible=False')
    return '\n'.join(lines).strip()


def search_v17_default_chat_memories_vector_text(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
) -> Optional[str]:
    """Return LLM-ready hydrated V17 vector memory results for Omi chat.

    Returns `None` when persisted V17 read rollout/default-memory grant is not
    enabled so the mature chat search tool can fall back to legacy vector search
    without touching V17 vector search or `users/{uid}/memory_items`.
    """

    decision = read_v17_chat_default_memory_rollout(uid=uid, db_client=db_client)
    if not decision.rollout_capabilities.v17_reads_enabled:
        return None
    if not decision.app_has_default_memory_grant:
        return None

    bounded_limit = max(1, min(limit, 20))
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.omi_chat,
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
    items = response['items']
    if not items:
        return f"No V17 vector memories found matching '{query}'."

    scores_by_memory_id = response.get('scores_by_memory_id', {})
    lines = [f"Found {len(items)} V17 vector memories matching '{query}':", '']
    for item in items:
        updated_at = _parse_datetime(item.get('updated_at') or item.get('date'))
        date_str = updated_at.strftime('%Y-%m-%d') if updated_at else 'Unknown'
        score = float(scores_by_memory_id.get(item.get('memory_id'), 0))
        lines.append(
            f"- {item.get('content') or ''} (relevance: {score:.2f}, tier: {item.get('tier')}, date: {date_str})"
        )
    lines.append('')
    lines.append('archive_default_visible=False')
    return '\n'.join(lines).strip()


def _parse_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    return None
