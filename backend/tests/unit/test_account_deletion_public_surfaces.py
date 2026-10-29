"""Public links disappear as soon as their owner enters account deletion."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from routers import chat, users


def test_pending_owner_cannot_read_an_existing_shared_chat_link(monkeypatch):
    monkeypatch.setattr(
        chat,
        'get_chat_share',
        lambda _token: {'uid': 'owner', 'message_ids': ['message-1'], 'display_name': 'Owner'},
    )
    monkeypatch.setattr(chat, 'account_deletion_blocks_user_work', lambda _uid: True)
    monkeypatch.setattr(chat.chat_db, 'get_message', Mock())

    with pytest.raises(HTTPException) as error:
        chat.get_shared_chat_messages('share-token')

    assert error.value.status_code == 404
    chat.chat_db.get_message.assert_not_called()


def test_pending_owner_cannot_read_an_existing_shared_daily_summary(monkeypatch):
    monkeypatch.setattr(users, 'get_daily_summary_uid', lambda _summary_id: 'owner')
    monkeypatch.setattr(users, 'account_deletion_blocks_user_work', lambda _uid: True)
    monkeypatch.setattr(users.daily_summaries_db, 'get_daily_summary', Mock())

    with pytest.raises(HTTPException) as error:
        users.get_shared_daily_summary('summary-id')

    assert error.value.status_code == 404
    users.daily_summaries_db.get_daily_summary.assert_not_called()
