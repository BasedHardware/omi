"""Contract coverage for the advice router's request classification and error boundary.

Two defects shared one cause on ``/v1/advice*``: the route boundary declined to classify
what it already knew. ``DELETE /v1/advice/{advice_id}`` dropped ``advice_db.delete_advice``'s
boolean and answered ``{'status': 'ok'}`` even when no document was removed — the same
"unconfirmed deletion reported as success" shape as ``DELETE /v1/apps/{app_id}/keys/{key_id}``
(see ``test_app_api_key_revoke_contract.py``), so a failed delete was indistinguishable from
a real one. In the same boundary, a whitespace-only path coordinate or an empty PATCH body
reached the data layer as if the caller had said something, and any Firestore failure
escaped as a bare 500 with the raw exception text free to reach the client.

These tests drive the real route functions, and the real ASGI path, and assert the status
codes and messages a client actually receives.
"""

import logging
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from routers import advice as advice_routes

UID = 'user-1'
ADVICE_ID = 'adv-1'


# ============================================================================
# ROUTE LEVEL — the classification decisions
# ============================================================================


def test_delete_route_does_not_confirm_a_delete_that_removed_nothing(monkeypatch):
    removed = MagicMock(return_value=False)
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', removed)

    with pytest.raises(HTTPException) as caught:
        advice_routes.delete_advice(ADVICE_ID, uid=UID)

    assert caught.value.status_code == 404
    assert caught.value.detail == 'Advice not found'
    removed.assert_called_once_with(UID, ADVICE_ID)


def test_delete_route_confirms_a_delete_that_removed_the_advice(monkeypatch):
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', MagicMock(return_value=True))

    assert advice_routes.delete_advice(ADVICE_ID, uid=UID) == {'status': 'ok'}


def test_delete_route_rejects_a_blank_advice_id(monkeypatch):
    removed = MagicMock(return_value=True)
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', removed)

    with pytest.raises(HTTPException) as caught:
        advice_routes.delete_advice('   ', uid=UID)

    assert caught.value.status_code == 400
    assert caught.value.detail == 'Valid advice_id is required'
    removed.assert_not_called()


def test_update_route_requires_at_least_one_field(monkeypatch):
    updated = MagicMock(return_value=None)
    monkeypatch.setattr(advice_routes.advice_db, 'update_advice', updated)

    with pytest.raises(HTTPException) as caught:
        advice_routes.update_advice(ADVICE_ID, advice_routes.UpdateAdviceRequest(), uid=UID)

    assert caught.value.status_code == 400
    assert caught.value.detail == 'At least one of is_read or is_dismissed is required'
    updated.assert_not_called()


def test_update_route_rejects_a_blank_advice_id(monkeypatch):
    updated = MagicMock(return_value=None)
    monkeypatch.setattr(advice_routes.advice_db, 'update_advice', updated)

    with pytest.raises(HTTPException) as caught:
        advice_routes.update_advice('\t', advice_routes.UpdateAdviceRequest(is_read=True), uid=UID)

    assert caught.value.status_code == 400
    updated.assert_not_called()


def test_update_route_still_reports_not_found_for_a_missing_advice(monkeypatch):
    monkeypatch.setattr(advice_routes.advice_db, 'update_advice', MagicMock(return_value=None))

    with pytest.raises(HTTPException) as caught:
        advice_routes.update_advice(ADVICE_ID, advice_routes.UpdateAdviceRequest(is_read=True), uid=UID)

    assert caught.value.status_code == 404
    assert caught.value.detail == 'Advice not found'


def test_create_route_rejects_whitespace_only_content(monkeypatch):
    created = MagicMock(return_value={})
    monkeypatch.setattr(advice_routes.advice_db, 'create_advice', created)

    with pytest.raises(HTTPException) as caught:
        advice_routes.create_advice(advice_routes.CreateAdviceRequest(content='   \n\t '), uid=UID)

    assert caught.value.status_code == 400
    assert caught.value.detail == 'content cannot be empty or whitespace only'
    created.assert_not_called()


