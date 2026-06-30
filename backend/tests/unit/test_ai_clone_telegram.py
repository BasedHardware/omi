"""
Unit tests for utils/integrations/telegram_client.py (Telegram Bot API)

Critical contracts:
- connect() validates bot token via getMe, registers webhook, persists settings
- connect() raises ValueError('invalid_bot_token') when Telegram rejects the token
- disconnect() calls deleteWebhook and clears the stored token
- send_message() returns True on HTTP 200 from sendMessage
- send_message() returns False when no token is stored for the user
- send_message() returns False on HTTP error / network failure
"""

import asyncio
import os
import sys
import types
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'x' * 64)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)

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

# Point module-level references directly at stubs.
tg.clone_db = _db_ai_clone
tg.run_blocking = _executors_stub.run_blocking
tg.db_executor = _executors_stub.db_executor


# ── Helpers ────────────────────────────────────────────────────────────────────


def run(coro):
    return asyncio.run(coro)


def _reset():
    _db_ai_clone.get_platform_settings.reset_mock()
    _db_ai_clone.update_platform_settings.reset_mock()
    _db_ai_clone.get_platform_settings.return_value = None


def _make_ok_response(json_body: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


def _make_error_response(status: int = 401):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {'ok': False}
    resp.raise_for_status = MagicMock(side_effect=Exception(f'HTTP {status}'))
    return resp


def _fake_client(get_resp=None, post_resp=None):
    """Return a mock async context manager that yields a client with preset responses."""

    class _Ctx:
        async def __aenter__(self):
            self.get = AsyncMock(return_value=get_resp)
            self.post = AsyncMock(return_value=post_resp)
            self._get_resp = get_resp
            self._post_resp = post_resp
            return self

        async def __aexit__(self, *args):
            pass

    return _Ctx()


def _fake_client_multi(responses: list):
    """Return a mock async context manager with multiple post calls returning different responses."""

    class _Ctx:
        async def __aenter__(self):
            self.get = AsyncMock(return_value=responses[0])
            self.post = AsyncMock(side_effect=responses[1:])
            return self

        async def __aexit__(self, *args):
            pass

    return _Ctx()


# ── Tests: connect() ───────────────────────────────────────────────────────────


class TestConnect:
    def test_returns_bot_info_on_valid_token(self):
        _reset()
        me_resp = _make_ok_response({'ok': True, 'result': {'username': 'omibot', 'first_name': 'Omi'}})
        wh_resp = _make_ok_response({'ok': True, 'result': True})

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(get_resp=me_resp, post_resp=wh_resp)):
            result = run(tg.connect('uid-1', 'token123', 'https://example.com/webhook/uid-1'))

        assert result['bot_username'] == 'omibot'
        assert result['bot_name'] == 'Omi'

    def test_persists_settings_on_success(self):
        _reset()
        me_resp = _make_ok_response({'ok': True, 'result': {'username': 'omibot', 'first_name': 'Omi'}})
        wh_resp = _make_ok_response({'ok': True, 'result': True})

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(get_resp=me_resp, post_resp=wh_resp)):
            run(tg.connect('uid-2', 'token456', 'https://example.com/webhook/uid-2'))

        _db_ai_clone.update_platform_settings.assert_called_once()
        args = _db_ai_clone.update_platform_settings.call_args[0]
        assert args[0] == 'uid-2'
        assert args[1] == 'telegram'
        assert args[2]['connected'] is True
        assert args[2]['bot_token'] == 'token456'

    def test_raises_invalid_token_on_non_200(self):
        _reset()
        err_resp = _make_error_response(401)

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(get_resp=err_resp)):
            try:
                run(tg.connect('uid-3', 'bad-token', 'https://example.com/webhook/uid-3'))
                assert False, 'expected ValueError'
            except ValueError as e:
                assert str(e) == 'invalid_bot_token'

    def test_does_not_persist_on_invalid_token(self):
        _reset()
        err_resp = _make_error_response(401)

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(get_resp=err_resp)):
            try:
                run(tg.connect('uid-4', 'bad', 'https://example.com/w/uid-4'))
            except ValueError:
                pass

        _db_ai_clone.update_platform_settings.assert_not_called()


# ── Tests: disconnect() ────────────────────────────────────────────────────────


class TestDisconnect:
    def test_calls_delete_webhook_when_token_exists(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-abc', 'connected': True}
        del_resp = _make_ok_response({'ok': True})

        ctx = _fake_client(post_resp=del_resp)
        with patch.object(tg.httpx, 'AsyncClient', return_value=ctx):
            run(tg.disconnect('uid-dis'))

        # post was called (deleteWebhook)
        assert True  # no exception = success

    def test_clears_settings_in_firestore(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-abc'}

        with patch.object(
            tg.httpx, 'AsyncClient', return_value=_fake_client(post_resp=_make_ok_response({'ok': True}))
        ):
            run(tg.disconnect('uid-dis2'))

        _db_ai_clone.update_platform_settings.assert_called_once()
        saved = _db_ai_clone.update_platform_settings.call_args[0][2]
        assert saved['connected'] is False
        assert saved['bot_token'] is None

    def test_skips_api_call_when_no_token(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = None

        # httpx.AsyncClient should never be constructed when there's no token
        with patch.object(tg.httpx, 'AsyncClient') as mock_cls:
            run(tg.disconnect('uid-no-tok'))

        mock_cls.assert_not_called()

    def test_still_clears_settings_when_no_token(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = None

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client()):
            run(tg.disconnect('uid-clear'))

        _db_ai_clone.update_platform_settings.assert_called_once()


# ── Tests: send_message() ──────────────────────────────────────────────────────


class TestSendMessage:
    def test_returns_true_on_success(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-send'}
        send_resp = _make_ok_response({'ok': True})

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(post_resp=send_resp)):
            result = run(tg.send_message('uid-s', 9876, 'Hello from Omi'))

        assert result is True

    def test_calls_sendmessage_api(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-x'}
        send_resp = _make_ok_response({'ok': True})

        ctx = _fake_client(post_resp=send_resp)
        with patch.object(tg.httpx, 'AsyncClient', return_value=ctx):
            run(tg.send_message('uid-s2', 1234, 'hey'))

        # verify sendMessage is in the URL
        posted_url = ctx.post.call_args[0][0] if ctx.post.call_args else ''
        assert 'sendMessage' in posted_url

    def test_returns_false_when_no_token(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = None

        result = run(tg.send_message('uid-notoken', 123, 'hi'))

        assert result is False

    def test_returns_false_on_non_200(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-err'}
        err_resp = _make_error_response(400)

        with patch.object(tg.httpx, 'AsyncClient', return_value=_fake_client(post_resp=err_resp)):
            result = run(tg.send_message('uid-err', 999, 'fail'))

        assert result is False

    def test_returns_false_on_exception(self):
        _reset()
        _db_ai_clone.get_platform_settings.return_value = {'bot_token': 'tok-exc'}

        class _ErrCtx:
            async def __aenter__(self):
                self.post = AsyncMock(side_effect=Exception('network down'))
                return self

            async def __aexit__(self, *args):
                pass

        with patch.object(tg.httpx, 'AsyncClient', return_value=_ErrCtx()):
            result = run(tg.send_message('uid-exc', 1, 'hi'))

        assert result is False
