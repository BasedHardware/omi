"""The on-demand projection trigger exists only in explicit local development."""

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


def test_manual_generation_is_not_part_of_the_openapi_contract():
    app = FastAPI()
    app.include_router(projections.router)

    assert '/v1/users/projections/test' not in app.openapi()['paths']


def test_manual_generation_remains_available_for_local_development(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)
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


def test_hosted_development_hides_manual_generation_even_with_private_storage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('K_SERVICE', 'backend-dev')
    monkeypatch.setattr(projections.projection_storage, 'uses_gcs', lambda: True)

    response = _client().post('/v1/users/projections/test')

    assert response.status_code == 404


def test_non_hosted_dev_stage_does_not_enable_the_local_only_route(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('KUBERNETES_SERVICE_HOST', raising=False)

    response = _client().post('/v1/users/projections/test')

    assert response.status_code == 404
