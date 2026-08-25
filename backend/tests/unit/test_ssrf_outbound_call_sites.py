"""Call-site SSRF guards: outbound request helpers must validate/pin public URLs.

Hermetic — DNS and HTTP are always mocked. Covers developer webhooks, manifest
fetch, re-enable health probes, chat-tool invocation, and MCP client helpers.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import asyncio
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


async def _run_blocking(_executor, function, *args):
    return function(*args)


@pytest.mark.slow
def test_set_user_webhook_rejects_private_url():
    users_mod, SetUserWebhookUrlRequest = _load_users_router()
    users_mod.run_blocking = _run_blocking
    # Stubbed import graph turns utils.http_client symbols into MagicMocks;
    # restore the real exception type so `except UnsafeWebhookURLError` works.
    users_mod.UnsafeWebhookURLError = UnsafeWebhookURLError
    users_mod.assert_public_http_url = MagicMock(side_effect=UnsafeWebhookURLError('private'))
    with (
        patch.object(users_mod, 'set_user_webhook_db') as setdb,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                users_mod.set_user_webhook_endpoint(
                    wtype='memory_created',
                    data=SetUserWebhookUrlRequest(url='http://127.0.0.1/hook'),
                    uid='u1',
                )
            )
    assert exc_info.value.status_code == 400
    assert 'public' in exc_info.value.detail.lower()
    setdb.assert_not_called()
    enable.assert_not_called()


@pytest.mark.slow
def test_set_user_webhook_empty_url_skips_ssrf_check():
    users_mod, SetUserWebhookUrlRequest = _load_users_router()
    users_mod.run_blocking = _run_blocking
    users_mod.UnsafeWebhookURLError = UnsafeWebhookURLError
    users_mod.assert_public_http_url = MagicMock(side_effect=AssertionError('should not validate empty'))
    with (
        patch.object(users_mod, 'set_user_webhook_db'),
        patch.object(users_mod, 'disable_user_webhook_db') as disable,
        patch.object(users_mod, 'enable_user_webhook_db') as enable,
    ):
        result = asyncio.run(
            users_mod.set_user_webhook_endpoint(
                wtype='memory_created',
                data=SetUserWebhookUrlRequest(url=''),
                uid='u1',
            )
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
        patch('utils.webhooks.get_pinned_webhook_client', return_value=mock_client),
        patch('utils.webhooks.safe_request_targets', side_effect=UnsafeWebhookURLError('private')),
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
        patch('utils.webhooks.get_pinned_webhook_client', return_value=mock_client),
        patch('utils.webhooks.get_webhook_semaphore', return_value=mock_sem),
        patch('utils.webhooks.safe_request_targets', return_value=[(pinned, pin_kwargs)]),
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


@pytest.mark.asyncio
async def test_post_dev_webhook_retries_each_validated_address():
    mock_response = MagicMock(status_code=503)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    pinned_targets = [_pin(f'https://hooks.example.com/x?edge={index}', f'8.8.8.{index + 1}') for index in range(5)]
    mock_sem = AsyncMock()
    mock_sem.__aenter__ = AsyncMock()
    mock_sem.__aexit__ = AsyncMock()

    with (
        patch('utils.webhooks.get_pinned_webhook_client', return_value=mock_client),
        patch('utils.webhooks.get_webhook_semaphore', return_value=mock_sem),
        patch('utils.webhooks.safe_request_targets', return_value=pinned_targets),
    ):
        result = await _post_dev_webhook(
            'test_webhook',
            'https://hooks.example.com/x',
            json={'a': 1},
            retry_delays=(),
        )

    assert result is mock_response
    assert mock_client.post.await_count == len(pinned_targets)
    assert [call.args[0] for call in mock_client.post.await_args_list] == [target[0] for target in pinned_targets]


# ---------------------------------------------------------------------------
# Manifest fetch + tool endpoint validation
# ---------------------------------------------------------------------------


def _async_web_fetch_client(response):
    """Mock the shared async web-fetch client used by the manifest fetcher."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_fetch_manifest_rejects_non_public_url(monkeypatch):
    monkeypatch.setattr(apps_mod, 'safe_request_target', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    monkeypatch.setattr(apps_mod, 'get_generic_cache', MagicMock(return_value=None))

    assert await apps_mod.fetch_app_chat_tools_from_manifest('http://169.254.169.254/manifest.json') is None


@pytest.mark.asyncio
async def test_fetch_manifest_uses_pinned_target(monkeypatch):
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
    mock_client = _async_web_fetch_client(mock_resp)
    monkeypatch.setattr(apps_mod, 'get_web_fetch_client', lambda: mock_client)
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(return_value=PUBLIC_IP))

    result = await apps_mod.fetch_app_chat_tools_from_manifest('https://app.example.com/.well-known/omi-tools.json')
    assert result is not None
    assert result['tools'][0]['name'] == 't'
    assert mock_client.get.call_args.args[0] == pinned
    assert mock_client.get.call_args.kwargs['follow_redirects'] is False
    assert mock_client.get.call_args.kwargs['extensions']['sni_hostname'] == 'app.example.com'
    assert mock_client.get.call_args.kwargs['timeout'] == 10.0


