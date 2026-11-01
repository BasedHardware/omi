"""Deeply nested JSON must raise ValueError, not RecursionError (#13507)."""

from __future__ import annotations

import json

import pytest

from omi_cli.json_input import MAX_NESTING_DEPTH, load_json_input


def _nested(depth: int) -> str:
    return '{"a":' * depth + "1" + "}" * depth


def test_load_json_input_rejects_nesting_past_the_supported_depth():
    with pytest.raises(ValueError) as exc:
        load_json_input(_nested(MAX_NESTING_DEPTH + 1))
    assert "nesting" in str(exc.value).lower()


def test_load_json_input_accepts_the_supported_depth_and_the_result_serializes():
    json.dumps(load_json_input(_nested(MAX_NESTING_DEPTH)))


def test_load_json_input_maps_a_parse_time_recursion_error_to_value_error(monkeypatch):
    def raise_recursion_error(*args, **kwargs):
        raise RecursionError

    monkeypatch.setattr(json, "loads", raise_recursion_error)
    with pytest.raises(ValueError):
        load_json_input('{"a": 1}')


def test_load_json_input_still_rejects_malformed_json_as_value_error():
    with pytest.raises(ValueError):
        load_json_input("{not json")
