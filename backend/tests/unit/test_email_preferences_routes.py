"""Route-level contract tests for the unauthenticated unsubscribe endpoints.

Mirrors the monkeypatching style of test_share_email_routes.py: the router
module's already-imported names are patched directly rather than injecting a
fake Firestore client through a default parameter the route never threads
through.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import email_preferences as router_module
from utils.email.lifecycle import mint_unsubscribe_token

SIGNING_SECRET = 'test-lifecycle-signing-secret-do-not-use-in-prod'


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv('LIFECYCLE_EMAIL_SIGNING_SECRET', SIGNING_SECRET)


@pytest.fixture
def _opt_outs(monkeypatch):
    """Fake ``set_lifecycle_opted_out`` recording calls, no Firestore involved."""
    calls: list[tuple[str, bool]] = []

    def fake(uid: str, opted_out: bool, *, firestore_client=None):
        calls.append((uid, opted_out))

    monkeypatch.setattr(router_module, 'set_lifecycle_opted_out', fake)
    return calls


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router)
    return TestClient(app)


def test_get_unsubscribe_with_valid_token_opts_out_and_confirms(_opt_outs):
    token = mint_unsubscribe_token('uid-get')
    response = _client().get('/email/unsubscribe', params={'token': token})

    assert response.status_code == 200
    assert 'unsubscribed' in response.text.lower()
    assert _opt_outs == [('uid-get', True)]


def test_get_unsubscribe_never_echoes_the_token(_opt_outs):
    token = mint_unsubscribe_token('uid-no-echo')
    response = _client().get('/email/unsubscribe', params={'token': token})
    assert token not in response.text


def test_get_unsubscribe_missing_token_is_a_neutral_400(_opt_outs):
    response = _client().get('/email/unsubscribe')
    assert response.status_code == 400
    assert _opt_outs == []
    # The error message must not reveal anything about token validity or uid existence.
    assert 'uid' not in response.text.lower()


def test_get_unsubscribe_tampered_token_is_a_neutral_400(_opt_outs):
    token = mint_unsubscribe_token('uid-tampered')
    tampered = token[:-1] + ('a' if token[-1] != 'a' else 'b')
    response = _client().get('/email/unsubscribe', params={'token': tampered})
    assert response.status_code == 400
    assert _opt_outs == []


def test_get_unsubscribe_is_idempotent(_opt_outs):
    token = mint_unsubscribe_token('uid-twice')
    client = _client()
    first = client.get('/email/unsubscribe', params={'token': token})
    second = client.get('/email/unsubscribe', params={'token': token})
    assert first.status_code == 200
    assert second.status_code == 200
    assert _opt_outs == [('uid-twice', True), ('uid-twice', True)]


def test_get_unsubscribe_does_not_reveal_whether_the_uid_exists(_opt_outs):
    """A syntactically-valid, correctly-signed token for a uid the caller made
    up gets exactly the same 200 confirmation as a real one -- existence is
    never distinguishable from the response."""
    token = mint_unsubscribe_token('uid-does-not-exist-anywhere')
    response = _client().get('/email/unsubscribe', params={'token': token})
    assert response.status_code == 200
    assert _opt_outs == [('uid-does-not-exist-anywhere', True)]


def test_post_unsubscribe_one_click_with_valid_token_succeeds(_opt_outs):
    token = mint_unsubscribe_token('uid-post')
    # Gmail/Apple Mail send this as the RFC 8058 one-click body; the route
    # must accept it without requiring auth or validating the body shape.
    response = _client().post(
        '/email/unsubscribe',
        params={'token': token},
        data={'List-Unsubscribe': 'One-Click'},
    )
    assert response.status_code == 200
    assert _opt_outs == [('uid-post', True)]


def test_post_unsubscribe_missing_token_is_a_neutral_400(_opt_outs):
    response = _client().post('/email/unsubscribe', data={'List-Unsubscribe': 'One-Click'})
    assert response.status_code == 400
    assert _opt_outs == []


def test_post_unsubscribe_is_idempotent(_opt_outs):
    token = mint_unsubscribe_token('uid-post-twice')
    client = _client()
    first = client.post('/email/unsubscribe', params={'token': token})
    second = client.post('/email/unsubscribe', params={'token': token})
    assert first.status_code == 200
    assert second.status_code == 200
    assert _opt_outs == [('uid-post-twice', True), ('uid-post-twice', True)]
