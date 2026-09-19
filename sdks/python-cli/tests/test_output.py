"""Tests for the Renderer (Rich + JSON output paths)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

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


@pytest.mark.parametrize("literal", ["Missing [/bold]", "Keep [bold]tags[/bold] :warning:"])
def test_pretty_error_preserves_literal_message_detail_and_metadata(capsys, literal) -> None:
    renderer = Renderer(no_color=True)
    renderer.error(literal, detail=literal, extra={literal: literal})
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count(literal) == 4


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


@pytest.mark.parametrize(
    "rows, expected",
    [
        (["alpha", "beta"], ["alpha", "beta"]),
        ([17, 3.5], ["17", "3.5"]),
        ([True, False, None], ["✓", "✗"]),
    ],
)
def test_pretty_mode_renders_scalar_and_mixed_arrays(capsys, rows, expected) -> None:
    Renderer(no_color=True).emit(rows)
    output = capsys.readouterr().out
    for token in expected:
        assert token in output
    first = expected[0]
    second = expected[1]
    assert output.index(first) < output.index(second)


def test_pretty_mode_renders_mapping_row_inside_mixed_array(capsys) -> None:
    Renderer(no_color=True).emit(["alpha", 17, {"k": 1}])
    output = capsys.readouterr().out
    assert "value" in output
    assert "k" in output
    assert "alpha" in output
    assert "17" in output
    assert "1" in output
    assert output.index("alpha") < output.index("17")


def test_json_mode_preserves_scalar_array_shape(capsys) -> None:
    Renderer(json_mode=True).emit(["alpha", 17])
    assert json.loads(capsys.readouterr().out) == ["alpha", 17]


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


@pytest.mark.parametrize("first_row", [{}, {"id": "first"}])
def test_pretty_table_includes_fields_from_later_rows(capsys, first_row) -> None:
    Renderer(no_color=True).emit([first_row, {"id": "second", "detail": "later-value"}])
    output = capsys.readouterr().out
    assert "second" in output
    assert "detail" in output
    assert "later-value" in output


def test_pretty_table_respects_explicit_columns(capsys) -> None:
    Renderer(no_color=True).emit([{"id": "first"}, {"id": "second", "detail": "hidden-value"}], columns=["id"])
    output = capsys.readouterr().out
    assert "first" in output
    assert "second" in output
    assert "detail" not in output
    assert "hidden-value" not in output


def test_shorten_basic() -> None:
    assert shorten("abcdef", 3) == "ab…"
    assert shorten("abcdef", 10) == "abcdef"
    assert shorten(None) == ""
    assert shorten("") == ""


def test_coalesce_rows_handles_dicts_and_models() -> None:
    class Fake:
        def model_dump(self) -> dict:
            return {"x": 1}

    rows = coalesce_rows([{"a": 1}, Fake(), "scalar", 9])
    assert rows == [{"a": 1}, {"x": 1}, {"value": "scalar"}, {"value": 9}]


def test_no_color_env_disables_color(monkeypatch, capsys) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    renderer = Renderer(json_mode=False)
    renderer.success("done")
    captured = capsys.readouterr()
    # No ANSI codes when NO_COLOR is set.
    assert "\x1b[" not in captured.err


@pytest.mark.parametrize(
    "data",
    [
        [{"content": "[draft] literal [/bold] :warning:"}],
        {"content": "[draft] literal [/bold] :warning:"},
        "[draft] literal [/bold] :warning:",
    ],
)
def test_pretty_data_is_literal(data, capsys) -> None:
    Renderer(no_color=True).emit(data)
    assert "[draft] literal [/bold] :warning:" in capsys.readouterr().out


def test_pretty_data_keys_and_matched_tags_are_literal(capsys) -> None:
    renderer = Renderer(no_color=True)
    data = {"[key]": "[bold]keep tags[/bold] :warning:"}
    renderer.emit(data)
    renderer.emit([data])
    output = capsys.readouterr().out
    assert output.count("[key]") == 2
    assert output.count("[bold]keep tags[/bold] :warning:") == 2
