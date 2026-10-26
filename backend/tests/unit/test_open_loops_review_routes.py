"""Open-loop Review card routes: listing, answering, gating, and wire hygiene.

The service functions are pinned by ``test_open_loops_service.py``; these tests
pin the HTTP wiring: the standard user dependency, the ``OPEN_LOOPS_ENABLED``
kill switch (off → empty list / 404), 422 on an unknown action, the
404/409 mapping for missing vs already-answered cards, and that only the card
writer's rendered fields cross the wire.
"""

from typing import get_args
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.open_loops import OPEN_LOOP_ANSWER_STATE, OpenLoopAnswerRequest
from routers import review as router
from utils.open_loops import service as open_loops_service

UID = 'u1'
DATE_STR = '2026-10-26'


def _stored_card(card_id='ol-1', state='pending', **overrides):
    card = {
        'id': card_id,
        'loop_id': card_id,
        'question': 'Did Maya send the vendor write-up?',
        'context_line': "From Monday's Pricing sync, due Tuesday",
        'source_ref': 'Pricing sync (Monday), 2026-10-20',
        'polished': False,
        'value': 5,
        'state': state,
        'actions': ['done', 'remind', 'drop'],
        'generated_at': '2026-10-26T14:00:00+00:00',
    }
    card.update(overrides)
    return card


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'on')
    # Hermetic: the zone lookup and read-scope cache would otherwise reach Firestore.
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', lambda uid: None)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: UID
    return app, monkeypatch


@pytest.fixture
def client(harness):
    app, _ = harness
    with TestClient(app) as test_client:
        yield test_client


def test_get_lists_pending_cards_for_the_recap_day(client, monkeypatch):
    # The service already filters to pending cards in pass order; the route maps that list.
    listed = Mock(return_value=[_stored_card('a'), _stored_card('c')])
    recap_day = Mock(return_value=DATE_STR)
    monkeypatch.setattr(router.open_loops_service, 'list_pending_cards', listed)
    monkeypatch.setattr(router.open_loops_service, 'recap_completed_day', recap_day)
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', lambda uid: 'America/New_York')

    response = client.get('/v1/review/open-loops')

    assert response.status_code == 200
    body = response.json()
    # Only pending cards cross the wire, in pass order, under wire field names.
    assert [(card['card_id'], card['date']) for card in body['cards']] == [('a', DATE_STR), ('c', DATE_STR)]
    assert body['cards'][0]['question'] == 'Did Maya send the vendor write-up?'
    assert body['cards'][0]['context_line'] == "From Monday's Pricing sync, due Tuesday"


def test_get_never_returns_server_only_card_fields(client, monkeypatch):
    monkeypatch.setattr(router.open_loops_service, 'list_pending_cards', Mock(return_value=[_stored_card()]))
    body = client.get('/v1/review/open-loops').json()
    assert set(body['cards'][0]) == {'card_id', 'date', 'question', 'context_line'}


def test_get_resolves_the_zone_from_request_then_profile(client, monkeypatch):
    listed = Mock(return_value=[])
    monkeypatch.setattr(router.open_loops_service, 'list_pending_cards', listed)
    stored = Mock(return_value='America/New_York')
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', stored)

    # A valid request zone wins over the stored profile zone…
    client.get('/v1/review/open-loops', params={'time_zone': 'Europe/Berlin'})
    assert listed.call_args.kwargs['tz'] == 'Europe/Berlin'
    # …an invalid one is ignored in favor of the profile zone…
    client.get('/v1/review/open-loops', params={'time_zone': 'Mars/Olympus'})
    assert listed.call_args.kwargs['tz'] == 'America/New_York'
    # …and without either, UTC.
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', lambda uid: None)
    client.get('/v1/review/open-loops')
    assert listed.call_args.kwargs['tz'] is None
    stored.assert_called_once_with(UID)


def test_get_kill_switch_off_returns_empty_list_without_reading_cards(client, monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'off')
    listed = Mock(return_value=[_stored_card()])
    monkeypatch.setattr(router.open_loops_service, 'list_pending_cards', listed)

    response = client.get('/v1/review/open-loops')

    assert response.status_code == 200 and response.json() == {'cards': []}
    listed.assert_not_called()


def test_get_requires_auth(harness):
    app, _ = harness
    del app.dependency_overrides[router.auth.get_current_user_uid]
    app.dependency_overrides[router.auth.request_read_scope] = lambda: None
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get('/v1/review/open-loops').status_code == 401


@pytest.mark.parametrize('action,state', [('done', 'done'), ('remind', 'remind'), ('drop', 'dropped')])
def test_answer_wires_each_action_into_the_service(client, monkeypatch, action, state):
    answered = Mock(return_value=_stored_card(state=state))
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': action})

    assert response.status_code == 200
    assert response.json() == {'card_id': 'ol-1', 'date': DATE_STR, 'state': state}
    answered.assert_called_once_with(UID, 'ol-1', action, date_str=DATE_STR)


def test_answer_rejects_an_unknown_action_with_422(client, monkeypatch):
    answered = Mock()
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': 'snooze'})

    assert response.status_code == 422
    answered.assert_not_called()


def test_answer_wire_actions_match_the_service_contract():
    wire_actions = get_args(OpenLoopAnswerRequest.model_fields['action'].annotation)
    assert set(wire_actions) == set(open_loops_service.CARD_ACTIONS)
    # The typed response map must mirror the state the service actually writes.
    assert OPEN_LOOP_ANSWER_STATE == open_loops_service.CARD_STATE_BY_ACTION


def test_answer_kill_switch_off_returns_404(client, monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'off')
    answered = Mock()
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': 'done'})

    assert response.status_code == 404 and response.json()['detail'] == 'open_loops_disabled'
    answered.assert_not_called()


def test_answer_missing_card_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(router.open_loops_service, 'answer_card', Mock(return_value=None))
    monkeypatch.setattr(router, 'get_open_loop_cards', Mock(return_value=None))

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': 'done'})

    assert response.status_code == 404 and response.json()['detail'] == 'open_loop_card_not_found'


def test_answer_already_answered_card_maps_to_409(client, monkeypatch):
    monkeypatch.setattr(router.open_loops_service, 'answer_card', Mock(return_value=None))
    monkeypatch.setattr(router, 'get_open_loop_cards', Mock(return_value=[_stored_card(state='done')]))

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': 'remind'})

    assert response.status_code == 409 and response.json()['detail'] == 'open_loop_card_already_answered'


def test_review_surface_off_hides_the_open_loop_routes(client, monkeypatch):
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')

    assert client.get('/v1/review/open-loops').status_code == 404
    assert client.post(f'/v1/review/open-loops/{DATE_STR}/ol-1/answer', json={'action': 'done'}).status_code == 404
