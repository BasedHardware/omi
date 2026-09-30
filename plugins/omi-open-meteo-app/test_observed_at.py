from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

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


if __name__ == "__main__":
    test_includes_timezone_name_and_offset()
    test_negative_offset()
    test_falls_back_to_raw_time_without_metadata()
    print("All test_observed_at tests passed.")
