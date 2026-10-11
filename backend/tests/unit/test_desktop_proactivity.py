"""Released clients must back off without buying inference or reading accounts."""

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import retired_desktop_proactivity


@pytest.mark.parametrize('authorization', [None, 'Bearer expired-token'])
@pytest.mark.parametrize('body', [b'', b'not json', b'{"operation":"proactive_reasoning"}'])
def test_retirement_accepts_any_body_and_credentials_without_dependencies(authorization, body):
    app = FastAPI()
    app.include_router(retired_desktop_proactivity.router)
    route = next(route for route in app.routes if route.path == '/v1/desktop/proactivity/completions')
    assert route.dependant.dependencies == []
    assert route.dependant.body_params == []
    headers = {'Content-Type': 'application/json'}
    if authorization:
        headers['Authorization'] = authorization
    with TestClient(app) as client:
        response = client.post(route.path, content=body, headers=headers)
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '3600'
    assert response.headers['X-Proactive-Quota-Limit'] == '0'
    assert response.headers['X-Proactive-Quota-Remaining'] == '0'
    assert response.headers['X-Proactive-Quota-Reset'] == '3600'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {'detail': {'error': 'feature_retired', 'feature': 'desktop_proactivity'}}


def test_retirement_module_has_no_account_storage_flags_or_provider_imports():
    tree = ast.parse(Path(retired_desktop_proactivity.__file__).read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert all(isinstance(node, ast.ImportFrom) and node.module.startswith('fastapi') for node in imports)
