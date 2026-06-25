"""Regression test for the Gmail tool missing-await bug.

`utils/retrieval/tools/gmail_tools.py::get_gmail_messages` calls the async helper
`google_api_request(...)` at two sites. Before the fix the helper was a plain
`def` that invoked `google_api_request(...)` WITHOUT `await`, so it received a
coroutine object and immediately did `data.get('messages', [])` on it ->
`AttributeError: 'coroutine' object has no attribute 'get'`. The whole Gmail tool
was broken for every call.

The fix makes `get_gmail_messages` `async def` and awaits both
`google_api_request` calls (mirroring the already-correct
`get_google_calendar_events` in the sibling `calendar_tools.py`).

This test loads the REAL `gmail_tools` module by file path (so the heavy
`utils/retrieval/tools/__init__.py` aggregator, which eagerly imports every tool
and pulls in typesense/pinecone/etc., never runs). Only IO/heavy leaf modules are
stubbed via a meta-path finder. It patches `google_api_request` with an async
fake returning plain dicts and asserts `await get_gmail_messages(...)` returns a
list of message dicts without raising AttributeError.

Red before the fix: awaiting a sync function that internally builds a coroutine
and calls `.get(...)` on it raises `AttributeError: 'coroutine' object has no
attribute 'get'`.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

# backend/  (this file is backend/tests/unit/test_gmail_tools_await.py)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Stub only heavy / IO leaf modules. We deliberately do NOT stub the
# `utils.retrieval.tools` package (we load its submodules by file path below), so
# `gmail_tools`, `integration_base`, and `google_utils` run for real and we get the
# real `GoogleAPIError` and the real `get_gmail_messages` source.
_STUB = (
    'database',
    'firebase_admin',
    'google',
    'pinecone',
    'redis',
    'typesense',
    'utils.http_client',
    'utils.log_sanitizer',
)


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


def _make_pkg(name, path):
    """Register a real package object for `name` rooted at `path` WITHOUT running
    its __init__.py, so absolute submodule imports resolve but the aggregator
    __init__ (which pulls heavy deps) never executes."""
    if name in sys.modules:
        return sys.modules[name]
    pkg = types.ModuleType(name)
    pkg.__path__ = [path]
    pkg.__package__ = name
    sys.modules[name] = pkg
    return pkg


def _load_by_path(name, file_path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_tools_dir = os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'tools')

_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
_created_pkgs = []
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    # Build the package chain (real, __init__-skipped) so absolute imports inside
    # gmail_tools (utils.retrieval.tools.integration_base / google_utils) resolve.
    for _pkg_name, _pkg_path in (
        ('utils', os.path.join(_BACKEND_DIR, 'utils')),
        ('utils.retrieval', os.path.join(_BACKEND_DIR, 'utils', 'retrieval')),
        ('utils.retrieval.tools', _tools_dir),
    ):
        if _pkg_name not in sys.modules:
            _created_pkgs.append(_pkg_name)
        _make_pkg(_pkg_name, _pkg_path)

    # integration_base and google_utils are imported (absolutely) by gmail_tools.
    _load_by_path('utils.retrieval.tools.integration_base', os.path.join(_tools_dir, 'integration_base.py'))
    google_utils = _load_by_path('utils.retrieval.tools.google_utils', os.path.join(_tools_dir, 'google_utils.py'))
    mod = _load_by_path('utils.retrieval.tools.gmail_tools', os.path.join(_tools_dir, 'gmail_tools.py'))
    GoogleAPIError = google_utils.GoogleAPIError
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def test_get_gmail_messages_awaits_api_and_returns_dicts():
    """get_gmail_messages must await google_api_request and return real dicts.

    Red before the fix: the un-awaited call yields a coroutine and
    `coroutine.get('messages', [])` raises AttributeError.
    """
    list_response = {'messages': [{'id': 'm1'}, {'id': 'm2'}]}
    full_messages = {
        'm1': {'id': 'm1', 'threadId': 't1', 'snippet': 'hello', 'payload': {'headers': []}},
        'm2': {'id': 'm2', 'threadId': 't2', 'snippet': 'world', 'payload': {'headers': []}},
    }

    async def fake_api_request(method, url, access_token, params=None, body=None, allow_204=False):
        # The list endpoint ends in '/messages'; the per-message endpoint ends in '/messages/<id>'.
        if url.rstrip('/').endswith('/messages'):
            return list_response
        msg_id = url.rstrip('/').rsplit('/', 1)[-1]
        return full_messages[msg_id]

    with patch.object(mod, 'google_api_request', side_effect=fake_api_request) as mock_req:
        result = asyncio.run(mod.get_gmail_messages(access_token='tok', max_results=2))

    # Must be a concrete list of dicts, never a coroutine, and must not raise.
    assert isinstance(result, list)
    assert [m['id'] for m in result] == ['m1', 'm2']
    assert all(isinstance(m, dict) for m in result)
    # google_api_request was actually invoked (1 list call + 2 per-message calls).
    assert mock_req.call_count == 3


def test_get_gmail_messages_does_not_return_coroutine_items():
    """The returned items must be plain dicts, not unresolved coroutines."""

    async def fake_api_request(method, url, access_token, params=None, body=None, allow_204=False):
        if url.rstrip('/').endswith('/messages'):
            return {'messages': [{'id': 'only'}]}
        return {'id': 'only', 'payload': {'headers': []}, 'snippet': 's'}

    with patch.object(mod, 'google_api_request', side_effect=fake_api_request):
        result = asyncio.run(mod.get_gmail_messages(access_token='tok', max_results=1))

    assert isinstance(result, list)
    assert len(result) == 1
    assert not asyncio.iscoroutine(result[0])
    assert result[0]['id'] == 'only'


def _run_tool_with_refresh_retry(retry_error):
    """Drive get_gmail_messages_tool through the auth-error -> refresh -> retry path.

    The first get_gmail_messages call raises a 401 GoogleAPIError (auth), the token
    refresh succeeds, and the retried call raises `retry_error`. Returns the tool's
    string result so callers can assert how the post-refresh failure is reported.
    """
    calls = {'n': 0}

    async def fake_get_gmail_messages(access_token, query=None, max_results=10, label_ids=None):
        calls['n'] += 1
        if calls['n'] == 1:
            # First attempt: token expired.
            raise GoogleAPIError(401, "invalid_credentials")
        # Retry attempt (after refresh): fails again.
        raise retry_error

    async def fake_refresh(uid, integration):
        return 'new-token'

    # Bypass the DB-backed connection check; supply a known uid/integration/token.
    with patch.object(mod, 'prepare_access', return_value=('uid-1', {'refresh_token': 'r'}, 'old-token', None)):
        with patch.object(mod, 'refresh_google_token', side_effect=fake_refresh):
            with patch.object(mod, 'get_gmail_messages', side_effect=fake_get_gmail_messages):
                result = asyncio.run(mod.get_gmail_messages_tool.coroutine(query='hi', config={}))
    return result, calls['n']


def test_post_refresh_permission_error_is_structured_not_generic():
    """A 403 on the retried call must surface the actionable 'access denied' message.

    Red before the fix: the retry call sat directly inside `except GoogleAPIError`,
    so a second GoogleAPIError escaped to the outer `except Exception` and was
    returned as 'Unexpected error fetching Gmail messages: ...'.
    """
    result, attempts = _run_tool_with_refresh_retry(GoogleAPIError(403, "insufficient_permissions"))

    assert attempts == 2  # original call + one retry after refresh
    # Must NOT fall through to the generic outer handler.
    assert not result.startswith("Unexpected error fetching Gmail messages")
    # Permission errors keep their actionable reconnect guidance.
    assert "access denied" in result.lower()


def test_post_refresh_server_error_is_structured_not_generic():
    """A 500 on the retried call is reported via the structured Gmail message."""
    result, attempts = _run_tool_with_refresh_retry(GoogleAPIError(500, "backend_error"))

    assert attempts == 2
    assert not result.startswith("Unexpected error fetching Gmail messages")
    assert result.startswith("Error fetching Gmail messages")
    # The structured message carries the underlying detail, not a coroutine/AttributeError.
    assert "backend_error" in result
