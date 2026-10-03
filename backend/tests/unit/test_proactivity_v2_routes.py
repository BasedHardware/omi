from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.proactivity import ProactivityFeedResponse, ProactivityOutcomeRequest
from routers import proactivity as routes
from utils.other import endpoints as auth


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


def test_flag_off_empty_and_store_error_is_503(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    # Override the actual composed auth dependency rather than global Firebase state.
    for route in routes.router.routes:
        for dep in route.dependant.dependencies:
            app.dependency_overrides[dep.call] = lambda: 'u'
    monkeypatch.setattr(routes.proactivity, 'enabled', lambda uid: False)
    with TestClient(app) as client:
        assert client.get('/v1/proactivity/feed').json()['enabled'] is False

        def unavailable(uid):
            raise ConnectionError('offline')

        monkeypatch.setattr(routes.proactivity, 'enabled', unavailable)
        assert client.get('/v1/proactivity/feed').status_code == 503


def test_mentor_push_keeps_released_client_chat_route():
    payload = routes.proactivity.push_payload(
        dict(item_id='item', source_kind='conversation', source_id='source', producer='conversation_mentor_v2')
    )
    assert payload['navigate_to'] == '/chat/mentor'
    assert payload['item_id'] == 'item' and payload['target_id'] == 'source'
    assert payload['notification_type'] != 'plugin'  # Generic preview must not become a duplicate chat message.