@pytest.mark.asyncio
async def test_fetch_manifest_resolves_dns_off_the_event_loop(monkeypatch):
    """The manifest URL (and every absolute tool endpoint) must be resolved on the
    resolver pool — an unbounded tools array of stalled DNS lookups otherwise runs
    inline on the caller's event loop / route worker."""
    import threading

    seen_threads = []

    def _recording_target(url):
        seen_threads.append(threading.current_thread())
        return _pin(url)

    monkeypatch.setattr(apps_mod, 'safe_request_target', _recording_target)
    monkeypatch.setattr(apps_mod, 'get_generic_cache', MagicMock(return_value=None))
    monkeypatch.setattr(apps_mod, 'set_generic_cache', MagicMock())

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'tools': []}
    monkeypatch.setattr(apps_mod, 'get_web_fetch_client', lambda: _async_web_fetch_client(mock_resp))

    result = await apps_mod.fetch_app_chat_tools_from_manifest('https://app.example.com/.well-known/omi-tools.json')
    assert result is not None
    assert seen_threads
    main_thread = threading.main_thread()
    for thread in seen_threads:
        assert thread is not main_thread


@pytest.mark.asyncio
async def test_validate_tool_definition_rejects_private_endpoint(monkeypatch):
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    result = await apps_mod._validate_tool_definition(
        {'name': 't', 'description': 'd', 'endpoint': 'http://10.0.0.1/tool'}
    )
    assert result is None


@pytest.mark.asyncio
async def test_validate_tool_definition_keeps_path_relative_endpoint(monkeypatch):
    """The documented manifest format is relative ("/tools/x"); the router
    resolves it against app_home_url and invocation pins the resolved URL.
    Rejecting it here silently strips every tool from such an app."""
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(side_effect=AssertionError('relative')))
    result = await apps_mod._validate_tool_definition(
        {'name': 't', 'description': 'd', 'endpoint': '/tools/add_to_playlist'}
    )
    assert result is not None
    assert result['endpoint'] == '/tools/add_to_playlist'


@pytest.mark.asyncio
async def test_validate_tool_definition_rejects_scheme_relative_endpoint(monkeypatch):
    """ "//evil.example/x" is not app-relative -- it resolves to another origin."""
    monkeypatch.setattr(apps_mod, 'assert_public_http_url', MagicMock(side_effect=UnsafeWebhookURLError('scheme')))
    result = await apps_mod._validate_tool_definition(
        {'name': 't', 'description': 'd', 'endpoint': '//evil.example/x'}
    )
    assert result is None


