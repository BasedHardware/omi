"""
Level 1 live test: fair-use API endpoints via FastAPI TestClient.

Tests the admin and user-facing endpoints with reduced thresholds.
"""

import os
import sys
import time
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy deps before importing the app
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# In-memory fair_use DB
_state_store = {}
_events = []

_fair_use_db = types.ModuleType('database.fair_use')
_fair_use_db.get_fair_use_state = lambda uid: _state_store.get(uid, {})
_fair_use_db.update_fair_use_state = lambda uid, u: _state_store.setdefault(uid, {}).update(u)
_fair_use_db.create_fair_use_event = lambda uid, d: (_events.append({**d, 'uid': uid}), f'evt-{len(_events)}')[1]
_fair_use_db.get_fair_use_events = lambda uid, limit=50: [e for e in _events if e.get('uid') == uid][:limit]
_fair_use_db.get_violation_counts = lambda uid: {'violation_count_7d': 0, 'violation_count_30d': 0}
_fair_use_db.resolve_fair_use_event = lambda uid, eid, admin_uid='', notes='': None
_fair_use_db.reset_fair_use_state = lambda uid, admin_uid='': _state_store.pop(uid, None)
_fair_use_db.get_flagged_users = lambda stage_filter=None, limit=50: []
sys.modules['database.fair_use'] = _fair_use_db

sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('utils.notifications', MagicMock())

os.environ['FAIR_USE_ENABLED'] = 'true'
os.environ['FAIR_USE_DAILY_SPEECH_MS'] = '10000'
os.environ['FAIR_USE_3DAY_SPEECH_MS'] = '20000'
os.environ['FAIR_USE_WEEKLY_SPEECH_MS'] = '30000'
os.environ['ADMIN_KEY'] = 'test-admin-key-12345'

from fastapi import FastAPI
from fastapi.testclient import TestClient

import utils.fair_use as fair_use

# Import the router
from routers.fair_use_admin import router as admin_router
from utils.other.endpoints import get_current_user_uid

app = FastAPI()
app.include_router(admin_router)
client = TestClient(app)

TEST_UID = f'api_test_{int(time.time())}'
ADMIN_HEADERS = {'X-Admin-Key': 'test-admin-key-12345'}


def _cleanup():
    _state_store.clear()
    _events.clear()
    try:
        fair_use.redis_client.delete(
            fair_use._redis_key(TEST_UID),
            f'fair_use:bucket:{TEST_UID}',
            f'fair_use:stage:{TEST_UID}',
            f'fair_use:vad_delta:{TEST_UID}',
        )
    except Exception:
        pass


@pytest.fixture(autouse=True)
def cleanup():
    _cleanup()
    yield
    _cleanup()


