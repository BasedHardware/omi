"""Regression coverage for JSON-native values and pretty rendering of common result types."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path, PureWindowsPath
from uuid import UUID

import pytest
from pydantic import BaseModel

from omi_cli.output import Renderer


@pytest.mark.parametrize(
    "value, expected",
    [
        (date(2026, 10, 24), "2026-10-24"),
        (datetime(2026, 10, 24, 12, 30, tzinfo=timezone.utc), "2026-10-24T12:30:00+00:00"),
        (Path("exports/report.json"), "exports/report.json"),
        (PureWindowsPath("C:/exports/report.json"), "C:\\exports\\report.json"),
        (UUID("12345678-1234-5678-1234-567812345678"), "12345678-1234-5678-1234-567812345678"),
    ],
)
def test_json_common_scalars(capsys, value, expected) -> None:
    Renderer(json_mode=True).emit({"value": value})
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"value": expected}
    assert captured.err == ""


@pytest.mark.parametrize("container", [set, frozenset])
@pytest.mark.parametrize(
    "values, expected",
    [
        ([10, 2], [10, 2]),
        ([True, False], [False, True]),
        ([(2, False), (10, True)], [[10, True], [2, False]]),
        ([None, 3, "3", (1, True)], ["3", 3, [1, True], None]),
        ([], []),
    ],
)
def test_json_sets_preserve_native_values(capsys, container, values, expected) -> None:
    Renderer(json_mode=True).emit({"value": container(values)})
    result = json.loads(capsys.readouterr().out)["value"]
    # JSON text also distinguishes booleans from integer 0/1, unlike Python equality.
    assert json.dumps(result) == json.dumps(expected)


def test_json_nested_frozensets_and_custom_scalars(capsys) -> None:
    payload = {
        "nested": [
            {
                "days": {date(2026, 10, 24)},
                "path": Path("report.json"),
                "uuid": UUID(int=1),
                "groups": {frozenset({2, 3}), frozenset({1})},
            }
        ]
    }
    Renderer(json_mode=True).emit(payload)
    assert json.loads(capsys.readouterr().out) == {
        "nested": [
            {
                "days": ["2026-10-24"],
                "path": "report.json",
                "uuid": "00000000-0000-0000-0000-000000000001",
                "groups": [[1], [2, 3]],
            }
        ]
    }


@pytest.mark.parametrize("table", [False, True])
def test_pretty_nested_mapping_supports_common_types(capsys, table) -> None:
    row = {"data": {"day": date(2026, 10, 24), "path": Path("a.json"), "id": UUID(int=1), "flags": {True, False}}}
    Renderer(no_color=True).emit([row] if table else row)
    captured = capsys.readouterr()
    for token in ["2026-10-24", "a.json", "00000000-0000-0000-0000-000000000001", '"flags": [false, true]']:
        assert token in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("container", [set, frozenset])
@pytest.mark.parametrize("table", [False, True])
def test_pretty_sets_have_stable_literal_cells(capsys, container, table) -> None:
    row = {"items": container(["zeta", "[bold]alpha[/bold]"])}
    Renderer(no_color=True).emit([row] if table else row)
    captured = capsys.readouterr()
    assert "[bold]alpha[/bold], zeta" in captured.out
    assert captured.err == ""


def test_json_pydantic_model_uses_same_nested_type_conversion(capsys) -> None:
    class Result(BaseModel):
        day: date
        path: Path
        ids: frozenset[int]

    Renderer(json_mode=True).emit(Result(day=date(2026, 10, 24), path=Path("a.json"), ids=frozenset({2, 10})))
    assert json.loads(capsys.readouterr().out) == {"day": "2026-10-24", "path": "a.json", "ids": [10, 2]}


def test_json_set_order_is_stable_across_hash_seeds() -> None:
    script = "from omi_cli.output import Renderer; Renderer(json_mode=True).emit({'items': {'zeta', 'alpha', 'beta'}, 'values': {7, '7', (2, False)}})"
    outputs = [
        subprocess.check_output([sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": seed}, text=True)
        for seed in ["1", "2", "37"]
    ]
    assert len(set(outputs)) == 1
    assert json.loads(outputs[0])["values"] == ["7", 7, [2, False]]


def test_json_unsupported_objects_still_fail(capsys) -> None:
    with pytest.raises(TypeError, match="Object of type object is not JSON serializable"):
        Renderer(json_mode=True).emit({"value": object()})
    assert capsys.readouterr().out == ""
