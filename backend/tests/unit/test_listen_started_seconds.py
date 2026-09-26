"""Regression: boolean flags must never masquerade as epoch timestamps.

``bool`` subclasses ``int``, so ``persisted_started_seconds(True)`` used to
return ``1.0`` (one second after the Unix epoch). Callers treat a truthy
value as a real timestamp and skip their ``first_audio_byte_timestamp``
fallback, shifting every transcript segment offset by ~55 years (#19043).
"""

from routers.listen.contracts import persisted_started_seconds


def test_true_is_rejected():
    assert persisted_started_seconds(True) is None


def test_false_is_rejected():
    assert persisted_started_seconds(False) is None


def test_int_and_float_still_parse():
    assert persisted_started_seconds(1700000000) == 1700000000.0
    assert persisted_started_seconds(1700000000.5) == 1700000000.5
    assert persisted_started_seconds(0) == 0.0


def test_iso_string_and_none_unchanged():
    assert persisted_started_seconds("2024-01-01T00:00:00") == 1704045600.0
    assert persisted_started_seconds(None) is None
    assert persisted_started_seconds("not-a-date") is None
    assert persisted_started_seconds([1]) is None
