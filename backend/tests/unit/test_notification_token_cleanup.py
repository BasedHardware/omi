from unittest.mock import MagicMock

import pytest

from utils import notifications


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


def _make_messaging_fake():
    fake = MagicMock()
    fake.send_each = MagicMock()
    fake.Notification = _FakeNotification
    fake.AndroidConfig = lambda **kwargs: kwargs
    fake.AndroidNotification = lambda **kwargs: kwargs
    fake.APNSConfig = lambda **kwargs: kwargs
    fake.APNSPayload = lambda **kwargs: kwargs
    fake.Aps = lambda **kwargs: kwargs
    fake.WebpushConfig = lambda **kwargs: kwargs
    fake.WebpushNotification = lambda **kwargs: kwargs
    fake.WebpushFCMOptions = lambda **kwargs: kwargs
    fake.Message = lambda **kwargs: kwargs
    return fake


@pytest.fixture
def notification_db(monkeypatch):
    db = MagicMock()
    db.get_all_tokens = MagicMock()
    db.remove_bulk_tokens = MagicMock()
    monkeypatch.setattr(notifications, "notification_db", db)
    return db


@pytest.fixture
def messaging(monkeypatch):
    fake = _make_messaging_fake()
    monkeypatch.setattr(notifications, "messaging", fake)
    return fake


def test_send_notification_removes_not_found_tokens(notification_db, messaging):
    tokens = ["dead-token", "live-token"]
    notification_db.get_all_tokens.return_value = tokens
    messaging.send_each.return_value = _FakeBatchResponse(
        [
            _FakeResponse(success=False, exception=_FakeMessagingException("NOT_FOUND")),
            _FakeResponse(success=True),
        ]
    )

    notifications.send_notification("user-1", "omi", "hello")

    notification_db.remove_bulk_tokens.assert_called_once_with(["dead-token"])


def test_send_notification_keeps_transient_failures(notification_db, messaging):
    tokens = ["retry-token"]
    notification_db.get_all_tokens.return_value = tokens
    messaging.send_each.return_value = _FakeBatchResponse(
        [_FakeResponse(success=False, exception=_FakeMessagingException("UNAUTHENTICATED"))]
    )

    notifications.send_notification("user-1", "omi", "hello")

    notification_db.remove_bulk_tokens.assert_not_called()
