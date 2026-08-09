"""Return-only connector synthesis route uses the managed memories feature."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import integrations as integrations_router
from utils.llm.connector_synthesis import ConnectorSynthesis, SynthesizedTask

UID = 'uid-connector-synthesis'


def test_synthesize_connector_data_returns_without_persisting(monkeypatch):
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

    response = integrations_router.synthesize_connector_data(
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


def test_synthesize_connector_data_fails_closed_when_synthesis_returns_none(monkeypatch):
    import utils.llm.connector_synthesis as connector_synthesis

    monkeypatch.setattr(connector_synthesis, 'synthesize_connector_items', lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        integrations_router.synthesize_connector_data(
            integrations_router.ConnectorSynthesisRequest(source='notes', items=['Bought a piano']),
            uid=UID,
        )
    assert exc.value.status_code == 502
