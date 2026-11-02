"""The server preferred summary app can be set and cleared (back to Omi's own summary)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from database import redis_db
from routers import users as users_router

UID = 'uid-preferred-app'


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def set(self, key, value):
        self.store[key] = value.encode() if isinstance(value, str) else value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


def test_clear_removes_the_stored_preference(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake)
    redis_db.set_user_preferred_app(UID, 'template-app')
    assert redis_db.get_user_preferred_app(UID) == 'template-app'

    redis_db.clear_user_preferred_app(UID)

    assert redis_db.get_user_preferred_app(UID) is None
    assert fake.deleted == [f'user:{UID}:preferred_app']


def test_clear_is_idempotent(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake)
    redis_db.clear_user_preferred_app(UID)
    redis_db.clear_user_preferred_app(UID)
    assert redis_db.get_user_preferred_app(UID) is None


def test_delete_route_clears_for_the_caller(monkeypatch):
    cleared: list[str] = []
    monkeypatch.setattr(users_router, 'clear_user_preferred_app', cleared.append)

    response = users_router.clear_preferred_app_for_user(uid=UID)

    assert cleared == [UID]
    assert response['status'] == 'ok'


def test_delete_route_reports_a_store_failure(monkeypatch):
    def fail(uid):
        raise RuntimeError('redis down')

    monkeypatch.setattr(users_router, 'clear_user_preferred_app', fail)

    with pytest.raises(HTTPException) as exc:
        users_router.clear_preferred_app_for_user(uid=UID)

    assert exc.value.status_code == 500


def test_delete_route_is_registered_beside_put():
    methods = {
        method
        for route in users_router.router.routes
        if getattr(route, 'path', None) == '/v1/users/preferences/app'
        for method in getattr(route, 'methods', set())
    }
    assert {'PUT', 'DELETE'} <= methods
