"""Chat answer pushes use the client-displayed FCM path (#4375)."""

import asyncio
import inspect
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

    return _module(
        'firebase_admin.messaging',
        Notification=Notification,
        AndroidConfig=constructor,
        AndroidNotification=constructor,
        APNSConfig=constructor,
        APNSPayload=constructor,
        Aps=constructor,
        ApsAlert=constructor,
        WebpushConfig=constructor,
        WebpushNotification=constructor,
        WebpushFCMOptions=constructor,
        Message=constructor,
        send_each=lambda _messages: SimpleNamespace(responses=[]),
    )


@contextmanager
def _loaded_notifications() -> Iterator[ModuleType]:
    messaging = _messaging_module()
    auth = _module(
        'firebase_admin.auth',
        get_user=lambda _uid: SimpleNamespace(display_name='Ada', email='ada@example.com'),
    )
    firebase_admin = _module('firebase_admin', messaging=messaging, auth=auth)
    notification_db = _module(
        'database.notifications',
        get_all_tokens=lambda _uid: ['device-token'],
        remove_bulk_tokens=lambda _tokens: None,
    )
    redis_db = _module(
        'database.redis_db',
        has_credit_limit_notification_been_sent=lambda _uid: False,
        set_credit_limit_notification_sent=lambda _uid: None,
        has_silent_user_notification_been_sent=lambda _uid: False,
        set_silent_user_notification_sent=lambda _uid: None,
    )
    database_auth = _module('database.auth', get_user_from_uid=lambda _uid: None)

    async def generate_notification_message(_uid: str, _name: str, _plan: str) -> tuple[str, str]:
        return 'Welcome', 'Subscription active'

    async def generate_credit_limit_notification(_uid: str, _name: str) -> tuple[str, str]:
        return 'Limit reached', 'Upgrade to continue'

    llm_notifications = _module(
        'utils.llm.notifications',
        generate_notification_message=generate_notification_message,
        generate_credit_limit_notification=generate_credit_limit_notification,
        generate_silent_user_notification=lambda _name: ('We miss you', 'Capture something today'),
    )

    with stub_modules(
        {
            'firebase_admin': firebase_admin,
            'firebase_admin.messaging': messaging,
            'firebase_admin.auth': auth,
            'database.notifications': notification_db,
            'database.redis_db': redis_db,
            'database.auth': database_auth,
            'utils.llm.notifications': llm_notifications,
        }
    ):
        yield load_module_fresh(
            'utils.notifications',
            str(BACKEND_DIR / 'utils' / 'notifications.py'),
        )


def test_stringify_fcm_data_coerces_values_to_strings():
    with _loaded_notifications() as notifications:
        out = notifications._stringify_fcm_data({'a': 1, 'b': None, 'c': True, 'd': 'x'})
        assert out == {'a': '1', 'b': '', 'c': 'True', 'd': 'x'}


def test_client_displayed_message_omits_top_level_notification():
    with _loaded_notifications() as notifications:
        data = {
            'push_type': 'chat_answer',
            'title': 'omi says',
            'text': 'Long answer that should expand',
            'navigate_to': '/chat/omi',
            'notification_type': 'plugin',
        }
        msg = notifications._build_message(
            token='token-1',
            tag='tag-1',
            notification=None,
            data=data,
            priority='high',
            client_displayed=True,
            display_title='omi says',
            display_body='Long answer that should expand',
        )
        assert msg.notification is None
        assert msg.data['navigate_to'] == '/chat/omi'
        assert msg.data['push_type'] == 'chat_answer'
        assert msg.data['text'] == 'Long answer that should expand'
        assert 'body' not in msg.data
        assert msg.android is not None
        assert getattr(msg.android, 'notification', None) is None
        assert msg.apns is not None
        assert msg.apns.payload.aps.alert.title == 'omi says'
        assert msg.apns.payload.aps.alert.body == 'Long answer that should expand'


def test_send_client_displayed_notification_sets_push_type():
    with _loaded_notifications() as notifications:
        captured: dict[str, Any] = {}

        def fake_send_each(messages):
            captured['messages'] = messages
            return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

        notifications.messaging.send_each = fake_send_each
        notifications.notification_db.get_all_tokens = lambda _uid: ['t1']

        notifications.send_client_displayed_notification(
            'uid-1',
            'omi says',
            'Answer body',
            {
                'notification_type': 'plugin',
                'navigate_to': '/chat/omi',
                'id': 'msg-1',
                'text': 'Answer body',
            },
        )

        assert len(captured['messages']) == 1
        msg = captured['messages'][0]
        assert msg.notification is None
        assert msg.data['push_type'] == 'chat_answer'
        assert msg.data['title'] == 'omi says'
        assert msg.data['text'] == 'Answer body'
        assert 'body' not in msg.data
        assert msg.data['navigate_to'] == '/chat/omi'
        assert msg.apns.payload.aps.alert.body == 'Answer body'


def test_send_client_displayed_notification_async_matches_sync_shape():
    with _loaded_notifications() as notifications:
        assert inspect.iscoroutinefunction(notifications.send_client_displayed_notification_async)
        captured: dict[str, Any] = {}

        def fake_send_each(messages):
            captured['messages'] = messages
            return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

        notifications.messaging.send_each = fake_send_each
        notifications.notification_db.get_all_tokens = lambda _uid: ['t1']

        asyncio.run(
            notifications.send_client_displayed_notification_async(
                'uid-1',
                'omi says',
                'Async answer body',
                {
                    'notification_type': 'plugin',
                    'navigate_to': '/chat/omi',
                    'id': 'msg-2',
                    'text': 'Async answer body',
                },
            )
        )

        assert len(captured['messages']) == 1
        msg = captured['messages'][0]
        assert msg.notification is None
        assert msg.data['push_type'] == 'chat_answer'
        assert msg.data['text'] == 'Async answer body'
        assert 'body' not in msg.data
        assert msg.data['navigate_to'] == '/chat/omi'
        assert msg.apns.payload.aps.alert.body == 'Async answer body'


def test_send_client_displayed_notification_fills_text_when_missing():
    with _loaded_notifications() as notifications:
        captured: dict[str, Any] = {}

        def fake_send_each(messages):
            captured['messages'] = messages
            return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None)])

        notifications.messaging.send_each = fake_send_each
        notifications.notification_db.get_all_tokens = lambda _uid: ['t1']

        notifications.send_client_displayed_notification(
            'uid-1',
            'omi says',
            'Only in body arg',
            {'notification_type': 'plugin', 'navigate_to': '/chat/omi', 'id': 'msg-3'},
        )

        msg = captured['messages'][0]
        assert msg.data['text'] == 'Only in body arg'
        assert 'body' not in msg.data
