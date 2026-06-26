"""
Unit tests for utils/integrations/telegram_client.py

Critical contracts:
- get_client returns None when TELEGRAM_API_ID / TELEGRAM_API_HASH are not set
- get_client returns cached client when it is already connected + authorized
- send_code raises RuntimeError when API credentials are missing
- send_message returns False when there is no authenticated client
- poll_new_messages returns [] when there is no authenticated client
- Session string is persisted to Firestore after successful verify_code
- Session string is fetched from Firestore on cache miss
- disconnect removes client from cache and clears Firestore session
- poll_new_messages skips outgoing messages and bot dialogs
"""

import os
import sys
import types
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'x' * 64)
# Deliberately leave TELEGRAM_API_ID unset for "not configured" tests

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)

# ── Stub Telethon before importing the module ──────────────────────────────────

_telethon_stub = types.ModuleType('telethon')
_sessions_stub = types.ModuleType('telethon.sessions')
_types_stub = types.ModuleType('telethon.tl.types')
_tl_stub = types.ModuleType('telethon.tl')


class _FakeStringSession:
    def __init__(self, string=''):
        self._string = string

    def save(self):
        return self._string or 'session-string-abc'


_sessions_stub.StringSession = _FakeStringSession


class _FakeUser:
    first_name = 'Test'
    last_name = 'User'
    username = 'testuser'


_types_stub.User = _FakeUser
_telethon_stub.TelegramClient = MagicMock
sys.modules['telethon'] = _telethon_stub
sys.modules['telethon.sessions'] = _sessions_stub
sys.modules['telethon.tl'] = _tl_stub
sys.modules['telethon.tl.types'] = _types_stub

# ── Stub database.ai_clone ─────────────────────────────────────────────────────

_db_ai_clone = types.ModuleType('database.ai_clone')
_db_ai_clone.get_platform_settings = MagicMock(return_value=None)
_db_ai_clone.update_platform_settings = MagicMock()
sys.modules['database'] = sys.modules.get('database') or types.ModuleType('database')
sys.modules['database.ai_clone'] = _db_ai_clone

# ── Stub executors ─────────────────────────────────────────────────────────────

_executors_stub = types.ModuleType('utils.executors')
_executors_stub.db_executor = MagicMock()


async def _run_blocking(executor, fn, *args):
    return fn(*args)


_executors_stub.run_blocking = _run_blocking
sys.modules['utils'] = sys.modules.get('utils') or types.ModuleType('utils')
sys.modules['utils.executors'] = _executors_stub

# ── Import the module under test ───────────────────────────────────────────────

sys.modules.pop('utils.integrations', None)
sys.modules.pop('utils.integrations.telegram_client', None)

_integrations_pkg = types.ModuleType('utils.integrations')
sys.modules['utils.integrations'] = _integrations_pkg

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    'utils.integrations.telegram_client',
    os.path.join(BACKEND_DIR, 'utils', 'integrations', 'telegram_client.py'),
)
tg = _ilu.module_from_spec(_spec)
sys.modules['utils.integrations.telegram_client'] = tg
_spec.loader.exec_module(tg)


# ── Helpers ────────────────────────────────────────────────────────────────────


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_client(*, connected=True, authorized=True):
    client = MagicMock()
    client.is_connected = MagicMock(return_value=connected)
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.connect = AsyncMock()
    client.log_out = AsyncMock()
    client.send_message = AsyncMock()
    client.get_me = AsyncMock(return_value=_FakeUser())
    client.session = _FakeStringSession('saved-session')
    return client


def _clear_clients():
    tg._clients.clear()
    tg._pending_clients.clear()
    _db_ai_clone.get_platform_settings.reset_mock()
    _db_ai_clone.update_platform_settings.reset_mock()


# ── Tests: get_client ──────────────────────────────────────────────────────────


