import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _set_module(name, module):
    sys.modules[name] = module
    parent_name, _, attr_name = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr_name, module)


def _drop_module(name):
    module = sys.modules.pop(name, None)
    parent_name, _, attr_name = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if module is not None and parent is not None and getattr(parent, attr_name, None) is module:
        delattr(parent, attr_name)
    return module


def _restore_module(name, module):
    if module is None:
        _drop_module(name)
        return
    _set_module(name, module)


def _ensure_package(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType):
        module = types.ModuleType(name)
        _set_module(name, module)
    module.__path__ = [str(path)]
    parent_name, _, attr_name = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr_name, module)
    return module


_ensure_package("database", BACKEND_DIR / "database")
_ensure_package("utils", BACKEND_DIR / "utils")
_ensure_package("utils.llm", BACKEND_DIR / "utils" / "llm")


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

notification_db = types.ModuleType("database.notifications")
notification_db.get_all_tokens = MagicMock()
notification_db.remove_bulk_tokens = MagicMock()

redis_db = types.ModuleType("database.redis_db")
for attr in [
    "set_credit_limit_notification_sent",
    "has_credit_limit_notification_been_sent",
    "set_silent_user_notification_sent",
    "has_silent_user_notification_been_sent",
]:
    setattr(redis_db, attr, MagicMock())

auth_db = types.ModuleType("database.auth")
auth_db.get_user_from_uid = MagicMock()

llm_notifications = types.ModuleType("utils.llm.notifications")
for attr in [
    "generate_notification_message",
    "generate_credit_limit_notification",
    "generate_silent_user_notification",
]:
    setattr(llm_notifications, attr, MagicMock())

_module_overrides = {
    "firebase_admin": firebase_admin,
    "firebase_admin.auth": firebase_admin.auth,
    "firebase_admin.messaging": firebase_admin.messaging,
    "database.notifications": notification_db,
    "database.redis_db": redis_db,
    "database.auth": auth_db,
    "utils.llm.notifications": llm_notifications,
}
_previous_modules = {name: sys.modules.get(name) for name in [*list(_module_overrides), "utils.notifications"]}

_drop_module("utils.notifications")
for _name, _module in _module_overrides.items():
    _set_module(_name, _module)

from utils import notifications

for _name, _module in _previous_modules.items():
    _restore_module(_name, _module)


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
