"""Held-content wire policy. A choice never grants managed processing entitlement."""

from datetime import datetime, timezone
from typing import Any, Mapping

HELD_CONTENT_CAPABILITY = 'X-Omi-Held-Content'
CHOICES = frozenset({'on_device', 'upgrade'})


def budget_period(now: datetime | None = None) -> str:
    """Legacy usage and annual subscriptions currently share UTC calendar-month buckets."""
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m')


def current_choice(record: Mapping[str, Any] | None, period: str) -> dict[str, Any] | None:
    if not record or record.get('period') != period or record.get('choice') not in CHOICES:
        return None
    return {
        'period': period,
        'choice': record['choice'],
        'dont_ask_again': record.get('dont_ask_again') is True,
    }


def capture_state(*, managed: bool, exhausted: bool, choice: Mapping[str, Any] | None) -> str:
    """Upgrade is intent only: remain held until the allowance resolver admits managed STT."""
    if managed:
        return 'managed'
    if not exhausted:
        return 'unavailable'
    return 'on_device' if choice and choice.get('choice') == 'on_device' else 'held_pending_choice'
