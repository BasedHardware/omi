"""Projection feedback is owner-scoped and idempotently replaces the latest signal."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import projections as projections_db
from routers import projections


class _Snapshot:
    def __init__(self, *, exists: bool):
        self.exists = exists


class _ProjectionRef:
    def __init__(self, *, exists: bool):
        self.exists = exists
        self.updates: list[dict] = []

    def get(self):
        return _Snapshot(exists=self.exists)

    def update(self, value: dict):
        self.updates.append(value)


class _Collection:
    def __init__(self, ref: _ProjectionRef):
        self.ref = ref

    def document(self, _identifier: str):
        return self

    def collection(self, _name: str):
        return self

    def get(self):
        return self.ref.get()

    def update(self, value: dict):
        self.ref.update(value)


class _Firestore:
    def __init__(self, ref: _ProjectionRef):
        self.ref = ref

    def collection(self, _name: str):
        return _Collection(self.ref)


def _client(uid: str) -> TestClient:
    app = FastAPI()
    app.include_router(projections.router)
    app.dependency_overrides[projections.auth.get_current_user_uid] = lambda: uid
    return TestClient(app)


def test_database_feedback_replaces_one_owner_scoped_field():
    ref = _ProjectionRef(exists=True)

    assert (
        projections_db.set_projection_feedback(
            'owner-a',
            'projection-1',
            'up',
            firestore_client=_Firestore(ref),
        )
        is True
    )
    assert len(ref.updates) == 1
    assert ref.updates[0]['feedback']['rating'] == 'up'


def test_feedback_route_returns_not_found_across_owner_boundary(monkeypatch):
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        projections.projections_db,
        'set_projection_feedback',
        lambda uid, projection_id, rating: calls.append((uid, projection_id, rating)) or False,
    )

    response = _client('owner-b').post(
        '/v1/users/projections/00000000-0000-0000-0000-000000000001/feedback',
        json={'rating': 'down'},
    )

    assert response.status_code == 404
    assert calls == [('owner-b', '00000000-0000-0000-0000-000000000001', 'down')]


def test_feedback_route_records_valid_owner_signal(monkeypatch):
    monkeypatch.setattr(
        projections.projections_db,
        'set_projection_feedback',
        lambda uid, projection_id, rating: (uid, rating) == ('owner-a', 'up'),
    )

    response = _client('owner-a').post(
        '/v1/users/projections/00000000-0000-0000-0000-000000000001/feedback',
        json={'rating': 'up'},
    )

    assert response.status_code == 200
    assert response.json()['rating'] == 'up'


def test_feedback_route_rejects_unknown_rating_without_writing(monkeypatch):
    monkeypatch.setattr(
        projections.projections_db,
        'set_projection_feedback',
        lambda *_args: (_ for _ in ()).throw(AssertionError('invalid feedback must not write')),
    )

    response = _client('owner-a').post(
        '/v1/users/projections/00000000-0000-0000-0000-000000000001/feedback',
        json={'rating': 'maybe'},
    )

    assert response.status_code == 422
