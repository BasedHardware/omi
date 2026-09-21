import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from starlette.requests import Request

import routers.apps as apps_router
from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router

COMPLETED = b'{"is_setup_completed": true}'


class _RecordingClient:
    def __init__(self):
        self.urls = []

    async def get(self, url, **_kwargs):
        self.urls.append(url)
        return httpx.Response(
            200,
            content=COMPLETED,
            headers={'Content-Type': 'application/json'},
            request=httpx.Request('GET', url),
        )


def _external_app(setup_completed_url: str) -> dict:
    return {
        'id': 'app-1',
        'name': 'Test App',
        'image': 'https://example.com/app.png',
        'author': 'Test Author',
        'uid': 'owner-uid',
        'email': 'dev@example.com',
        'category': 'productivity-and-organization',
        'description': 'test app',
        'capabilities': {'external_integration'},
        'deleted': False,
        'private': False,
        'external_integration': {'setup_completed_url': setup_completed_url},
    }


def _enable(setup_completed_url: str) -> list[str]:
    client = _RecordingClient()
    with (
        patch.object(apps_router, 'get_available_app_by_id', lambda _app_id, _uid: _external_app(setup_completed_url)),
        patch.object(apps_router, 'get_webhook_client', lambda: client),
        patch.object(apps_router, 'is_tester', lambda _uid: False),
        patch.object(apps_router, 'enable_app', lambda _uid, _app_id: None),
        patch.object(apps_router, 'increase_app_installs_count', lambda _app_id: None),
    ):
        # Minimal ASGI-scope Request double: record_product_event only reads
        # request.headers (fail-open otherwise), matching
        # tests/unit/test_product_metrics.py's construction.
        request = Request({'type': 'http', 'headers': []})
        assert asyncio.run(apps_router.enable_app_endpoint(app_id='app-1', request=request, uid='user-1')) == {
            'status': 'ok'
        }
    return client.urls


def _exchange_token(setup_completed_url: str) -> list[str]:
    client = _RecordingClient()
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):

        class _ExternalApp(oauth.AppModel):
            def __init__(self, **values):
                super().__init__(**values)
                self.external_integration = SimpleNamespace(
                    app_home_url='https://app.test/complete',
                    setup_completed_url=setup_completed_url,
                    actions=[],
                    triggers_on=None,
                )

            def works_externally(self) -> bool:
                return True

        oauth.AppModel = _ExternalApp
        oauth.is_user_app_enabled = lambda _uid, _app_id: False
        oauth.get_auth_client = lambda: client
        result = asyncio.run(
            oauth.oauth_token(
                firebase_id_token='token',
                app_id='app-1',
                state='opaque',
                csrf_token='matching-csrf-token',
                oauth_csrf_cookie='matching-csrf-token',
            )
        )
        assert result['uid'] == 'user-1'
    return client.urls


@pytest.mark.parametrize('check', [_enable, _exchange_token], ids=['apps-enable', 'oauth-token'])
def test_setup_url_with_a_query_gets_uid_as_its_own_param(check):
    (url,) = check('https://provider.test/status?app=omi')

    assert url == 'https://provider.test/status?app=omi&uid=user-1'
    assert dict(httpx.URL(url).params) == {'app': 'omi', 'uid': 'user-1'}


@pytest.mark.parametrize('check', [_enable, _exchange_token], ids=['apps-enable', 'oauth-token'])
def test_setup_url_without_a_query_is_unchanged(check):
    assert check('https://provider.test/status') == ['https://provider.test/status?uid=user-1']
