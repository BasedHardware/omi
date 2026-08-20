"""Return-only connector synthesis route uses the managed memories feature."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import integrations as integrations_router
from tests.unit.test_connector_synthesis_helper import byok_rate_limit_error, patch_llm_raising
from utils.llm.connector_synthesis import ConnectorSynthesis, SynthesizedTask

UID = 'uid-connector-synthesis'


def _http_client() -> TestClient:
    """Drive the real route: mounted router, only the auth edge overridden."""
    app = FastAPI()
    app.include_router(integrations_router.router)
    app.dependency_overrides[integrations_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.fixture(autouse=True)
def _entitled(monkeypatch):
    """Default to an entitled account; the paywall gate has its own test."""
    monkeypatch.setattr(integrations_router, 'is_trial_paywalled', lambda uid, platform: False)


async def test_synthesize_connector_data_returns_without_persisting(monkeypatch):
    calls: dict[str, object] = {}

    def fake_synthesize(uid, source, items, **kwargs):
        calls['uid'] = uid
        calls['source'] = source
        calls['items'] = items
        calls['kwargs'] = kwargs
        return ConnectorSynthesis(
            memories=['Runs a weekly standup'],
            tasks=[SynthesizedTask(description='Prep the Q3 demo', priority='high', due_at='2026-08-11T09:00:00Z')],
            profile='Engineering manager.',
        )

    import utils.llm.connector_synthesis as connector_synthesis

    monkeypatch.setattr(connector_synthesis, 'synthesize_connector_items', fake_synthesize)

    response = await integrations_router.synthesize_connector_data(
        integrations_router.ConnectorSynthesisRequest(
            source='calendar',
            items=['[2026-08-11T09:00:00Z] Q3 demo'],
            existing_memories=['Lives in NYC'],
        ),
        uid=UID,
    )

    assert response.memories == ['Runs a weekly standup']
    assert response.tasks[0].description == 'Prep the Q3 demo'
    assert response.tasks[0].priority == 'high'
    assert response.profile == 'Engineering manager.'
    assert calls['uid'] == UID
    assert calls['source'] == 'calendar'
    assert calls['items'] == ['[2026-08-11T09:00:00Z] Q3 demo']
    assert calls['kwargs']['existing_memories'] == ['Lives in NYC']


async def test_synthesize_connector_data_fails_closed_when_synthesis_returns_none(monkeypatch):
    import utils.llm.connector_synthesis as connector_synthesis

    monkeypatch.setattr(connector_synthesis, 'synthesize_connector_items', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await integrations_router.synthesize_connector_data(
            integrations_router.ConnectorSynthesisRequest(source='notes', items=['Bought a piano']),
            uid=UID,
        )
    assert exc.value.status_code == 502


def test_synthesize_connector_data_surfaces_byok_rate_limit_as_429(monkeypatch):
    """A rate-limited BYOK key is a typed, retryable class — not a generic 502.

    Only the provider client is stubbed: the request runs through the real route, the
    real ``synthesize_connector_items`` and the real executor hop, which is where the
    production 502 was manufactured.
    """
    patch_llm_raising(monkeypatch, byok_rate_limit_error())

    response = _http_client().post('/v1/connectors/synthesize', json={'source': 'gmail', 'items': ['From: a']})

    assert response.status_code == 429
    detail = response.json()['detail']
    assert detail['code'] == 'byok_rate_limit'
    assert (
        detail['message'] == 'The configured provider account is rate limited. Please retry later or check its limits.'
    )
    # The provider error body never reaches the client.
    assert 'gateway.test' not in response.text


def test_synthesize_connector_data_keeps_502_for_untyped_failures(monkeypatch):
    import utils.llm.connector_synthesis as connector_synthesis

    monkeypatch.setattr(connector_synthesis, 'synthesize_connector_items', lambda *a, **k: None)

    response = _http_client().post('/v1/connectors/synthesize', json={'source': 'notes', 'items': ['Bought a piano']})

    assert response.status_code == 502
    assert response.json()['detail'] == 'connector_synthesis_failed'


async def test_synthesize_connector_data_blocks_a_trial_expired_account(monkeypatch):
    monkeypatch.setattr(integrations_router, 'is_trial_paywalled', lambda uid, platform: True)

    with pytest.raises(HTTPException) as exc:
        await integrations_router.synthesize_connector_data(
            integrations_router.ConnectorSynthesisRequest(source='notes', items=['Bought a piano']),
            uid=UID,
        )
    assert exc.value.status_code == 402
