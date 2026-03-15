import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


class _FakeMessagingException(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _FakeResponse:
    def __init__(self, success, exception=None):
        self.success = success
        self.exception = exception


class _FakeBatchResponse:
    def __init__(self, responses):
        self.responses = responses


class _FakeNotification:
    def __init__(self, title, body):
        self.title = title
        self.body = body


firebase_admin = types.ModuleType("firebase_admin")
firebase_admin.auth = MagicMock()
firebase_admin.messaging = types.SimpleNamespace(
    send_each=MagicMock(),
    Notification=_FakeNotification,
    AndroidConfig=lambda **kwargs: kwargs,
    AndroidNotification=lambda **kwargs: kwargs,
    APNSConfig=lambda **kwargs: kwargs,
    APNSPayload=lambda **kwargs: kwargs,
    Aps=lambda **kwargs: kwargs,
    WebpushConfig=lambda **kwargs: kwargs,
    WebpushNotification=lambda **kwargs: kwargs,
    WebpushFCMOptions=lambda **kwargs: kwargs,
    Message=lambda **kwargs: kwargs,
)
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin.auth
sys.modules["firebase_admin.messaging"] = firebase_admin.messaging

notification_db = types.ModuleType("database.notifications")
notification_db.get_all_tokens = MagicMock()
notification_db.remove_bulk_tokens = MagicMock()
sys.modules["database.notifications"] = notification_db

redis_db = types.ModuleType("database.redis_db")
for attr in [
    "set_credit_limit_notification_sent",
    "has_credit_limit_notification_been_sent",
    "set_silent_user_notification_sent",
    "has_silent_user_notification_been_sent",
]:
    setattr(redis_db, attr, MagicMock())
sys.modules["database.redis_db"] = redis_db

auth_db = types.ModuleType("database.auth")
auth_db.get_user_from_uid = MagicMock()
sys.modules["database.auth"] = auth_db

llm_notifications = types.ModuleType("utils.llm.notifications")
for attr in [
    "generate_notification_message",
    "generate_credit_limit_notification",
    "generate_silent_user_notification",
]:
    setattr(llm_notifications, attr, MagicMock())
sys.modules["utils.llm.notifications"] = llm_notifications

from utils import notifications


def setup_function():
    notification_db.get_all_tokens.reset_mock()
    notification_db.remove_bulk_tokens.reset_mock()
    firebase_admin.messaging.send_each.reset_mock()


def test_send_notification_removes_not_found_tokens():
    tokens = ["dead-token", "live-token"]
    notification_db.get_all_tokens.return_value = tokens
    firebase_admin.messaging.send_each.return_value = _FakeBatchResponse(
        [
            _FakeResponse(success=False, exception=_FakeMessagingException("NOT_FOUND")),
            _FakeResponse(success=True),
        ]
    )

    notifications.send_notification("user-1", "omi", "hello")

    notification_db.remove_bulk_tokens.assert_called_once_with(["dead-token"])


def test_send_notification_keeps_transient_failures():
    tokens = ["retry-token"]
    notification_db.get_all_tokens.return_value = tokens
    firebase_admin.messaging.send_each.return_value = _FakeBatchResponse(
        [_FakeResponse(success=False, exception=_FakeMessagingException("UNAUTHENTICATED"))]
    )

    notifications.send_notification("user-1", "omi", "hello")

    notification_db.remove_bulk_tokens.assert_not_called()