class TestGetClient:
    def test_returns_none_when_api_not_configured(self):
        _clear_clients()
        # API_ID is 0 (not set) by default in this test environment
        tg.API_ID = 0
        tg.API_HASH = ''

        result = run(tg.get_client('uid-1'))

        assert result is None

    def test_returns_cached_client_when_connected(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        tg._clients['uid-cached'] = fake

        result = run(tg.get_client('uid-cached'))

        assert result is fake
        # Should NOT have fetched a session from Firestore
        _db_ai_clone.get_platform_settings.assert_not_called()

    def test_fetches_session_from_firestore_on_cache_miss(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        _db_ai_clone.get_platform_settings.return_value = {'session_string': 'my-session', 'connected': True}

        fake = _make_fake_client(connected=True, authorized=True)
        with patch.object(tg, 'TelegramClient', return_value=fake):
            result = run(tg.get_client('uid-new'))

        assert result is fake
        _db_ai_clone.get_platform_settings.assert_called_with('uid-new', 'telegram')

    def test_returns_none_when_no_session_in_firestore(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        _db_ai_clone.get_platform_settings.return_value = None

        result = run(tg.get_client('uid-no-session'))

        assert result is None

    def test_evicts_and_returns_none_when_session_invalid(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        _db_ai_clone.get_platform_settings.return_value = {'session_string': 'expired-sess'}

        fake = _make_fake_client(connected=True, authorized=False)
        with patch.object(tg, 'TelegramClient', return_value=fake):
            result = run(tg.get_client('uid-expired'))

        assert result is None
        assert 'uid-expired' not in tg._clients


# ── Tests: send_code ──────────────────────────────────────────────────────────


class TestSendCode:
    def test_raises_when_api_not_configured(self):
        _clear_clients()
        tg.API_ID = 0
        tg.API_HASH = ''

        try:
            run(tg.send_code('+1234567890'))
            assert False, 'Expected RuntimeError'
        except RuntimeError as e:
            assert 'TELEGRAM_API_ID' in str(e) or 'not set' in str(e).lower()

    def test_stashes_client_in_pending(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'

        fake_client = _make_fake_client()
        fake_result = MagicMock()
        fake_result.phone_code_hash = 'hash-abc'
        fake_client.send_code_request = AsyncMock(return_value=fake_result)

        with patch.object(tg, 'TelegramClient', return_value=fake_client):
            result = run(tg.send_code('+19995550001'))

        assert result == {'phone_code_hash': 'hash-abc'}
        assert '+19995550001' in tg._pending_clients

    def test_returns_phone_code_hash(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'

        fake_client = _make_fake_client()
        fake_result = MagicMock()
        fake_result.phone_code_hash = 'xyz-hash'
        fake_client.send_code_request = AsyncMock(return_value=fake_result)

        with patch.object(tg, 'TelegramClient', return_value=fake_client):
            result = run(tg.send_code('+10000000000'))

        assert result['phone_code_hash'] == 'xyz-hash'


# ── Tests: verify_code ────────────────────────────────────────────────────────


class TestVerifyCode:
    def test_saves_session_to_firestore(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'

        fake_client = _make_fake_client()
        fake_me = MagicMock()
        fake_me.first_name = 'Alice'
        fake_me.last_name = 'Smith'
        fake_client.get_me = AsyncMock(return_value=fake_me)
        fake_client.sign_in = AsyncMock()
        tg._pending_clients['+1555'] = fake_client

        run(tg.verify_code('uid-v', '+1555', '12345', 'hash-v'))

        _db_ai_clone.update_platform_settings.assert_called_once()
        call_args = _db_ai_clone.update_platform_settings.call_args
        uid_arg, platform_arg, data_arg = call_args[0]
        assert uid_arg == 'uid-v'
        assert platform_arg == 'telegram'
        assert data_arg['connected'] is True
        assert 'session_string' in data_arg

    def test_caches_client_after_verify(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'

        fake_client = _make_fake_client()
        fake_me = MagicMock()
        fake_me.first_name = 'Bob'
        fake_me.last_name = None
        fake_client.get_me = AsyncMock(return_value=fake_me)
        fake_client.sign_in = AsyncMock()
        tg._pending_clients['+1777'] = fake_client

        run(tg.verify_code('uid-cache-test', '+1777', '99999', 'hash'))

        assert 'uid-cache-test' in tg._clients

    def test_returns_display_name_and_phone(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'

        fake_client = _make_fake_client()
        fake_me = MagicMock()
        fake_me.first_name = 'Karthik'
        fake_me.last_name = 'Y'
        fake_client.get_me = AsyncMock(return_value=fake_me)
        fake_client.sign_in = AsyncMock()
        tg._pending_clients['+1999'] = fake_client

        result = run(tg.verify_code('uid-name-test', '+1999', '11111', 'hash'))

        assert result['phone'] == '+1999'
        assert 'Karthik' in result['display_name']


# ── Tests: send_message ───────────────────────────────────────────────────────


class TestSendMessage:
    def test_returns_false_when_no_client(self):
        _clear_clients()
        tg.API_ID = 0
        tg.API_HASH = ''

        result = run(tg.send_message('uid-1', 123456, 'Hello!'))

        assert result is False

    def test_calls_telethon_send_message(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        tg._clients['uid-send'] = fake

        result = run(tg.send_message('uid-send', 9876, 'Hey there!'))

        assert result is True
        fake.send_message.assert_called_with(9876, 'Hey there!')

    def test_returns_false_on_telethon_exception(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        fake.send_message = AsyncMock(side_effect=Exception('network error'))
        tg._clients['uid-err'] = fake

        result = run(tg.send_message('uid-err', 123, 'hi'))

        assert result is False


# ── Tests: poll_new_messages ──────────────────────────────────────────────────


class TestPollNewMessages:
    def test_returns_empty_when_no_client(self):
        _clear_clients()
        tg.API_ID = 0
        tg.API_HASH = ''

        result = run(tg.poll_new_messages('uid-1', 0))

        assert result == []

    def test_skips_outgoing_messages(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        tg._clients['uid-poll'] = fake

        import datetime

        cutoff = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)

        # One outgoing message, one incoming
        outgoing_msg = MagicMock()
        outgoing_msg.out = True
        outgoing_msg.message = 'I sent this'
        outgoing_msg.date = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)

        incoming_msg = MagicMock()
        incoming_msg.out = False
        incoming_msg.message = 'They sent this'
        incoming_msg.date = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)

        async def _fake_iter_messages(dialog, limit):
            yield outgoing_msg
            yield incoming_msg

        async def _fake_iter_dialogs():
            dialog = MagicMock()
            dialog.is_user = True
            entity = MagicMock()
            entity.bot = False
            entity.first_name = 'Friend'
            entity.last_name = None
            entity.username = 'friend'
            dialog.entity = entity
            dialog.id = 111
            yield dialog

        fake.iter_dialogs = _fake_iter_dialogs
        fake.iter_messages = _fake_iter_messages

        result = run(tg.poll_new_messages('uid-poll', cutoff.timestamp()))

        assert len(result) == 1
        assert result[0]['message'] == 'They sent this'

    def test_skips_bot_dialogs(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        tg._clients['uid-bots'] = fake

        async def _fake_iter_dialogs():
            dialog = MagicMock()
            dialog.is_user = True
            entity = MagicMock()
            entity.bot = True  # This is a bot — must be skipped
            dialog.entity = entity
            dialog.id = 999
            yield dialog

        fake.iter_dialogs = _fake_iter_dialogs

        result = run(tg.poll_new_messages('uid-bots', 0))

        assert result == []

    def test_skips_group_chats(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client(connected=True, authorized=True)
        tg._clients['uid-group'] = fake

        async def _fake_iter_dialogs():
            dialog = MagicMock()
            dialog.is_user = False  # Group chat — must be skipped
            yield dialog

        fake.iter_dialogs = _fake_iter_dialogs

        result = run(tg.poll_new_messages('uid-group', 0))

        assert result == []


# ── Tests: disconnect ─────────────────────────────────────────────────────────


class TestDisconnect:
    def test_removes_client_from_cache(self):
        _clear_clients()
        tg.API_ID = 12345
        tg.API_HASH = 'hash'
        fake = _make_fake_client()
        tg._clients['uid-disc'] = fake

        run(tg.disconnect('uid-disc'))

        assert 'uid-disc' not in tg._clients

    def test_calls_log_out(self):
        _clear_clients()
        fake = _make_fake_client()
        tg._clients['uid-logout'] = fake

        run(tg.disconnect('uid-logout'))

        fake.log_out.assert_called_once()

    def test_clears_session_in_firestore(self):
        _clear_clients()
        fake = _make_fake_client()
        tg._clients['uid-clear'] = fake
        _db_ai_clone.update_platform_settings.reset_mock()

        run(tg.disconnect('uid-clear'))

        _db_ai_clone.update_platform_settings.assert_called_once()
        args = _db_ai_clone.update_platform_settings.call_args[0]
        uid_arg, platform_arg, data_arg = args
        assert uid_arg == 'uid-clear'
        assert platform_arg == 'telegram'
        assert data_arg.get('connected') is False
        assert data_arg.get('session_string') is None

    def test_handles_missing_client_gracefully(self):
        _clear_clients()
        _db_ai_clone.update_platform_settings.reset_mock()

        run(tg.disconnect('uid-never-connected'))

        _db_ai_clone.update_platform_settings.assert_called_once()
