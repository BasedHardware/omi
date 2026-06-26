"""
Unit tests for routers/ai_clone.py (FastAPI endpoint behavior)

Critical contracts:
- POST /generate-reply returns 400 when message is blank / whitespace-only
- POST /generate-reply calls generate_clone_reply with correct args and saves to Firestore
- GET  /settings returns the user's current settings
- PUT  /settings persists the settings dict
- PATCH /messages/{id} updates status and optionally final_reply
- POST /telegram/send-code returns 503 when Telethon not configured (RuntimeError)
- POST /telegram/verify returns 400 on bad OTP code
- GET  /telegram/messages returns empty list on backend error (safe degradation)
- POST /telegram/send returns 503 when no Telegram client
"""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'x' * 64)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test')

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)

# ── Pre-stub all heavy dependencies before importing FastAPI app ────────────────


def _stub(name, attrs=None):
    mod = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


for heavy in [
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'pinecone',
    'openai',
    'anthropic',
    'posthog',
    'sentry_sdk',
    'langchain',
    'langchain_core',
    'langchain_openai',
    'langchain_community',
    'langchain.schema',
    'langchain_core.messages',
    'redis',
]:
    if heavy not in sys.modules:
        sys.modules[heavy] = types.ModuleType(heavy)

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].verify_id_token = MagicMock(return_value={'uid': 'uid-test'})

_firestore_client = MagicMock()
sys.modules['google.cloud.firestore'].Client = MagicMock(return_value=_firestore_client)
sys.modules['google.cloud.firestore'].FieldFilter = MagicMock()
sys.modules['google.cloud.firestore'].Query = MagicMock()
sys.modules['google.cloud.firestore'].SERVER_TIMESTAMP = object()
sys.modules['google.cloud.firestore'].DELETE_FIELD = object()

# Stub database._client so imports don't hit real Firestore
_db_client_stub = types.ModuleType('database._client')
_db_client_stub.db = _firestore_client
_db_client_stub.document_id_from_seed = MagicMock(return_value='seed-id')
sys.modules['database._client'] = _db_client_stub

# Stub database.ai_clone
_db_ai_clone = types.ModuleType('database.ai_clone')
_db_ai_clone.get_clone_settings = MagicMock(return_value={'enabled': False, 'auto_reply': False, 'platforms': {}})
_db_ai_clone.update_clone_settings = MagicMock()
_db_ai_clone.save_clone_message = MagicMock(return_value='msg-id-123')
_db_ai_clone.get_clone_messages = MagicMock(return_value=[])
_db_ai_clone.update_clone_message = MagicMock()
_db_ai_clone.get_platform_settings = MagicMock(return_value=None)
_db_ai_clone.update_platform_settings = MagicMock()
sys.modules.setdefault('database', types.ModuleType('database'))
sys.modules['database.ai_clone'] = _db_ai_clone

# Stub LLM clone
_clone_stub = types.ModuleType('utils.llm.clone')
_clone_stub.generate_clone_reply = MagicMock(return_value='Mock reply from AI clone')
sys.modules.setdefault('utils', types.ModuleType('utils'))
sys.modules.setdefault('utils.llm', types.ModuleType('utils.llm'))
sys.modules['utils.llm.clone'] = _clone_stub

# Stub telegram_client
_tg_stub = types.ModuleType('utils.integrations.telegram_client')
_tg_stub.send_code = AsyncMock(return_value={'phone_code_hash': 'hash-123'})
_tg_stub.verify_code = AsyncMock(return_value={'display_name': 'Alice', 'phone': '+1234'})
_tg_stub.disconnect = AsyncMock()
_tg_stub.poll_new_messages = AsyncMock(return_value=[])
_tg_stub.send_message = AsyncMock(return_value=True)
sys.modules.setdefault('utils.integrations', types.ModuleType('utils.integrations'))
sys.modules['utils.integrations.telegram_client'] = _tg_stub

# Stub executors
_exec_stub = types.ModuleType('utils.executors')
_exec_stub.db_executor = MagicMock()
_exec_stub.llm_executor = MagicMock()


async def _run_blocking(executor, fn, *args):
    return fn(*args)


