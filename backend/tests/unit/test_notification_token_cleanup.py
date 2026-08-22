import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import MagicMock

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _FakeMessagingException(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _FakeResponse:
    def __init__(self, success: bool, exception: Exception | None = None):
        self.success = success
        self.exception = exception


class _FakeBatchResponse:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = responses


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
        send_each=MagicMock(),
    )


@contextmanager
def _loaded_notifications() -> Iterator[tuple[ModuleType, ModuleType, ModuleType]]:
    messaging = _messaging_module()
    auth = _module('firebase_admin.auth', get_user=MagicMock())
    notification_db = _module(
        'database.notifications',
        get_all_tokens=MagicMock(),
        remove_bulk_tokens=MagicMock(),
    )
    stubs = {
        'firebase_admin': _module('firebase_admin', messaging=messaging, auth=auth),
        'firebase_admin.messaging': messaging,
        'firebase_admin.auth': auth,
        'database.notifications': notification_db,
        'database.redis_db': _module(
            'database.redis_db',
            set_credit_limit_notification_sent=MagicMock(),
            has_credit_limit_notification_been_sent=MagicMock(),
            set_silent_user_notification_sent=MagicMock(),
            has_silent_user_notification_been_sent=MagicMock(),
        ),
        'database.auth': _module('database.auth', get_user_from_uid=MagicMock()),
        'utils.llm.notifications': _module(
            'utils.llm.notifications',
            generate_notification_message=MagicMock(),
            generate_credit_limit_notification=MagicMock(),
            generate_silent_user_notification=MagicMock(),
        ),
    }

    with stub_modules(stubs):
        notifications = load_module_fresh(
            'utils.notifications',
            str(BACKEND_DIR / 'utils' / 'notifications.py'),
        )
        yield notifications, notification_db, messaging


def test_send_notification_removes_not_found_tokens() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        tokens = ['dead-token', 'live-token']
        notification_db.get_all_tokens.return_value = tokens
        messaging.send_each.return_value = _FakeBatchResponse(
            [
                _FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND')),
                _FakeResponse(success=True),
            ]
        )

        notifications.send_notification('user-1', 'omi', 'hello')

        notification_db.remove_bulk_tokens.assert_called_once_with(['dead-token'])


def test_send_notification_keeps_transient_failures() -> None:
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['retry-token']
        messaging.send_each.return_value = _FakeBatchResponse(
            [_FakeResponse(success=False, exception=_FakeMessagingException('UNAUTHENTICATED'))]
        )

        notifications.send_notification('user-1', 'omi', 'hello')

        notification_db.remove_bulk_tokens.assert_not_called()


def test_send_notification_body_is_plain_text() -> None:
    """Markdown in the body must not reach the OS notification (asterisks showed up literally)."""
    with _loaded_notifications() as (notifications, notification_db, messaging):
        notification_db.get_all_tokens.return_value = ['live-token']
        messaging.send_each.return_value = _FakeBatchResponse([_FakeResponse(success=True)])

        notifications.send_notification(
            'user-1',
            'omi says',
            "- 🇺🇸 **US President**: Donald Trump\n- 🇮🇳 **India's President**: Droupadi Murmu",
        )

        sent_messages = messaging.send_each.call_args.args[0]
        body = sent_messages[0].notification.body
        assert '**' not in body
        assert body == "• 🇺🇸 US President: Donald Trump\n• 🇮🇳 India's President: Droupadi Murmu"


def test_bulk_one_failing_chunk_does_not_discard_the_other_chunks_cleanup(monkeypatch) -> None:
    """A raise in one FCM chunk must not throw away every chunk's invalid-token cleanup.

    ``send_bulk_notification`` fans the sends out with ``asyncio.gather(*tasks)``. Without
    ``return_exceptions=True`` the first raising chunk propagates straight into the function's outer
    ``except Exception``, so the ``invalid_tokens`` collected from every OTHER chunk is discarded and
    ``remove_bulk_tokens`` never runs — the dead tokens survive and are retried on every future
    notification. ``send_batch`` calls ``messaging.send_each`` with no try of its own for a <=500 chunk,
    and firebase-admin validates all messages before sending, so one malformed message is enough to
    raise. The sibling daily-summary fan-out in utils/other/notifications.py already passes
    ``return_exceptions=True``.

    The env is pinned: this harness does not set PUSH_NOTIFICATION_BACKEND, so under an ambient
    ``disabled``/``unifiedpush`` value the FCM assertions below would pass vacuously.
    """
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'fcm')
    with _loaded_notifications() as (notifications, notification_db, messaging):
        # 501 tokens over a 500 batch size -> two chunks: the first raises, the second reports a dead token.
        tokens = [f'token-{i}' for i in range(501)]
        calls = {'n': 0}
        counter_lock = threading.Lock()

        def _send_each(messages):
            # Keyed on the CHUNK, not on call order: the chunks are dispatched to a thread pool, so
            # `if this is the first call` decided at random which chunk raised — under machine load this
            # test failed ~3 runs in 4. `calls['n'] += 1` was not atomic either, so both threads could
            # read 0 and both raise, leaving nothing to clean up.
            with counter_lock:
                calls['n'] += 1
            if len(messages) == 500:
                raise RuntimeError('transport rejected the whole chunk')
            return _FakeBatchResponse([_FakeResponse(success=False, exception=_FakeMessagingException('NOT_FOUND'))])

        messaging.send_each = _send_each

        asyncio.run(notifications.send_bulk_notification(tokens, 'title', 'body'))

        assert calls['n'] == 2, 'both chunks must be attempted'
        notification_db.remove_bulk_tokens.assert_called_once_with(['token-500'])
