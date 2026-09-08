from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from utils.memory.product_authorization import ProductAuthorizationContext
from utils.memory.default_read_rollout import MemoryReadDecision

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
class McpVerifiedAuth:
    """Server-verified MCP identity/scope payload for future memory memory reads.

    Existing MCP API-key dependencies return only uid and remain unchanged. This
    helper type is deliberately fake-injectable so REST/OAuth/SSE call sites can
    adopt it only after they can supply stable app/key identity and verified
    scopes from persisted MCP key scopes or OAuth token introspection.
    """

    uid: str
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    scopes: tuple[str, ...] = ()


MCP_MEMORY_DEFAULT_MEMORY_READ_SURFACE = 'mcp_default_memory_read'
MCP_MEMORY_DEFAULT_MEMORY_WRITE_SURFACE = 'mcp_default_memory_write'


def build_mcp_default_memory_read_context(auth: McpVerifiedAuth) -> ProductAuthorizationContext:
    """Build the MCP memory default-memory authorization context.

    This function does not grant access by itself. Missing app/key identity or a
    missing `memories.read` scope is carried into the shared app/key/scope
    authorization seam, which fails closed with deterministic reasons. Archive is
    never enabled by this default-read context.
    """

    return ProductAuthorizationContext(
        uid=auth.uid,
        consumer='mcp',
        surface=MCP_MEMORY_DEFAULT_MEMORY_READ_SURFACE,
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=tuple(scope for scope in auth.scopes if scope in {'memories.read', 'memories.write'}),
    )


def build_mcp_default_memory_write_context(auth: McpVerifiedAuth) -> ProductAuthorizationContext:
    """Build the MCP memory write authorization context.

    Mirrors the read context but carries a distinct surface for observability so
    write mutations can be attributed separately. Missing app/key identity or a
    missing `memories.write` scope is carried into the shared app/key/scope grant
    seam, which fails closed with deterministic reasons.
    """

    return ProductAuthorizationContext(
        uid=auth.uid,
        consumer='mcp',
        surface=MCP_MEMORY_DEFAULT_MEMORY_WRITE_SURFACE,
        app_id=auth.app_id,
        key_id=auth.key_id,
        scopes=tuple(scope for scope in auth.scopes if scope in {'memories.read', 'memories.write'}),
    )


@dataclass(frozen=True)
class McpMemorySearchResult:
    memories: List[Dict[str, Any]]
    read_decision: MemoryReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return False


@dataclass(frozen=True)
class McpMemoryListResult:
    memories: List[Dict[str, Any]]
    read_decision: MemoryReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return False


def mcp_legacy_read_authorized(result: 'McpMemorySearchResult | McpMemoryListResult') -> bool:
    """Historical storage is never a second MCP product authority."""
    return False


MCP_MEMORY_READ_DENIED_FALLBACK_REASON = 'memory_read_denied'


def mcp_denied_read_payload(result: 'McpMemorySearchResult | McpMemoryListResult') -> Optional[Dict[str, Any]]:
    """Client-visible payload for a refused MCP memory read, or None to serve an empty result.

    Callers reach this only after `mcp_legacy_read_authorized` has refused the legacy
    surface. Every such state is an authorization or indeterminate-rollout condition the
    caller cannot see or act on, so it must be reported rather than rendered as an empty
    account — an empty success is indistinguishable from "you have no memories", which is
    the reading most likely to make a user believe their data was deleted. The payload
    mirrors the existing grant-denial shape so both refusals read the same to a client.

    Returning the whole payload rather than a bare reason keeps both the classification and
    the wire shape here, so each surface adds only its own raise.
    """
    reason = result.fallback_reason or MCP_MEMORY_READ_DENIED_FALLBACK_REASON
    return {'enabled': False, 'reason': reason, 'consumer': 'mcp'}


def build_mcp_default_memory_rollout_observability(
    decision: Any,
) -> Dict[str, Any]:
    from utils.memory.default_read_rollout import build_default_read_rollout_observability

    observability = build_default_read_rollout_observability(decision)
    return {
        'uid': decision.uid,
        'source_path': decision.source_path,
        'enabled': decision.memory_default_mcp_enabled,
        'reason': observability['reason'],
        'mode': observability['mode'],
        'memory_reads_enabled': observability['memory_reads_enabled'],
        'legacy_reads_authoritative': observability['legacy_reads_authoritative'],
        'mcp_default_memory_grant': observability['default_memory_grant'],
        'archive_default_visible': observability['archive_default_visible'],
        'archive_capability': observability['archive_capability'],
        'fallback_reason': observability['fallback_reason'],
        'grants': {'mcp_default_memory': observability['default_memory_grant']},
        'capabilities': observability['capabilities'],
    }


def parse_mcp_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as e:
        raise ValueError(f"Invalid {field_name} format: '{value}'. Expected ISO 8601.") from e


