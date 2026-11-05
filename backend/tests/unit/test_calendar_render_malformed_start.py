"""Regression tests for malformed start/end dicts in render_calendar_event."""

from pathlib import Path
from types import ModuleType

from testing.import_isolation import load_module_fresh, stub_modules
from utils.model_text import DisplayClock

BACKEND_DIR = Path(__file__).resolve().parents[2]
TOOLS_DIR = BACKEND_DIR / "utils" / "retrieval" / "tools"


def _package(name: str) -> ModuleType:
    package = ModuleType(name)
    package.__path__ = []
    return package


def test_render_calendar_event_handles_null_start_and_null_datetime():
    with stub_modules({"utils.retrieval.tools": _package("utils.retrieval.tools")}):
        calendar_render = load_module_fresh(
            "utils.retrieval.tools.calendar_render",
            str(TOOLS_DIR / "calendar_render.py"),
        )
    render_calendar_event = calendar_render.render_calendar_event
    clock = DisplayClock.utc()

    null_start = render_calendar_event({"summary": "NullStart", "start": None, "end": None}, 1, clock)
    assert "NullStart" in null_start
    assert "When:" not in null_start

    null_dt = render_calendar_event(
        {"summary": "NullDateTime", "start": {"dateTime": None}, "end": {"dateTime": None}},
        2,
        clock,
    )
    assert "NullDateTime" in null_dt
    assert "When: unknown time (event timestamp could not be parsed)" in null_dt

    null_dt_all_day = render_calendar_event(
        {
            "summary": "AllDayFallback",
            "start": {"dateTime": None, "date": "2026-04-20"},
            "end": {"dateTime": None, "date": "2026-04-22"},
        },
        3,
        clock,
    )
    assert "AllDayFallback" in null_dt_all_day
    assert "When: all day," in null_dt_all_day
    assert "\u2013" in null_dt_all_day