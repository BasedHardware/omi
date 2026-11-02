"""Open-loop Review card routes: listing, answering, gating, and wire hygiene.

The service functions are pinned by ``test_open_loops_service.py``; these tests
pin the HTTP wiring: the standard user dependency, the ``OPEN_LOOPS_ENABLED``
kill switch (off → empty list / 404), 422 on an unknown action or a malformed
date/card id (never a Firestore error), the 404/409 mapping for missing vs
already-answered cards, and that only the card writer's rendered fields cross
the wire.
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
# The id formats the pass writes: store.stable_key ids and task-born loop ids.
CARD_ID = 'ol-0123456789abcdef'
TASK_CARD_ID = 'task-550e8400-e29b-41d4-a716-446655440000'


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


def test_get_lists_pending_cards_for_the_resolved_day(client, monkeypatch):
    # The service already resolves the producer's day (with fallback) and
    # filters to pending cards in pass order; the route maps that list.
    owner_listing = Mock(return_value=(DATE_STR, [_stored_card('a'), _stored_card('c')]))
    monkeypatch.setattr(router.open_loops_service, 'list_owner_pending_cards', owner_listing)
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', lambda uid: 'America/New_York')

    response = client.get('/v1/review/open-loops')

    assert response.status_code == 200
    body = response.json()
    # Only pending cards cross the wire, in pass order, under wire field names.
    assert [(card['card_id'], card['date']) for card in body['cards']] == [('a', DATE_STR), ('c', DATE_STR)]
    assert body['cards'][0]['question'] == 'Did Maya send the vendor write-up?'
    assert body['cards'][0]['context_line'] == "From Monday's Pricing sync, due Tuesday"
    owner_listing.assert_called_once_with(UID, tz='America/New_York')


def test_get_reports_the_fallback_day_on_the_cards(client, monkeypatch):
    """When the service falls back to a previous day's document, the wire's
    date — the app's answer path — is that day, not the resolved one."""
    monkeypatch.setattr(
        router.open_loops_service, 'list_owner_pending_cards', Mock(return_value=('2026-10-24', [_stored_card('a')]))
    )
    body = client.get('/v1/review/open-loops').json()
    assert body['cards'][0]['date'] == '2026-10-24'


def test_get_never_returns_server_only_card_fields(client, monkeypatch):
    monkeypatch.setattr(
        router.open_loops_service, 'list_owner_pending_cards', Mock(return_value=(DATE_STR, [_stored_card()]))
    )
    body = client.get('/v1/review/open-loops').json()
    assert set(body['cards'][0]) == {'card_id', 'date', 'question', 'context_line'}


def test_get_resolves_the_zone_from_request_then_profile(client, monkeypatch):
    owner_listing = Mock(return_value=(DATE_STR, []))
    monkeypatch.setattr(router.open_loops_service, 'list_owner_pending_cards', owner_listing)
    stored = Mock(return_value='America/New_York')
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', stored)

    # A valid request zone wins over the stored profile zone…
    client.get('/v1/review/open-loops', params={'time_zone': 'Europe/Berlin'})
    assert owner_listing.call_args.kwargs['tz'] == 'Europe/Berlin'
    # …an invalid one is ignored in favor of the profile zone…
    client.get('/v1/review/open-loops', params={'time_zone': 'Mars/Olympus'})
    assert owner_listing.call_args.kwargs['tz'] == 'America/New_York'
    # …and without either, UTC.
    monkeypatch.setattr(router.notification_db, 'get_user_time_zone', lambda uid: None)
    client.get('/v1/review/open-loops')
    assert owner_listing.call_args.kwargs['tz'] is None
    stored.assert_called_once_with(UID)


def test_get_kill_switch_off_returns_empty_list_without_reading_cards(client, monkeypatch):
    monkeypatch.setenv('OPEN_LOOPS_ENABLED', 'off')
    owner_listing = Mock(return_value=(DATE_STR, [_stored_card()]))
    monkeypatch.setattr(router.open_loops_service, 'list_owner_pending_cards', owner_listing)

    response = client.get('/v1/review/open-loops')

    assert response.status_code == 200 and response.json() == {'cards': []}
    owner_listing.assert_not_called()


