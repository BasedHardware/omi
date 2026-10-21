"""Hermetic router-resilience tests for ``backend/routers/focus_sessions.py`` (issue #22531).

Covers the four safeguards the issue asks for:
1. ``_require_session_id`` rejects blank / traversal / reserved / oversized document ids
2. ``DELETE`` returns 404 when the data layer reports a missing document
3. whitespace-only ``app_or_site`` / ``description`` / ``app_filter`` payloads are
   stripped (blank required fields rejected with 400, blank filter normalized to None)
4. every data-layer call is wrapped in an error boundary that logs via ``sanitize``
   and raises a clean HTTP 500

No Firestore, no network: the data layer, auth and sanitizer are stubbed in
``sys.modules`` before the router module is loaded from file, mirroring the
isolation approach used across this suite.
"""

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    restore_sys_modules,
    snapshot_sys_modules,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROUTER_PATH = BACKEND_DIR / 'routers' / 'focus_sessions.py'

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


# ---------------------------------------------------------------------------
# Module isolation harness
# ---------------------------------------------------------------------------
def _stub_module(name, **attrs):
    mod = sys.modules.get(name)
    if mod is None:
        mod = AutoMockModule(name)
        sys.modules[name] = mod
    for key, value in attrs.items():
        setattr(mod, key, value)
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, mod)
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, mod)
    return mod


_ISOLATED_MODULE_NAMES = (
    'database',
    'database.focus_sessions',
    'database.screen_activity',
    'utils',
    'utils.log_sanitizer',
    'utils.other',
    'utils.other.endpoints',
    'utils.request_validation',
    'models',
    'models.focus_session',
    'models.screen_activity',
    'models.shared',
    'focus_sessions_router_under_test',
)


@pytest.fixture(autouse=True)
def isolated_router():
    """Load the router with every heavy dependency stubbed; restore afterwards."""
    snap = snapshot_sys_modules(_ISOLATED_MODULE_NAMES)

    _stub_package('database')
    focus_db = _stub_module('database.focus_sessions')
    screen_db = _stub_module('database.screen_activity')

    _stub_package('utils')
    _stub_module('utils.log_sanitizer', sanitize=lambda s: s)
    _stub_package('utils.other')
    _stub_module('utils.other.endpoints', get_current_user_uid=MagicMock(name='get_current_user_uid'))
    _stub_module('utils.request_validation', validate_calendar_date=lambda value: value)

