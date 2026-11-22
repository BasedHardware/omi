"""The real boundary route validates and persists its authenticated request."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import boundary_evidence as endpoint
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture
def client(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(endpoint.boundary_store, 'get_firestore_client', lambda: store)
    app = FastAPI()
    app.include_router(endpoint.router)
    dependency = endpoint.router.routes[0].dependant.dependencies[0].call
    app.dependency_overrides[dependency] = lambda: 'fixture-owner-39'
    with TestClient(app) as http:
        yield http, store


def test_endpoint_is_idempotent_and_validates_ended_at(client):
    http, store = client
    body = [{'kind': 'desktop_meeting', 'external_id': 'event-test', 'started_at': '2026-10-22T15:00:00Z'}]
    first = http.post('/v1/capture/boundary-evidence', json=body)
    assert first.status_code == 200 and first.json() == {'stored': 1}
    assert http.post('/v1/capture/boundary-evidence', json=body).json() == {'stored': 0}
    body[0]['ended_at'] = '2026-10-22T14:00:00Z'
    assert http.post('/v1/capture/boundary-evidence', json=body).status_code == 422


def test_endpoint_bounds_batches(client):
    http, _ = client
    signal = {'kind': 'phone_call', 'started_at': '2026-10-22T15:00:00Z'}
    assert http.post('/v1/capture/boundary-evidence', json=[signal] * 65).status_code == 422
