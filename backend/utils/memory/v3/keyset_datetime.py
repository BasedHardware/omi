"""Encode and decode V3 keyset cursor timestamps with explicit time units."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


class KeysetTimeUnit(Enum):
    MILLISECONDS = 'milliseconds'
    MICROSECONDS = 'microseconds'


def _require_timezone_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('datetime must be timezone-aware')
    return value.astimezone(timezone.utc)


def encode_keyset_time(value: datetime, unit: KeysetTimeUnit) -> int:
    """Encode a timezone-aware datetime as integer keyset time in ``unit``."""
    utc_value = _require_timezone_aware_utc(value)
    delta = utc_value - _EPOCH_UTC
    match unit:
        case KeysetTimeUnit.MICROSECONDS:
            encoded = delta.days * 24 * 60 * 60 * 1_000_000 + delta.seconds * 1_000_000 + delta.microseconds
        case KeysetTimeUnit.MILLISECONDS:
            encoded = delta.days * 24 * 60 * 60 * 1_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
        case _:
            raise ValueError(f'unsupported keyset time unit: {unit!r}')
    if encoded < 0:
        raise ValueError('keyset time must be non-negative')
    return encoded


def decode_keyset_time(value: int, unit: KeysetTimeUnit) -> datetime:
    """Decode integer keyset time in ``unit`` to a UTC-aware datetime."""
    if type(value) is not int:
        raise ValueError('keyset time must be a non-negative integer')
    if value < 0:
        raise ValueError('keyset time must be non-negative')
    try:
        match unit:
            case KeysetTimeUnit.MILLISECONDS:
                return _EPOCH_UTC + timedelta(milliseconds=value)
            case KeysetTimeUnit.MICROSECONDS:
                return _EPOCH_UTC + timedelta(microseconds=value)
            case _:
                raise ValueError(f'unsupported keyset time unit: {unit!r}')
    except (OverflowError, ValueError) as exc:
        raise ValueError('keyset time out of range') from exc
