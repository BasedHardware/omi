"""The on-demand projection trigger is a non-production demo seam."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import projections


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(projections.router)
    app.dependency_overrides[projections.auth.get_current_user_uid] = lambda: 'owner-a'
    return TestClient(app)


def test_manual_generation_is_hidden_in_production(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(
        projections,
        'generate_projection',
        lambda uid: (_ for _ in ()).throw(AssertionError('production must not generate')),
    )

    response = _client().post('/v1/users/projections/test')

    assert response.status_code == 404


def test_manual_generation_remains_available_for_demo(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(
        projections,
        'generate_projection',
        lambda uid: {'id': 'projection-1', 'imperative': 'Cross the threshold.'},
    )
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        projections.projections_db,
        'create_projection',
        lambda uid, projection: persisted.append((uid, projection['id'])),
    )

    response = _client().post('/v1/users/projections/test')

    assert response.status_code == 200
    assert response.json()['id'] == 'projection-1'
    assert persisted == [('owner-a', 'projection-1')]
