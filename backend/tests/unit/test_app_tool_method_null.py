"""Regression test: a manifest tool with method=null must not crash validation.

utils.apps._validate_tool_definition normalizes an app-manifest tool. It guarded name /
description / endpoint against non-string values but built
`'method': typed_tool.get('method', 'POST').upper()`. dict.get's default applies only to
ABSENT keys, so a present-but-null method (`"method": null`) made get return None and
None.upper() raised AttributeError, aborting manifest tool validation. method now falls back
to 'POST' for a null or empty value.
"""

from utils.apps import _validate_tool_definition


def _tool(**overrides):
    t = {'name': 't', 'description': 'd', 'endpoint': 'https://e'}
    t.update(overrides)
    return t


def test_null_method_defaults_to_post():
    result = _validate_tool_definition(_tool(method=None))
    assert result is not None
    assert result['method'] == 'POST'


def test_absent_method_defaults_to_post():
    result = _validate_tool_definition(_tool())
    assert result is not None
    assert result['method'] == 'POST'


def test_string_method_is_uppercased():
    result = _validate_tool_definition(_tool(method='get'))
    assert result is not None
    assert result['method'] == 'GET'
