"""
Tests for ChatTool.deserialize_parameters tolerance of malformed stored JSON.

A ChatTool's `parameters` is stored as a JSON string in Firestore (to avoid
Firestore nesting limits) and parsed by a pre-validator. A single malformed
stored string must not 500 an app read/list: the validator should drop the
malformed value (parameters -> None) instead of raising JSONDecodeError.
"""

import os

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.app import App, ChatTool


def test_malformed_parameters_json_does_not_raise():
    """A non-JSON parameters string is tolerated and yields parameters=None."""
    tool = ChatTool(name='t', description='d', endpoint='e', parameters='{not json')
    assert tool.parameters is None


def test_valid_parameters_json_still_parsed():
    """A valid JSON parameters string is still deserialized to a dict."""
    tool = ChatTool(
        name='t',
        description='d',
        endpoint='e',
        parameters='{"type": "object", "properties": {}}',
    )
    assert tool.parameters == {"type": "object", "properties": {}}


def test_app_with_malformed_chat_tool_parameters_succeeds():
    """Building an App whose chat_tool has malformed parameters does not 500."""
    app_dict = {
        'id': 'app-1',
        'name': 'My App',
        'category': 'productivity',
        'author': 'tester',
        'description': 'an app',
        'image': '/image.png',
        'capabilities': ['chat'],
        'chat_tools': [
            {
                'name': 't',
                'description': 'd',
                'endpoint': 'e',
                'parameters': '{not json',
            }
        ],
    }
    app = App(**app_dict)
    assert app.chat_tools[0].parameters is None
