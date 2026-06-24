"""Regression test for POST /v1/task-integrations/{app_key}/tasks input validation.

create_task_via_integration parsed a free-form Optional[str] due_date with datetime.fromisoformat and no
guard, so an invalid value (e.g. "tomorrow") raised an unhandled ValueError that surfaced as HTTP 500.
It now returns 422 for a malformed due_date.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


for _n in [
    'database._client',
    'database.users',
    'database.redis_db',
    'firebase_admin',
    'firebase_admin.auth',
    'google.cloud.firestore',
]:
    if _n not in sys.modules:
        sys.modules[_n] = _AutoMockModule(_n)

# Provide a real callable for the auth dependency so FastAPI can resolve it.
_endpoints = sys.modules.get('utils.other.endpoints')
if _endpoints is None:
    _endpoints = ModuleType('utils.other.endpoints')
    sys.modules['utils.other.endpoints'] = _endpoints


def _fake_uid():  # pragma: no cover - dependency stand-in
    return 'uid1'


if not hasattr(_endpoints, 'get_current_user_uid'):
    _endpoints.get_current_user_uid = _fake_uid

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import routers.task_integrations as ti  # noqa: E402


def _client():
    app = FastAPI()
    app.include_router(ti.router)
    return TestClient(app, raise_server_exceptions=False)


def _connected_integration():
    ti.users_db.get_task_integration = MagicMock(return_value={'connected': True, 'access_token': 'tok'})


def test_invalid_due_date_returns_422_not_500():
    _connected_integration()
    with patch.object(ti, '_create_task_internal', new=AsyncMock(return_value={'success': True})) as internal:
        resp = _client().post('/v1/task-integrations/todoist/tasks', json={'title': 'x', 'due_date': 'tomorrow'})
    assert resp.status_code == 422
    internal.assert_not_called()


def test_valid_due_date_is_parsed_and_passed_through():
    _connected_integration()
    with patch.object(
        ti, '_create_task_internal', new=AsyncMock(return_value={'success': True, 'external_task_id': 'ext-1'})
    ) as internal:
        resp = _client().post(
            '/v1/task-integrations/todoist/tasks', json={'title': 'x', 'due_date': '2026-06-09T15:00:00Z'}
        )
    assert resp.status_code == 200
    internal.assert_called_once()
    assert isinstance(internal.call_args.kwargs['due_date'], datetime)


def test_no_due_date_passes_through():
    _connected_integration()
    with patch.object(
        ti, '_create_task_internal', new=AsyncMock(return_value={'success': True, 'external_task_id': 'ext-2'})
    ) as internal:
        resp = _client().post('/v1/task-integrations/todoist/tasks', json={'title': 'x'})
    assert resp.status_code == 200
    internal.assert_called_once()
    assert internal.call_args.kwargs['due_date'] is None
