"""Router tests for desktop message persistence quota accounting."""

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
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


def _make_client():
    saved = {k: v for k, v in sys.modules.items()}

    _install_package('database', BACKEND_DIR / 'database')
    _install_package('utils', BACKEND_DIR / 'utils')
    _install_package('utils.other', BACKEND_DIR / 'utils' / 'other')
    _install_package('utils.llm', BACKEND_DIR / 'utils' / 'llm')

    chat_db = _install_module('database.chat')
    chat_db.save_message = MagicMock(
        return_value={'id': 'client-msg-1', 'created_at': '2026-07-02T00:00:00+00:00', 'created': True}
    )
    chat_db.get_messages = MagicMock(return_value=[])
    chat_db.delete_messages = MagicMock(return_value=0)
    chat_db.create_chat_session = MagicMock()
    chat_db.get_chat_sessions = MagicMock()
    chat_db.get_chat_session_by_id = MagicMock()
    chat_db.update_chat_session = MagicMock()
    chat_db.delete_chat_session = MagicMock()
    chat_db.update_message_rating = MagicMock()
    chat_db.get_message_count = MagicMock(return_value=0)

    llm_usage_db = _install_module('database.llm_usage')
    llm_usage_db.record_chat_quota_question = MagicMock(return_value=True)
    users_db = _install_module('database.users')
    users_db.set_chat_message_rating_score = MagicMock()

    chat_utils = _install_module('utils.chat', ModuleType('utils.chat'))
    chat_utils.initial_message_util = MagicMock()
    llm_clients = _install_module('utils.llm.clients', ModuleType('utils.llm.clients'))
    llm_clients.get_llm = MagicMock()

    auth = _install_module('utils.other.endpoints', ModuleType('utils.other.endpoints'))
    auth.get_current_user_uid = lambda: 'test-uid'
    auth.with_rate_limit = lambda func, _policy: func

    sys.modules.pop('routers.chat_sessions', None)
    spec = importlib.util.spec_from_file_location('routers.chat_sessions', BACKEND_DIR / 'routers' / 'chat_sessions.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['routers.chat_sessions'] = module
    spec.loader.exec_module(module)

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), module, saved


def _cleanup(saved):
    for name in [k for k in sys.modules if k not in saved]:
        del sys.modules[name]
    for name, module in saved.items():
        sys.modules[name] = module


def test_desktop_human_message_records_quota_once_after_persistence_acceptance():
    client, module, saved = _make_client()
    try:
        response = client.post(
            '/v2/desktop/messages',
            json={'text': 'hello', 'sender': 'human', 'client_message_id': 'client-msg-1'},
            headers={'X-App-Platform': 'macos'},
        )

        assert response.status_code == 200
        module.chat_db.save_message.assert_called_once_with(
            'test-uid',
            text='hello',
            sender='human',
            app_id=None,
            session_id=None,
            metadata=None,
            client_message_id='client-msg-1',
            message_source='desktop_chat',
        )
        module.llm_usage_db.record_chat_quota_question.assert_called_once_with(
            'test-uid',
            idempotency_key='desktop_messages:client-msg-1',
            source='desktop_messages',
            message_id='client-msg-1',
            chat_session_id=None,
            platform='macos',
        )
    finally:
        _cleanup(saved)


def test_desktop_duplicate_human_message_retries_idempotent_quota_record():
    client, module, saved = _make_client()
    try:
        module.chat_db.save_message.return_value = {
            'id': 'client-msg-1',
            'created_at': '2026-07-02T00:00:00+00:00',
            'created': False,
        }
        duplicate = client.post(
            '/v2/desktop/messages',
            json={'text': 'hello', 'sender': 'human', 'client_message_id': 'client-msg-1'},
        )
        assert duplicate.status_code == 200
        module.chat_db.save_message.assert_called_once_with(
            'test-uid',
            text='hello',
            sender='human',
            app_id=None,
            session_id=None,
            metadata=None,
            client_message_id='client-msg-1',
            message_source='desktop_chat',
        )
        module.llm_usage_db.record_chat_quota_question.assert_called_once_with(
            'test-uid',
            idempotency_key='desktop_messages:client-msg-1',
            source='desktop_messages',
            message_id='client-msg-1',
            chat_session_id=None,
            platform=None,
        )
    finally:
        _cleanup(saved)


def test_desktop_ai_message_does_not_record_quota():
    client, module, saved = _make_client()
    try:
        module.chat_db.save_message.return_value = {
            'id': 'ai-msg-1',
            'created_at': '2026-07-02T00:00:00+00:00',
            'created': True,
        }
        ai = client.post(
            '/v2/desktop/messages',
            json={'text': 'hello back', 'sender': 'ai', 'client_message_id': 'ai-msg-1'},
        )
        assert ai.status_code == 200
        module.llm_usage_db.record_chat_quota_question.assert_not_called()
    finally:
        _cleanup(saved)


def test_realtime_voice_human_message_does_not_record_desktop_message_quota():
    client, module, saved = _make_client()
    try:
        module.chat_db.save_message.return_value = {
            'id': 'voice-msg-1',
            'created_at': '2026-07-02T00:00:00+00:00',
            'created': True,
        }
        response = client.post(
            '/v2/desktop/messages',
            json={
                'text': 'voice transcript',
                'sender': 'human',
                'client_message_id': 'voice-msg-1',
                'message_source': 'realtime_voice',
            },
        )
        assert response.status_code == 200
        module.chat_db.save_message.assert_called_once_with(
            'test-uid',
            text='voice transcript',
            sender='human',
            app_id=None,
            session_id=None,
            metadata=None,
            client_message_id='voice-msg-1',
            message_source='realtime_voice',
        )
        module.llm_usage_db.record_chat_quota_question.assert_not_called()
    finally:
        _cleanup(saved)
