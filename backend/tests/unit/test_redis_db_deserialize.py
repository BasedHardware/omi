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
