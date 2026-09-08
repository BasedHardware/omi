import os
import sys
import types
from importlib.util import find_spec
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-for-unit-tests')
os.environ.setdefault('ANTHROPIC_API_KEY', 'ant-test-fake-for-unit-tests')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class _Notification:
    def __init__(self, title: str, body: str):
        self.title = title
        self.body = body


class _Message:
    def __init__(self, token: str, notification, data):
        self.token = token
        self.notification = notification
        self.data = data


def _ensure_byok_error_notification_deps():
    import utils.llm.byok_errors as byok_errors

    if byok_errors.notification_db is None:
        byok_errors.notification_db = SimpleNamespace(
            get_all_tokens=MagicMock(),
            remove_bulk_tokens=MagicMock(),
        )
    if byok_errors.messaging is None:
        byok_errors.messaging = SimpleNamespace(
            Notification=_Notification,
            Message=_Message,
            send_each=MagicMock(),
        )


_ensure_byok_error_notification_deps()


def _module_available(name: str) -> bool:
    if name in sys.modules:
        return True
    try:
        return find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


@pytest.fixture(autouse=True)
def _install_optional_import_stubs(monkeypatch):
    if 'database._client' not in sys.modules:
        monkeypatch.setitem(sys.modules, 'database._client', MagicMock())
    if 'database.notifications' not in sys.modules:
        notification_db_stub = types.ModuleType('database.notifications')
        notification_db_stub.get_all_tokens = MagicMock()
        notification_db_stub.remove_bulk_tokens = MagicMock()
        monkeypatch.setitem(sys.modules, 'database.notifications', notification_db_stub)

    if not _module_available('cachetools'):
        cachetools_stub = types.ModuleType('cachetools')

        class _TTLCache(dict):
            def __init__(self, *args, **kwargs):
                super().__init__()

        cachetools_stub.TTLCache = _TTLCache
        monkeypatch.setitem(sys.modules, 'cachetools', cachetools_stub)

    if not _module_available('fastapi'):
        fastapi_stub = types.ModuleType('fastapi')

        class _FastAPIHTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = ''):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fastapi_stub.HTTPException = _FastAPIHTTPException
        fastapi_stub.Request = MagicMock()
        monkeypatch.setitem(sys.modules, 'fastapi', fastapi_stub)

    if not _module_available('starlette.middleware.base'):
        starlette_stub = types.ModuleType('starlette')
        middleware_stub = types.ModuleType('starlette.middleware')
        base_stub = types.ModuleType('starlette.middleware.base')
        base_stub.BaseHTTPMiddleware = object
        if 'starlette' not in sys.modules:
            monkeypatch.setitem(sys.modules, 'starlette', starlette_stub)
        if 'starlette.middleware' not in sys.modules:
            monkeypatch.setitem(sys.modules, 'starlette.middleware', middleware_stub)
        monkeypatch.setitem(sys.modules, 'starlette.middleware.base', base_stub)

    if not _module_available('starlette.websockets'):
        websockets_stub = types.ModuleType('starlette.websockets')
        websockets_stub.WebSocket = MagicMock()
        monkeypatch.setitem(sys.modules, 'starlette.websockets', websockets_stub)

    if not _module_available('firebase_admin'):
        firebase_stub = types.ModuleType('firebase_admin')
        messaging_stub = types.ModuleType('firebase_admin.messaging')

        messaging_stub.Notification = _Notification
        messaging_stub.Message = _Message
        messaging_stub.send_each = MagicMock()
        firebase_stub.messaging = messaging_stub
        monkeypatch.setitem(sys.modules, 'firebase_admin', firebase_stub)
        monkeypatch.setitem(sys.modules, 'firebase_admin.messaging', messaging_stub)
    _ensure_byok_error_notification_deps()


class _HTTPError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_notifies_actionable_byok_error(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
):
    from utils.llm.byok_errors import handle_llm_error

    mock_send_each.return_value = SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    mock_get_tokens.assert_called_once_with('user-1')
    mock_send_each.assert_called_once()
    message = mock_send_each.call_args.args[0][0]
    assert message.data == {'type': 'byok_llm_error', 'provider': 'openai', 'reason': 'quota'}


