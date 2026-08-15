from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils.memory.v3.keyset_datetime import (
    KeysetTimeUnit,
    decode_keyset_time,
    encode_keyset_time,
)

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ('unit', 'delta_kwargs'),
    [
        (KeysetTimeUnit.MICROSECONDS, {'microseconds': 1}),
        (KeysetTimeUnit.MICROSECONDS, {'seconds': 42, 'microseconds': 123_456}),
        (KeysetTimeUnit.MICROSECONDS, {'days': 10, 'hours': 3, 'minutes': 17, 'seconds': 59, 'microseconds': 999_999}),
        (KeysetTimeUnit.MILLISECONDS, {'milliseconds': 1}),
        (KeysetTimeUnit.MILLISECONDS, {'seconds': 42, 'milliseconds': 123}),
        (KeysetTimeUnit.MILLISECONDS, {'days': 2, 'hours': 5, 'minutes': 30, 'seconds': 15, 'milliseconds': 500}),
    ],
)
def test_keyset_time_round_trips_for_unit(unit: KeysetTimeUnit, delta_kwargs: dict[str, int]):
    original = EPOCH + timedelta(**delta_kwargs)

    encoded = encode_keyset_time(original, unit)
    decoded = decode_keyset_time(encoded, unit)

    assert decoded == original


def test_microsecond_unit_preserves_sub_millisecond_precision():
    original = datetime(2026, 8, 2, 12, 0, 0, 123_456, tzinfo=UTC)

    encoded = encode_keyset_time(original, KeysetTimeUnit.MICROSECONDS)
    decoded = decode_keyset_time(encoded, KeysetTimeUnit.MICROSECONDS)

    assert decoded == original
    assert encoded % 1_000 != 0


def test_millisecond_unit_truncates_sub_millisecond_precision():
    original = datetime(2026, 8, 2, 12, 0, 0, 123_456, tzinfo=UTC)
    expected = datetime(2026, 8, 2, 12, 0, 0, 123_000, tzinfo=UTC)

    encoded = encode_keyset_time(original, KeysetTimeUnit.MILLISECONDS)
    decoded = decode_keyset_time(encoded, KeysetTimeUnit.MILLISECONDS)

    assert decoded == expected
    assert encoded == encode_keyset_time(expected, KeysetTimeUnit.MILLISECONDS)


def test_encode_converts_non_utc_timezone_aware_datetime_to_utc():
    eastern = timezone(timedelta(hours=-4))
    local_value = datetime(2026, 8, 2, 8, 0, 0, 500_000, tzinfo=eastern)
    utc_value = datetime(2026, 8, 2, 12, 0, 0, 500_000, tzinfo=UTC)

    assert encode_keyset_time(local_value, KeysetTimeUnit.MICROSECONDS) == encode_keyset_time(
        utc_value,
        KeysetTimeUnit.MICROSECONDS,
    )


@pytest.mark.parametrize(
    'value',
    [
        datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC),
        datetime(1969, 1, 1, tzinfo=UTC),
    ],
)
def test_encode_rejects_negative_epoch_times(value: datetime):
    with pytest.raises(ValueError, match='non-negative'):
        encode_keyset_time(value, KeysetTimeUnit.MICROSECONDS)


def test_encode_rejects_naive_datetime():
    with pytest.raises(ValueError, match='timezone-aware'):
        encode_keyset_time(datetime(2026, 8, 2, 12, 0, 0), KeysetTimeUnit.MICROSECONDS)


@pytest.mark.parametrize(
    'value',
    [
        -1,
        True,
        False,
        1.5,
        '123',
        None,
    ],
)
def test_decode_rejects_invalid_values(value: object):
    with pytest.raises(ValueError):
        decode_keyset_time(value, KeysetTimeUnit.MICROSECONDS)  # type: ignore[arg-type]


def test_decode_rejects_negative_integer():
    with pytest.raises(ValueError, match='non-negative'):
        decode_keyset_time(-1, KeysetTimeUnit.MICROSECONDS)


def test_epoch_round_trip():
    assert encode_keyset_time(EPOCH, KeysetTimeUnit.MICROSECONDS) == 0
    assert decode_keyset_time(0, KeysetTimeUnit.MICROSECONDS) == EPOCH
    assert encode_keyset_time(EPOCH, KeysetTimeUnit.MILLISECONDS) == 0
    assert decode_keyset_time(0, KeysetTimeUnit.MILLISECONDS) == EPOCH
