"""Regression tests for #13507: deeply nested JSON must raise ValueError, not RecursionError."""

import pytest

from omi_cli.json_input import load_json_input


def test_deeply_nested_json_raises_value_error():
    raw = '{"child":' * 10_000 + "0" + "}" * 10_000
    with pytest.raises(ValueError, match="nested too deeply"):
        load_json_input(raw)


def test_normal_nested_json_still_works():
    assert load_json_input('{"a":{"b":{"c":1}}}')["a"]["b"]["c"] == 1


def test_malformed_json_still_raises_value_error():
    with pytest.raises(ValueError):
        load_json_input('{"unclosed"}')


def test_non_finite_number_still_raises_value_error():
    with pytest.raises(ValueError):
        load_json_input('{"x": Infinity}')
