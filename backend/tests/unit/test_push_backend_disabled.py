"""ADR-0011 push feature flag: PUSH_NOTIFICATION_BACKEND=disabled sends nothing.

With the flag off the backend must run fully — every send path short-circuits before
touching Firebase, and (legacy-principal) a user who already has registered device
tokens still receives no remote push. Default (flag unset) stays FCM and is covered by
test_notification_token_cleanup / test_notification_async_boundaries.
"""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: Any) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _messaging_module() -> ModuleType:
    class Notification:
        def __init__(self, title: str, body: str):
            self.title = title
            self.body = body

    def constructor(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    def _unexpected_send(_messages: Any) -> Any:
        raise AssertionError('send_each must not be called when push is disabled')

    return _module(
        'firebase_admin.messaging',
        Notification=Notification,
        AndroidConfig=constructor,
        AndroidNotification=constructor,
        APNSConfig=constructor,
        APNSPayload=constructor,
        Aps=constructor,
        WebpushConfig=constructor,
        WebpushNotification=constructor,
        WebpushFCMOptions=constructor,
        Message=constructor,
        send_each=_unexpected_send,
    )


@contextmanager
def _loaded_notifications() -> Iterator[tuple[ModuleType, dict[str, int]]]:
    messaging = _messaging_module()
    auth = _module('firebase_admin.auth', get_user=lambda _uid: SimpleNamespace(display_name='Ada'))
    # Legacy principal: a user WITH a registered device token. Disabled must still send nothing;
    # the counter proves the flag short-circuits before the token store is even read.
    reads = {'get_all_tokens': 0, 'remove_bulk_tokens': 0}

    def _get_all_tokens(_uid: str) -> list[str]:
        reads['get_all_tokens'] += 1
        return ['registered-device-token']

    def _remove_bulk_tokens(_tokens: Any) -> None:
        reads['remove_bulk_tokens'] += 1

    notification_db = _module(
        'database.notifications',
        get_all_tokens=_get_all_tokens,
        remove_bulk_tokens=_remove_bulk_tokens,
    )
    stubs = {
        'firebase_admin': _module('firebase_admin', messaging=messaging, auth=auth),
        'firebase_admin.messaging': messaging,
        'firebase_admin.auth': auth,
        'database.notifications': notification_db,
        'database.redis_db': _module(
            'database.redis_db',
            set_credit_limit_notification_sent=lambda _uid: None,
            has_credit_limit_notification_been_sent=lambda _uid: False,
            set_silent_user_notification_sent=lambda _uid: None,
            has_silent_user_notification_been_sent=lambda _uid: False,
        ),
        'database.auth': _module('database.auth', get_user_from_uid=lambda _uid: None),
        'utils.llm.notifications': _module(
            'utils.llm.notifications',
            generate_notification_message=lambda *_a, **_k: ('t', 'b'),
            generate_credit_limit_notification=lambda *_a, **_k: ('t', 'b'),
            generate_silent_user_notification=lambda *_a, **_k: ('t', 'b'),
        ),
    }

    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.notifications',
            str(BACKEND_DIR / 'utils' / 'notifications.py'),
        )
        yield notifications, reads


def test_disabled_backend_sends_nothing_sync(monkeypatch: Any) -> None:
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'disabled')
    with _loaded_notifications() as (notifications, reads):
        # send_each raises if reached; a clean return proves the short-circuit.
        notifications.send_notification('user-1', 'omi', 'hello')
        assert reads['get_all_tokens'] == 0
        assert reads['remove_bulk_tokens'] == 0


def test_disabled_backend_sends_nothing_async(monkeypatch: Any) -> None:
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'disabled')
    with _loaded_notifications() as (notifications, reads):
        asyncio.run(notifications.send_notification_async('user-2', 'omi', 'hello'))
        assert reads['get_all_tokens'] == 0


def test_disabled_backend_skips_bulk(monkeypatch: Any) -> None:
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'disabled')
    with _loaded_notifications() as (notifications, _reads):
        # Pre-fetched recipient tokens are supplied directly; disabled must not send them.
        asyncio.run(notifications.send_bulk_notification(['registered-device-token'], 'omi', 'hello'))


def test_unset_backend_defaults_to_fcm_and_sends(monkeypatch: Any) -> None:
    monkeypatch.delenv('PUSH_NOTIFICATION_BACKEND', raising=False)
    with _loaded_notifications() as (notifications, reads):
        # Default path reads tokens and attempts FCM delivery (send_each raises here, proving
        # the code took the FCM branch rather than the disabled short-circuit).
        try:
            notifications.send_notification('user-3', 'omi', 'hello')
        except AssertionError as exc:
            assert 'send_each must not be called' in str(exc)
        assert reads['get_all_tokens'] == 1
