"""Regression coverage for app API-key revocation reporting success without a deletion.

The app treats any 2xx from ``DELETE /v1/apps/{app_id}/keys/{key_id}`` as a confirmed
revocation: ``AddAppProvider.deleteApiKey`` awaits ``deleteApiKeyServer`` (which only
throws on a non-200) and ``ApiKeysWidget`` then shows "API key revoked successfully".
The route used to drop ``delete_api_key_db``'s result and answer 200 even when no key
document was removed, so a failed revocation was indistinguishable from a real one.
"""

from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from database import apps as apps_db
from routers import apps as apps_routes

APP_ID = 'app-1'
KEY_ID = 'key-1'
UID = 'user-1'


class _Snapshot:
    def __init__(self, exists: bool):
        self.exists = exists


class _Document:
    def __init__(self, stored_keys: set, key_id: str):
        self.stored_keys = stored_keys
        self.key_id = key_id
        self.delete_calls = 0

    def get(self, transaction=None):
        return _Snapshot(self.key_id in self.stored_keys)

    def delete(self):
        self.delete_calls += 1
        self.stored_keys.discard(self.key_id)


class _KeysCollection:
    def __init__(self, firestore: '_FakeFirestore'):
        self.firestore = firestore

    def document(self, key_id: str) -> _Document:
        return self.firestore.key_documents.setdefault(key_id, _Document(self.firestore.stored_keys, key_id))


class _AppDocument:
    def __init__(self, firestore: '_FakeFirestore'):
        self.firestore = firestore

    def collection(self, name: str) -> _KeysCollection:
        assert name == 'api_keys'
        return _KeysCollection(self.firestore)


class _FakeFirestore:
    """Only the app -> api_keys subcollection path that revocation walks."""

    def __init__(self, stored_keys: set):
        self.stored_keys = set(stored_keys)
        self.key_documents: dict[str, _Document] = {}
        self.app_document_reads: list[str] = []

    def collection(self, name: str) -> '_FakeFirestore':
        assert name == apps_db.apps_collection
        return self

    def document(self, app_id: str) -> _AppDocument:
        self.app_document_reads.append(app_id)
        return _AppDocument(self)


def test_delete_api_key_db_reports_false_when_the_key_is_absent(monkeypatch):
    firestore = _FakeFirestore(stored_keys=set())
    monkeypatch.setattr(apps_db, 'db', firestore)

    assert apps_db.delete_api_key_db(APP_ID, KEY_ID) is False
    assert firestore.key_documents[KEY_ID].delete_calls == 0


def test_delete_api_key_db_removes_a_stored_key_and_reports_true(monkeypatch):
    firestore = _FakeFirestore(stored_keys={KEY_ID})
    monkeypatch.setattr(apps_db, 'db', firestore)

    assert apps_db.delete_api_key_db(APP_ID, KEY_ID) is True
    assert firestore.key_documents[KEY_ID].delete_calls == 1
    assert firestore.stored_keys == set()


def _own_the_app(monkeypatch):
    monkeypatch.setattr(apps_routes, 'get_available_app_by_id', lambda app_id, uid: {'id': app_id, 'uid': uid})


def test_delete_route_does_not_confirm_a_revocation_that_deleted_nothing(monkeypatch):
    _own_the_app(monkeypatch)
    revoked = MagicMock(return_value=False)
    monkeypatch.setattr(apps_routes, 'delete_api_key_db', revoked)

    with pytest.raises(HTTPException) as caught:
        apps_routes.delete_api_key(APP_ID, KEY_ID, uid=UID)

    assert caught.value.status_code == 404
    assert caught.value.detail == 'API key not found'
    revoked.assert_called_once_with(APP_ID, KEY_ID)


def test_delete_route_confirms_a_revocation_that_deleted_the_key(monkeypatch):
    _own_the_app(monkeypatch)
    monkeypatch.setattr(apps_routes, 'delete_api_key_db', MagicMock(return_value=True))

    assert apps_routes.delete_api_key(APP_ID, KEY_ID, uid=UID) == {'status': 'ok', 'message': 'API key deleted'}
