from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.proactivity import ProactivityFeedResponse, ProactivityOutcomeRequest
from routers import proactivity as routes
from utils.other import endpoints as auth
from tests.unit.test_proactivity_v2_budget import store


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
    monkeypatch.setattr(routes.proactivity_flags, 'enabled', lambda uid: False)
    with TestClient(app) as client:
        assert client.get('/v1/proactivity/feed').json()['enabled'] is False

        def unavailable(uid):
            raise ConnectionError('offline')

        monkeypatch.setattr(routes.proactivity_flags, 'enabled', unavailable)
        assert client.get('/v1/proactivity/feed').status_code == 503


def test_mentor_push_keeps_released_client_chat_route():
    payload = routes.proactivity.push_payload(
        dict(item_id='item', source_kind='conversation', source_id='source', producer='conversation_mentor_v2')
    )
    assert payload['navigate_to'] == '/chat/mentor'
    assert payload['item_id'] == 'item' and payload['target_id'] == 'source'
    assert payload['notification_type'] != 'plugin'  # Generic preview must not become a duplicate chat message.


def test_timeout_first_id_conflicts_over_real_outcome_route(store, monkeypatch):
    from tests.unit.test_proactivity_v2_ledger import ready
    from tests.unit.test_proactivity_v2_budget import NOW

    item = ready(store)
    app = FastAPI()
    app.include_router(routes.router)
    for route in routes.router.routes:
        for dep in route.dependant.dependencies:
            app.dependency_overrides[dep.call] = lambda: 'u'
    monkeypatch.setattr(routes.ledger, 'client_or_default', lambda client=None: store)
    monkeypatch.setattr(routes.ledger, 'utc_now', lambda: NOW)
    body = dict(event_id=str(uuid4()), action='timeout', surface='ios', channel='feed')
    url = f"/v1/proactivity/items/{item['item_id']}/outcomes"
    with TestClient(app) as client:
        first = client.post(url, json=body)
        assert first.status_code == 200 and first.json()['recorded']
        assert not client.post(url, json=body).json()['recorded']
        conflict = client.post(url, json=dict(body, action='opened'))
        assert conflict.status_code == 409 and conflict.json()['detail'] == 'event_conflict'


def test_shared_producer_targets_and_push_match_public_wire():
    import json
    from pathlib import Path
    from models.proactivity import ProactivityFeedItem

    fixture = json.loads((Path(__file__).parents[3] / 'contracts/parity/proactivity_v2.json').read_text())
    items = [ProactivityFeedItem(**item) for item in fixture['producer_items']]
    assert [(i.producer, i.target.kind) for i in items] == [
        ('conversation_mentor_v2', 'conversation'),
        ('commitment_followup', 'action_item'),
    ]
    mentor = items[0]
    assert (
        routes.proactivity.push_payload(
            dict(
                item_id=mentor.id, source_kind=mentor.target.kind, source_id=mentor.target.id, producer=mentor.producer
            )
        )
        == fixture['mentor_push']
    )


@pytest.mark.asyncio
async def test_push_wakeup_obeys_admission_and_never_counts_exposure(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus

    service = routes.proactivity
    item = dict(uid='u', item_id='item', producer='conversation_mentor_v2', source_kind='conversation', source_id='c')
    monkeypatch.setattr(service, 'ensure_admitted', AsyncMock())
    monkeypatch.setattr(service, '_push_preferences', Mock())
    monkeypatch.setattr(service.ledger, 'claim_push', Mock(return_value=item))
    validate = Mock()
    monkeypatch.setattr(service.ledger, 'validate_push', validate)
    finish = Mock()
    monkeypatch.setattr(service.ledger, 'finish_push', finish)
    wakeup = Mock()
    monkeypatch.setattr(service, '_publish_listen_wakeup', wakeup)
    dispatch = AsyncMock(return_value=NotificationDispatchOutcome(NotificationDispatchStatus.DISPATCHED, delivered=1))
    monkeypatch.setattr(service, 'dispatch_notification_async', dispatch)
    await service.push_item(item=item)
    wakeup.assert_called_once_with('u', service.push_payload(item))
    assert dispatch.call_args.args[0].data == service.push_payload(item)
    finish.assert_called_once_with(uid='u', item_id='item', status='accepted')
    validate.side_effect = service.ProactivityDenied('disabled')
    wakeup.reset_mock()
    dispatch.reset_mock()
    await service.push_item(item=item)
    wakeup.assert_not_called()
    dispatch.assert_not_called()


def test_feed_and_outcome_use_dedicated_flag_token_without_v2_redis(store, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from database import proactivity_redis
    from tests.unit.test_proactivity_v2_budget import NOW
    from tests.unit.test_proactivity_v2_ledger import ready

    flags = routes.proactivity_flags
    flags.flag_client.cache_clear()
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_TOKEN', 'phc_dedicated-v2-token')
    monkeypatch.setenv('POSTHOG_API_KEY', 'test-existing-posthog-key')
    monkeypatch.setenv('POSTHOG_EVENTS_API_KEY', 'test-events-key-must-not-select-flags')
    monkeypatch.setenv('POSTHOG_HOST', 'https://shared-host.invalid')
    monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_HOST', 'https://us.posthog.com')
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    for key in ('HOST', 'PORT', 'PASSWORD'):
        monkeypatch.delenv(f'PROACTIVITY_REDIS_{key}', raising=False)
    v2_client = Mock(side_effect=AssertionError('feed/outcome must not acquire Redis'))
    monkeypatch.setattr(proactivity_redis, 'get_client', v2_client)
    flag_client = Mock()
    flag_client.get_feature_variants.return_value = {'proactivity_v2': True}
    factory = Mock(return_value=flag_client)
    monkeypatch.setattr(
        flags, 'importlib', SimpleNamespace(import_module=lambda name: SimpleNamespace(Posthog=factory))
    )
    item = ready(store)
    monkeypatch.setattr(routes.ledger, 'client_or_default', lambda client=None: store)
    monkeypatch.setattr(routes.ledger, 'utc_now', lambda: NOW)
    feed_read = Mock(return_value=([], '', False))
    monkeypatch.setattr(routes.ledger, 'list_feed', feed_read)
    app = FastAPI()
    app.include_router(routes.router)
    for route in routes.router.routes:
        for dep in route.dependant.dependencies:
            app.dependency_overrides[dep.call] = lambda: 'u'
    try:
        with TestClient(app) as client:
            response = client.get('/v1/proactivity/feed')
            assert response.status_code == 200 and response.json()['enabled'] is True
            response = client.post(
                f"/v1/proactivity/items/{item['item_id']}/outcomes",
                json=dict(event_id=str(uuid4()), action='opened', surface='macos', channel='feed'),
            )
            assert response.status_code == 200 and response.json()['recorded'] is True
        assert flags.mentor_pipeline('u') == 'v2'
        factory.assert_called_once_with(
            project_api_key='phc_dedicated-v2-token',
            host='https://us.posthog.com',
            send=False,
            sync_mode=True,
            feature_flags_request_timeout_seconds=2,
        )
        feed_read.assert_called_once_with(uid='u', limit=20, cursor='')
        v2_client.assert_not_called()
    finally:
        flags.flag_client.cache_clear()
