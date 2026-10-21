from unittest.mock import MagicMock, patch
import pytest

from utils.retrieval.tools.edit_tools import (
    _extract_configurable,
    owner,
    update_conversation,
    rename_person,
    edit_memory,
    delete_memory,
)


def test_extract_configurable():
    assert _extract_configurable(None) == {}
    assert _extract_configurable({}) == {}
    assert _extract_configurable({'configurable': None}) == {}
    assert _extract_configurable({'configurable': {'user_id': 'u1'}}) == {'user_id': 'u1'}
    assert _extract_configurable({'configurable': 'not-a-dict'}) == {}


def test_owner_none_config():
    with pytest.raises(PermissionError, match="Authenticated owner required"):
        owner(None)


def test_owner_none_configurable():
    with pytest.raises(PermissionError, match="Authenticated owner required"):
        owner({'configurable': None})


def test_owner_top_level_user_id():
    assert owner({'user_id': 'user_direct'}) == 'user_direct'


def test_owner_nested_user_id():
    assert owner({'configurable': {'user_id': 'user_nested'}}) == 'user_nested'


def test_update_conversation_none_or_empty_correction():
    config = {'configurable': {'user_id': 'test_user'}}
    with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
        res = update_conversation.invoke({
            'conversation_id': 'conv_1',
            'correction': None,
            'title': 'New Title',
        }, config=config)
        assert 'invalid_correction' in str(res) or 'Provide a confirmed correction' in str(res)

        res_empty = update_conversation.invoke({
            'conversation_id': 'conv_1',
            'correction': '   ',
            'title': 'New Title',
        }, config=config)
        assert 'invalid_correction' in str(res_empty) or 'Provide a confirmed correction' in str(res_empty)


def test_update_conversation_invalid_title():
    config = {'configurable': {'user_id': 'test_user'}}
    with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
        res = update_conversation.invoke({
            'conversation_id': 'conv_1',
            'correction': 'Fix title',
            'title': '   ',
        }, config=config)
        assert 'invalid_title' in str(res) or 'Title must contain' in str(res)


def test_update_conversation_invalid_overview():
    config = {'configurable': {'user_id': 'test_user'}}
    with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('conv_1', None)):
        res = update_conversation.invoke({
            'conversation_id': 'conv_1',
            'correction': 'Fix overview',
            'overview': '   ',
        }, config=config)
        assert 'invalid_overview' in str(res) or 'Overview must contain' in str(res)


def test_rename_person_invalid_name():
    config = {'configurable': {'user_id': 'test_user'}}
    with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('person_1', None)):
        res_none = rename_person.invoke({
            'person_id': 'person_1',
            'name': None,
        }, config=config)
        assert 'person name must be a non-empty string' in res_none

        res_empty = rename_person.invoke({
            'person_id': 'person_1',
            'name': '   ',
        }, config=config)
        assert 'person name must be a non-empty string' in res_empty


def test_edit_memory_invalid_content():
    config = {'configurable': {'user_id': 'test_user'}}
    with patch('utils.retrieval.tools.edit_tools.resolve_edit_ref', return_value=('mem_1', None)):
        res_none = edit_memory.invoke({
            'memory_id': 'mem_1',
            'content': None,
        }, config=config)
        assert 'memory content must contain 1 to 20000 characters' in res_none

        res_empty = edit_memory.invoke({
            'memory_id': 'mem_1',
            'content': '   ',
        }, config=config)
        assert 'memory content must contain 1 to 20000 characters' in res_empty
