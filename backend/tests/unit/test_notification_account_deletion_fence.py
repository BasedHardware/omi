"""Every FCM path checks the shared owner fence at the transport boundary."""

import asyncio
from unittest.mock import Mock

import pytest

from utils import notifications


def test_pending_owner_is_suppressed_before_sync_token_lookup_or_send(monkeypatch):
    token_lookup = Mock()
    transport = Mock()
    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', lambda _uid: True)
    monkeypatch.setattr(notifications.notification_db, 'get_all_tokens', token_lookup)
    monkeypatch.setattr(notifications, '_send_messages', transport)

    result = notifications.send_notification_result('pending-owner', 'title', 'body')

    assert result == 0
    token_lookup.assert_not_called()
    transport.assert_not_called()


def test_pending_owner_is_suppressed_before_async_token_lookup_or_send(monkeypatch):
    token_lookup = Mock()
    transport = Mock()
    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', lambda _uid: True)
    monkeypatch.setattr(notifications.notification_db, 'get_all_tokens', token_lookup)
    monkeypatch.setattr(notifications, '_send_messages', transport)

    result = asyncio.run(notifications._send_to_user_async('pending-owner', 'tag'))

    assert result == 0
    token_lookup.assert_not_called()
    transport.assert_not_called()


def test_notification_authority_failure_fails_closed_at_transport(monkeypatch):
    transport = Mock()

    def unavailable(_uid):
        raise RuntimeError('synthetic marker outage')

    monkeypatch.setattr(notifications, 'account_deletion_blocks_user_work', unavailable)
    monkeypatch.setattr(notifications, '_send_messages', transport)

    assert notifications.send_notification_result('owner', 'title', 'body') == 0
    transport.assert_not_called()
