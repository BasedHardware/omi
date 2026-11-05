"""A malformed stored app must 404 the OAuth consent and token routes, not 500.

Both `GET /v1/oauth/authorize` (the public consent page) and `POST /v1/oauth/token`
built `App(**app_data)` after only a truthiness check, so a stored app doc missing a
required field (name, category, image, ...) raised `ValidationError`. The routes now use
`App.deserialize_safe`, as the app detail routes do since #19584.

The shared `_loaded_oauth_router` harness swaps `models.app` for a fake, so these tests
load the real router and model to exercise the actual validation.
"""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import oauth

MALFORMED_APP = {'id': 'app-1', 'private': False}
CSRF = 'csrf-token'


def _client():
    app = FastAPI()
    app.include_router(oauth.router)
    return TestClient(app, raise_server_exceptions=False)


def test_the_consent_page_for_a_malformed_app_is_not_found():
    with patch.object(oauth, 'get_app_by_id_db', return_value=dict(MALFORMED_APP)):
        response = _client().get('/v1/oauth/authorize', params={'app_id': 'app-1'})

    assert response.status_code == 404


def test_the_token_exchange_for_a_malformed_app_is_not_found():
    client = _client()
    client.cookies.set(oauth.OAUTH_CSRF_COOKIE_NAME, CSRF)
    with patch.object(oauth.firebase_admin.auth, 'verify_id_token', return_value={'uid': 'user-1'}), patch.object(
        oauth, 'enforce_jit_qa_uid'
    ), patch.object(oauth, 'enforce_account_deletion_http_access'), patch.object(
        oauth, 'get_app_by_id_db', return_value=dict(MALFORMED_APP)
    ):
        response = client.post(
            '/v1/oauth/token',
            data={'firebase_id_token': 'token', 'app_id': 'app-1', 'csrf_token': CSRF},
        )

    assert response.status_code == 404