def test_create_route_stores_trimmed_content(monkeypatch):
    created = MagicMock(return_value={})
    monkeypatch.setattr(advice_routes.advice_db, 'create_advice', created)

    advice_routes.create_advice(advice_routes.CreateAdviceRequest(content='  Drink water  '), uid=UID)

    assert created.call_args.kwargs['content'] == 'Drink water'


# ============================================================================
# ERROR BOUNDARY — fixed client messages, sanitized server-side detail
# ============================================================================


def _boom(*args, **kwargs):
    raise RuntimeError('firestore deadline exceeded')


@pytest.mark.parametrize(
    'route_call, expected_detail',
    [
        (lambda: advice_routes.delete_advice(ADVICE_ID, uid=UID), 'Failed to delete advice'),
        (
            lambda: advice_routes.update_advice(ADVICE_ID, advice_routes.UpdateAdviceRequest(is_read=True), uid=UID),
            'Failed to update advice',
        ),
        (
            lambda: advice_routes.create_advice(advice_routes.CreateAdviceRequest(content='hi'), uid=UID),
            'Failed to create advice',
        ),
        (lambda: advice_routes.get_advice(uid=UID), 'Failed to load advice'),
        (lambda: advice_routes.mark_all_advice_read(uid=UID), 'Failed to mark advice as read'),
    ],
)
def test_database_faults_become_a_fixed_500_and_log_the_detail(monkeypatch, caplog, route_call, expected_detail):
    for name in ('delete_advice', 'update_advice', 'create_advice', 'get_advice', 'mark_all_advice_read'):
        monkeypatch.setattr(advice_routes.advice_db, name, _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as caught:
            route_call()

    assert caught.value.status_code == 500
    assert caught.value.detail == expected_detail
    # The internal text stays in the log...
    assert 'firestore deadline exceeded' in caplog.text
    # ...and never reaches the client.
    assert 'firestore' not in caught.value.detail
    assert 'deadline' not in caught.value.detail


# ============================================================================
# REAL HTTP PATH — the status code a client actually receives
# ============================================================================


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(advice_routes.router)
    app.dependency_overrides[advice_routes.auth.get_current_user_uid] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


def test_delete_over_http_returns_404_for_an_unknown_advice(monkeypatch):
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', MagicMock(return_value=False))

    response = _client().delete(f'/v1/advice/{ADVICE_ID}')

    assert response.status_code == 404
    assert response.json() == {'detail': 'Advice not found'}


def test_delete_over_http_returns_200_when_the_advice_is_deleted(monkeypatch):
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', MagicMock(return_value=True))

    response = _client().delete(f'/v1/advice/{ADVICE_ID}')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_delete_over_http_rejects_a_whitespace_only_path_coordinate(monkeypatch):
    removed = MagicMock(return_value=True)
    monkeypatch.setattr(advice_routes.advice_db, 'delete_advice', removed)

    response = _client().delete('/v1/advice/%20')

    assert response.status_code == 400
    assert response.json() == {'detail': 'Valid advice_id is required'}
    removed.assert_not_called()


def test_update_over_http_returns_400_for_an_empty_body(monkeypatch):
    updated = MagicMock(return_value=None)
    monkeypatch.setattr(advice_routes.advice_db, 'update_advice', updated)

    response = _client().patch(f'/v1/advice/{ADVICE_ID}', json={})

    assert response.status_code == 400
    assert response.json() == {'detail': 'At least one of is_read or is_dismissed is required'}
    updated.assert_not_called()


def test_update_over_http_returns_200_for_a_real_update(monkeypatch):
    stored = {
        'id': ADVICE_ID,
        'content': 'hi',
        'category': 'other',
        'created_at': '2026-09-28T00:00:00+00:00',
        'updated_at': '2026-09-28T00:00:00+00:00',
        'is_read': True,
    }
    monkeypatch.setattr(advice_routes.advice_db, 'update_advice', MagicMock(return_value=stored))

    response = _client().patch(f'/v1/advice/{ADVICE_ID}', json={'is_read': True})

    assert response.status_code == 200
    assert response.json()['id'] == ADVICE_ID
    assert response.json()['is_read'] is True
