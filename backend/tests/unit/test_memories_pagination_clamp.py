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
    from fastapi import HTTPException

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Memory cursor unavailable")
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
    from fastapi import HTTPException

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Canonical memory unavailable")
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
    from fastapi import HTTPException

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Historical memory unavailable")
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == ['memory-from-offset-read']
    service.read_page.assert_called_once()
    service.read.assert_called_once()


def test_first_page_falls_back_to_offset_read_when_scan_row_budget_is_exhausted():
    """Prod 2026-08-18: first pages 504'd at the 30s edge timeout (~100/h).

    Once the ``memories`` composite indexes went READY the keyset scans actually
    served, and an account whose historical set is fully suppressed by canonical
    made ``read_page`` walk every historical row before it could emit anything.
    The walk now stops at the scan row budget; the offset ``read`` path does not
    walk suppressed rows, so the first page must fall back to it.
    """
    from fastapi import HTTPException

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail=mem_mod.MEMORY_LIST_SCAN_BUDGET_DETAIL)
    service.read.return_value = ['memory-from-offset-read']

    result = _get_first_page(service)

    assert result == ['memory-from-offset-read']
    service.read_page.assert_called_once()
    service.read.assert_called_once()


def test_first_page_propagates_unrelated_503_detail():
    from fastapi import HTTPException

    import pytest

    service = MagicMock()
    service.read_page.side_effect = HTTPException(status_code=503, detail="Some other degradation")

    with pytest.raises(HTTPException) as exc_info:
        _get_first_page(service)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Some other degradation"
    service.read.assert_not_called()


def test_first_page_propagates_non_503_errors():
    from fastapi import HTTPException

    import pytest

    service = MagicMock()
    service.read_page.side_effect = HTTPException(
        status_code=402, detail="A paid plan is required to access this memory."
    )

    with pytest.raises(HTTPException) as exc_info:
        _get_first_page(service)

    assert exc_info.value.status_code == 402
    service.read.assert_not_called()