# wire models stay real: models.focus_session / models.screen_activity / models.shared are
    # pure pydantic+stdlib, so the router's response_model classes validate for FastAPI

    spec = importlib.util.spec_from_file_location('focus_sessions_router_under_test', str(ROUTER_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    yield types.SimpleNamespace(router=mod, focus_db=focus_db, screen_db=screen_db)

    restore_sys_modules(snap)


# ---------------------------------------------------------------------------
# 1. _require_session_id — path coordinate validation
# ---------------------------------------------------------------------------
def test_rejects_blank_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('')
    assert err.value.status_code == 400


def test_rejects_whitespace_only_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('   ')
    assert err.value.status_code == 400


def test_rejects_dot_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('.')
    assert err.value.status_code == 400


def test_rejects_dotdot_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('..')
    assert err.value.status_code == 400


def test_rejects_path_traversal_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('a/../b')
    assert err.value.status_code == 400


def test_rejects_embedded_slash_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('x/y')
    assert err.value.status_code == 400


def test_rejects_reserved_double_underscore_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('__proto__')
    assert err.value.status_code == 400


def test_rejects_reserved_bare_double_underscore_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('__')
    assert err.value.status_code == 400


def test_rejects_oversized_session_id(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router._require_session_id('k' * 1501)
    assert err.value.status_code == 400


def test_accepts_max_length_session_id(isolated_router):
    assert isolated_router.router._require_session_id('k' * 1500) == 'k' * 1500


def test_strips_surrounding_whitespace_from_session_id(isolated_router):
    assert isolated_router.router._require_session_id('  abc123  ') == 'abc123'


# ---------------------------------------------------------------------------
# 2. DELETE — 404 on missing document, error boundary
# ---------------------------------------------------------------------------
def test_delete_returns_404_when_missing(isolated_router):
    isolated_router.focus_db.delete_focus_session.return_value = False
    with pytest.raises(HTTPException) as err:
        isolated_router.router.delete_focus_session('sess-1', uid='u1')
    assert err.value.status_code == 404
    assert err.value.detail == 'Focus session not found'


def test_delete_returns_ok_when_deleted(isolated_router):
    isolated_router.focus_db.delete_focus_session.return_value = True
    assert isolated_router.router.delete_focus_session('sess-1', uid='u1') == {'status': 'ok'}


def test_delete_maps_data_layer_error_to_500(isolated_router, caplog):
    isolated_router.focus_db.delete_focus_session.side_effect = RuntimeError('firestore boom <token>')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.delete_focus_session('sess-1', uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to delete focus session'
    assert 'firestore boom' in caplog.text  # raw detail stays in the server log


def test_delete_rejects_blank_id_without_touching_data_layer(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router.delete_focus_session('   ', uid='u1')
    assert err.value.status_code == 400
    isolated_router.focus_db.delete_focus_session.assert_not_called()


def test_delete_passes_stripped_id_to_data_layer(isolated_router):
    isolated_router.focus_db.delete_focus_session.return_value = True
    isolated_router.router.delete_focus_session('  sess-9  ', uid='u1')
    isolated_router.focus_db.delete_focus_session.assert_called_once_with('u1', 'sess-9')


# ---------------------------------------------------------------------------
# 3. POST — whitespace payloads rejected/stripped, error boundary
# ---------------------------------------------------------------------------
def _create_request(router, app_or_site='  Slack  ', description='  deep work  ', message='  hi  ', duration_seconds=60):
    return router.CreateFocusSessionRequest(
        status='focused', app_or_site=app_or_site, description=description,
        message=message, duration_seconds=duration_seconds,
    )


def test_create_strips_fields_before_data_layer(isolated_router):
    isolated_router.focus_db.create_focus_session.return_value = {'id': 'f1'}
    isolated_router.router.create_focus_session(_create_request(isolated_router.router, ), uid='u1')
    _, kwargs = isolated_router.focus_db.create_focus_session.call_args
    assert kwargs['app_or_site'] == 'Slack'
    assert kwargs['description'] == 'deep work'
    assert kwargs['message'] == 'hi'


def test_create_rejects_whitespace_only_app_or_site(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router.create_focus_session(_create_request(isolated_router.router, app_or_site='   '), uid='u1')
    assert err.value.status_code == 400
    isolated_router.focus_db.create_focus_session.assert_not_called()


def test_create_rejects_whitespace_only_description(isolated_router):
    with pytest.raises(HTTPException) as err:
        isolated_router.router.create_focus_session(_create_request(isolated_router.router, description='   '), uid='u1')
    assert err.value.status_code == 400
    isolated_router.focus_db.create_focus_session.assert_not_called()


def test_create_allows_none_message(isolated_router):
    isolated_router.focus_db.create_focus_session.return_value = {'id': 'f1'}
    isolated_router.router.create_focus_session(_create_request(isolated_router.router, message=None), uid='u1')
    _, kwargs = isolated_router.focus_db.create_focus_session.call_args
    assert kwargs['message'] is None


def test_create_maps_data_layer_error_to_500(isolated_router):
    isolated_router.focus_db.create_focus_session.side_effect = RuntimeError('store down')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.create_focus_session(_create_request(isolated_router.router, ), uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to create focus session'


def test_create_returns_data_layer_result(isolated_router):
    isolated_router.focus_db.create_focus_session.return_value = {'id': 'f1'}
    assert isolated_router.router.create_focus_session(_create_request(isolated_router.router, ), uid='u1') == {'id': 'f1'}


# ---------------------------------------------------------------------------
# 4. GET list + stats — error boundaries
# ---------------------------------------------------------------------------
def test_get_focus_sessions_maps_data_layer_error_to_500(isolated_router):
    isolated_router.focus_db.get_focus_sessions.side_effect = RuntimeError('query failed')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.get_focus_sessions(limit=10, offset=0, date=None, uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to load focus sessions'


def test_get_focus_sessions_forwards_pagination_and_date(isolated_router):
    isolated_router.focus_db.get_focus_sessions.return_value = []
    isolated_router.router.get_focus_sessions(limit=7, offset=3, date='2026-10-21', uid='u1')
    isolated_router.focus_db.get_focus_sessions.assert_called_once_with(
        'u1', limit=7, offset=3, date='2026-10-21')


def test_get_focus_sessions_returns_deserialized_rows(isolated_router):
    isolated_router.focus_db.get_focus_sessions.return_value = [{'id': 'a'}]
    assert isolated_router.router.get_focus_sessions(limit=1, offset=0, date=None, uid='u1') == []


def test_get_focus_stats_maps_data_layer_error_to_500(isolated_router):
    isolated_router.focus_db.get_focus_stats.side_effect = RuntimeError('stats failed')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.get_focus_stats(date=None, uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to load focus stats'


def test_get_focus_stats_returns_data_layer_result(isolated_router):
    isolated_router.focus_db.get_focus_stats.return_value = {'total': 5}
    assert isolated_router.router.get_focus_stats(date='2026-10-21', uid='u1') == {'total': 5}


# ---------------------------------------------------------------------------
# 5. screen-activity — app_filter normalization + error boundaries
# ---------------------------------------------------------------------------
def test_screen_activity_blank_app_filter_normalized_to_none(isolated_router):
    isolated_router.screen_db.get_screen_activity.return_value = []
    isolated_router.router.list_screen_activity(date=None, app_filter='   ', limit=10, uid='u1')
    _, kwargs = isolated_router.screen_db.get_screen_activity.call_args
    assert kwargs['app_filter'] is None


def test_screen_activity_strips_app_filter(isolated_router):
    isolated_router.screen_db.get_screen_activity.return_value = []
    isolated_router.router.list_screen_activity(date=None, app_filter='  Slack  ', limit=10, uid='u1')
    _, kwargs = isolated_router.screen_db.get_screen_activity.call_args
    assert kwargs['app_filter'] == 'Slack'


def test_screen_activity_maps_data_layer_error_to_500(isolated_router):
    isolated_router.screen_db.get_screen_activity.side_effect = RuntimeError('scan failed')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.list_screen_activity(date=None, app_filter=None, limit=10, uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to load screen activity'


def test_screen_activity_returns_data_layer_result(isolated_router):
    isolated_router.screen_db.get_screen_activity.return_value = [{'id': 'r1'}]
    assert isolated_router.router.list_screen_activity(date=None, app_filter=None, limit=1, uid='u1') == [{'id': 'r1'}]


def test_screen_activity_summary_maps_data_layer_error_to_500(isolated_router):
    isolated_router.screen_db.get_screen_activity_summary.side_effect = RuntimeError('summary failed')
    with pytest.raises(HTTPException) as err:
        isolated_router.router.screen_activity_summary(date=None, uid='u1')
    assert err.value.status_code == 500
    assert err.value.detail == 'Failed to load screen activity summary'


def test_screen_activity_summary_returns_data_layer_result(isolated_router):
    isolated_router.screen_db.get_screen_activity_summary.return_value = {'apps': {}, 'total_screenshots': 0}
    assert isolated_router.router.screen_activity_summary(date='2026-10-21', uid='u1') == {
        'apps': {}, 'total_screenshots': 0}
