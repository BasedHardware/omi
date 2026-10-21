from unittest.mock import MagicMock, patch
import pytest

from utils.retrieval.tools.file_tools import search_files_tool, _names_request_field


def test_names_request_field():
    assert _names_request_field('model', None)
    assert _names_request_field('messages[0]', None)
    assert not _names_request_field('messages[0].file.file_id', None)
    assert _names_request_field(None, 'model_not_found')
    assert not _names_request_field('other_param', 'other_code')


def test_empty_or_none_question():
    config = {'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}}
    res_none = search_files_tool.invoke({'question': None}, config=config)
    assert res_none == "Error: Question cannot be empty."

    res_empty = search_files_tool.invoke({'question': '   '}, config=config)
    assert res_empty == "Error: Question cannot be empty."


def test_missing_config_or_session():
    res_no_cfg = search_files_tool.invoke({'question': 'Summary'}, config=None)
    assert res_no_cfg == "Error: Configuration not available"

    res_no_session = search_files_tool.invoke({'question': 'Summary'}, config={'configurable': {'user_id': 'u1'}})
    assert res_no_session == "No active chat session. Files are not available."


@patch('utils.retrieval.tools.file_tools.chat_db')
def test_top_level_config_fallback(mock_chat_db):
    mock_chat_db.get_chat_session_by_id.return_value = None
    res = search_files_tool.invoke({'question': 'Summary'}, config={'user_id': 'u1', 'chat_session_id': 's1'})
    assert res == "Chat session not found."
    mock_chat_db.get_chat_session_by_id.assert_called_with('u1', 's1')


@patch('utils.retrieval.tools.file_tools.chat_db')
def test_session_not_found(mock_chat_db):
    mock_chat_db.get_chat_session_by_id.return_value = None
    res = search_files_tool.invoke({'question': 'Summary'}, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})
    assert res == "Chat session not found."


@patch('utils.retrieval.tools.file_tools.chat_db')
def test_no_files_uploaded_to_session(mock_chat_db):
    mock_chat_db.get_chat_session_by_id.return_value = {'file_ids': []}
    res = search_files_tool.invoke({'question': 'Summary'}, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})
    assert "No files have been uploaded to this chat session yet" in res


@patch('utils.retrieval.tools.file_tools.FileChatTool')
@patch('utils.retrieval.tools.file_tools.chat_db')
def test_search_specified_file_found(mock_chat_db, mock_fc_cls):
    mock_chat_db.get_chat_session_by_id.return_value = {'file_ids': ['f1', 'f2']}
    mock_fc_instance = MagicMock()
    mock_fc_instance.process_chat_with_file.return_value = "File summary content"
    mock_fc_cls.return_value = mock_fc_instance

    res = search_files_tool.invoke({
        'question': 'What is in f1?',
        'file_ids': ['f1'],
    }, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})

    assert res == "File summary content"
    mock_fc_instance.process_chat_with_file.assert_called_with('What is in f1?', ['f1'], None)


@patch('utils.retrieval.tools.file_tools.FileChatTool')
@patch('utils.retrieval.tools.file_tools.chat_db')
def test_search_single_string_file_id_coercion(mock_chat_db, mock_fc_cls):
    mock_chat_db.get_chat_session_by_id.return_value = {'file_ids': ['f1', 'f2']}
    mock_fc_instance = MagicMock()
    mock_fc_instance.process_chat_with_file.return_value = "Single file content"
    mock_fc_cls.return_value = mock_fc_instance

    res = search_files_tool.invoke({
        'question': 'What is in f2?',
        'file_ids': 'f2',
    }, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})

    assert res == "Single file content"
    mock_fc_instance.process_chat_with_file.assert_called_with('What is in f2?', ['f2'], None)


@patch('utils.retrieval.tools.file_tools.chat_db')
def test_search_file_not_in_session(mock_chat_db):
    mock_chat_db.get_chat_session_by_id.return_value = {'file_ids': ['f1']}
    res = search_files_tool.invoke({
        'question': 'What is in f999?',
        'file_ids': ['f999'],
    }, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})

    assert res == "The specified files are not available in this chat session."


@patch('utils.retrieval.tools.file_tools.FileChatTool')
@patch('utils.retrieval.tools.file_tools.chat_db')
def test_video_window_seconds_safe_coercion(mock_chat_db, mock_fc_cls):
    mock_chat_db.get_chat_session_by_id.return_value = {'file_ids': ['v1']}
    mock_fc_instance = MagicMock()
    mock_fc_instance.process_chat_with_file.return_value = "Video frame content"
    mock_fc_cls.return_value = mock_fc_instance

    res = search_files_tool.invoke({
        'question': 'What happened at 10s?',
        'start_seconds': "10.5",
        'end_seconds': "15.5",
    }, config={'configurable': {'user_id': 'u1', 'chat_session_id': 's1'}})

    assert res == "Video frame content"
    mock_fc_instance.process_chat_with_file.assert_called_with('What happened at 10s?', ['v1'], (10.5, 15.5))