def test_get_requires_auth(harness):
    app, _ = harness
    del app.dependency_overrides[router.auth.get_current_user_uid]
    app.dependency_overrides[router.auth.request_read_scope] = lambda: None
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get('/v1/review/open-loops').status_code == 401


@pytest.mark.parametrize('card_id', [CARD_ID, TASK_CARD_ID])
@pytest.mark.parametrize('action,state', [('done', 'done'), ('remind', 'remind'), ('drop', 'dropped')])
def test_answer_wires_each_action_into_the_service(client, monkeypatch, card_id, action, state):
    answered = Mock(return_value=_stored_card(card_id, state=state))
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{card_id}/answer', json={'action': action})

    assert response.status_code == 200
    assert response.json() == {'card_id': card_id, 'date': DATE_STR, 'state': state}
    answered.assert_called_once_with(UID, card_id, action, date_str=DATE_STR)


def test_answer_rejects_an_unknown_action_with_422(client, monkeypatch):
    answered = Mock()
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{CARD_ID}/answer', json={'action': 'snooze'})

    assert response.status_code == 422
    answered.assert_not_called()


@pytest.mark.parametrize(
    'bad_date',
    ['2026-13-01', '2026-02-30', '26-10-2026', '2026-1-1', 'not-a-date', '2026-10-26x', '20261026'],
)
def test_answer_rejects_a_malformed_date_with_422_before_any_read(client, monkeypatch, bad_date):
    """The date is the cards document's id: garbage must die as a client error,
    never as a Firestore store failure."""
    answered = Mock()
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{bad_date}/{CARD_ID}/answer', json={'action': 'done'})

    assert response.status_code == 422 and response.json()['detail'] == 'invalid_open_loop_date'
    answered.assert_not_called()


@pytest.mark.parametrize(
    'bad_card_id',
    ['ol-1', 'OL-0123456789abcdef', 'ol-0123456789abcdeff', 'task-', 'tasks-7', 'drop', 'task-' + 'x' * 65],
)
def test_answer_rejects_a_card_id_the_pass_never_writes(client, monkeypatch, bad_card_id):
    """Card ids are loop ids ('ol-<16 hex>' or 'task-<task id>'); anything else
    is a client error before any read."""
    answered = Mock()
    monkeypatch.setattr(router.open_loops_service, 'answer_card', answered)

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{bad_card_id}/answer', json={'action': 'done'})

    assert response.status_code == 422 and response.json()['detail'] == 'invalid_open_loop_card_id'
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

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{CARD_ID}/answer', json={'action': 'done'})

    assert response.status_code == 404 and response.json()['detail'] == 'open_loops_disabled'
    answered.assert_not_called()


def test_answer_missing_card_maps_to_404(client, monkeypatch):
    monkeypatch.setattr(router.open_loops_service, 'answer_card', Mock(return_value=None))
    monkeypatch.setattr(router, 'get_open_loop_cards', Mock(return_value=None))

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{CARD_ID}/answer', json={'action': 'done'})

    assert response.status_code == 404 and response.json()['detail'] == 'open_loop_card_not_found'


def test_answer_already_answered_card_maps_to_409(client, monkeypatch):
    monkeypatch.setattr(router.open_loops_service, 'answer_card', Mock(return_value=None))
    monkeypatch.setattr(router, 'get_open_loop_cards', Mock(return_value=[_stored_card(CARD_ID, state='done')]))

    response = client.post(f'/v1/review/open-loops/{DATE_STR}/{CARD_ID}/answer', json={'action': 'remind'})

    assert response.status_code == 409 and response.json()['detail'] == 'open_loop_card_already_answered'


def test_review_surface_off_hides_the_open_loop_routes(client, monkeypatch):
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')

    assert client.get('/v1/review/open-loops').status_code == 404
    assert client.post(f'/v1/review/open-loops/{DATE_STR}/{CARD_ID}/answer', json={'action': 'done'}).status_code == 404