@pytest.mark.asyncio
async def test_reenable_health_check_rejects_non_public_url(monkeypatch):
    monkeypatch.setattr('utils.apps.safe_request_target', MagicMock(side_effect=UnsafeWebhookURLError('private')))
    with pytest.raises(HTTPException) as exc_info:
        await validate_app_endpoints_for_reenable(
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
@pytest.mark.slow
async def test_call_tool_endpoint_rejects_non_public():
    app_tools = _load_app_tools_module()
    tool = ChatTool(name='secret_tool', description='d', endpoint='http://127.0.0.1/tool', method='POST')
    config = {'configurable': {'user_id': 'uid-1'}}

    with (
        patch.object(app_tools, 'is_app_webhook_disabled', return_value=False),
        patch.object(app_tools, 'safe_request_target', side_effect=UnsafeWebhookURLError('private')),
        patch.object(app_tools, 'get_webhook_circuit_breaker') as mock_cb_factory,
        patch.object(app_tools, 'record_app_webhook_failure', return_value=0) as mock_fail,
        patch.object(app_tools, '_handle_app_webhook_disable'),
        patch('httpx.AsyncClient') as mock_client_cls,
    ):
        mock_cb_factory.return_value.allow_request.return_value = True
        result = await app_tools._call_tool_endpoint({}, config, tool, 'app-1')

    assert 'invalid or unavailable' in result
    # Resolution failure must count on the same failure path (breaker + health accounting).
    mock_cb_factory.return_value.record_failure.assert_called_once()
    mock_fail.assert_called_once()
    assert mock_fail.call_args.args[0] == 'app-1'
    assert mock_fail.call_args.args[1] == 0
    assert '127.0.0.1' not in result
    mock_cb_factory.assert_called_once_with(tool.endpoint)
    mock_cb_factory.return_value.release_probe.assert_called_once()
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


@pytest.mark.asyncio
async def test_mcp_post_surfaces_redirect_instead_of_empty_result():
    """With redirects disabled, a 3xx has an empty body -- returning {} would
    look like a successful notification ack and silently drop the tool call."""
    import httpx

    pinned, pin_kwargs = _pin('https://mcp.example.com/http')
    redirect = httpx.Response(
        307,
        headers={'location': 'https://elsewhere.example.com/http'},
        request=httpx.Request('POST', pinned),
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=redirect)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(mcp_mod, '_safe_request_target', return_value=(pinned, pin_kwargs)),
        patch('utils.mcp_client.httpx.AsyncClient', return_value=mock_client),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_mod._mcp_post('https://mcp.example.com/http', {'jsonrpc': '2.0', 'method': 'x', 'id': 1})


@pytest.mark.asyncio
async def test_sse_post_redirect_fails_fast_instead_of_waiting_for_the_timeout():
    """A redirected SSE POST endpoint never delivers replies on the stream;
    discarding its 3xx made the caller wait out the 30s SSE timeout."""
    import httpx

    sse_url = 'https://mcp.example.com/sse'
    pinned_sse, sse_pin = _pin(sse_url)
    pinned_post, post_pin = _pin('https://mcp.example.com/messages')

    class _Stream:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def aiter_text(self):
            yield 'event: endpoint\ndata: /messages\n\n'
            # Server sends nothing further -- the reply would have come via the
            # POST target we were redirected away from.

    redirect = httpx.Response(
        307,
        headers={'location': 'https://elsewhere.example.com/messages'},
        request=httpx.Request('POST', pinned_post),
    )

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=_Stream())
    mock_client.post = AsyncMock(return_value=redirect)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    def _resolve(url):
        return (pinned_sse, sse_pin) if url == sse_url else (pinned_post, post_pin)

    with (
        patch.object(mcp_mod, '_safe_request_target', side_effect=_resolve),
        patch('utils.mcp_client.httpx.AsyncClient', return_value=mock_client),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_mod._sse_send_and_receive_inner(sse_url, [{'jsonrpc': '2.0', 'method': 'x', 'id': 1}])

    assert mock_client.post.await_args.kwargs['follow_redirects'] is False
