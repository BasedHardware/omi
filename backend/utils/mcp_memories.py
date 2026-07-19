from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from config.memory_rollout import MemoryRolloutCapabilities
from models.product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.memory.default_read_rollout import (
    DefaultReadRolloutDecision,
    MemoryReadDecision,
    build_default_read_rollout_observability,
)
from utils.memory.default_read_surface import (
    DefaultReadSearchResult,
    fetch_default_read_list,
    fetch_default_read_vector,
    rollout_decision_from_legacy_args,
)
from utils.memory.product_memory_read_service import fetch_default_product_memory_search

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
        return self.read_decision == MemoryReadDecision.USE_LEGACY_SAFE


@dataclass(frozen=True)
class McpMemoryListResult:
    memories: List[Dict[str, Any]]
    read_decision: MemoryReadDecision
    fallback_reason: Optional[str] = None

    @property
    def should_use_legacy_fallback(self) -> bool:
        return self.read_decision == MemoryReadDecision.USE_LEGACY_SAFE


def _mcp_search_result(result: DefaultReadSearchResult) -> McpMemorySearchResult:
    return McpMemorySearchResult(
        memories=result.items,
        read_decision=result.read_decision,
        fallback_reason=result.fallback_reason,
    )


def _mcp_list_result(result: DefaultReadSearchResult) -> McpMemoryListResult:
    return McpMemoryListResult(
        memories=result.items,
        read_decision=result.read_decision,
        fallback_reason=result.fallback_reason,
    )


def _attach_mcp_vector_score(
    memory: Dict[str, Any], item: Dict[str, Any], scores_by_memory_id: Dict[str, float]
) -> Dict[str, Any]:
    memory['relevance_score'] = round(float(scores_by_memory_id.get(item['memory_id'], 0)), 4)
    return memory


def _format_memory_mcp_default_memory_item(item: Dict[str, Any], policy: MemoryAccessPolicy) -> Dict[str, Any]:
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': 'other',
        'category_source': 'mcp_memory_compatibility_default_no_source_category',
        'reviewed': False,
        'reviewed_source': 'mcp_memory_compatibility_default_no_review_state',
        'manually_added': False,
        'manually_added_source': 'mcp_memory_compatibility_default_no_manual_state',
        'memory_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def build_mcp_default_memory_rollout_observability(
    decision: DefaultReadRolloutDecision,
) -> Dict[str, Any]:
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
    rollout_capabilities: Optional[MemoryRolloutCapabilities],
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

    if not rollout_capabilities or not rollout_capabilities.memory_reads_enabled:
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

    formatted: List[Dict[str, Any]] = []
    for rank, item in enumerate(response['items']):
        formatted.append(
            {
                'id': item['memory_id'],
                'content': item['content'],
                'category': 'other',
                'category_source': 'mcp_memory_compatibility_default_no_source_category',
                'reviewed': False,
                'reviewed_source': 'mcp_memory_compatibility_default_no_review_state',
                'manually_added': False,
                'manually_added_source': 'mcp_memory_compatibility_default_no_manual_state',
                'relevance_score': round(1.0 - (rank * 0.0001), 4),
                'memory_default_memory': True,
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


def list_default_mcp_memories(
    *,
    uid: str,
    limit: int,
    offset: int,
    db_client: Any,
    rollout_decision: Optional[DefaultReadRolloutDecision] = None,
    rollout_capabilities: Optional[MemoryRolloutCapabilities] = None,
    app_has_default_memory_grant: bool = True,
    categories: Optional[List[str]] = None,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    now: Optional[datetime] = None,
) -> McpMemoryListResult:
    """List default-visible memory memories for MCP get/list callers.

    This mirrors the MCP search adapter's rollout decision contract: malformed,
    missing, no-grant, disabled, and shadow states return an explicit decision and
    touch no `memory_items`; callers may enter legacy only for an explicit
    USE_LEGACY_SAFE decision. Archive remains unavailable by default.
    """

    decision = rollout_decision_from_legacy_args(
        uid=uid,
        consumer='mcp',
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )

    normalized_categories = {str(category) for category in categories or [] if str(category)}

    def _mcp_list_filter(memory: Dict[str, Any]) -> bool:
        if normalized_categories and memory['category'] not in normalized_categories:
            return False
        if reviewed is not None and memory['reviewed'] != reviewed:
            return False
        if manually_added is not None and memory['manually_added'] != manually_added:
            return False
        return True

    return _mcp_list_result(
        fetch_default_read_list(
            uid=uid,
            query='',
            limit=limit,
            offset=offset,
            db_client=db_client,
            decision=decision,
            consumer=MemoryConsumer.mcp,
            now=now,
            item_filter=_mcp_list_filter,
            item_formatter=_format_memory_mcp_default_memory_item,
        )
    )


def search_default_mcp_memories_vector(
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
) -> McpMemorySearchResult:
    """Search hydrated memory vectors for the concrete MCP memory-search caller.

    Returns an explicit read decision before vector lookup or
    `users/{uid}/memory_items` reads. Missing/malformed/no-grant/disabled rollout
    states are DENY_MEMORY/SHADOW_ONLY, not implicit legacy fallback; callers may
    reach legacy only when the decision is explicitly USE_LEGACY_SAFE.
    Archive is deliberately default-disabled here; explicit Archive routes remain
    separate and capability-gated.
    """

    decision = rollout_decision_from_legacy_args(
        uid=uid,
        consumer='mcp',
        rollout_decision=rollout_decision,
        rollout_capabilities=rollout_capabilities,
        app_has_default_memory_grant=app_has_default_memory_grant,
    )
    return _mcp_search_result(
        fetch_default_read_vector(
            uid=uid,
            query=query,
            limit=limit,
            db_client=db_client,
            decision=decision,
            consumer=MemoryConsumer.mcp,
            vector_query=vector_query,
            required_projection_commit_id=required_projection_commit_id,
            now=now,
            item_formatter=_format_memory_mcp_default_memory_item,
            score_attacher=_attach_mcp_vector_score,
        )
    )
