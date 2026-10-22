"""Stored timestamps have one UTC representation before arithmetic or sorting."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.conversations.datetime_utils import coerce_utc_datetime


@pytest.mark.parametrize(
    'value',
    [
        datetime(2026, 10, 1, 12),
        datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        '2026-10-01T12:00:00',
        '2026-10-01T12:00:00Z',
        ' 2026-10-01T17:30:00+05:30 ',
        1790856000,
        1790856000.0,
    ],
)
def test_normalizes_timestamp_shapes(value):
    result = coerce_utc_datetime(value)
    assert result == datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert result.tzinfo is timezone.utc


@pytest.mark.parametrize(
    'value',
    [None, '', 'not-a-date', True, False, {}, [], float('nan'), float('inf'), -float('inf'), 10**100],
)
def test_invalid_timestamp_is_absent(value):
    assert coerce_utc_datetime(value) is None


def test_epoch_zero_and_fractional_seconds_are_valid():
    assert coerce_utc_datetime(0) == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert coerce_utc_datetime(1790856000.5).microsecond == 500000


def test_utc_conversion_outside_datetime_range_is_absent():
    assert coerce_utc_datetime(datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))) is None
