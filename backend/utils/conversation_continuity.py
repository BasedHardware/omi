"""Shared boundary arithmetic; callers supply their observed timeline coverage."""

from datetime import datetime
from typing import Any, Mapping

DEFAULT_GAP_SECONDS = 120


def gap_splits(seconds: float, timeout: float = DEFAULT_GAP_SECONDS) -> bool:
    return seconds >= timeout


def intervals_connect(start: float, end: float, other_start: float, other_end: float) -> bool:
    return not gap_splits(max(start - other_end, other_start - end))


def resumable_continuation(
    row: Mapping[str, Any], *, source: str, device_id: str | None, now: datetime, timeout: int
) -> bool:
    """Unknown device is a partition, not permission to join another device."""
    finish = row.get('finished_at')
    return (
        row.get('status') == 'in_progress'
        and not any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        and row.get('source') == source
        and row.get('client_device_id') == device_id
        and isinstance(finish, datetime)
        and not gap_splits((now - finish).total_seconds(), timeout)
    )