def parse_mcp_int(value: Any, field_name: str, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        parsed = default
    else:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid {field_name}: expected integer.") from e
    return max(minimum, min(parsed, maximum))


def parse_optional_mcp_bool(value: Any, field_name: str) -> Optional[bool]:
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


def parse_mcp_bool(value: Any, field_name: str, *, default: bool) -> bool:
    if value is None:
        return default
    parsed = parse_optional_mcp_bool(value, field_name)
    return default if parsed is None else parsed


def _datetime_timestamp(value: Any) -> Optional[float]:
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


def is_activity_memory(memory: Dict[str, Any]) -> bool:
    tags_value: Any = memory.get('tags') or []
    tags = {str(tag).lower() for tag in tags_value}
    if tags.intersection(ACTIVITY_TAGS):
        return True

    source = str(memory.get('source') or memory.get('source_type') or '').lower()
    if source in ACTIVITY_TAGS:
        return True

    content = str(memory.get('content') or '').strip().lower()
    return any(content.startswith(prefix) for prefix in ACTIVITY_PREFIXES)


def is_sensitive_memory(memory: Dict[str, Any]) -> bool:
    level = str(memory.get('data_protection_level') or '').lower()
    return bool(level and level not in {'standard', 'none'})


def filter_and_sort_memories(
    memories: List[Dict[str, Any]],
    *,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    updated_after: Optional[datetime] = None,
    sort: str = 'scoring_desc',
    categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    category_set = {c for c in categories} if categories else None
    filtered: List[Dict[str, Any]] = []
    updated_after_ts = _datetime_timestamp(updated_after) if updated_after else None
    for memory in memories:
        if category_set is not None:
            mem_category = memory.get('category')
            mem_category = getattr(mem_category, 'value', mem_category)
            if mem_category not in category_set:
                continue
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
    fetch_batch: Callable[[int, int], List[Dict[str, Any]]],
    *,
    limit: int,
    offset: int,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    updated_after: Optional[datetime] = None,
    sort: str = 'scoring_desc',
    categories: Optional[List[str]] = None,
    max_scan: int = 5000,
) -> Dict[str, Any]:
    target_count = offset + limit + 1
    requires_global_sort = sort in {'created_desc', 'updated_desc', 'manual_first'}
    requires_sparse_scan = (
        requires_global_sort
        or reviewed is not None
        or manually_added is not None
        or updated_after is not None
        or not include_sensitive
        or categories is not None
    )
    batch_size = min(500, max(100, limit * 3))
    scanned_count = 0
    candidates: List[Dict[str, Any]] = []

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
                    categories=categories,
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
            categories=categories,
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


def search_default_mcp_memories(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client: Any,
    rollout_capabilities: Optional[Any],
    app_has_default_memory_grant: bool = True,
    now: Optional[datetime] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Search default-visible memory product memory for the MCP memory-search caller.

    This is an explicit caller adapter for `/v1/mcp/memories/search`: callers must
    pass memory read rollout capabilities and the MCP default-memory grant before it
    touches Firestore. Archive capability is always false here; Archive remains
    available only through the separate explicit product Archive search seam.

    Returns `None` when the caller should keep using the legacy MCP memory path.
    """

    bounded_limit = max(1, min(limit, 20))
    from utils.memory.memory_service import MemoryService

    return MemoryService(db_client=db_client).search_mcp(uid, query, limit=bounded_limit)


def list_default_mcp_memories(
    *,
    uid: str,
    limit: int,
    offset: int,
    db_client: Any,
    rollout_decision: Optional[Any] = None,
    rollout_capabilities: Optional[Any] = None,
    app_has_default_memory_grant: bool = True,
    categories: Optional[List[str]] = None,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    now: Optional[datetime] = None,
) -> McpMemoryListResult:
    """List universal MCP memories while retaining the old result envelope."""
    from utils.memory.memory_service import MemoryService

    service = MemoryService(db_client=db_client)
    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    target_end = bounded_offset + bounded_limit
    max_scan = 5000
    scanned_offset = 0
    source_rows: List[Dict[str, Any]] = []
    # Read in universal pages, then apply sparse filters and the requested
    # offset.  The old adapter fetched only the first 500 rows before slicing,
    # silently hiding later memories from larger accounts.
    while scanned_offset < max_scan and len(source_rows) < max_scan:
        batch_limit = min(500, max_scan - scanned_offset)
        batch = service.read(uid, limit=batch_limit, offset=scanned_offset)
        if not batch:
            break
        source_rows.extend(memory.model_dump(mode='json') for memory in batch)
        scanned_offset += len(batch)
        if len(batch) < batch_limit:
            break

    memories = filter_and_sort_memories(
        source_rows,
        reviewed=reviewed,
        manually_added=manually_added,
        categories=categories,
        sort='created_desc',
    )
    page = memories[bounded_offset:target_end]
    return McpMemoryListResult(memories=page, read_decision=MemoryReadDecision.USE_MEMORY)


def search_default_mcp_memories_vector(
    *,
    uid: str,
    query: str,
    limit: int,
    db_client: Any,
    rollout_capabilities: Optional[Any] = None,
    app_has_default_memory_grant: bool = True,
    rollout_decision: Optional[Any] = None,
    vector_query: Optional[Callable[..., Any]] = None,
    required_projection_commit_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> McpMemorySearchResult:
    from utils.memory.memory_service import MemoryService

    return McpMemorySearchResult(
        memories=MemoryService(db_client=db_client).search_mcp(uid, query, limit=max(1, min(limit, 20))),
        read_decision=MemoryReadDecision.USE_MEMORY,
    )
