from datetime import datetime, timezone
from typing import Callable, Optional

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
