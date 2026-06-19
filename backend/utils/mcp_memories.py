from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config.v17_memory import V17Capabilities
from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_product_authorization import V17ProductAuthorizationContext
from utils.memory.v17_default_read_rollout import (
    V17DefaultReadRolloutDecision,
    V17ReadDecision,
    build_v17_default_read_rollout_observability,
    disabled_v17_default_read_rollout_decision,
    read_v17_default_read_rollout,
)
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search
from utils.memory.v17_vector_search_service import fetch_default_v17_vector_memory_search

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


V17McpDefaultMemoryRolloutDecision = V17DefaultReadRolloutDecision


@dataclass(frozen=True)
class McpV17VerifiedAuth:
    """Server-verified MCP identity/scope payload for future V17 memory reads.

    Existing MCP API-key dependencies return only uid and remain unchanged. This
    helper type is deliberately fake-injectable so REST/OAuth/SSE call sites can
    adopt it only after they can supply stable app/key identity and verified
    scopes from persisted MCP key scopes or OAuth token introspection.
    """

    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()


MCP_V17_DEFAULT_MEMORY_READ_SURFACE = 'mcp_default_memory_read'


def build_mcp_v17_default_memory_read_context(auth: McpV17VerifiedAuth) -> V17ProductAuthorizationContext:
    """Build the MCP V17 default-memory authorization context.

    This function does not grant access by itself. Missing app/key identity or a
    missing `memories.read` scope is carried into the shared app/key/scope
    authorization seam, which fails closed with deterministic reasons. Archive is
    never enabled by this default-read context.
    """

    return V17ProductAuthorizationContext(
        uid=auth.uid,
        consumer='mcp',
        surface=MCP_V17_DEFAULT_MEMORY_READ_SURFACE,
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=tuple(scope for scope in auth.scopes if scope in {'memories.read', 'memories.write'}),
    )


@dataclass(frozen=True)
class V17McpMemorySearchResult:
    memories: list[dict]
    read_decision: V17ReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == V17ReadDecision.USE_LEGACY_SAFE


@dataclass(frozen=True)
class V17McpMemoryListResult:
    memories: list[dict]
    read_decision: V17ReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == V17ReadDecision.USE_LEGACY_SAFE


def _format_v17_mcp_default_memory_item(item: dict, policy: MemoryAccessPolicy) -> dict:
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': 'other',
        'v17_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def build_v17_mcp_default_memory_rollout_observability(
    decision: V17McpDefaultMemoryRolloutDecision,
) -> dict:
    observability = build_v17_default_read_rollout_observability(decision)
    return {
        'uid': decision.uid,
        'source_path': decision.source_path,
        'enabled': decision.v17_default_mcp_enabled,
        'reason': observability['reason'],
        'mode': observability['mode'],
        'v17_reads_enabled': observability['v17_reads_enabled'],
        'legacy_reads_authoritative': observability['legacy_reads_authoritative'],
        'mcp_default_memory_grant': observability['default_memory_grant'],
        'archive_default_visible': observability['archive_default_visible'],
        'archive_capability': observability['archive_capability'],
        'fallback_reason': observability['fallback_reason'],
        'grants': {'mcp_default_memory': observability['default_memory_grant']},
        'capabilities': observability['capabilities'],
    }


def read_v17_mcp_default_memory_rollout(*, uid: str, db_client) -> V17McpDefaultMemoryRolloutDecision:
    """Read server-owned V17 MCP default-memory rollout state.

    The authoritative per-user document is `users/{uid}/memory_control/state`.
    Missing, malformed, or grant-less docs fail closed to legacy MCP search before
    any `users/{uid}/memory_items` read. Archive is deliberately not derived here:
    the MCP default search path always keeps `archive_capability=False`.
    """

    return read_v17_default_read_rollout(uid=uid, db_client=db_client, consumer='mcp')


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