_exec_stub.run_blocking = _run_blocking
sys.modules['utils.executors'] = _exec_stub

# Stub auth dependency
_auth_stub = types.ModuleType('utils.other.endpoints')
_auth_stub.get_current_user_uid = lambda: 'uid-test'
sys.modules.setdefault('utils.other', types.ModuleType('utils.other'))
sys.modules['utils.other.endpoints'] = _auth_stub
sys.modules.setdefault('utils.other.endpoints', _auth_stub)

# Now import the router
sys.modules.pop('routers.ai_clone', None)
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    'routers.ai_clone',
    os.path.join(BACKEND_DIR, 'routers', 'ai_clone.py'),
)
_router_mod = _ilu.module_from_spec(_spec)
sys.modules['routers.ai_clone'] = _router_mod
_spec.loader.exec_module(_router_mod)

# Patch module-level references directly so sys.modules contamination from
# other test files (e.g. test_ai_clone_database.py importing the real module)
# cannot stale-bind the router to the wrong objects.
_router_mod.clone_db = _db_ai_clone
_router_mod.generate_clone_reply = _clone_stub.generate_clone_reply
_router_mod.run_blocking = _run_blocking
_router_mod.db_executor = _exec_stub.db_executor
_router_mod.llm_executor = _exec_stub.llm_executor
_router_mod.tg = _tg_stub

from fastapi import FastAPI
from fastapi.testclient import TestClient

_app = FastAPI()
_app.include_router(_router_mod.router)

# Override auth dependency to return test uid
from fastapi import Depends

_app.dependency_overrides[_auth_stub.get_current_user_uid] = lambda: 'uid-test'

client = TestClient(_app)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _reset_mocks():
    _db_ai_clone.get_clone_settings.reset_mock()
    _db_ai_clone.update_clone_settings.reset_mock()
    _db_ai_clone.save_clone_message.reset_mock()
    _db_ai_clone.save_clone_message.return_value = 'msg-id-123'
    _db_ai_clone.get_clone_messages.reset_mock()
    _db_ai_clone.update_clone_message.reset_mock()
    _clone_stub.generate_clone_reply.reset_mock()
    _clone_stub.generate_clone_reply.return_value = 'Mock reply from AI clone'
    _tg_stub.send_code.reset_mock()
    _tg_stub.verify_code.reset_mock()


# ── POST /v1/ai-clone/generate-reply ─────────────────────────────────────────


class TestGenerateReplyEndpoint:
    def test_returns_400_for_blank_message(self):
        _reset_mocks()
        r = client.post('/v1/ai-clone/generate-reply', json={'platform': 'telegram', 'sender': 'Bob', 'message': '   '})
        assert r.status_code == 400
        assert 'empty' in r.json()['detail'].lower()

    def test_returns_400_for_empty_message(self):
        _reset_mocks()
        r = client.post('/v1/ai-clone/generate-reply', json={'platform': 'telegram', 'sender': 'Bob', 'message': ''})
        assert r.status_code == 400

    def test_successful_reply_returns_message_id_and_reply(self):
        _reset_mocks()
        r = client.post(
            '/v1/ai-clone/generate-reply',
            json={'platform': 'imessage', 'sender': 'Alice', 'message': 'Hey, how are you?'},
        )
        assert r.status_code == 200
        data = r.json()
        assert 'reply' in data
        assert 'message_id' in data
        assert data['reply'] == 'Mock reply from AI clone'
        assert data['message_id'] == 'msg-id-123'

    def test_calls_generate_clone_reply_with_correct_args(self):
        _reset_mocks()
        client.post(
            '/v1/ai-clone/generate-reply',
            json={'platform': 'telegram', 'sender': 'Charlie', 'message': 'What are you up to?'},
        )
        _clone_stub.generate_clone_reply.assert_called_once_with(
            'uid-test', 'Charlie', 'What are you up to?', 'telegram', None
        )

    def test_saves_message_to_database(self):
        _reset_mocks()
        client.post(
            '/v1/ai-clone/generate-reply',
            json={'platform': 'imessage', 'sender': 'Dave', 'message': 'Lunch?'},
        )
        _db_ai_clone.save_clone_message.assert_called_once()
        saved_doc = _db_ai_clone.save_clone_message.call_args[0][1]
        assert saved_doc['platform'] == 'imessage'
        assert saved_doc['sender'] == 'Dave'
        assert saved_doc['incoming'] == 'Lunch?'
        assert saved_doc['status'] == 'pending'
        assert saved_doc['draft_reply'] == 'Mock reply from AI clone'

    def test_passes_conversation_history_to_llm(self):
        _reset_mocks()
        history = [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'hey'}]
        client.post(
            '/v1/ai-clone/generate-reply',
            json={'platform': 'telegram', 'sender': 'Eve', 'message': 'yo', 'conversation_history': history},
        )
        call_args = _clone_stub.generate_clone_reply.call_args
        assert call_args[0][4] == history


