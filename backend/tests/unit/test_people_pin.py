from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import people as people_db
from routers import people as router_module
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
PATH = ('users', 'u', 'people', 'p1')


def test_pin_and_unpin_stamp_pinned_at():
    store = StrictFirestore()
    store.rows[PATH] = {'id': 'p1', 'name': 'Maya Chen'}
    pinned = people_db.set_person_pinned('u', 'p1', True, now=NOW, firestore_client=store)
    assert pinned['pinned'] is True and pinned['pinned_at'] == NOW
    assert store.rows[PATH]['pinned'] is True and store.rows[PATH]['pinned_at'] == NOW
    # Pinning again is a no-op that keeps the original timestamp.
    later = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert people_db.set_person_pinned('u', 'p1', True, now=later, firestore_client=store)['pinned_at'] == NOW
    unpinned = people_db.set_person_pinned('u', 'p1', False, now=later, firestore_client=store)
    assert unpinned['pinned'] is False and store.rows[PATH]['pinned_at'] is None
    assert people_db.set_person_pinned('u', 'missing', True, firestore_client=store) is None


def test_pin_cannot_access_another_users_person():
    store = StrictFirestore()
    store.rows[PATH] = {'id': 'p1', 'name': 'Maya Chen'}
    assert people_db.set_person_pinned('other', 'p1', True, firestore_client=store) is None
    assert 'pinned' not in store.rows[PATH]


def _client():
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: 'u'
    return TestClient(app)


def test_pin_route_returns_the_updated_person_and_404s(monkeypatch):
    calls = []

    def fake(uid, person_id, value):
        calls.append((uid, person_id, value))
        if person_id == 'p1':
            return {'id': 'p1', 'name': 'Maya Chen', 'pinned': value, 'pinned_at': NOW if value else None}
        if person_id == 'broken':
            return {'id': 'broken'}
        return None

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake)
    client = _client()
    body = client.patch('/v1/users/people/p1/pinned', params={'value': 'true'}).json()
    assert body['pinned'] is True and body['name'] == 'Maya Chen' and body['confidence'] == 'unknown'
    assert client.patch('/v1/users/people/nobody/pinned', params={'value': 'false'}).status_code == 404
    assert client.patch('/v1/users/people/broken/pinned', params={'value': 'true'}).status_code == 404
    assert client.patch('/v1/users/people/p1/pinned').status_code == 422
    assert calls[0] == ('u', 'p1', True)
