from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from config.v17_memory import V17Capabilities, V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections
from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search

ACTIVITY_TAGS = {
    'activity',
    'focus',
    'screen',
    'screen_activity',
    'rewind',
    'distraction',
    'distracted',
}

ACTIVITY_PREFIXES = (
    'focused on ',
    'distracted on ',
    'viewing ',
)


@dataclass(frozen=True)
class V17McpDefaultMemoryRolloutDecision:
    uid: str
    source_path: str
    rollout_capabilities: V17Capabilities
    app_has_default_memory_grant: bool
    archive_capability: bool = False
    reason: str = 'ok'

    @property
    def v17_default_mcp_enabled(self) -> bool:
        return self.rollout_capabilities.v17_reads_enabled and self.app_has_default_memory_grant


def _disabled_v17_mcp_rollout_decision(uid: str, source_path: str, reason: str) -> V17McpDefaultMemoryRolloutDecision:
    return V17McpDefaultMemoryRolloutDecision(
        uid=uid,
        source_path=source_path,
        rollout_capabilities=V17Capabilities(
            uid=uid,
            mode=V17Mode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            v17_writes_enabled=False,
            v17_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
    )


def _mcp_default_memory_grant_enabled(data: dict) -> bool:
    grants = data.get('grants')
    if isinstance(grants, dict):
        mcp_grants = grants.get('mcp')
        if isinstance(mcp_grants, dict) and mcp_grants.get('default_memory') is True:
            return True
    return data.get('mcp_default_memory_grant') is True


def read_v17_mcp_default_memory_rollout(*, uid: str, db_client) -> V17McpDefaultMemoryRolloutDecision:
    """Read server-owned V17 MCP default-memory rollout state.

    The authoritative per-user document is `users/{uid}/memory_control/state`.
    Missing, malformed, or grant-less docs fail closed to legacy MCP search before
    any `users/{uid}/memory_items` read. Archive is deliberately not derived here:
    the MCP default search path always keeps `archive_capability=False`.
    """

    source_path = V17Collections(uid=uid).memory_control_state
    try:
        snapshot = db_client.document(source_path).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
        if not isinstance(data, dict):
            return _disabled_v17_mcp_rollout_decision(uid, source_path, 'missing_rollout_state')
        if data.get('uid', uid) != uid:
            return _disabled_v17_mcp_rollout_decision(uid, source_path, 'uid_mismatch')

        state = V17RolloutState(
            uid=uid,
            mode=data.get('mode', V17Mode.off.value),
            mode_epoch=int(data.get('mode_epoch', 0) or 0),
            cutover_epoch=int(data.get('cutover_epoch', 0) or 0),
            account_generation=int(data.get('account_generation', 0) or 0),
            last_reconciled_legacy_revision=data.get('last_reconciled_legacy_revision'),
            fallback_projection_ready=data.get('fallback_projection_ready') is True,
            persistent_v17_writes_started=data.get('persistent_v17_writes_started') is True,
            decommission_reconciled=data.get('decommission_reconciled') is True,
            writes_blocked=data.get('writes_blocked') is True,
            stage_gates=data.get('stage_gates') or {},
        )
        capabilities = decide_v17_capabilities(uid, state.mode, state)
        return V17McpDefaultMemoryRolloutDecision(
            uid=uid,
            source_path=source_path,
            rollout_capabilities=capabilities,
            app_has_default_memory_grant=_mcp_default_memory_grant_enabled(data),
            archive_capability=False,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return _disabled_v17_mcp_rollout_decision(uid, source_path, 'malformed_rollout_state')


def parse_mcp_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f"Invalid {field_name} format: '{value}'. Expected ISO 8601.") from e


def parse_mcp_int(value, field_name: str, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid {field_name}: expected integer.") from e
    return max(minimum, min(parsed, maximum))


def parse_optional_mcp_bool(value, field_name: str) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes'}:
            return True
        if normalized in {'false', '0', 'no'}:
            return False
    raise ValueError(f"Invalid {field_name}: expected boolean.")


def parse_mcp_bool(value, field_name: str, *, default: bool) -> bool:
    if value is None:
        return default
    parsed = parse_optional_mcp_bool(value, field_name)
    return default if parsed is None else parsed


def _datetime_timestamp(value) -> Optional[float]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return None
    return None


def is_activity_memory(memory: dict) -> bool:
    tags = {str(tag).lower() for tag in memory.get('tags') or []}
    if tags.intersection(ACTIVITY_TAGS):
        return True

    source = str(memory.get('source') or memory.get('source_type') or '').lower()
    if source in ACTIVITY_TAGS:
        return True

    content = str(memory.get('content') or '').strip().lower()
    return any(content.startswith(prefix) for prefix in ACTIVITY_PREFIXES)


def is_sensitive_memory(memory: dict) -> bool:
    level = str(memory.get('data_protection_level') or '').lower()
    return bool(level and level not in {'standard', 'none'})


def filter_and_sort_memories(
    memories: list[dict],
    *,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    updated_after: Optional[datetime] = None,
    sort: str = 'scoring_desc',
) -> list[dict]:
    filtered = []
    updated_after_ts = _datetime_timestamp(updated_after) if updated_after else None
    for memory in memories:
        if reviewed is not None and bool(memory.get('reviewed')) != reviewed:
            continue
        if manually_added is not None and bool(memory.get('manually_added')) != manually_added:
            continue
        if not include_activity and is_activity_memory(memory):
            continue
        if not include_sensitive and is_sensitive_memory(memory):
            continue
        if updated_after_ts is not None:
            updated_at = _datetime_timestamp(memory.get('updated_at'))
            if updated_at is None or updated_at < updated_after_ts:
                continue
        filtered.append(memory)

    if sort == 'created_desc':
        filtered.sort(key=lambda item: _datetime_timestamp(item.get('created_at')) or float('-inf'), reverse=True)
    elif sort == 'updated_desc':
        filtered.sort(key=lambda item: _datetime_timestamp(item.get('updated_at')) or float('-inf'), reverse=True)
    elif sort == 'manual_first':
        filtered.sort(
            key=lambda item: (
                bool(item.get('manually_added')),
                _datetime_timestamp(item.get('updated_at'))
                or _datetime_timestamp(item.get('created_at'))
                or float('-inf'),
            ),
            reverse=True,
        )

    return filtered


def collect_filtered_memories(
    fetch_batch: Callable[[int, int], list[dict]],
    *,
    limit: int,
    offset: int,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    updated_after: Optional[datetime] = None,
    sort: str = 'scoring_desc',
    max_scan: int = 5000,
) -> dict:
    target_count = offset + limit + 1
    requires_global_sort = sort in {'created_desc', 'updated_desc', 'manual_first'}
    requires_sparse_scan = (
        requires_global_sort
        or reviewed is not None
        or manually_added is not None
        or updated_after is not None
        or not include_sensitive
    )
    batch_size = min(500, max(100, limit * 3))
    scanned_count = 0
    candidates: list[dict] = []

    while scanned_count < max_scan:
        batch_limit = min(batch_size, max_scan - scanned_count)
        batch = fetch_batch(scanned_count, batch_limit)
        if not batch:
            break
        scanned_count += len(batch)

        if requires_sparse_scan:
            candidates.extend(batch)
        else:
            candidates.extend(
                filter_and_sort_memories(
                    batch,
                    reviewed=reviewed,
                    manually_added=manually_added,
                    include_activity=include_activity,
                    include_sensitive=include_sensitive,
                    updated_after=updated_after,
                    sort=sort,
                )
            )
            if len(candidates) >= target_count:
                break

        if len(batch) < batch_limit:
            break

    if requires_sparse_scan:
        candidates = filter_and_sort_memories(
            candidates,
            reviewed=reviewed,
            manually_added=manually_added,
            include_activity=include_activity,
            include_sensitive=include_sensitive,
            updated_after=updated_after,
            sort=sort,
        )

    paged = candidates[offset : offset + limit]
    scan_truncated = scanned_count >= max_scan
    return {
        'memories': paged,
        'returned_count': len(paged),
        'has_more': len(candidates) > offset + limit or scan_truncated,
        'offset': offset,
        'limit': limit,
        'sort': sort,
        'include_activity': include_activity,
        'include_sensitive': include_sensitive,
        'scanned_count': scanned_count,
        'scan_truncated': scan_truncated,
    }


def search_v17_default_mcp_memories(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities],
    app_has_default_memory_grant: bool = True,
    now: Optional[datetime] = None,
) -> Optional[list[dict]]:
    """Search default-visible V17 product memory for the MCP memory-search caller.

    This is an explicit caller adapter for `/v1/mcp/memories/search`: callers must
    pass V17 read rollout capabilities and the MCP default-memory grant before it
    touches Firestore. Archive capability is always false here; Archive remains
    available only through the separate explicit product Archive search seam.

    Returns `None` when the caller should keep using the legacy MCP memory path.
    """

    if not rollout_capabilities or not rollout_capabilities.v17_reads_enabled:
        return None
    if not app_has_default_memory_grant:
        return None

    bounded_limit = max(1, min(limit, 20))
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.mcp,
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

    formatted = []
    for rank, item in enumerate(response['items']):
        formatted.append(
            {
                'id': item['memory_id'],
                'content': item['content'],
                'category': 'other',
                'relevance_score': round(1.0 - (rank * 0.0001), 4),
                'v17_default_memory': True,
                'archive_default_visible': False,
                'policy': {
                    'consumer': policy.consumer.value,
                    'app_has_default_memory_grant': policy.app_has_default_memory_grant,
                    'archive_capability': policy.archive_capability,
                    'raw_provenance_capability': policy.raw_provenance_capability,
                },
            }
        )
    return formatted