def list_v17_default_mcp_memories(
    *,
    uid: str,
    limit: int,
    offset: int,
    db_client,
    rollout_decision: Optional[V17McpDefaultMemoryRolloutDecision] = None,
    rollout_capabilities: Optional[V17Capabilities] = None,
    app_has_default_memory_grant: bool = True,
    now: Optional[datetime] = None,
) -> V17McpMemoryListResult:
    """List default-visible V17 memories for MCP get/list callers.

    This mirrors the MCP search adapter's rollout decision contract: malformed,
    missing, no-grant, disabled, and shadow states return an explicit decision and
    touch no `memory_items`; callers may enter legacy only for an explicit
    USE_LEGACY_SAFE decision. Archive remains unavailable by default.
    """

    if rollout_decision is None:
        if rollout_capabilities is None:
            rollout_decision = disabled_v17_default_read_rollout_decision(
                uid=uid,
                source_path=f'users/{uid}/memory_control/state',
                consumer='mcp',
                reason='missing_rollout_state',
            )
        else:
            rollout_decision = V17DefaultReadRolloutDecision(
                uid=uid,
                source_path=f'users/{uid}/memory_control/state',
                consumer='mcp',
                rollout_capabilities=rollout_capabilities,
                app_has_default_memory_grant=app_has_default_memory_grant,
                archive_capability=False,
            )

    if rollout_decision.read_decision != V17ReadDecision.USE_V17:
        return V17McpMemoryListResult(
            memories=[],
            read_decision=rollout_decision.read_decision,
            fallback_reason=rollout_decision.fallback_reason,
        )

    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.mcp,
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    response = fetch_default_product_memory_search(
        uid=uid,
        query='',
        db_client=db_client,
        policy=policy,
        now=now,
        limit=bounded_limit,
        offset=bounded_offset,
    )
    return V17McpMemoryListResult(
        memories=[_format_v17_mcp_default_memory_item(item, policy) for item in response['items']],
        read_decision=V17ReadDecision.USE_V17,
    )


def search_v17_default_mcp_memories_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[V17McpDefaultMemoryRolloutDecision] = None,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
) -> V17McpMemorySearchResult:
    """Search hydrated V17 vectors for the concrete MCP memory-search caller.

    Returns an explicit read decision before vector lookup or
    `users/{uid}/memory_items` reads. Missing/malformed/no-grant/disabled rollout
    states are DENY_MEMORY/SHADOW_ONLY, not implicit legacy fallback; callers may
    reach legacy only when the decision is explicitly USE_LEGACY_SAFE.
    Archive is deliberately default-disabled here; explicit Archive routes remain
    separate and capability-gated.
    """

    if rollout_decision is None:
        if rollout_capabilities is None:
            rollout_decision = disabled_v17_default_read_rollout_decision(
                uid=uid,
                source_path=f'users/{uid}/memory_control/state',
                consumer='mcp',
                reason='missing_rollout_state',
            )
        else:
            rollout_decision = V17DefaultReadRolloutDecision(
                uid=uid,
                source_path=f'users/{uid}/memory_control/state',
                consumer='mcp',
                rollout_capabilities=rollout_capabilities,
                app_has_default_memory_grant=app_has_default_memory_grant,
                archive_capability=False,
            )

    if rollout_decision.read_decision != V17ReadDecision.USE_V17:
        return V17McpMemorySearchResult(
            memories=[],
            read_decision=rollout_decision.read_decision,
            fallback_reason=rollout_decision.fallback_reason,
        )

    bounded_limit = max(1, min(limit, 20))
    projection_commit_id = required_projection_commit_id or rollout_decision.vector_projection_commit_id
    if not projection_commit_id:
        return V17McpMemorySearchResult(
            memories=[],
            read_decision=V17ReadDecision.DENY_MEMORY,
            fallback_reason='missing_vector_projection_commit_id',
        )
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.mcp,
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
        required_account_generation=rollout_decision.rollout_capabilities.account_generation,
    )

    scores_by_memory_id = response.get('scores_by_memory_id', {})
    formatted = []
    for item in response['items']:
        memory_id = item['memory_id']
        formatted.append(
            {
                'id': memory_id,
                'content': item.get('content') or '',
                'category': 'other',
                'relevance_score': round(float(scores_by_memory_id.get(memory_id, 0)), 4),
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
    return V17McpMemorySearchResult(memories=formatted, read_decision=V17ReadDecision.USE_V17)
