"""Unit tests for chat_sessions router validation, LLM content extraction, and error boundaries."""

import importlib.util
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


def _install_package(name: str, path: Path) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


def _install_module(name: str, module=None):
    module = module or MagicMock()
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


@contextmanager
def _noop_track_usage(*_args, **_kwargs):
    yield


@pytest.fixture
def router_env():
    saved = {k: v for k, v in sys.modules.items()}
    try:
        _install_package('database', BACKEND_DIR / 'database')
        _install_package('utils', BACKEND_DIR / 'utils')
        _install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
        _install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')

        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        sample_session = {
            'id': 'sess-1',
            'title': 'New Chat',
            'preview': None,
            'created_at': now,
            'updated_at': now,
            'app_id': None,
            'plugin_id': None,
            'message_count': 0,
            'starred': False,
        }

        chat_db = _install_module('database.chat')
        chat_db.ClientMessageIdPayloadConflict = type('ClientMessageIdPayloadConflict', (ValueError,), {})
        chat_db.MessageReconcileCursorError = type('MessageReconcileCursorError', (ValueError,), {})
        chat_db.create_chat_session = MagicMock(return_value=sample_session)
        chat_db.get_chat_sessions = MagicMock(return_value=[sample_session])
        chat_db.get_chat_session_by_id = MagicMock(return_value=sample_session)
        chat_db.update_chat_session = MagicMock(return_value=sample_session)
        chat_db.delete_chat_session = MagicMock(return_value=None)
        chat_db.save_message = MagicMock(
            return_value={'id': 'msg-1', 'created_at': '2026-10-19T12:00:00+00:00', 'created': True}
        )
        chat_db.get_messages = MagicMock(return_value=[])
        chat_db.get_messages_reconcile_page = MagicMock(return_value=([], None, False))
        chat_db.delete_messages = MagicMock(return_value=3)
        chat_db.update_message_rating = MagicMock(return_value={'id': 'msg-1', 'plugin_id': 'app-1'})
        chat_db.get_message_count = MagicMock(return_value=42)

        llm_usage_db = _install_module('database.llm_usage')
        llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)
        users_db = _install_module('database.users')
        users_db.set_chat_message_rating_score = MagicMock()

        feedback_utils = _install_module('utils.feedback', ModuleType('utils.feedback'))
        feedback_utils.record_chat_message_feedback = MagicMock()

        product_metrics = _install_module('utils.product_metrics', ModuleType('utils.product_metrics'))
        product_metrics.extract_app_build = MagicMock(return_value='unknown')
        product_metrics.record_product_event = MagicMock()

        generated_compute = _install_module('utils.generated_compute', ModuleType('utils.generated_compute'))
        generated_compute.require_generated_compute = MagicMock()

        chat_utils = _install_module('utils.chat', ModuleType('utils.chat'))
        chat_utils.initial_message_util = MagicMock(return_value=SimpleNamespace(text='Hello!', id='msg-init'))

        llm_clients = _install_module('utils.llm.clients', ModuleType('utils.llm.clients'))
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = SimpleNamespace(content='Project Kickoff')
        llm_clients.get_llm = MagicMock(return_value=mock_llm)

        usage_tracker = _install_module('utils.llm.usage_tracker', ModuleType('utils.llm.usage_tracker'))
        usage_tracker.Features = SimpleNamespace(CHAT='chat')
        usage_tracker.track_usage = _noop_track_usage

        auth = _install_module('utils.other.endpoints', ModuleType('utils.other.endpoints'))
        auth.get_current_user_uid = lambda: 'test-uid'
        auth.with_rate_limit = lambda func, _policy: func

        sys.modules.pop('routers.chat_sessions', None)
        spec = importlib.util.spec_from_file_location(
            'routers.chat_sessions', BACKEND_DIR / 'routers' / 'chat_sessions.py'
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules['routers.chat_sessions'] = module
        spec.loader.exec_module(module)

        app = FastAPI()
        app.include_router(module.router)
        yield TestClient(app), module, mock_llm
    finally:
        for name in [k for k in sys.modules if k not in saved]:
            del sys.modules[name]
        for name, mod in saved.items():
            sys.modules[name] = mod


@pytest.mark.parametrize('bad_id', ['', '   ', '.', '..', ' . ', 'a/b', '__reserved__', 'x' * 1501])
def test_require_doc_id_rejects_invalid_identifiers(router_env, bad_id):
    _, module, _ = router_env
    with pytest.raises(HTTPException) as exc_info:
        module._require_doc_id(bad_id, 'session_id')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Valid session_id is required'


def test_optional_doc_id_normalizes_blank_and_rejects_invalid(router_env):
    _, module, _ = router_env
    assert module._optional_doc_id(None, 'app_id') is None
    assert module._optional_doc_id('   ', 'app_id') is None
    assert module._optional_doc_id('  app-123  ', 'app_id') == 'app-123'
    with pytest.raises(HTTPException) as exc_info:
        module._optional_doc_id('../bad', 'app_id')
    assert exc_info.value.status_code == 400


def test_extract_llm_text_handles_string_list_blocks_and_none(router_env):
    _, module, _ = router_env
    assert module._extract_llm_text('Plain Title') == 'Plain Title'
    assert module._extract_llm_text(['Part 1', {'type': 'text', 'text': 'Part 2'}, 123]) == 'Part 1 Part 2'
    assert module._extract_llm_text(None) == ''
    assert module._extract_llm_text(42) == ''


def test_create_chat_session_normalizes_blank_title_and_app_id(router_env):
    client, module, _ = router_env
    res = client.post('/v2/chat-sessions', json={'title': '   ', 'app_id': '  app-1  '})
    assert res.status_code == 200
    module.chat_db.create_chat_session.assert_called_once_with('test-uid', title=None, app_id='app-1')


def test_create_chat_session_rejects_invalid_app_id(router_env):
    client, module, _ = router_env
    res = client.post('/v2/chat-sessions', json={'title': 'Hello', 'app_id': 'bad/app'})
    assert res.status_code == 400
    module.chat_db.create_chat_session.assert_not_called()


def test_update_chat_session_rejects_empty_update_or_blank_title(router_env):
    client, module, _ = router_env
    res_empty = client.patch('/v2/chat-sessions/sess-1', json={})
    assert res_empty.status_code == 400
    assert 'At least one of title or starred is required' in res_empty.json()['detail']

    res_blank = client.patch('/v2/chat-sessions/sess-1', json={'title': '   '})
    assert res_blank.status_code == 400
    assert 'title cannot be empty' in res_blank.json()['detail']
    module.chat_db.update_chat_session.assert_not_called()


def test_get_update_delete_session_reject_whitespace_path_id(router_env):
    client, _, _ = router_env
    assert client.get('/v2/chat-sessions/%20%20').status_code == 400
    assert client.patch('/v2/chat-sessions/%20%20', json={'starred': True}).status_code == 400
    assert client.delete('/v2/chat-sessions/%20%20').status_code == 400


def test_save_message_rejects_whitespace_only_text_without_content_blocks(router_env):
    client, module, _ = router_env
    res = client.post('/v2/desktop/messages', json={'text': '   ', 'sender': 'human'})
    assert res.status_code == 400
    assert 'text cannot be empty' in res.json()['detail']
    module.chat_db.save_message.assert_not_called()


def test_save_message_rejects_invalid_session_id_or_app_id(router_env):
    client, module, _ = router_env
    res = client.post(
        '/v2/desktop/messages',
        json={'text': 'hello', 'sender': 'human', 'session_id': 'bad/session'},
    )
    assert res.status_code == 400
    module.chat_db.save_message.assert_not_called()


def test_reconcile_messages_rejects_blank_or_invalid_cursor(router_env):
    client, module, _ = router_env
    res_blank = client.get('/v2/desktop/messages/reconcile?cursor=%20%20')
    assert res_blank.status_code == 400
    res_slash = client.get('/v2/desktop/messages/reconcile?cursor=bad/cursor')
    assert res_slash.status_code == 400
    module.chat_db.get_messages_reconcile_page.assert_not_called()


def test_rate_message_tolerates_analytics_side_effect_failure(router_env):
    client, module, _ = router_env
    module.set_chat_message_rating_score.side_effect = RuntimeError('analytics outage')
    res = client.patch('/v2/desktop/messages/msg-1/rating', json={'rating': 1})
    assert res.status_code == 200
    assert res.json() == {'status': 'ok'}


def test_generate_session_title_handles_list_and_none_llm_content(router_env):
    client, module, mock_llm = router_env
    mock_llm.invoke.return_value = SimpleNamespace(content=[{'type': 'text', 'text': '  "Sprint Planning"  '}])

    res = client.post(
        '/v2/chat/generate-title',
        json={'session_id': '  sess-1  ', 'messages': [{'sender': 'human', 'text': 'Let us plan the sprint'}]},
    )
    assert res.status_code == 200
    assert res.json() == {'title': 'Sprint Planning'}
    module.chat_db.update_chat_session.assert_called_once_with('test-uid', 'sess-1', title='Sprint Planning')

    # None content falls back to 'New Chat' without AttributeError
    mock_llm.invoke.return_value = SimpleNamespace(content=None)
    res_none = client.post(
        '/v2/chat/generate-title',
        json={'session_id': 'sess-1', 'messages': [{'sender': 'human', 'text': 'hi'}]},
    )
    assert res_none.status_code == 200
    assert res_none.json() == {'title': 'New Chat'}


def test_generate_session_title_and_initial_message_reject_invalid_session_id(router_env):
    client, _, _ = router_env
    res_init = client.post('/v2/chat/initial-message', json={'session_id': '   '})
    assert res_init.status_code == 400

    res_title = client.post(
        '/v2/chat/generate-title',
        json={'session_id': 'bad/id', 'messages': [{'sender': 'human', 'text': 'hi'}]},
    )
    assert res_title.status_code == 400


def test_endpoints_return_sanitized_500_on_store_or_llm_failures(router_env):
    client, module, mock_llm = router_env
    err = RuntimeError('Firestore token=secret_xyz failed')

    module.chat_db.create_chat_session.side_effect = err
    assert client.post('/v2/chat-sessions', json={'title': 'T'}).status_code == 500

    module.chat_db.get_chat_sessions.side_effect = err
    assert client.get('/v2/chat-sessions').status_code == 500

    module.chat_db.get_chat_session_by_id.side_effect = err
    assert client.get('/v2/chat-sessions/sess-1').status_code == 500

    module.chat_db.update_chat_session.side_effect = err
    assert client.patch('/v2/chat-sessions/sess-1', json={'starred': True}).status_code == 500

    module.chat_db.delete_chat_session.side_effect = err
    assert client.delete('/v2/chat-sessions/sess-1').status_code == 500

    module.chat_db.save_message.side_effect = err
    assert client.post('/v2/desktop/messages', json={'text': 'hi', 'sender': 'human'}).status_code == 500

    module.chat_db.get_messages.side_effect = err
    assert client.get('/v2/desktop/messages').status_code == 500

    module.chat_db.get_messages_reconcile_page.side_effect = err
    assert client.get('/v2/desktop/messages/reconcile').status_code == 500

    module.chat_db.delete_messages.side_effect = err
    assert client.delete('/v2/desktop/messages').status_code == 500

    module.chat_db.update_message_rating.side_effect = err
    assert client.patch('/v2/desktop/messages/msg-1/rating', json={'rating': 1}).status_code == 500

    module.initial_message_util.side_effect = err
    assert client.post('/v2/chat/initial-message', json={'session_id': 'sess-1'}).status_code == 500

    mock_llm.invoke.side_effect = err
    assert (
        client.post(
            '/v2/chat/generate-title',
            json={'session_id': 'sess-1', 'messages': [{'sender': 'human', 'text': 'hi'}]},
        ).status_code
        == 500
    )

    module.chat_db.get_message_count.side_effect = err
    assert client.get('/v1/users/stats/chat-messages').status_code == 500