# ── GET /v1/ai-clone/settings ─────────────────────────────────────────────────


class TestGetSettings:
    def test_returns_settings_dict(self):
        _reset_mocks()
        _db_ai_clone.get_clone_settings.return_value = {'enabled': True, 'auto_reply': False, 'platforms': {}}

        r = client.get('/v1/ai-clone/settings')

        assert r.status_code == 200
        assert r.json()['enabled'] is True

    def test_calls_get_clone_settings_with_uid(self):
        _reset_mocks()
        client.get('/v1/ai-clone/settings')
        _db_ai_clone.get_clone_settings.assert_called_with('uid-test')


# ── PUT /v1/ai-clone/settings ─────────────────────────────────────────────────


class TestUpdateSettings:
    def test_returns_ok(self):
        _reset_mocks()
        r = client.put('/v1/ai-clone/settings', json={'enabled': True, 'auto_reply': False, 'platforms': {}})
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_calls_update_clone_settings(self):
        _reset_mocks()
        client.put('/v1/ai-clone/settings', json={'enabled': True, 'auto_reply': True, 'platforms': {}})
        _db_ai_clone.update_clone_settings.assert_called_once()


# ── GET /v1/ai-clone/messages ─────────────────────────────────────────────────


class TestGetMessages:
    def test_returns_list(self):
        _reset_mocks()
        _db_ai_clone.get_clone_messages.return_value = [{'id': 'm1', 'status': 'pending'}]

        r = client.get('/v1/ai-clone/messages')

        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert r.json()[0]['id'] == 'm1'

    def test_respects_limit_param(self):
        _reset_mocks()
        client.get('/v1/ai-clone/messages?limit=5')
        _db_ai_clone.get_clone_messages.assert_called_with('uid-test', 5)


# ── PATCH /v1/ai-clone/messages/{id} ─────────────────────────────────────────


class TestUpdateMessage:
    def test_updates_status(self):
        _reset_mocks()
        r = client.patch('/v1/ai-clone/messages/msg-xyz', json={'status': 'sent'})
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_passes_status_to_database(self):
        _reset_mocks()
        client.patch('/v1/ai-clone/messages/msg-abc', json={'status': 'dismissed'})
        _db_ai_clone.update_clone_message.assert_called_once()
        updates = _db_ai_clone.update_clone_message.call_args[0][2]
        assert updates['status'] == 'dismissed'

    def test_includes_final_reply_when_edited(self):
        _reset_mocks()
        client.patch('/v1/ai-clone/messages/msg-edit', json={'status': 'sent', 'edited_reply': 'Fixed reply'})
        updates = _db_ai_clone.update_clone_message.call_args[0][2]
        assert updates['final_reply'] == 'Fixed reply'

    def test_no_final_reply_when_not_edited(self):
        _reset_mocks()
        client.patch('/v1/ai-clone/messages/msg-no-edit', json={'status': 'sent'})
        updates = _db_ai_clone.update_clone_message.call_args[0][2]
        assert 'final_reply' not in updates


# ── POST /v1/ai-clone/telegram/send-code ─────────────────────────────────────


