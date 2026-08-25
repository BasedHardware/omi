"""Regression tests for UTC-anchored date parsing in MCP conversation search.

Both the REST endpoint (``/v1/mcp/conversations/search`` in routers/mcp.py) and the
SSE tool (``search_conversations`` in routers/mcp_sse.py) filter conversation vectors
by a UTC epoch ``created_at``. They used to parse the ``YYYY-MM-DD`` filter with a
naive ``datetime.strptime(...).timestamp()``, which is interpreted in the *server's*
local timezone. On any host east/west of UTC the window silently shifted by the UTC
offset, and the end date only matched up to its local midnight (dropping the rest of
the day). The fix anchors both bounds to UTC and includes the full end day.

These tests stub the data layer (same harness as test_mcp_search_memories.py, with
snapshot/restore so the stubs do not leak into sibling test modules) and assert on the
exact timestamps handed to ``query_vectors`` / ``get_conversations``.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.unit.memory_import_isolation import (  # noqa: E402
    install_mcp_search_memories_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_MCP_STUB_NAMES = [
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.dev_api_key',
    'database.screen_activity',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
    'google',
    'google.cloud',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'utils.other.storage',
    'utils.other.endpoints',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.render',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.log_sanitizer',
    'utils.executors',
    'utils.mcp_data',
    'utils.mcp_memories',
    'dependencies',
    'routers.mcp',
    'routers.mcp_sse',
    'utils',
    'utils.retrieval',
    'models',
]


@pytest.fixture(scope='module', autouse=True)
def _mcp_date_import_isolation():
    saved = snapshot_sys_modules(_MCP_STUB_NAMES)
    install_mcp_search_memories_stubs(_BACKEND_DIR)
    sys.modules.pop('routers.mcp', None)
    sys.modules.pop('routers.mcp_sse', None)
    import routers.mcp as mcp_router_mod
    import routers.mcp_sse as mcp_sse_router_mod

    globals()['mcp_router'] = mcp_router_mod
    globals()['mcp_sse_router'] = mcp_sse_router_mod
    yield
    restore_sys_modules(saved)
    sys.modules.pop('routers.mcp', None)
    sys.modules.pop('routers.mcp_sse', None)
    globals()['mcp_router'] = None
    globals()['mcp_sse_router'] = None


def _utc_epoch(y, m, d, hour=0, minute=0, second=0, microsecond=0):
    return int(datetime(y, m, d, hour, minute, second, microsecond, tzinfo=timezone.utc).timestamp())


class TestRestSearchUtcBounds:
    """/v1/mcp/conversations/search must filter on UTC day bounds, not server-local."""

    def test_start_date_anchors_to_utc_midnight(self):
        captured = {}

        def _query_vectors(query, uid, starts_at=None, ends_at=None, k=None):
            captured.update(starts_at=starts_at, ends_at=ends_at, k=k)
            return []

        with patch.object(mcp_router.vector_db, 'query_vectors', side_effect=_query_vectors):
            mcp_router.search_conversations(
                query='hi',
                start_date='2026-08-01',
                end_date='2026-08-02',
                uid='user-1',
            )

        assert captured['starts_at'] == _utc_epoch(2026, 8, 1)
        assert captured['ends_at'] == _utc_epoch(2026, 8, 2, hour=23, minute=59, second=59, microsecond=999999)

    def test_end_date_includes_full_end_day(self):
        captured = {}

        def _query_vectors(query, uid, starts_at=None, ends_at=None, k=None):
            captured.update(starts_at=starts_at, ends_at=ends_at, k=k)
            return []

        with patch.object(mcp_router.vector_db, 'query_vectors', side_effect=_query_vectors):
            mcp_router.search_conversations(query='hi', end_date='2026-08-01', uid='user-1')

        # 2026-08-01T23:59:59.999999Z, not 2026-08-01T00:00:00Z (naive local parse).
        assert captured['ends_at'] == _utc_epoch(2026, 8, 1, hour=23, minute=59, second=59, microsecond=999999)
        assert captured['starts_at'] is None

    def test_malformed_date_still_400(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            mcp_router.search_conversations(query='hi', start_date='not-a-date', uid='user-1')
        assert exc.value.status_code == 400


class TestSseSearchUtcBounds:
    """MCP SSE search_conversations must convert to UTC epoch bounds for the vector index."""

    def test_start_and_end_utc_bounds(self):
        captured = {}

        def _query_vectors(query, uid, starts_at=None, ends_at=None, k=None):
            captured.update(starts_at=starts_at, ends_at=ends_at, k=k)
            return []

        with patch.object(mcp_sse_router.vector_db, 'query_vectors', side_effect=_query_vectors):
            mcp_sse_router.execute_tool(
                'user-1',
                'search_conversations',
                {'query': 'hi', 'start_date': '2026-08-01', 'end_date': '2026-08-02'},
            )

        assert captured['starts_at'] == _utc_epoch(2026, 8, 1)
        assert captured['ends_at'] == _utc_epoch(2026, 8, 2, hour=23, minute=59, second=59, microsecond=999999)

    def test_get_conversations_utc_aware_dates(self):
        captured = {}

        def _get_conversations(uid, limit, offset, **kwargs):
            captured.update(start_date=kwargs.get('start_date'), end_date=kwargs.get('end_date'))
            return []

        with patch.object(mcp_sse_router.conversations_db, 'get_conversations', side_effect=_get_conversations):
            mcp_sse_router.execute_tool(
                'user-1', 'get_conversations', {'start_date': '2026-08-01', 'end_date': '2026-08-02'}
            )

        # Firestore compares against tz-aware UTC created_at; a naive datetime must not reach it.
        assert captured['start_date'].tzinfo is not None
        assert captured['start_date'].utcoffset() == timezone.utc.utcoffset(None)
        assert captured['end_date'] == datetime(2026, 8, 2, 23, 59, 59, 999999, tzinfo=timezone.utc)

    def test_action_items_due_dates_utc_aware(self):
        captured = {}

        def _get_action_items(uid, **kwargs):
            captured.update(due_start=kwargs.get('due_start_date'), due_end=kwargs.get('due_end_date'))
            return []

        with patch.object(mcp_sse_router.action_items_db, 'get_action_items', side_effect=_get_action_items):
            mcp_sse_router.execute_tool(
                'user-1',
                'get_action_items',
                {'due_start_date': '2026-08-01', 'due_end_date': '2026-08-02'},
            )

        assert captured['due_start'].tzinfo is not None
        assert captured['due_start'] == datetime(2026, 8, 1, tzinfo=timezone.utc)
        assert captured['due_end'] == datetime(2026, 8, 2, 23, 59, 59, 999999, tzinfo=timezone.utc)

    def test_screen_activity_end_bound_includes_full_end_day(self):
        """get_screen_activity must pass a UTC end bound that covers the whole
        end day. The DB layer formats the bound via strftime, so the router must
        apply the end-of-day increment before the parse's UTC midnight reaches it
        (previously the end bound was 00:00:00.999 of the end day, dropping the
        rest of the day)."""
        captured = {}

        def _get_screen_activity(uid, start_date=None, end_date=None, app_filter=None, limit=None):
            captured.update(start_date=start_date, end_date=end_date)
            return []

        with patch.object(mcp_sse_router.screen_activity_db, 'get_screen_activity', side_effect=_get_screen_activity):
            mcp_sse_router.execute_tool(
                'user-1',
                'get_screen_activity',
                {'start_date': '2026-08-01', 'end_date': '2026-08-02'},
            )

        assert captured['start_date'].tzinfo is not None
        assert captured['start_date'].utcoffset() == timezone.utc.utcoffset(None)
        assert captured['end_date'] == datetime(2026, 8, 2, 23, 59, 59, 999999, tzinfo=timezone.utc)

    def test_screen_activity_summary_end_bound_includes_full_end_day(self):
        captured = {}

        def _get_screen_activity_summary(uid, start_date=None, end_date=None):
            captured.update(start_date=start_date, end_date=end_date)
            return []

        with patch.object(
            mcp_sse_router.screen_activity_db, 'get_screen_activity_summary', side_effect=_get_screen_activity_summary
        ):
            mcp_sse_router.execute_tool(
                'user-1',
                'get_screen_activity',
                {'start_date': '2026-08-01', 'end_date': '2026-08-02', 'summary': True},
            )

        assert captured['end_date'] == datetime(2026, 8, 2, 23, 59, 59, 999999, tzinfo=timezone.utc)
