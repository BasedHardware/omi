"""Regression test for PATCH /v1/conversations/{id}/events index bounds.

set_conversation_events_state took parallel lists events_idx / values and only guarded the
UPPER bound (event_idx >= len(events)). Two bugs followed:

  1. A negative event_idx (e.g. -1) passed the guard and wrote to events[-1] -- silent
     corruption of the wrong event.
  2. events_idx and values of mismatched length let data.values[i] raise IndexError -> HTTP 500.

The fix rejects a length mismatch with 422 and bounds-checks both ends
(0 <= event_idx < len(events)) so a negative or out-of-range index is skipped instead of
corrupting data or 500ing. This test mounts the conversations router (heavy deps stubbed, same
pattern as the other router unit tests) and calls the handler directly.
"""

import os
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

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


# Import the real, lightweight utils submodules the router actually needs at module level
# (utils.executors line 42, utils.conversations.factory line 31) BEFORE stubbing, so they stay
# cached as the real modules. The stub loop below replaces sys.modules['utils'] with an AutoMock
# (a side effect of auto-stubbing utils.other.*); we re-pin the real utils package afterward so
# `from utils.executors import ...` resolves the real module instead of an empty-path stub.
import utils as _real_utils_pkg  # noqa: E402
import utils.executors  # noqa: E402,F401
import utils.conversations  # noqa: E402,F401
import utils.conversations.factory  # noqa: E402,F401

_save_module_for_restore('utils')

for _mod_name in _stubs:
    _register_module(_mod_name, _AutoMockModule(_mod_name))

# Re-pin the real utils package so its real submodules (executors, conversations.factory) load.
sys.modules['utils'] = _real_utils_pkg

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI needs
# real callables to build the dependants, so provide small stand-ins.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_endpoints.get_user = MagicMock()
_register_module('utils.other.endpoints', _endpoints)

from fastapi import HTTPException  # noqa: E402

_remove_module_for_fresh_import('routers.conversations')
_remove_module_for_fresh_import('routers')
try:
    from routers import conversations as conv  # noqa: E402
    from models.conversation import SetConversationEventsStateRequest  # noqa: E402
finally:
    _restore_stubbed_modules()


class _FakeEvent:
    """Minimal stand-in for a structured event: tracks .created and is .dict()-able."""

    def __init__(self):
        self.created = False

    def dict(self):
        return {'created': self.created}


def _fake_conversation_with_events(count):
    events = [_FakeEvent() for _ in range(count)]
    structured = SimpleNamespace(events=events)
    return SimpleNamespace(structured=structured), events


def test_mismatched_lengths_returns_422():
    """events_idx longer than values must 422, not IndexError -> 500."""
    convo, _events = _fake_conversation_with_events(2)
    with patch.object(conv, '_get_valid_conversation_by_id', return_value={'id': 'c1'}), patch.object(
        conv, 'deserialize_conversation', return_value=convo
    ):
        data = SetConversationEventsStateRequest(events_idx=[0, 1], values=[True])
        with pytest.raises(HTTPException) as exc:
            conv.set_conversation_events_state('c1', data, uid='u1')
        assert exc.value.status_code == 422


def test_negative_index_is_skipped_not_corrupting():
    """A negative event_idx (-1) must NOT write to the last event."""
    convo, events = _fake_conversation_with_events(2)
    with patch.object(conv, '_get_valid_conversation_by_id', return_value={'id': 'c1'}), patch.object(
        conv, 'deserialize_conversation', return_value=convo
    ):
        data = SetConversationEventsStateRequest(events_idx=[-1], values=[True])
        result = conv.set_conversation_events_state('c1', data, uid='u1')

    # No event should have been mutated by the out-of-range negative index.
    assert all(event.created is False for event in events)
    assert result == {"status": "Ok"}


def test_valid_index_still_updates():
    """Sanity: an in-range index still applies the value (fix must not break the happy path)."""
    convo, events = _fake_conversation_with_events(2)
    with patch.object(conv, '_get_valid_conversation_by_id', return_value={'id': 'c1'}), patch.object(
        conv, 'deserialize_conversation', return_value=convo
    ):
        data = SetConversationEventsStateRequest(events_idx=[1], values=[True])
        conv.set_conversation_events_state('c1', data, uid='u1')

    assert events[1].created is True
    assert events[0].created is False
