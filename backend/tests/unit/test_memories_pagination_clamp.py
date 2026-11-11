"""GET /v3/memories must clamp limit/offset so an out-of-range value can't 500 the request.

The endpoint passed limit/offset straight to Firestore .limit()/.offset(), which raise on a negative
argument, so /v3/memories?offset=-1 returned HTTP 500. routers/memories.py has a heavy import graph, so
we import it under a stub finder, then call get_memories directly with its db call mocked.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

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
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_stubbed_modules_snapshot = _snapshot_stubbed_modules()
_clear_stubbed_modules()
_remove_python_multipart_stub = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import memories as mem_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

from fastapi import HTTPException


class MemoryBackingStoreUnavailable(HTTPException):
    """Stand-in for the real type: this module imports the router under stubs."""

    def __init__(self, detail, *, stream):
        super().__init__(status_code=503, detail=detail)
        self.stream = stream


mem_mod.MemoryBackingStoreUnavailable = MemoryBackingStoreUnavailable
# The router is imported under a stubbed ``utils`` package, so the scan-budget
# constant arrives as a MagicMock. Pin the real detail string the route compares.
mem_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL = "Memory scan budget exceeded"


def _call(limit, offset):
    service = MagicMock()
    service.read.return_value = []
    scope_request = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
    ):
        mem_mod.get_memories(
            response=MagicMock(),
            limit=limit,
            offset=offset,
            uid='uid1',
            device_scope='all',
            client_device_id=None,
            x_app_platform=None,
            x_device_id_hash=None,
        )
    if service.read.called:
        return service.read.call_args.kwargs['limit'], service.read.call_args.kwargs['offset']
    return service.read_page.call_args.kwargs['limit'], 0


def test_negative_offset_is_clamped_not_500():
    _, offset = _call(50, -1)
    assert offset == 0


def test_huge_limit_is_capped():
    # Hard page cap is 500 (no first-page 5000 expansion — prod GET 504s).
    limit, _ = _call(99999, 10)
    assert limit == 500


def test_negative_limit_is_floored():
    limit, _ = _call(-5, 10)
    assert limit == 1


def test_blank_cursor_falls_back_to_offset_read_when_cursor_secret_missing():
    """GET 503 root cause: first-page read_page needs MEMORY_V3_CURSOR_SECRET.

    MEMORY_V3_GET_ENABLED is unused on the route. A blank ``?cursor=`` must not
    skip the first-page fallback, or MEMORY_ENABLED=on still 503s list.
    """
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Memory cursor unavailable", stream="cursor")
    service.read.return_value = []
    scope_request = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'memory_list_response', return_value=[]),
    ):
        mem_mod.get_memories(
            response=MagicMock(),
            limit=100,
            offset=0,
            cursor='  ',
            uid='uid1',
            device_scope='all',
            client_device_id=None,
            x_app_platform=None,
            x_device_id_hash=None,
        )
    service.read.assert_called_once()
    service.read_page.assert_called_once()


def _get_first_page(service):
    scope_request = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'memory_list_response', side_effect=lambda memories, _exposure, headers=None: memories),
    ):
        return mem_mod.get_memories(
            response=MagicMock(),
            limit=100,
            offset=0,
            cursor=None,
            uid='uid1',
            device_scope='all',
            client_device_id=None,
            x_app_platform=None,
            x_device_id_hash=None,
        )


def test_first_page_falls_back_to_offset_read_when_canonical_scan_unavailable():
    """GET 503: canonical keyset scan wraps any failure as this detail.

    The offset ``read`` path does not use the scan, so the first page must be
    served from ``read`` instead of failing the whole list endpoint.
    """
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Canonical memory unavailable", stream="canonical")
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == ['memory-from-offset-read']
    service.read_page.assert_called_once()
    service.read.assert_called_once()


def test_first_page_falls_back_to_offset_read_when_historical_scan_unavailable():
    """Prod 2026-08-18: first page 503d for 5.5h while a composite index built.

    ``read_page``'s historical keyset scan orders by (updated_at DESC,
    __name__) and so returned FAILED_PRECONDITION for every request while the
    matching ``memories`` composite index was still building, surfacing as this
    detail. The offset ``read`` path orders by ``updated_at`` alone, does not
    match that index, and could serve the page — so this detail must fall back
    like the other two scan failures instead of failing the list endpoint.
    """
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical")
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == ['memory-from-offset-read']
    service.read_page.assert_called_once()
    service.read.assert_called_once()


def test_first_page_scan_row_budget_does_not_fall_back_to_offset_read():
    """Keyset budget exhaustion must not restart through the offset reader.

    That reader used to stream the whole canonical collection and, once the
    request budget died, return an empty 200. The route serves a truncated
    page instead. ``read_page`` itself returns the prefix it already walked;
    this guards the case where the walk still raises the budget detail.
    """
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Memory scan budget exceeded", stream="historical")
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == []
    service.read_page.assert_called_once()
    service.read.assert_not_called()


def test_first_page_falls_back_on_typed_unavailable_regardless_of_detail():
    """A new or renamed detail on the typed exception must still degrade."""
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Brand new backing-store message", stream="canonical")
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == ['memory-from-offset-read']
    service.read.assert_called_once()


def test_first_page_does_not_match_unavailable_detail_strings():
    """The 2026-08-17 outage class: a matching string on a plain 503 is not enough."""
    import pytest

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Historical memory unavailable")

    with pytest.raises(HTTPException) as exc_info:
        _get_first_page(service)

    assert exc_info.value.detail == "Historical memory unavailable"
    service.read.assert_not_called()


def test_first_page_fallback_records_degraded_firestore_read():
    service = MagicMock()
    service.read_page.side_effect = MemoryBackingStoreUnavailable("Historical memory unavailable", stream="historical")
    service.read.return_value = []
    recorded = []

    def _record(**kwargs):
        recorded.append(kwargs)

    with patch.object(mem_mod, 'record_fallback', _record):
        _get_first_page(service)

    assert recorded == [
        {
            'component': 'firestore_read',
            'from_mode': 'cursor_page',
            'to_mode': 'offset_read',
            'reason': 'other',
            'outcome': 'degraded',
            'log': mem_mod.logger,
        }
    ]


def test_first_page_propagates_unrelated_503_detail():
    import pytest

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Some other degradation")

    with pytest.raises(HTTPException) as exc_info:
        _get_first_page(service)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Some other degradation"
    service.read.assert_not_called()


def test_first_page_propagates_non_503_errors():
    import pytest

    service = MagicMock()
    service.read_page.side_effect = HTTPException(
        status_code=402, detail="A paid plan is required to access this memory."
    )

    with pytest.raises(HTTPException) as exc_info:
        _get_first_page(service)

    assert exc_info.value.status_code == 402
    service.read.assert_not_called()


def test_index_window_invalid_cursor_falls_back_to_released_offset_read():
    service = MagicMock()
    service.read_page.side_effect = HTTPException(400, 'invalid_or_stale_cursor:expired_cursor')
    service.read.return_value = ['legacy-page']
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod.firestore_read_levers, 'lever_enabled', return_value=True),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'memory_list_response', side_effect=lambda values, *a, **kw: values),
    ):
        result = mem_mod.get_memories(response=MagicMock(), uid='uid1', limit=7, offset=14, cursor='expired')
    assert result == ['legacy-page']
    service.read.assert_called_once()
    assert service.read.call_args.kwargs['offset'] == 14
    service.read_page.assert_called_once()


def test_index_window_response_returns_existing_cursor_header_with_page():
    service = MagicMock()
    service.read_page.return_value = types.SimpleNamespace(
        memories=['bounded-page'], next_cursor='next-window', truncated=False
    )
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod.firestore_read_levers, 'lever_enabled', return_value=True),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(
            mem_mod,
            'list_read_budget_for_request',
            return_value=types.SimpleNamespace(truncated=False, observe=lambda *a: None),
        ),
        patch.object(mem_mod, 'memory_list_response', side_effect=lambda values, *a, **kw: (values, kw['headers'])),
    ):
        values, headers = mem_mod.get_memories(response=MagicMock(), uid='uid1', limit=7, offset=0, cursor='valid')
    assert values == ['bounded-page']
    assert headers['X-Omi-Memory-Next-Cursor'] == 'next-window'
    service.read.assert_not_called()


def test_index_window_invalid_cursor_restarts_first_page_with_continuation():
    service = MagicMock()
    service.read_page.side_effect = [
        HTTPException(400, 'invalid_or_stale_cursor:expired_cursor'),
        types.SimpleNamespace(memories=['fresh-page'], next_cursor='fresh-continuation', truncated=False),
    ]
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod.firestore_read_levers, 'lever_enabled', return_value=True),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'record_fallback') as fallback,
        patch.object(
            mem_mod,
            'list_read_budget_for_request',
            return_value=types.SimpleNamespace(truncated=False, observe=lambda *a: None),
        ),
        patch.object(mem_mod, 'memory_list_response', side_effect=lambda values, *a, **kw: (values, kw['headers'])),
    ):
        values, headers = mem_mod.get_memories(response=MagicMock(), uid='uid1', limit=7, offset=0, cursor='expired')
    assert values == ['fresh-page']
    assert headers['X-Omi-Memory-Next-Cursor'] == 'fresh-continuation'
    assert [call.kwargs['cursor'] for call in service.read_page.call_args_list] == ['expired', None]
    assert (
        service.read_page.call_args_list[0].kwargs['request_budget']
        is service.read_page.call_args.kwargs['request_budget']
    )
    service.read.assert_not_called()
    fallback.assert_called_once()


def test_index_window_valid_cursor_with_offset_preserves_400():
    import pytest

    service = MagicMock()
    service.read_page.return_value = types.SimpleNamespace(memories=[], next_cursor='next', truncated=False)
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod.firestore_read_levers, 'lever_enabled', return_value=True),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        pytest.raises(HTTPException) as exc_info,
    ):
        mem_mod.get_memories(response=MagicMock(), uid='uid1', limit=7, offset=14, cursor='valid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Memory cursor pagination cannot be combined with offset'
    service.read.assert_not_called()


def test_index_window_off_preserves_invalid_cursor_400():
    service = MagicMock()
    service.read_page.side_effect = HTTPException(400, 'invalid_or_stale_cursor:malformed_cursor')
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod.firestore_read_levers, 'lever_enabled', return_value=False),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
    ):
        try:
            mem_mod.get_memories(response=MagicMock(), uid='uid1', limit=7, offset=0, cursor='bad')
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError('off requests must retain the released invalid-cursor response')
    service.read.assert_not_called()
