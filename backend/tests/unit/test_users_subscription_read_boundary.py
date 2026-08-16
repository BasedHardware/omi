"""Subscriptions preserve strict corruption semantics at the Firestore read boundary."""

from unittest.mock import patch

import pytest

import database.read_boundary as read_boundary
import database.users as users_db


class _Snapshot:
    exists = True
    id = 'user-1'

    def to_dict(self):
        return {'subscription': ['not-a-mapping']}


class _Database:
    def collection(self, *_args):
        return self

    def document(self, *_args):
        return self

    def get(self, *_args, **_kwargs):
        return _Snapshot()


def test_existing_subscription_with_malformed_payload_raises_typed_error(monkeypatch):
    monkeypatch.setattr(users_db, 'db', _Database())

    with patch.object(read_boundary, 'record_fallback') as fallback:
        with pytest.raises(read_boundary.MalformedDocError):
            users_db.get_existing_user_subscription('user-1')

    fallback.assert_not_called()
