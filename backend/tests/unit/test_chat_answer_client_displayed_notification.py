"""Chat answer pushes use the client-displayed FCM path (#4375)."""

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
def _loaded_chat_answer_notifications() -> Iterator[ModuleType]:
    messaging = _messaging_module()
    firebase_admin = _module('firebase_admin', messaging=messaging)
    notification_db = _module(
        'database.notifications',
        get_all_tokens=lambda _uid: ['device-token'],
        remove_bulk_tokens=lambda _tokens: None,
    )

    with stub_modules(
        {
            'firebase_admin': firebase_admin,
            'firebase_admin.messaging': messaging,
            'database.notifications': notification_db,
        }
    ):
        yield load_module_fresh(
            'utils.chat_answer_notifications',
            BACKEND_DIR / 'utils' / 'chat_answer_notifications.py',
        )


def test_stringify_fcm_data_coerces_values_to_strings():
    with _loaded_chat_answer_notifications() as notifications:
        out = notifications._stringify_fcm_data({'a': 1, 'b': None, 'c': True, 'd': 'x'})
        assert out == {'a': '1', 'b': '', 'c': 'True', 'd': 'x'}


def test_build_client_displayed_message_omits_top_level_notification():
    with _loaded_chat_answer_notifications() as notifications:
        data = {
            'push_type': 'chat_answer',
            'title': 'omi says',
            'body': 'Long answer that should expand',
            'navigate_to': '/chat/omi',
            'notification_type': 'plugin',
        }
        msg = notifications._build_client_displayed_message(
            token='token-1',
            tag='tag-1',
            title='omi says',
            body='Long answer that should expand',
            data=data,
        )
        assert msg.notification is None
        assert msg.data['navigate_to'] == '/chat/omi'
        assert msg.data['push_type'] == 'chat_answer'
        assert msg.android is not None
        assert getattr(msg.android, 'notification', None) is None
        assert msg.apns is not None
        assert msg.apns.payload.aps.alert.title == 'omi says'
        assert msg.apns.payload.aps.alert.body == 'Long answer that should expand'


def test_send_client_displayed_notification_sets_push_type():
    with _loaded_chat_answer_notifications() as notifications:
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
            {'notification_type': 'plugin', 'navigate_to': '/chat/omi', 'id': 'msg-1'},
        )

        assert len(captured['messages']) == 1
        msg = captured['messages'][0]
        assert msg.notification is None
        assert msg.data['push_type'] == 'chat_answer'
        assert msg.data['title'] == 'omi says'
        assert msg.data['body'] == 'Answer body'
        assert msg.data['navigate_to'] == '/chat/omi'
