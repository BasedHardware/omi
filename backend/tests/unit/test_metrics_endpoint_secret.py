"""`GET /metrics` is the only door to `omi_fallback_total`, and it is shut unless METRICS_SECRET is set.

This fork keeps adding to that counter — `vendor_egress` (ADR-0057), `vector_store` (ADR-0033),
`object_store` (ADR-0032), `stt_selection` — because `docs/agents/fallback-telemetry.md` says a branch that
loses a capability must record it rather than invent a counter. Measured on the live on-prem stack: the
endpoint answered **401 to everyone**, on the backend and on the llm-gateway alike, because METRICS_SECRET
was declared in neither compose nor Helm. Every one of those events existed only in the log. A counter
nobody can scrape is a capability lost in silence, which is the exact thing the counter was added to stop.

The declaration is enforced elsewhere (`check_oss_runtime_env_parity.py`, which failed on METRICS_SECRET
until the env-file and the chart declared it). What these tests pin is the *gate*, including the case that
must NOT change: an unset secret keeps the door shut, which is upstream's own behaviour and the
legacy-principal case `AGENTS.md` asks every fail-closed gate to carry.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = 'a' * 64


def _client(monkeypatch, secret: str | None) -> TestClient:
    """A bare app with just the metrics router, so nothing else's auth is in the way."""
    if secret is None:
        monkeypatch.delenv('METRICS_SECRET', raising=False)
    else:
        monkeypatch.setenv('METRICS_SECRET', secret)
    module = importlib.import_module('routers.metrics')
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def test_unset_secret_shuts_the_door_even_with_a_token(monkeypatch):
    """The legacy principal: a deployment that never set it keeps getting 401, not an open endpoint.

    `if not expected or not hmac.compare_digest(...)` — the empty-string check has to come first, or an
    unset secret would match an empty bearer and expose the metric surface to anything reaching the port.
    """
    client = _client(monkeypatch, None)
    assert client.get('/metrics').status_code == 401
    assert client.get('/metrics', headers={'Authorization': 'Bearer '}).status_code == 401
    assert client.get('/metrics', headers={'Authorization': f'Bearer {SECRET}'}).status_code == 401


def test_the_right_token_opens_it_and_the_body_is_prometheus_text(monkeypatch):
    client = _client(monkeypatch, SECRET)
    response = client.get('/metrics', headers={'Authorization': f'Bearer {SECRET}'})

    assert response.status_code == 200
    assert 'omi_fallback_total' in response.text, 'the counter this endpoint exists to expose'


def test_a_wrong_or_missing_token_is_still_401(monkeypatch):
    client = _client(monkeypatch, SECRET)
    assert client.get('/metrics').status_code == 401
    assert client.get('/metrics', headers={'Authorization': 'Bearer ' + 'b' * 64}).status_code == 401


def test_a_recorded_fallback_reaches_the_exported_body(monkeypatch):
    """The end-to-end point of L43: recording a fallback and being able to READ it are two different
    things, and only the second one was missing. This asserts the whole path in one go."""
    from utils.observability.fallback import record_fallback

    client = _client(monkeypatch, SECRET)
    record_fallback(
        component='vendor_egress',
        from_mode='hume_prosody',
        to_mode='skipped',
        reason='policy',
        outcome='degraded',
    )

    body = client.get('/metrics', headers={'Authorization': f'Bearer {SECRET}'}).text

    assert 'component="vendor_egress"' in body
    assert 'from_mode="hume_prosody"' in body
    assert 'reason="policy"' in body


@pytest.mark.parametrize('module_name', ['routers.metrics', 'llm_gateway.routers.metrics'])
def test_both_processes_gate_the_same_way(monkeypatch, module_name):
    """The gateway is a separate process with its own copy of the route. Declaring the token for one and
    not the other leaves half the stack unreadable — which is why both env-files carry it."""
    monkeypatch.setenv('METRICS_SECRET', SECRET)
    module = importlib.import_module(module_name)
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app)

    assert client.get('/metrics').status_code == 401
    assert client.get('/metrics', headers={'Authorization': f'Bearer {SECRET}'}).status_code == 200
