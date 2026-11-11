import pytest
from database.redis_db import _deserialize_cache_value


def test_deserialize_json():
    assert _deserialize_cache_value('{"key": "value"}') == {"key": "value"}
    assert _deserialize_cache_value('["a", "b"]') == ["a", "b"]
    assert _deserialize_cache_value('"hello"') == "hello"


def test_deserialize_legacy_python_literals():
    assert _deserialize_cache_value("{'key': 'value'}") == {"key": "value"}
    assert _deserialize_cache_value("['a', 'b']") == ["a", "b"]
    assert _deserialize_cache_value("{'a': 1, 'b': -2.5, 'c': True, 'd': None}") == {
        'a': 1,
        'b': -2.5,
        'c': True,
        'd': None,
    }


def test_deserialize_malformed():
    assert _deserialize_cache_value("just some text") == "just some text"


def test_deserialize_unsupported_ast():
    # An expression that is valid Python but we don't want to support
    assert _deserialize_cache_value("1 + 2") == "1 + 2"
    assert _deserialize_cache_value("__import__('os').system('ls')") == "__import__('os').system('ls')"


def test_deserialize_rejects_dict_unpacking():
    # Partial parse would silently drop **payload; fail open to the raw string.
    raw = "{'fingerprint': 'x', **payload}"
    assert _deserialize_cache_value(raw) == raw


def test_deserialize_complex_literal_is_raw_string():
    # Complex literals are not in the allowlist; pin the fail-open outcome.
    assert _deserialize_cache_value("-1j") == "-1j"


def test_deserialize_oversized_literal_skips_ast_parse():
    # Must not be valid JSON, or json.loads short-circuits before the AST size cap.
    raw = "[" + ",".join(["'x'"] * 20000) + "]"
    assert len(raw) > 64 * 1024
    assert _deserialize_cache_value(raw) == raw
