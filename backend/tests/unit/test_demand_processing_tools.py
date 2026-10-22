"""Hermetic unit tests for demand_processing_tools."""

import json
from unittest.mock import Mock, patch
import pytest

from utils.retrieval.tools.demand_processing_tools import (
    process_recent_conversations,
    _coerce_int,
    _get_uid,
    agent_config_context,
)


def test_coerce_int():
    # Valid ints
    assert _coerce_int(5, default=6, min_val=1, max_val=6) == 5
    assert _coerce_int(1, default=6, min_val=1, max_val=6) == 1
    assert _coerce_int(6, default=6, min_val=1, max_val=6) == 6

    # Clamping
    assert _coerce_int(10, default=6, min_val=1, max_val=6) == 6
    assert _coerce_int(0, default=6, min_val=1, max_val=6) == 1
    assert _coerce_int(-5, default=6, min_val=1, max_val=6) == 1

    # String coercion
    assert _coerce_int("4", default=6, min_val=1, max_val=6) == 4
    assert _coerce_int("10", default=6, min_val=1, max_val=6) == 6
    assert _coerce_int("-1", default=6, min_val=1, max_val=6) == 1

    # Float coercion
    assert _coerce_int(3.0, default=6, min_val=1, max_val=6) == 3
    assert _coerce_int(4.8, default=6, min_val=1, max_val=6) == 4

    # Invalid fallbacks
    assert _coerce_int("invalid", default=6, min_val=1, max_val=6) == 6
    assert _coerce_int(None, default=6, min_val=1, max_val=6) == 6
    assert _coerce_int([], default=6, min_val=1, max_val=6) == 6


def test_get_uid_safe_extraction():
    # Direct configurable dict
    assert _get_uid({'configurable': {'user_id': 'user_123'}}) == 'user_123'
    assert _get_uid({'configurable': {'user_id': '  user_123  '}}) == 'user_123'

    # Configurable is None
    assert _get_uid({'configurable': None}) == ''

    # Config is None or empty
    assert _get_uid(None) == ''
    assert _get_uid({}) == ''

    # Non-dict config
    assert _get_uid("invalid") == ''

    # Fallback to agent_config_context
    token = agent_config_context.set({'configurable': {'user_id': 'context_user'}})
    try:
        assert _get_uid(None) == 'context_user'
        assert _get_uid({}) == 'context_user'
        # Explicit config takes priority over context
        assert _get_uid({'configurable': {'user_id': 'explicit_user'}}) == 'explicit_user'
    finally:
        agent_config_context.reset(token)


def test_tool_signature_and_args():
    assert process_recent_conversations.name == "process_recent_conversations"
    assert set(process_recent_conversations.args) == {'hours', 'limit'}


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_default_arguments(mock_process_recent):
    mock_process_recent.return_value = {'ready': True, 'status': 'completed', 'promoted': 5}
    config = {'configurable': {'user_id': 'owner_1'}}

    res = process_recent_conversations.invoke({}, config=config)
    data = json.loads(res)

    assert data['ready'] is True
    assert data['status'] == 'completed'
    mock_process_recent.assert_called_once_with('owner_1', hours=6, limit=20)


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_custom_integer_arguments(mock_process_recent):
    mock_process_recent.return_value = {'ready': False, 'status': 'pending'}
    config = {'configurable': {'user_id': 'owner_2'}}

    res = process_recent_conversations.invoke({'hours': 3, 'limit': 10}, config=config)
    data = json.loads(res)

    assert data['ready'] is False
    mock_process_recent.assert_called_once_with('owner_2', hours=3, limit=10)


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_string_and_float_coercion(mock_process_recent):
    mock_process_recent.return_value = {'ready': True, 'status': 'completed'}
    config = {'configurable': {'user_id': 'owner_3'}}

    res = process_recent_conversations.invoke({'hours': "4", 'limit': 15.0}, config=config)
    data = json.loads(res)

    assert data['status'] == 'completed'
    mock_process_recent.assert_called_once_with('owner_3', hours=4, limit=15)


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_bounds_clamping(mock_process_recent):
    mock_process_recent.return_value = {'ready': True}
    config = {'configurable': {'user_id': 'owner_4'}}

    # Out of range high
    process_recent_conversations.invoke({'hours': 100, 'limit': 50}, config=config)
    mock_process_recent.assert_called_with('owner_4', hours=6, limit=20)

    # Out of range low
    process_recent_conversations.invoke({'hours': 0, 'limit': -10}, config=config)
    mock_process_recent.assert_called_with('owner_4', hours=1, limit=1)


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_invalid_argument_fallback(mock_process_recent):
    mock_process_recent.return_value = {'ready': True}
    config = {'configurable': {'user_id': 'owner_5'}}

    process_recent_conversations.invoke({'hours': 'invalid_string', 'limit': None}, config=config)
    mock_process_recent.assert_called_with('owner_5', hours=6, limit=20)


def test_tool_requires_authenticated_owner():
    with pytest.raises(PermissionError, match='authenticated owner required'):
        process_recent_conversations.invoke({})

    with pytest.raises(PermissionError, match='authenticated owner required'):
        process_recent_conversations.invoke({}, config={})

    with pytest.raises(PermissionError, match='authenticated owner required'):
        process_recent_conversations.invoke({}, config={'configurable': None})

    with pytest.raises(PermissionError, match='authenticated owner required'):
        process_recent_conversations.invoke({}, config={'configurable': {'user_id': ''}})


@patch("utils.conversations.demand_processing.process_recent")
def test_tool_handles_downstream_exception_gracefully(mock_process_recent):
    mock_process_recent.side_effect = RuntimeError("Redis connection failure")
    config = {'configurable': {'user_id': 'owner_6'}}

    res = process_recent_conversations.invoke({}, config=config)
    data = json.loads(res)

    assert data['ready'] is False
    assert data['status'] == 'failed'
    assert 'unavailable' in data['error'].lower()
