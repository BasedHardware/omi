from datetime import datetime, timezone
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import people as router_module
from routers.people import _clean_id

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.auth.get_current_user_uid] = lambda: 'test_uid_123'
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_clean_id_helper():
    assert _clean_id(None) == ""
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id("  person_abc  ") == "person_abc"
    assert _clean_id(123) == ""  # non-string


def test_set_person_pinned_success_pin(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        assert uid == 'test_uid_123'
        assert person_id == 'p100'
        assert value is True
        return {'id': 'p100', 'name': 'Maya Chen', 'pinned': True, 'pinned_at': NOW}

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 200
    data = resp.json()
    assert data['id'] == 'p100'
    assert data['name'] == 'Maya Chen'
    assert data['pinned'] is True


def test_set_person_pinned_success_unpin(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        assert uid == 'test_uid_123'
        assert person_id == 'p100'
        assert value is False
        return {'id': 'p100', 'name': 'Maya Chen', 'pinned': False, 'pinned_at': None}

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=false')
    assert resp.status_code == 200
    data = resp.json()
    assert data['id'] == 'p100'
    assert data['name'] == 'Maya Chen'
    assert data['pinned'] is False


def test_set_person_pinned_whitespace_id_returns_400(client):
    resp = client.patch('/v1/users/people/%20%20%20/pinned?value=true')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Invalid person ID'


def test_set_person_pinned_excessive_length_returns_400(client):
    too_long = 'p' * 300
    resp = client.patch(f'/v1/users/people/{too_long}/pinned?value=true')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Invalid person ID'


def test_set_person_pinned_value_error_returns_400(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        raise ValueError("Invalid document ID")

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Invalid person ID'


def test_set_person_pinned_lookup_error_returns_404(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        raise LookupError("Person doc does not exist")

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Person not found'


def test_set_person_pinned_returns_none_returns_404(client, monkeypatch):
    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', lambda uid, pid, val: None)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Person not found'


def test_set_person_pinned_deserialization_empty_returns_404(client, monkeypatch):
    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', lambda uid, pid, val: {'id': pid})
    # 'broken' dictionary missing required fields fails Person.deserialize_many_safe
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Person not found'


def test_set_person_pinned_deserialization_exception_returns_500(client, monkeypatch):
    monkeypatch.setattr(
        router_module.people_db,
        'set_person_pinned',
        lambda uid, pid, val: {'id': 'p100', 'name': 'Maya Chen'},
    )

    def fake_deserialize(items):
        raise RuntimeError("Corrupt memory segment")

    monkeypatch.setattr(router_module.Person, 'deserialize_many_safe', fake_deserialize)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to update person pin status'


def test_set_person_pinned_db_exception_returns_500_masked(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        raise RuntimeError("Firestore socket timeout on collection /users/u/people/secret_internal_table")

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 500
    assert resp.json()['detail'] == 'Failed to update person pin status'
    # Ensure sensitive internal paths are not reflected in response
    assert 'Firestore' not in resp.text
    assert 'secret_internal_table' not in resp.text


def test_set_person_pinned_propagates_http_exception(client, monkeypatch):
    def fake_set_pinned(uid, person_id, value):
        raise HTTPException(status_code=403, detail='Operation forbidden')

    monkeypatch.setattr(router_module.people_db, 'set_person_pinned', fake_set_pinned)
    resp = client.patch('/v1/users/people/p100/pinned?value=true')
    assert resp.status_code == 403
    assert resp.json()['detail'] == 'Operation forbidden'
