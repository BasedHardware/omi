from unittest.mock import MagicMock, patch
import pytest

from utils.retrieval.tools.preference_tools import (
    _get_uid,
    _write_provenance,
    save_user_preference_tool,
    preference_duplicate_message,
)


def test_get_uid_top_level():
    assert _get_uid({'user_id': 'u_top'}) == 'u_top'


def test_get_uid_nested():
    assert _get_uid({'configurable': {'user_id': 'u_nested'}}) == 'u_nested'


def test_get_uid_empty_or_none():
    assert _get_uid(None) == ''
    assert _get_uid({}) == ''
    assert _get_uid({'configurable': None}) == ''


def test_write_provenance_safe_none_preference():
    prov = _write_provenance('u1', None, {'configurable': {'user_id': 'u1'}})
    assert prov is not None


def test_save_user_preference_empty_or_none():
    config = {'configurable': {'user_id': 'u1'}}
    res_none = save_user_preference_tool.invoke({'preference': None}, config=config)
    assert res_none == "Error: Preference content cannot be empty"

    res_empty = save_user_preference_tool.invoke({'preference': '   '}, config=config)
    assert res_empty == "Error: Preference content cannot be empty"


def test_save_user_preference_none_replace_memory_id():
    config = {'configurable': {'user_id': 'u1'}}
    with patch('utils.retrieval.tools.preference_tools.get_data_plane_firestore_client'),          patch('utils.retrieval.tools.preference_tools.search_canonical_memories', return_value=[]),          patch('utils.retrieval.tools.preference_tools.ensure_canonical_apply_control_state') as mock_ctrl,          patch('utils.retrieval.tools.preference_tools._save_compatibility_preference', return_value='mem_123'),          patch('utils.retrieval.tools.preference_tools.record_write', return_value=''):
        mock_ctrl.return_value.writer_mode = 'compatibility'
        res = save_user_preference_tool.invoke({
            'preference': 'Likes dark chocolate',
            'replace_memory_id': None,
        }, config=config)
        assert "Preference saved (memory_id=mem_123)" in res


def test_save_user_preference_whitespace_replace_memory_id():
    config = {'configurable': {'user_id': 'u1'}}
    with patch('utils.retrieval.tools.preference_tools.get_data_plane_firestore_client'),          patch('utils.retrieval.tools.preference_tools.search_canonical_memories', return_value=[]),          patch('utils.retrieval.tools.preference_tools.ensure_canonical_apply_control_state') as mock_ctrl,          patch('utils.retrieval.tools.preference_tools._save_compatibility_preference', return_value='mem_456'),          patch('utils.retrieval.tools.preference_tools.record_write', return_value=''):
        mock_ctrl.return_value.writer_mode = 'compatibility'
        res = save_user_preference_tool.invoke({
            'preference': 'Likes white chocolate',
            'replace_memory_id': '   ',
        }, config=config)
        assert "Preference saved (memory_id=mem_456)" in res


def test_save_user_preference_missing_user_id():
    res = save_user_preference_tool.invoke({'preference': 'Likes coffee'}, config={})
    assert res == "Error: Could not determine user ID"
