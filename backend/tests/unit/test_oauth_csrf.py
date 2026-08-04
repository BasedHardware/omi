"""Tests for the OAuth authorize -> token exchange CSRF protection
(routers/oauth.py).

Background: the `state` query/form param is round-tripped between
/v1/oauth/authorize and /v1/oauth/token, but the *value* is opaque to Omi's
server and controlled by the third-party app -- Omi has no way to validate it
means anything. The actual CSRF protection is a double-submit token Omi
generates itself: /authorize sets it two ways (an HttpOnly SameSite=Strict
cookie, and a copy embedded directly in the consent page's JS), and /token
requires both copies to be present and equal. A cross-site attacker can't
read or set that cookie for our origin, so they can't produce a matching pair.

Covers what the reviewer asked for:
- /v1/oauth/authorize emits the CSRF cookie and a matching token in the
  rendered page.
- /v1/oauth/token rejects a missing cookie, a missing form token, and a
  mismatched pair.
- /v1/oauth/token accepts the valid matching pair.

Reuses the existing `_loaded_oauth_router` stubbing harness from
test_oauth_token_async_boundaries.py so the fakes for firebase_admin,
database.apps, database.redis_db, utils.apps, and models.app stay in exactly
one place.
"""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router

CSRF_TOKEN_RE = re.compile(r'const csrfToken = "([^"]*)"')


def _client_for(oauth_module) -> TestClient:
    app = FastAPI()
    app.include_router(oauth_module.router)
    return TestClient(app)


def _authorize(client: TestClient) -> tuple[str, str]:
    """Hit /v1/oauth/authorize and return (cookie_value, page_csrf_token)."""
    response = client.get('/v1/oauth/authorize', params={'app_id': 'app-1'})
    assert response.status_code == 200

    cookie_value = response.cookies.get('omi_oauth_csrf')
    assert cookie_value, 'expected /v1/oauth/authorize to set the CSRF cookie'

    match = CSRF_TOKEN_RE.search(response.text)
    assert match, 'expected the rendered page to embed a matching csrfToken'
    page_token = match.group(1)
    assert page_token, 'csrfToken embedded in the page must not be empty'

    return cookie_value, page_token


def test_authorize_emits_cookie_and_matching_page_token():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        cookie_value, page_token = _authorize(client)
        assert cookie_value == page_token


def test_authorize_cookie_is_httponly_and_samesite_strict():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        response = client.get('/v1/oauth/authorize', params={'app_id': 'app-1'})
        set_cookie_header = response.headers.get('set-cookie', '')
        assert 'httponly' in set_cookie_header.lower()
        assert 'samesite=strict' in set_cookie_header.lower()


def test_token_accepts_valid_matching_pair():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        cookie_value, page_token = _authorize(client)

        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1', 'csrf_token': page_token},
            cookies={'omi_oauth_csrf': cookie_value},
        )
        assert response.status_code == 200
        assert response.json()['uid'] == 'user-1'


def test_token_rejects_missing_cookie():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        _cookie_value, page_token = _authorize(client)

        # No cookie sent at all -- e.g. a cross-site POST that never had it.
        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1', 'csrf_token': page_token},
        )
        assert response.status_code == 403


def test_token_rejects_missing_form_token():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        cookie_value, _page_token = _authorize(client)

        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1'},
            cookies={'omi_oauth_csrf': cookie_value},
        )
        # csrf_token is a required Form(...) field -> FastAPI itself 422s.
        assert response.status_code == 422


def test_token_rejects_mismatched_pair():
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        cookie_value, page_token = _authorize(client)
        assert page_token != 'attacker-supplied-token'

        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1', 'csrf_token': 'attacker-supplied-token'},
            cookies={'omi_oauth_csrf': cookie_value},
        )
        assert response.status_code == 403


def test_token_rejects_pair_from_a_different_authorize_call():
    """Each /authorize call mints a fresh token; an old page's token/cookie
    pair from a previous session must not validate against a stale value an
    attacker might have observed."""
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        client = _client_for(oauth)
        first_cookie, first_token = _authorize(client)
        second_cookie, second_token = _authorize(client)
        assert first_token != second_token, 'CSRF tokens must be freshly random per authorize call'

        # Mix a valid cookie with a token minted for a *different* page load.
        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1', 'csrf_token': second_token},
            cookies={'omi_oauth_csrf': first_cookie},
        )
        assert response.status_code == 403
