"""Subscriptions preserve strict corruption semantics at the read boundary (WP2 storage port)."""

from unittest.mock import patch

import pytest

import database.read_boundary as read_boundary
import database.users as users_db
from tests.store_fakes import FakeDocumentStore


def test_existing_subscription_with_malformed_payload_raises_typed_error(monkeypatch):
    store = FakeDocumentStore()
    store.set('users/user-1', {'subscription': ['not-a-mapping']})
    monkeypatch.setattr(users_db, '_store', lambda: store)

    with patch.object(read_boundary, 'record_fallback') as fallback:
        with pytest.raises(read_boundary.MalformedDocError):
            users_db.get_existing_user_subscription('user-1')

    fallback.assert_not_called()
