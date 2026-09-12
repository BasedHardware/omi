"""Unit tests for timezone-aware observation timestamps (issue #13194)."""

from main import _format_observed_at


def test_includes_timezone_name_and_offset():
    current = {"time": "2026-09-11T14:00"}
    payload = {"timezone": "Europe/Berlin", "utc_offset_seconds": 7200}
    out = _format_observed_at(current, payload)
    assert "2026-09-11T14:00" in out
    assert "Europe/Berlin" in out
    assert "UTC+02:00" in out


def test_negative_offset():
    current = {"time": "2026-09-11T09:00"}
    payload = {"timezone": "America/New_York", "utc_offset_seconds": -14400}
    out = _format_observed_at(current, payload)
    assert "UTC-04:00" in out


def test_falls_back_to_raw_time_without_metadata():
    out = _format_observed_at({"time": "2026-09-11T14:00"}, {})
    assert out == "2026-09-11T14:00"
