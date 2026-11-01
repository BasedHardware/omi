from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.proactivity import ProactivityFeedResponse, ProactivityOutcomeRequest
from routers import proactivity as routes


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    # Override the actual composed auth dependency rather than global Firebase state.
    for route in routes.router.routes:
        for dep in route.dependant.dependencies:
            app.dependency_overrides[dep.call] = lambda: 'u'
    return TestClient(app)


def test_outcome_wire_rejects_null_server_and_unknown_fields():
    body = dict(event_id=str(uuid4()), action='opened', surface='ios', channel='feed')
    assert ProactivityOutcomeRequest(**body).action == 'opened'
    for patch in [{'channel': None}, {'surface': 'server'}, {'cost': 0}, {'uid': 'another'}]:
        with pytest.raises(ValidationError):
            ProactivityOutcomeRequest(**dict(body, **patch))


def test_feed_has_no_nullable_wire_fields():
    wire = ProactivityFeedResponse(
        enabled=False, items=[], next_cursor='', has_more=False, server_time=datetime.now(timezone.utc)
    ).model_dump(mode='json')
    assert all(value is not None for value in wire.values())
    assert wire['server_time'].endswith('Z')


def test_stub_feed_is_disabled_with_no_items_and_no_flag_or_ledger_access():
    with _app() as client:
        response = client.get('/v1/proactivity/feed')
        assert response.status_code == 200
        body = response.json()
        assert body['enabled'] is False and body['items'] == []
        assert body['schema_version'] == 1
        # The stub must never depend on the flag service or item storage: an
        # offline lookup stays a decode-able disabled feed, not a 503.
        assert 'flag_unavailable' not in body


def test_stub_outcome_is_a_recorded_no_op_for_any_released_action():
    with _app() as client:
        for action in ['shown', 'opened', 'accepted', 'thumbs_up', 'replied', 'thumbs_down', 'dismissed', 'timeout']:
            response = client.post(
                '/v1/proactivity/items/0123456789abcdef0123456789abcdef/outcomes',
                json=dict(event_id=str(uuid4()), action=action, surface='macos', channel='feed'),
            )
            assert response.status_code == 200
            assert response.json() == {
                'item_id': '0123456789abcdef0123456789abcdef',
                'recorded': False,
                'acted_24h': False,
                'negative': False,
            }


def test_stub_outcome_rejects_unknown_wire_values():
    with _app() as client:
        response = client.post(
            '/v1/proactivity/items/x/outcomes',
            json=dict(event_id=str(uuid4()), action='opened', surface='server', channel='feed'),
        )
        assert response.status_code == 422
