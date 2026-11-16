"""Run the production static return routes without loading payment services.

Only the two dependency-free route ASTs are compiled; all their response bodies
and FastAPI declarations are production code, not copied test implementations.
No Stripe/Firebase client or production account read is needed.
"""

import ast
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    path = Path(__file__).resolve().parents[2] / 'routers' / 'payment.py'
    source = ast.parse(path.read_text())
    routes = [
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in {'stripe_success', 'stripe_cancel'}
    ]
    assert len(routes) == 2
    router = APIRouter()
    namespace = {'router': router, 'HTMLResponse': HTMLResponse, 'Query': Query}
    exec(compile(ast.Module(body=routes, type_ignores=[]), str(path), 'exec'), namespace)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    'path,signal,title',
    [
        ('/v1/payments/success?session_id=private-session', 'client_navigation_completed', 'Payment Successful!'),
        ('/v1/payments/cancel', 'cancelled', 'Payment Cancelled'),
    ],
)
def test_return_page_static_observer_has_no_payment_or_account_data(client, path, signal, title):
    response = client.get(path)
    assert response.status_code == 200
    assert f'<h1>{title}</h1>' in response.text
    assert f"window.opener.postMessage('omi:checkout:{signal}', '*')" in response.text
    assert 'private-session' not in response.text
    assert 'session_id' not in response.text
    assert 'fetch(' not in response.text
    assert 'try {' in response.text  # Isolated/missing opener cannot break the existing landing page.


def test_success_still_requires_its_existing_query_parameter(client):
    assert client.get('/v1/payments/success').status_code == 422
