"""Call-site SSRF guards: outbound request helpers must validate/pin public URLs.

Hermetic — DNS and HTTP are always mocked. Covers developer webhooks, manifest
fetch, re-enable health probes, chat-tool invocation, and MCP client helpers.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from fastapi import HTTPException
from models.app import ChatTool
from testing.import_isolation import load_module_fresh, stub_modules
from utils import apps as apps_mod
from utils import mcp_client as mcp_mod
from utils.apps import validate_app_endpoints_for_reenable
from utils.http_client import UnsafeWebhookURLError
from utils.webhooks import _post_dev_webhook

PUBLIC_IP = '8.8.8.8'
_BACKEND = os.path.join(os.path.dirname(__file__), '..', '..')


def _pin(url: str, ip: str = PUBLIC_IP):
    parsed = urlparse(url)
    host = parsed.hostname or 'example.com'
    netloc = ip
    if parsed.port:
        netloc = f'{ip}:{parsed.port}'
    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, {'headers': {'Host': host}, 'extensions': {'sni_hostname': host}}


def _load_app_tools_module():
    retrieval_pkg = types.ModuleType('utils.retrieval')
    retrieval_pkg.__path__ = []
    tools_pkg = types.ModuleType('utils.retrieval.tools')
    tools_pkg.__path__ = []
    with stub_modules({'utils.retrieval': retrieval_pkg, 'utils.retrieval.tools': tools_pkg}):
        return load_module_fresh(
            'utils.retrieval.tools.app_tools',
            os.path.join(_BACKEND, 'utils', 'retrieval', 'tools', 'app_tools.py'),
        )


# ---------------------------------------------------------------------------
# set_user_webhook_endpoint — private URL -> HTTP 400
# ---------------------------------------------------------------------------

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


def _install_python_multipart_stub():
    if 'python_multipart' in sys.modules:
        return False
    if importlib.util.find_spec('python_multipart') is not None:
        return False
    mod = types.ModuleType('python_multipart')
    mod.__version__ = '0.0.20'
    sys.modules['python_multipart'] = mod
    return True


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


def _load_users_router():
    """Import routers.users under a stub finder (heavy graph). Function-scoped
    so the module-isolation scanner does not see sys.modules mutations at
    import time."""
    finder = _Finder()
    snap = _snapshot_stubbed_modules()
    kept_real = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == 'utils' or name.startswith('utils.') or name == 'database' or name.startswith('database.')
    }
    _clear_stubbed_modules()
    rm_mp = _install_python_multipart_stub()
    sys.meta_path.insert(0, finder)
    try:
        from routers import users as users_mod
        from routers.users import SetUserWebhookUrlRequest

        return users_mod, SetUserWebhookUrlRequest
    finally:
        sys.meta_path.remove(finder)
        _restore_stubbed_modules(snap)
        sys.modules.update(kept_real)
        if rm_mp:
            sys.modules.pop('python_multipart', None)


def test_set_user_webhook_rejects_private_url():
    users_mod, SetUserWebhookUrlRequest = _load_users_router()
    # Stubbed import graph turns utils.http_client symbols into MagicMocks;
    # restore the real exception type so `except UnsafeWebhookURLError` works.
    users_mod.UnsafeWebhookURLError = UnsafeWebhookURLError
    users_mod.assert_public_http_url = MagicMock(side_effect=UnsafeWebhookURLError('private'))
    with (
        patch.object(users_mod, 'set_user_webhook_db') as setdb,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
    ):
        with pytest.raises(HTTPException) as exc_info:
            users_mod.set_user_webhook_endpoint(
                wtype='memory_created',
                data=SetUserWebhookUrlRequest(url='http://127.0.0.1/hook'),
                uid='u1',
            )
    assert exc_info.value.status_code == 400
    assert 'public' in exc_info.value.detail.lower()
    setdb.assert_not_called()
    enable.assert_not_called()


def test_set_user_webhook_empty_url_skips_ssrf_check():
    users_mod, SetUserWebhookUrlRequest = _load_users_router()
    users_mod.UnsafeWebhookURLError = UnsafeWebhookURLError
    users_mod.assert_public_http_url = MagicMock(side_effect=AssertionError('should not validate empty'))
    with (
        patch.object(users_mod, 'set_user_webhook_db'),
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
    ):
        result = users_mod.set_user_webhook_endpoint(
            wtype='memory_created',
            data=SetUserWebhookUrlRequest(url=''),
            uid='u1',
        )
    assert result['status'] == 'ok'
    disable.assert_called_once()
    enable.assert_not_called()
    users_mod.assert_public_http_url.assert_not_called()


# ---------------------------------------------------------------------------
# _post_dev_webhook — reject before delivery / breaker side effects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_dev_webhook_rejects_non_public_without_post():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock()
    with (
        patch('utils.webhooks.get_webhook_client', return_value=mock_client),
        patch('utils.webhooks.safe_request_target', side_effect=UnsafeWebhookURLError('private')),
    ):
        result = await _post_dev_webhook('test_webhook', 'http://127.0.0.1/hook', json={})
    assert result is None
    mock_client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_dev_webhook_pins_and_disables_redirects():
    mock_response = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_sem = AsyncMock()
    mock_sem.__aenter__ = AsyncMock()
    mock_sem.__aexit__ = AsyncMock()
    pinned, pin_kwargs = _pin('https://hooks.example.com/x')

    with (
        patch('utils.webhooks.get_webhook_client', return_value=mock_client),
        patch('utils.webhooks.get_webhook_semaphore', return_value=mock_sem),
        patch('utils.webhooks.safe_request_target', return_value=(pinned, pin_kwargs)),
    ):
        result = await _post_dev_webhook(
            'test_webhook',
            'https://hooks.example.com/x',
            json={'a': 1},
            retry_delays=(),
        )

    assert result is mock_response
    call_kwargs = mock_client.post.await_args
    assert call_kwargs.args[0] == pinned
    assert call_kwargs.kwargs['follow_redirects'] is False
    assert call_kwargs.kwargs['headers']['Host'] == 'hooks.example.com'
    assert call_kwargs.kwargs['extensions']['sni_hostname'] == 'hooks.example.com'


# ---------------------------------------------------------------------------
# Manifest fetch + tool endpoint validation
# ---------------------------------------------------------------------------


def test_fetch_manifest_rejects_non_public_url(monkeypatch):
    monkeypatch.setattr(apps_mod, 'safe_request_target', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    monkeypatch.setattr(apps_mod, 'get_generic_cache', MagicMock(return_value=None))
    client_cls = MagicMock()
    monkeypatch.setattr(apps_mod.httpx, 'Client', client_cls)

    assert apps_mod.fetch_app_chat_tools_from_manifest('http://169.254.169.254/manifest.json') is None
    client_cls.assert_not_called()


def test_fetch_manifest_uses_pinned_target(monkeypatch):
    pinned, pin_kwargs = _pin('https://app.example.com/.well-known/omi-tools.json')
    monkeypatch.setattr(apps_mod, 'safe_request_target', MagicMock(return_value=(pinned, pin_kwargs)))
    monkeypatch.setattr(apps_mod, 'get_generic_cache', MagicMock(return_value=None))
    monkeypatch.setattr(apps_mod, 'set_generic_cache', MagicMock())

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'tools': [
            {
                'name': 't',
                'description': 'd',
                'endpoint': 'https://app.example.com/tool',
            }
        ]
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_client
    mock_cm.__exit__.return_value = None
    monkeypatch.setattr(apps_mod.httpx, 'Client', MagicMock(return_value=mock_cm))
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(return_value=PUBLIC_IP))

    result = apps_mod.fetch_app_chat_tools_from_manifest('https://app.example.com/.well-known/omi-tools.json')
    assert result is not None
    assert result['tools'][0]['name'] == 't'
    assert mock_client.get.call_args.args[0] == pinned
    assert mock_client.get.call_args.kwargs['follow_redirects'] is False
    assert mock_client.get.call_args.kwargs['extensions']['sni_hostname'] == 'app.example.com'


def test_validate_tool_definition_rejects_private_endpoint(monkeypatch):
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    result = apps_mod._validate_tool_definition({'name': 't', 'description': 'd', 'endpoint': 'http://10.0.0.1/tool'})
    assert result is None


def test_reenable_health_check_rejects_non_public_url(monkeypatch):
    monkeypatch.setattr('utils.apps.safe_request_target', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    with pytest.raises(HTTPException) as exc_info:
        validate_app_endpoints_for_reenable(
            {'external_integration': {'webhook_url': 'http://127.0.0.1/wh'}, 'chat_tools': []},
            {},
            'app-1',
        )
    assert exc_info.value.status_code == 400
    assert 'public' in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Chat tool invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_endpoint_rejects_non_public():
    app_tools = _load_app_tools_module()
    tool = ChatTool(name='secret_tool', description='d', endpoint='http://127.0.0.1/tool', method='POST')
    config = {'configurable': {'user_id': 'uid-1'}}

    with (
        patch.object(app_tools, 'is_app_webhook_disabled', return_value=False),
        patch.object(app_tools, 'safe_request_target', side_effect=UnsafeWebhookURLError('private')),
        patch.object(app_tools, 'get_webhook_circuit_breaker') as mock_cb_factory,
        patch('httpx.AsyncClient') as mock_client_cls,
    ):
        result = await app_tools._call_tool_endpoint({}, config, tool, 'app-1')

    assert 'invalid or unavailable' in result
    assert '127.0.0.1' not in result
    mock_cb_factory.assert_not_called()
    mock_client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# MCP client helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_oauth_metadata_returns_none_for_private_url():
    with patch.object(mcp_mod, '_safe_request_target', side_effect=UnsafeWebhookURLError('private')):
        result = await mcp_mod.discover_oauth_metadata('http://127.0.0.1:8080')
    assert result is None


@pytest.mark.asyncio
async def test_mcp_post_uses_pinned_url_and_no_redirects():
    pinned, pin_kwargs = _pin('https://mcp.example.com/http')
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"jsonrpc":"2.0","result":{}}'
    mock_resp.headers = {'content-type': 'application/json'}
    mock_resp.json.return_value = {'jsonrpc': '2.0', 'result': {}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(mcp_mod, '_safe_request_target', return_value=(pinned, pin_kwargs)),
        patch('utils.mcp_client.httpx.AsyncClient', return_value=mock_client),
    ):
        data, _session = await mcp_mod._mcp_post(
            'https://mcp.example.com/http', {'jsonrpc': '2.0', 'method': 'x', 'id': 1}
        )

    assert data == {'jsonrpc': '2.0', 'result': {}}
    assert mock_client.post.await_args.args[0] == pinned
    assert mock_client.post.await_args.kwargs['follow_redirects'] is False
    assert mock_client.post.await_args.kwargs['headers']['Host'] == 'mcp.example.com'
