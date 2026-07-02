"""GET /v1/conversations and /v1/conversations/count must reject an inverted date range.

Both endpoints accept start_date/end_date filters and forward them straight to Firestore inequality
filters (created_at >= start, created_at <= end). FastAPI Query() cannot validate one parameter
against another, so an inverted range (start > end) was passed through: Firestore then applies a
contradictory pair of filters and returns an empty list / a count of zero, so the caller cannot tell
a malformed request apart from a genuinely empty result. Both endpoints now validate start <= end
and return 400 first.

The comparison also normalizes timezone awareness first: FastAPI parses a query datetime as naive or
aware depending on whether the client included an offset, and comparing a naive against an aware
datetime raises TypeError (a 500). The endpoints normalize both bounds to UTC before comparing.

This mounts the conversations router with its heavy dependencies stubbed (same harness as the other
router unit tests) and calls the handlers directly.
"""

import os
import sys
from enum import Enum
from types import ModuleType
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_stubs = [
    'ulid',
    'pinecone',
    'typesense',
    'database._client',
    'database.conversations',
    'database.action_items',
    'database.memories',
    'database.redis_db',
    'database.users',
    'database.vector_db',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.conversations.factory',
    'utils.conversations.render',
    'utils.conversations.process_conversation',
    'utils.conversations.search',
    'utils.conversations.calendar_linking',
    'utils.conversations.calendar_utils',
    'utils.conversations.location',
    'utils.llm.conversation_processing',
    'utils.speaker_identification',
    'utils.app_integrations',
    'utils.retrieval.tools.calendar_tools',
    'utils.retrieval.tools.google_utils',
]

_MISSING = object()
_saved_modules = {}
_saved_parent_attrs = {}


def _save_module_for_restore(name):
    if name not in _saved_modules:
        _saved_modules[name] = sys.modules.get(name, _MISSING)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        key = (parent_name, attr)
        if key not in _saved_parent_attrs:
            previous_attr = parent.__dict__.get(attr, _MISSING) if parent is not None else _MISSING
            _saved_parent_attrs[key] = (parent, previous_attr)


def _register_module(name, module):
    _save_module_for_restore(name)
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if not isinstance(parent, _AutoMockModule):
            parent = _AutoMockModule(parent_name)
            _register_module(parent_name, parent)
        setattr(parent, attr, module)
    return module


def _remove_module_for_fresh_import(name):
    _save_module_for_restore(name)
    sys.modules.pop(name, None)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            parent.__dict__.pop(attr, None)


def _restore_stubbed_modules():
    for name in sorted(_saved_modules, key=lambda item: item.count('.'), reverse=True):
        previous = _saved_modules[name]
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    for (_parent_name, attr), (parent, previous_attr) in _saved_parent_attrs.items():
        if parent is None:
            continue
        if previous_attr is _MISSING:
            parent.__dict__.pop(attr, None)
        else:
            setattr(parent, attr, previous_attr)
    _saved_modules.clear()
    _saved_parent_attrs.clear()


# Import the real, lightweight utils submodules the router needs at module level BEFORE stubbing, so
# they stay cached as the real modules. The stub loop replaces sys.modules['utils'] with an AutoMock
# (a side effect of stubbing utils.other.*); we re-pin the real utils package afterward.
import utils as _real_utils_pkg  # noqa: E402
import utils.executors  # noqa: E402,F401
import utils.conversations  # noqa: E402,F401
import utils.conversations.factory  # noqa: E402,F401

_save_module_for_restore('utils')

for _mod_name in _stubs:
    _register_module(_mod_name, _AutoMockModule(_mod_name))

sys.modules['utils'] = _real_utils_pkg

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI builds the
# dependants at decoration time, so it needs real callables.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_endpoints.get_user = MagicMock()
_register_module('utils.other.endpoints', _endpoints)

_utils_memory_pkg = ModuleType('utils.memory')
_utils_memory_pkg.__path__ = []
_register_module('utils.memory', _utils_memory_pkg)

_memory_service_stub = ModuleType('utils.memory.memory_service')
setattr(_memory_service_stub, 'MemoryService', MagicMock())
_register_module('utils.memory.memory_service', _memory_service_stub)


class _MemorySystem(str, Enum):
    LEGACY = 'legacy'
    CANONICAL = 'canonical'


_memory_system_stub = ModuleType('utils.memory.memory_system')
setattr(_memory_system_stub, 'MemorySystem', _MemorySystem)
_register_module('utils.memory.memory_system', _memory_system_stub)

_canonical_activation_stub = ModuleType('utils.memory.canonical_activation')
setattr(_canonical_activation_stub, 'canonical_write_enabled', MagicMock(return_value=False))
_register_module('utils.memory.canonical_activation', _canonical_activation_stub)

_surface_routing_stub = ModuleType('utils.memory.surface_routing')
setattr(_surface_routing_stub, 'pin_memory_system', MagicMock())
_register_module('utils.memory.surface_routing', _surface_routing_stub)

_apps_stub = ModuleType('utils.apps')
setattr(_apps_stub, 'get_available_app_by_id_with_reviews', MagicMock())
setattr(_apps_stub, 'get_is_user_paid_app', MagicMock(return_value=False))
_register_module('utils.apps', _apps_stub)

_request_validation_stub = ModuleType('utils.request_validation')
setattr(_request_validation_stub, 'NonNegativeOffset', int)
setattr(_request_validation_stub, 'PositiveLimit', int)
_register_module('utils.request_validation', _request_validation_stub)

from fastapi import HTTPException  # noqa: E402

_remove_module_for_fresh_import('routers.conversations')
_remove_module_for_fresh_import('routers')
try:
    from routers import conversations as conv  # noqa: E402
finally:
    _restore_stubbed_modules()


def _call_list(**overrides):
    kwargs = dict(
        limit=100,
        offset=0,
        statuses="processing,completed",
        include_discarded=True,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        uid='u1',
    )
    kwargs.update(overrides)
    return conv.get_conversations(**kwargs)


def _call_count(**overrides):
    kwargs = dict(
        statuses=None,
        include_discarded=False,
        start_date=None,
        end_date=None,
        folder_id=None,
        starred=None,
        uid='u1',
    )
    kwargs.update(overrides)
    return conv.get_conversations_count(**kwargs)


def test_inverted_range_list_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call_list(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_inverted_range_count_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call_count(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_mixed_timezone_awareness_inverted_returns_400():
    # A naive bound compared against an aware bound must still yield a clean 400, not a TypeError 500.
    with pytest.raises(HTTPException) as exc:
        _call_list(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert exc.value.status_code == 400


def test_equal_dates_are_allowed():
    same = datetime(2024, 6, 1)
    with patch.object(conv.conversations_db, 'get_conversations_count', return_value=0):
        result = _call_count(start_date=same, end_date=same)
    assert result == {'count': 0}


def test_valid_range_passes_through():
    with patch.object(conv.conversations_db, 'get_conversations_count', return_value=0):
        result = _call_count(start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31, tzinfo=timezone.utc))
    assert result == {'count': 0}
