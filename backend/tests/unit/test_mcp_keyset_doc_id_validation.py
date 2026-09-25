from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database import action_item_sync, mcp_conversation_pages


def test_mcp_conversation_pages_doc_id_none_raises_value_error():
    client = MagicMock()
    after_ts = datetime.now(timezone.utc)
    # after_id is None
    with pytest.raises(ValueError) as exc:
        mcp_conversation_pages.get_mcp_conversation_cards_page(
            'u1',
            limit=10,
            after=(after_ts, None),
            firestore_client=client,
        )
    assert 'conversation keyset doc id is invalid' in str(exc.value)


def test_mcp_conversation_pages_doc_id_non_string_raises_value_error():
    client = MagicMock()
    after_ts = datetime.now(timezone.utc)
    # after_id is int
    with pytest.raises(ValueError) as exc:
        mcp_conversation_pages.get_mcp_conversation_cards_page(
            'u1',
            limit=10,
            after=(after_ts, 12345),
            firestore_client=client,
        )
    assert 'conversation keyset doc id is invalid' in str(exc.value)


def test_action_item_sync_doc_id_none_raises_value_error():
    client = MagicMock()
    after_dt = datetime.now(timezone.utc)
    # after_id is None
    with pytest.raises(ValueError) as exc:
        action_item_sync.get_action_items_sync_page(
            'u1',
            limit=10,
            after=(after_dt, None),
            firestore_client=client,
        )
    assert 'action item sync doc id is invalid' in str(exc.value)


def test_action_item_sync_doc_id_non_string_raises_value_error():
    client = MagicMock()
    after_dt = datetime.now(timezone.utc)
    # after_id is int
    with pytest.raises(ValueError) as exc:
        action_item_sync.get_action_items_sync_page(
            'u1',
            limit=10,
            after=(after_dt, 12345),
            firestore_client=client,
        )
    assert 'action item sync doc id is invalid' in str(exc.value)
