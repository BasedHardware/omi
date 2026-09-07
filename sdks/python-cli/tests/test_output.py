"""Tests for the Renderer (Rich + JSON output paths)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from omi_cli.output import Renderer, coalesce_rows, shorten


def test_json_mode_emits_valid_json_to_stdout(capsys) -> None:
    renderer = Renderer(json_mode=True)
    renderer.emit({"id": "m1", "content": "hi"})
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed == {"id": "m1", "content": "hi"}
    # Stderr should be quiet for emit() in JSON mode.
    assert captured.err == ""


def test_json_mode_silences_info_and_success(capsys) -> None:
    renderer = Renderer(json_mode=True)
    renderer.info("hello")
    renderer.success("yay")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_json_mode_emits_errors_as_json_to_stderr(capsys) -> None:
    renderer = Renderer(json_mode=True)
    renderer.error("bad", detail="reason")
    captured = capsys.readouterr()
    assert captured.out == ""
    parsed = json.loads(captured.err)
    assert parsed == {"error": "bad", "detail": "reason"}


def test_json_mode_serializes_datetime() -> None:
    import sys
    from io import StringIO

    renderer = Renderer(json_mode=True)
    buffer = StringIO()
    sys.stdout, original = buffer, sys.stdout
    try:
        renderer.emit({"created_at": datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)})
    finally:
        sys.stdout = original
    parsed = json.loads(buffer.getvalue())
    assert parsed["created_at"].startswith("2026-04-26T12:00:00")


def test_pretty_mode_renders_table_for_list(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit([{"id": "m1", "content": "hello"}], columns=["id", "content"], title="memories")
    captured = capsys.readouterr()
    assert "m1" in captured.out
    assert "hello" in captured.out


def test_pretty_mode_renders_no_results_for_empty_list(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit([])
    captured = capsys.readouterr()
    assert "no results" in captured.out


def test_shorten_basic() -> None:
    assert shorten("abcdef", 3) == "ab…"
    assert shorten("abcdef", 10) == "abcdef"
    assert shorten(None) == ""
    assert shorten("") == ""


def test_coalesce_rows_handles_dicts_and_models() -> None:
    class Fake:
        def model_dump(self) -> dict:
            return {"x": 1}

    rows = coalesce_rows([{"a": 1}, Fake()])
    assert rows == [{"a": 1}, {"x": 1}]


def test_no_color_env_disables_color(monkeypatch, capsys) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    renderer = Renderer(json_mode=False)
    renderer.success("done")
    captured = capsys.readouterr()
    # No ANSI codes when NO_COLOR is set.
    assert "\x1b[" not in captured.err


# --- Regression tests for issue #12959: API data must render literally ---

MARKUP_CONTENT = "Remember [bold]literal[/bold]"
UNSAFE_CONTENT = "Remember [/bold]"


def test_pretty_memory_content_preserves_literal_markup_tags(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit({"id": "m1", "content": MARKUP_CONTENT})
    captured = capsys.readouterr()
    assert MARKUP_CONTENT in captured.out


def test_pretty_memory_content_with_invalid_markup_does_not_crash(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit({"id": "m1", "content": UNSAFE_CONTENT})
    captured = capsys.readouterr()
    assert UNSAFE_CONTENT in captured.out


def test_pretty_table_cell_preserves_literal_markup_tags(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit([{"id": "m1", "content": MARKUP_CONTENT}], columns=["id", "content"], title="memories")
    captured = capsys.readouterr()
    assert MARKUP_CONTENT in captured.out


def test_pretty_table_cell_with_invalid_markup_does_not_crash(capsys) -> None:
    renderer = Renderer(json_mode=False, no_color=True)
    renderer.emit([{"id": "m1", "content": UNSAFE_CONTENT}], columns=["id", "content"], title="memories")
    captured = capsys.readouterr()
    assert UNSAFE_CONTENT in captured.out