class TestTelegramSendCode:
    def test_returns_phone_code_hash(self):
        _reset_mocks()
        _tg_stub.send_code.return_value = {'phone_code_hash': 'abc123'}
        r = client.post('/v1/ai-clone/telegram/send-code', json={'phone': '+1234567890'})
        assert r.status_code == 200
        assert r.json()['phone_code_hash'] == 'abc123'

    def test_returns_503_when_api_not_configured(self):
        _reset_mocks()
        _tg_stub.send_code.side_effect = RuntimeError('TELEGRAM_API_ID / TELEGRAM_API_HASH not set')
        r = client.post('/v1/ai-clone/telegram/send-code', json={'phone': '+1234567890'})
        assert r.status_code == 503
        _tg_stub.send_code.side_effect = None

    def test_returns_500_on_unexpected_error(self):
        _reset_mocks()
        _tg_stub.send_code.side_effect = Exception('network down')
        r = client.post('/v1/ai-clone/telegram/send-code', json={'phone': '+1234567890'})
        assert r.status_code == 500
        _tg_stub.send_code.side_effect = None


# ── POST /v1/ai-clone/telegram/verify ────────────────────────────────────────


class TestTelegramVerify:
    def test_returns_display_name_on_success(self):
        _reset_mocks()
        _tg_stub.verify_code.return_value = {'display_name': 'Karthik Y', 'phone': '+1999'}
        r = client.post(
            '/v1/ai-clone/telegram/verify',
            json={'phone': '+1999', 'code': '12345', 'phone_code_hash': 'hash-h'},
        )
        assert r.status_code == 200
        assert r.json()['display_name'] == 'Karthik Y'

    def test_returns_400_on_bad_code(self):
        _reset_mocks()
        _tg_stub.verify_code.side_effect = Exception('PhoneCodeInvalidError')
        r = client.post(
            '/v1/ai-clone/telegram/verify',
            json={'phone': '+1999', 'code': '00000', 'phone_code_hash': 'hash-bad'},
        )
        assert r.status_code == 400
        _tg_stub.verify_code.side_effect = None


# ── GET /v1/ai-clone/telegram/messages ───────────────────────────────────────


class TestTelegramPollMessages:
    def test_returns_messages_list(self):
        _reset_mocks()
        _tg_stub.poll_new_messages.return_value = [
            {'sender': 'Bob', 'sender_id': 1, 'chat_id': 1, 'message': 'hey', 'timestamp': 1700000000.0}
        ]
        r = client.get('/v1/ai-clone/telegram/messages?since=0')
        assert r.status_code == 200
        assert len(r.json()['messages']) == 1

    def test_returns_empty_on_error(self):
        _reset_mocks()
        _tg_stub.poll_new_messages.side_effect = Exception('telethon error')
        r = client.get('/v1/ai-clone/telegram/messages?since=0')
        assert r.status_code == 200
        assert r.json()['messages'] == []
        _tg_stub.poll_new_messages.side_effect = None

    def test_passes_since_param(self):
        _reset_mocks()
        _tg_stub.poll_new_messages.return_value = []
        client.get('/v1/ai-clone/telegram/messages?since=1700000000.5')
        _tg_stub.poll_new_messages.assert_called_with('uid-test', 1700000000.5)


# ── POST /v1/ai-clone/telegram/send ──────────────────────────────────────────


class TestTelegramSend:
    def test_returns_ok_on_success(self):
        _reset_mocks()
        _tg_stub.send_message.return_value = True
        r = client.post('/v1/ai-clone/telegram/send', json={'chat_id': 123, 'text': 'hello'})
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_returns_503_when_send_fails(self):
        _reset_mocks()
        _tg_stub.send_message.return_value = False
        r = client.post('/v1/ai-clone/telegram/send', json={'chat_id': 456, 'text': 'hey'})
        assert r.status_code == 503


# ── POST /v1/ai-clone/telegram/disconnect ────────────────────────────────────


class TestTelegramDisconnect:
    def test_returns_ok(self):
        _reset_mocks()
        r = client.post('/v1/ai-clone/telegram/disconnect', json={})
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'

    def test_calls_tg_disconnect_with_uid(self):
        _reset_mocks()
        client.post('/v1/ai-clone/telegram/disconnect', json={})
        _tg_stub.disconnect.assert_called_with('uid-test')
