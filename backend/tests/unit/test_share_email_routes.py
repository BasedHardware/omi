"""Route-level contract tests for the meeting-summary share endpoints.

Drives the real mounted router with only the auth edge overridden, so the
recipient-membership rejection and the publish→send→rollback ordering are
exercised through the same code paths the desktop client calls.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import conversations as conversations_router

UID = 'uid-share-email-routes'
CONV_ID = 'conv-share-routes-1'


def _conversation() -> dict:
    return {
        'id': CONV_ID,
        'visibility': 'private',
        'structured': {'title': 'Weekly sync', 'overview': 'Notes'},
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'evt-1',
                'title': 'Weekly sync',
                'participants': [
                    {'name': 'Owner', 'email': 'owner@acme.com'},
                    {'name': 'Sarah Chen', 'email': 'sarah@acme.com'},
                ],
            }
        },
    }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[conversations_router.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_data_layer(monkeypatch):
    state = {'visibility': 'private', 'redis': set(), 'sent': []}

    monkeypatch.setattr(conversations_router, '_get_valid_conversation_by_id', lambda uid, cid, **kw: _conversation())
    monkeypatch.setattr(
        conversations_router.share_email,
        'get_user_from_uid',
        lambda uid: {'uid': uid, 'email': 'owner@acme.com', 'display_name': 'Owner'},
    )
    monkeypatch.setattr(
        conversations_router.conversations_db,
        'set_conversation_visibility',
        lambda uid, cid, value: state.__setitem__('visibility', getattr(value, 'value', value)),
    )
    monkeypatch.setattr(
        conversations_router.redis_db, 'store_conversation_to_uid', lambda cid, uid: state['redis'].add(cid)
    )
    monkeypatch.setattr(
        conversations_router.redis_db, 'add_public_conversation', lambda cid: state['redis'].add(f'pub:{cid}')
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        'remove_conversation_to_uid',
        lambda cid: state['redis'].discard(cid),
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        'remove_public_conversation',
        lambda cid: state['redis'].discard(f'pub:{cid}'),
    )
    yield state


def test_share_recipients_excludes_owner():
    response = _client().get(f'/v1/conversations/{CONV_ID}/share-recipients')
    assert response.status_code == 200
    assert response.json() == {'recipients': [{'name': 'Sarah Chen', 'email': 'sarah@acme.com'}]}


def test_share_email_rejects_foreign_recipient(_stub_data_layer):
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['attacker@evil.com']},
    )
    assert response.status_code == 400
    assert _stub_data_layer['visibility'] == 'private'
    assert _stub_data_layer['redis'] == set()


def test_share_email_success_publishes_and_sends(monkeypatch, _stub_data_layer):
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com', 'SARAH@acme.com']},
    )
    assert response.status_code == 200
    assert response.json() == {'sent_to': ['sarah@acme.com']}
    assert _stub_data_layer['visibility'] == 'shared'
    assert CONV_ID in _stub_data_layer['redis']


def test_share_email_provider_failure_rolls_back_visibility(monkeypatch, _stub_data_layer):
    def failing_send(*, uid, conversation, recipient_emails):
        raise RuntimeError('email provider rejected the send')

    monkeypatch.setattr(conversations_router.share_email, 'send_summary_email', failing_send)
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 502
    assert _stub_data_layer['visibility'] == 'private'
    assert _stub_data_layer['redis'] == set()


def test_share_email_preserves_public_visibility(monkeypatch, _stub_data_layer):
    public_conversation = _conversation() | {'visibility': 'public'}
    monkeypatch.setattr(
        conversations_router, '_get_valid_conversation_by_id', lambda uid, cid, **kw: public_conversation
    )
    _stub_data_layer['visibility'] = 'public'
    monkeypatch.setattr(
        conversations_router.share_email,
        'send_summary_email',
        lambda *, uid, conversation, recipient_emails: {'sent_to': recipient_emails},
    )
    response = _client().post(
        f'/v1/conversations/{CONV_ID}/share-email',
        json={'recipient_emails': ['sarah@acme.com']},
    )
    assert response.status_code == 200
    assert _stub_data_layer['visibility'] == 'public'
    assert CONV_ID in _stub_data_layer['redis']
