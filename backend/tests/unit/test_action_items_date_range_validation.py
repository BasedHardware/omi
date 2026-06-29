"""GET /v1/action-items must reject an inverted date range instead of silently returning nothing.

get_action_items accepts start_date/end_date (created_at) and due_start_date/due_end_date (due_at)
filters and forwards them straight to Firestore inequality filters. FastAPI Query() cannot validate
one parameter against another, so an inverted range (start > end) was passed through unguarded:
Firestore then applies conflicting `>=` and `<=` filters and returns an empty list, so the caller
gets "no action items" and cannot tell a bad request apart from a genuinely empty result. The
endpoint now validates start <= end for both pairs and returns 400 first.

This mounts the action-items router with its heavy dependencies stubbed (same harness as the other
router unit tests) and calls the handler directly.
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from datetime import datetime

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
    'database.action_items',
    'database.conversations',
    'database.redis_db',
    'database.vector_db',
    'utils.users',
    'utils.notifications',
    'utils.task_sync',
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


# Import the real, lightweight utils submodule the router needs at module level
# (utils.executors line 6) BEFORE stubbing, so it stays cached as the real module. The stub loop
# replaces sys.modules['utils'] with an AutoMock (a side effect of stubbing utils.users etc.); we
# re-pin the real utils package afterward so `from utils.executors import ...` resolves the real one.
import utils as _real_utils_pkg  # noqa: E402
import utils.executors  # noqa: E402,F401

_save_module_for_restore('utils')

for _mod_name in _stubs:
    _register_module(_mod_name, _AutoMockModule(_mod_name))

# Re-pin the real utils package so its real submodule (executors) loads.
sys.modules['utils'] = _real_utils_pkg

# utils.other.endpoints exposes the auth dependency used in route signatures; FastAPI builds the
# dependant at decoration time, so it needs a real callable, not a MagicMock.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_register_module('utils.other.endpoints', _endpoints)

from fastapi import HTTPException  # noqa: E402

_remove_module_for_fresh_import('routers.action_items')
_remove_module_for_fresh_import('routers')
try:
    from routers import action_items as ai  # noqa: E402
finally:
    _restore_stubbed_modules()


def _call(**overrides):
    kwargs = dict(
        limit=50,
        offset=0,
        completed=None,
        conversation_id=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
        uid='u1',
    )
    kwargs.update(overrides)
    return ai.get_action_items(**kwargs)


def test_inverted_created_date_range_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_inverted_due_date_range_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call(due_start_date=datetime(2024, 12, 31), due_end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_equal_dates_are_allowed():
    # An inclusive range where start == end is valid and must not be rejected.
    same = datetime(2024, 6, 1)
    with patch.object(ai.action_items_db, 'get_action_items', return_value=[]):
        result = _call(start_date=same, end_date=same)
    assert result == {"action_items": [], "has_more": False}


def test_valid_range_passes_through():
    with patch.object(ai.action_items_db, 'get_action_items', return_value=[]):
        result = _call(start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31))
    assert result == {"action_items": [], "has_more": False}