@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=False)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_deduplicates_recent_notification(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    mock_send_each.assert_not_called()


@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value=None)
def test_handle_llm_error_does_not_notify_platform_error(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_send_each,
):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_not_called()
    mock_send_each.assert_not_called()


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.notification_db.remove_bulk_tokens')
@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['bad-token'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_removes_permanent_bad_tokens(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
    mock_remove_tokens,
    mock_release,
):
    from utils.llm.byok_errors import handle_llm_error

    fcm_error = SimpleNamespace(code='UNREGISTERED')
    mock_send_each.return_value = SimpleNamespace(responses=[SimpleNamespace(success=False, exception=fcm_error)])

    handle_llm_error(_HTTPError("bad key", 401), 'openai', feature='memories', model='gpt-test')

    mock_remove_tokens.assert_called_once_with(['bad-token'])
    # No device received the notification, so the dedupe lock must be released for retry.
    mock_release.assert_called_once_with('user-1', 'openai', 'invalid')


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.messaging.send_each', side_effect=RuntimeError('fcm unavailable'))
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_releases_lock_when_send_raises(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
    mock_release,
):
    from utils.llm.byok_errors import handle_llm_error

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    mock_lock.assert_called_once_with('user-1', 'openai', 'quota')
    # send_each raised, so nothing was delivered: the lock must be released for retry.
    mock_release.assert_called_once_with('user-1', 'openai', 'quota')


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_releases_lock_when_no_send_succeeds(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
    mock_release,
):
    from utils.llm.byok_errors import handle_llm_error

    transient = SimpleNamespace(code='UNAVAILABLE')
    mock_send_each.return_value = SimpleNamespace(responses=[SimpleNamespace(success=False, exception=transient)])

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    # Every send failed (transiently): release the lock so the next error retries.
    mock_release.assert_called_once_with('user-1', 'openai', 'quota')


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens', return_value=['token-1', 'token-2'])
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_keeps_lock_when_a_send_succeeds(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
    mock_release,
):
    from utils.llm.byok_errors import handle_llm_error

    mock_send_each.return_value = SimpleNamespace(
        responses=[
            SimpleNamespace(success=True, exception=None),
            SimpleNamespace(success=False, exception=SimpleNamespace(code='UNAVAILABLE')),
        ]
    )

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    # At least one device was notified — the dedupe lock must be kept (not released).
    mock_release.assert_not_called()


@patch('utils.llm.byok_errors.release_byok_llm_error_notification_lock')
@patch('utils.llm.byok_errors.messaging.send_each')
@patch('utils.llm.byok_errors.notification_db.get_all_tokens')
@patch('utils.llm.byok_errors.try_acquire_byok_llm_error_notification_lock', return_value=True)
@patch('utils.llm.byok_errors.get_byok_uid', return_value='user-1')
@patch('utils.llm.byok_errors.get_byok_key', return_value='sk-user')
def test_handle_llm_error_batches_sends_over_500_tokens(
    mock_get_key,
    mock_get_uid,
    mock_lock,
    mock_get_tokens,
    mock_send_each,
    mock_release,
):
    from utils.llm.byok_errors import handle_llm_error

    mock_get_tokens.return_value = [f'token-{i}' for i in range(600)]
    mock_send_each.side_effect = lambda batch: SimpleNamespace(
        responses=[SimpleNamespace(success=True, exception=None) for _ in batch]
    )

    handle_llm_error(_HTTPError("insufficient_quota", 429), 'openai', feature='memories', model='gpt-test')

    # Firebase caps send_each() at 500 messages, so 600 tokens must split into 500 + 100.
    assert mock_send_each.call_count == 2
    batch_sizes = [len(call.args[0]) for call in mock_send_each.call_args_list]
    assert batch_sizes == [500, 100]
    assert all(size <= 500 for size in batch_sizes)
    mock_release.assert_not_called()
