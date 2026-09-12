"""Deeply nested JSON must raise ValueError, not RecursionError (#13507)."""

from __future__ import annotations

import json

import pytest

from omi_cli.json_input import load_json_input


def test_load_json_input_maps_recursion_error_to_value_error():
    raw = '{"a":' * 20000 + "1" + "}" * 20000
    with pytest.raises(ValueError) as exc:
        load_json_input(raw)
    assert "nesting" in str(exc.value).lower() or "recursion" in str(exc.value).lower()


def test_load_json_input_still_rejects_malformed_json_as_value_error():
    with pytest.raises(ValueError):
        load_json_input("{not json")
