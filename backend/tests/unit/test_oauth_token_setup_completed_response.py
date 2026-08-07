"""Regression: POST /v1/oauth/token must not 500 on a malformed setup_completed_url body.

`routers/oauth.oauth_token` auto-enables the app before handing back the redirect, and that
check reads the developer-controlled `setup_completed_url` body with
`res.json().get('is_setup_completed', False)`. When an app answered with a bare JSON scalar
(e.g. `true`) that raised `AttributeError: 'bool' object has no attribute 'get'`, so the
intended 400 "App setup is not completed" became an unhandled 500 (prod, 2026-07-30). The
same crasher was fixed for POST /v1/apps/enable in ff286b0b but this sibling call site was
missed.

Drives the real `oauth_token` coroutine through the existing stub harness. No live services.
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router

SETUP_URL = 'https://app.test/setup-completed'


def _install_pending_setup_app(oauth, body: bytes, content_type: str = 'application/json') -> None:
    """Point the loaded router at a not-yet-enabled external app whose setup URL returns `body`."""

    class _ExternalApp(oauth.AppModel):
        def __init__(self, **values):
            super().__init__(**values)
            self.external_integration = SimpleNamespace(
                app_home_url='https://app.test/complete',
                setup_completed_url=SETUP_URL,
                actions=[],
                triggers_on=None,
            )

        def works_externally(self) -> bool:
            return True

    async def _get_pinned_http_url_once(url, _pin_kwargs, **_kwargs):
        return httpx.Response(
            200,
            content=body,
            headers={'Content-Type': content_type},
            request=httpx.Request('GET', url),
        )

    oauth.AppModel = _ExternalApp
    oauth.is_user_app_enabled = lambda _uid, _app_id: False
    oauth.get_pinned_http_url_once = _get_pinned_http_url_once


def _exchange(oauth):
    return asyncio.run(
        oauth.oauth_token(
            firebase_id_token='token',
            app_id='app-1',
            state='opaque',
            csrf_token='matching-csrf-token',
            oauth_csrf_cookie='matching-csrf-token',
        )
    )


@pytest.mark.parametrize('body', [b'true', b'false', b'"ok"', b'null', b'[{"is_setup_completed": true}]'])
def test_non_object_setup_body_is_a_400_not_a_crash(body: bytes) -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_pending_setup_app(oauth, body)

        with pytest.raises(HTTPException) as exc:
            _exchange(oauth)

        assert exc.value.status_code == 400
        assert 'setup is not completed' in exc.value.detail


def test_non_json_setup_body_still_reports_an_invalid_response() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_pending_setup_app(oauth, b'<html>OK</html>', 'text/html')

        with pytest.raises(HTTPException) as exc:
            _exchange(oauth)

        assert exc.value.status_code == 503


def test_completed_setup_still_authorizes() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_pending_setup_app(oauth, b'{"is_setup_completed": true}')

        assert _exchange(oauth)['redirect_url'] == 'https://app.test/complete'


def test_incomplete_setup_is_still_rejected() -> None:
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        _install_pending_setup_app(oauth, b'{"is_setup_completed": false}')

        with pytest.raises(HTTPException) as exc:
            _exchange(oauth)

        assert exc.value.status_code == 400