class TestAdminEndpoints:
    """Test admin fair-use endpoints."""

    def test_get_flagged_users(self):
        """GET /v1/admin/fair-use/flagged returns users list."""
        resp = client.get('/v1/admin/fair-use/flagged', headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert 'users' in data
        assert 'fair_use_enabled' in data
        assert data['fair_use_enabled'] is True

    def test_flagged_users_requires_admin_key(self):
        """GET without admin key should 422 (missing header)."""
        resp = client.get('/v1/admin/fair-use/flagged')
        assert resp.status_code == 422

    def test_flagged_users_rejects_bad_key(self):
        """GET with wrong admin key should 403."""
        resp = client.get('/v1/admin/fair-use/flagged', headers={'X-Admin-Key': 'wrong'})
        assert resp.status_code == 403

    def test_get_user_detail(self):
        """GET /v1/admin/fair-use/user/{uid} returns state + speech."""
        fair_use.record_speech_ms(TEST_UID, 5000)

        resp = client.get(f'/v1/admin/fair-use/user/{TEST_UID}', headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data['uid'] == TEST_UID
        assert 'current_speech_ms' in data
        assert data['current_speech_ms']['daily_ms'] == 5000

    def test_set_stage(self):
        """POST /v1/admin/fair-use/user/{uid}/set-stage updates stage."""
        resp = client.post(
            f'/v1/admin/fair-use/user/{TEST_UID}/set-stage?stage=warning',
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()['stage'] == 'warning'
        assert _state_store[TEST_UID]['stage'] == 'warning'

    def test_set_invalid_stage(self):
        """POST with invalid stage should 400."""
        resp = client.post(
            f'/v1/admin/fair-use/user/{TEST_UID}/set-stage?stage=ban',
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    def test_reset_user(self):
        """POST /v1/admin/fair-use/user/{uid}/reset clears state."""
        _state_store[TEST_UID] = {'stage': 'warning'}

        resp = client.post(f'/v1/admin/fair-use/user/{TEST_UID}/reset', headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert TEST_UID not in _state_store

    def test_set_stage_none_clears_enforcement(self):
        """Setting stage to 'none' should reset durations."""
        _state_store[TEST_UID] = {
            'stage': 'throttle',
            'throttle_until': datetime.utcnow() + timedelta(days=7),
        }

        resp = client.post(
            f'/v1/admin/fair-use/user/{TEST_UID}/set-stage?stage=none',
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200
        state = _state_store[TEST_UID]
        assert state['throttle_until'] is None
        assert state['restrict_until'] is None


class TestUserFacingEndpoint:
    """Test the user-facing /v1/fair-use/status endpoint."""

    def test_status_returns_speech_hours(self):
        """User can see their own fair-use status."""
        fair_use.record_speech_ms(TEST_UID, 5000)

        # Patch get_current_user_uid to return our test uid
        app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID
        resp = client.get('/v1/fair-use/status')
        app.dependency_overrides.pop(get_current_user_uid, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data['stage'] == 'none'
        assert 'speech_hours_today' in data
        assert 'message' in data
        assert 'normal limits' in data['message']

    def test_status_shows_warning_message(self):
        """Warning stage shows appropriate message."""
        _state_store[TEST_UID] = {'stage': 'warning'}

        app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID
        resp = client.get('/v1/fair-use/status')
        app.dependency_overrides.pop(get_current_user_uid, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data['stage'] == 'warning'
        assert 'personal conversations' in data['message']

    def test_status_shows_restrict_message(self):
        """Restrict stage shows support contact info."""
        _state_store[TEST_UID] = {'stage': 'restrict'}

        app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID
        resp = client.get('/v1/fair-use/status')
        app.dependency_overrides.pop(get_current_user_uid, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data['stage'] == 'restrict'
        assert 'team@basedhardware.com' in data['message']


class TestPublicCaseStatusEndpoint:
    """Test the unauthenticated public case status lookup."""

    def test_valid_case_ref_returns_status(self):
        """Public endpoint returns stage, message, timestamps, support_email."""
        _state_store[TEST_UID] = {'stage': 'warning'}
        _events.append(
            {
                'uid': TEST_UID,
                'case_ref': 'FU-AABBCCDDEEFF',
                'created_at': '2026-03-18 01:00:00',
            }
        )

        # Mock the Firestore collection_group query
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            'case_ref': 'FU-AABBCCDDEEFF',
            'created_at': '2026-03-18 01:00:00',
        }
        mock_doc.reference.path = f'users/{TEST_UID}/fair_use_events/evt-1'

        with patch.object(_db_client.db, 'collection_group') as mock_cg:
            mock_cg.return_value.where.return_value.limit.return_value.stream.return_value = [mock_doc]
            resp = client.get('/v1/fair-use/case/FU-AABBCCDDEEFF/status')

        assert resp.status_code == 200
        data = resp.json()
        assert data['case_ref'] == 'FU-AABBCCDDEEFF'
        assert data['stage'] == 'warning'
        assert data['support_email'] == 'team@basedhardware.com'
        assert 'message' in data
        assert 'created_at' in data
        assert 'updated_at' in data
        # Must NOT contain usage data or user identity
        assert 'uid' not in data
        assert 'usage_pct' not in data
        assert 'speech_hours' not in str(data)

    def test_invalid_case_ref_returns_404(self):
        """Unknown case ref returns 404."""
        with patch.object(_db_client.db, 'collection_group') as mock_cg:
            mock_cg.return_value.where.return_value.limit.return_value.stream.return_value = []
            resp = client.get('/v1/fair-use/case/FU-DOESNOTEXIST/status')

        assert resp.status_code == 404

    def test_no_auth_required(self):
        """Public endpoint works without any auth headers."""
        with patch.object(_db_client.db, 'collection_group') as mock_cg:
            mock_cg.return_value.where.return_value.limit.return_value.stream.return_value = []
            resp = client.get('/v1/fair-use/case/FU-ANYTHING/status')

        # Should get 404 (not found), NOT 401/403/422 (auth error)
        assert resp.status_code == 404


class TestCaseRefFormat:
    """Test case reference generation format."""

    def _generate_case_ref(self):
        """Generate case ref using the same logic as database.fair_use."""
        import uuid

        return f'FU-{uuid.uuid4().hex[:12].upper()}'

    def test_case_ref_format_and_length(self):
        """Case ref should be FU- prefix + 12 uppercase hex chars."""
        import re

        for _ in range(20):
            ref = self._generate_case_ref()
            assert ref.startswith('FU-')
            hex_part = ref[3:]
            assert len(hex_part) == 12
            assert re.match(r'^[0-9A-F]{12}$', hex_part)

    def test_case_refs_are_unique(self):
        """Generated refs should be unique (from UUID4)."""
        refs = {self._generate_case_ref() for _ in range(100)}
        assert len(refs) == 100
