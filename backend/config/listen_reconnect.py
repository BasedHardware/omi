"""Bounded mobile batch transport continuity; no content or IO in this contract."""

import os
from datetime import datetime, timezone
from typing import Any, Mapping

FIELD = 'listen_batch_producer'
LEASE_SECONDS = 120
RENEW_SECONDS = 30
TERMINAL_REASONS = frozenset(
    {'user_stop', 'finish_and_continue', 'meeting_started', 'meeting_ended', 'max_duration_rotation'}
)


def enabled() -> bool:
    return os.getenv('LISTEN_BATCH_RECONNECT_ENABLED', 'false').strip().lower() == 'true'


def grace_seconds() -> int:
    try:
        value = int(os.getenv('LISTEN_BATCH_RECONNECT_GRACE_SECONDS', '120'))
    except ValueError:
        return 120
    return max(1, min(value, 120))


def utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def producer(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get(FIELD)
    return value if isinstance(value, Mapping) and value.get('version') == 1 else {}


def deadline(row: Mapping[str, Any], quiet_deadline: datetime, *, now: datetime) -> datetime:
    state = producer(row)
    end = utc(state.get('deadline_at'))
    if state.get('phase') in {'disconnected', 'ended'} and state.get('drained') is True and end is not None:
        return min(quiet_deadline, end) if enabled() else min(quiet_deadline, end, now)
    return quiet_deadline


def end_due(row: Mapping[str, Any], now: datetime) -> bool:
    state = producer(row)
    end = utc(state.get('deadline_at'))
    return bool(
        state.get('phase') in {'disconnected', 'ended'}
        and state.get('drained') is True
        and end
        and (not enabled() or end <= now)
    )


def grace_expired(row: Mapping[str, Any], now: datetime) -> bool:
    # Resume eligibility must still reach the listener's durable switch-off exit.
    state = producer(row)
    end = utc(state.get('deadline_at'))
    return bool(state.get('phase') in {'disconnected', 'ended'} and state.get('drained') is True and end and end <= now)


def write_owned(row: Mapping[str, Any], token: str | None) -> bool:
    state = producer(row)
    return not state or bool(token and state.get('token') == token and state.get('phase') == 'active')
