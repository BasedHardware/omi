"""Tests for the desktop Python backend CRUD migration (PR #6175).

Covers:
1. Pydantic request validation (boundary tests for all desktop models)
2. Wire-compatibility (notification settings field mapping, assistant settings
   deep-merge, message field expectations)
3. Score computation (weekly uses created_at, default_tab logic)
4. LLM usage (dual-write, cost-only sums desktop_chat bucket)
5. Batch limit (commit triggers at BATCH_LIMIT=500)
"""

import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies before any production imports
# ---------------------------------------------------------------------------
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

# Stub google.cloud.firestore sentinels used by desktop.py
firestore_stub = sys.modules["google.cloud.firestore"]
firestore_stub.Increment = lambda x: f"__increment_{x}__"
firestore_stub.Query = MagicMock()
firestore_stub.Query.ASCENDING = "ASCENDING"
firestore_stub.Query.DESCENDING = "DESCENDING"

# Stub FieldFilter — used by both desktop.py (via base_query) and other db modules (direct import)
field_filter_stub = sys.modules["google.cloud.firestore_v1.base_query"]
field_filter_stub.FieldFilter = MagicMock()
# Also expose FieldFilter on firestore_v1 directly (some modules do `from google.cloud.firestore_v1 import FieldFilter`)
sys.modules["google.cloud.firestore_v1"].FieldFilter = field_filter_stub.FieldFilter

# Add backend dir to sys.path so Python can find database/ and routers/
sys.path.insert(0, str(BACKEND_DIR))

# Stub database package and _client
if "database" not in sys.modules:
    db_pkg = _stub_package("database")
    db_pkg.__path__ = [str(BACKEND_DIR / "database")]
else:
    db_mod = sys.modules["database"]
    if not hasattr(db_mod, '__path__'):
        db_mod.__path__ = [str(BACKEND_DIR / "database")]

client_stub = _stub_module("database._client")
mock_db = MagicMock()
client_stub.db = mock_db

# Stub database.action_items (imported by desktop.py)
action_items_db_stub = _stub_module("database.action_items")
action_items_db_stub.create_action_item = MagicMock(return_value="test-action-id")
action_items_db_stub.get_action_item = MagicMock(return_value={'id': 'test-action-id', 'description': 'test'})

# Now we can import desktop.py — it will use our stubs
import database.desktop as desktop_db  # noqa: E402

# ---------------------------------------------------------------------------
# Stub utils.other.endpoints for routers that import it
# ---------------------------------------------------------------------------
_stub_package("utils")
_stub_package("utils.other")
endpoints_stub = _stub_module("utils.other.endpoints")
endpoints_stub.get_current_user_uid = MagicMock()

# ---------------------------------------------------------------------------
# Import Pydantic models from lightweight router files (chat_sessions,
# focus_sessions, advice).  routers/users.py has a massive import tree,
# so we define its two Pydantic models inline below to avoid stubbing
# 30+ transitive dependencies.
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from routers.chat_sessions import SaveMessageRequest, RateMessageRequest  # noqa: E402
from routers.focus_sessions import CreateFocusSessionRequest  # noqa: E402
from routers.advice import CreateAdviceRequest  # noqa: E402


# Mirrors routers/users.py:1203-1205 — defined inline to avoid importing
# the entire users router (which pulls in 30+ database/utils modules).
class UpdateNotificationSettingsRequest(BaseModel):
    enabled: bool | None = None
    frequency: int | None = Field(None, ge=0, le=5)


# Mirrors routers/users.py:1326-1333
class RecordDesktopLlmUsageRequest(BaseModel):
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cache_read_tokens: int = Field(0, ge=0)
    cache_write_tokens: int = Field(0, ge=0)
    total_tokens: int = Field(0, ge=0)
    cost_usd: float = Field(0.0, ge=0.0)
    account: str = Field('omi', max_length=100)


# ===========================================================================
# 1. PYDANTIC REQUEST VALIDATION (boundary tests)
# ===========================================================================


class TestSaveMessageRequestValidation:
    def test_empty_text_fails(self):
        """SaveMessageRequest with empty text (min_length=1) should fail."""
        with pytest.raises(ValidationError) as exc_info:
            SaveMessageRequest(text='', sender='human')
        assert 'text' in str(exc_info.value)

    def test_invalid_sender_fails(self):
        """SaveMessageRequest with sender not 'human' or 'ai' should fail."""
        with pytest.raises(ValidationError) as exc_info:
            SaveMessageRequest(text='hello', sender='bot')
        assert 'sender' in str(exc_info.value)

    def test_valid_human_sender(self):
        """SaveMessageRequest with sender='human' should pass."""
        msg = SaveMessageRequest(text='hello', sender='human')
        assert msg.sender == 'human'

    def test_valid_ai_sender(self):
        """SaveMessageRequest with sender='ai' should pass."""
        msg = SaveMessageRequest(text='reply', sender='ai')
        assert msg.sender == 'ai'


class TestRateMessageRequestValidation:
    def test_rating_2_fails(self):
        """RateMessageRequest with rating=2 (out of range -1..1) should fail."""
        with pytest.raises(ValidationError) as exc_info:
            RateMessageRequest(rating=2)
        assert 'rating' in str(exc_info.value)

    def test_rating_minus_2_fails(self):
        """RateMessageRequest with rating=-2 should fail."""
        with pytest.raises(ValidationError) as exc_info:
            RateMessageRequest(rating=-2)
        assert 'rating' in str(exc_info.value)

    def test_rating_1_passes(self):
        r = RateMessageRequest(rating=1)
        assert r.rating == 1

    def test_rating_minus_1_passes(self):
        r = RateMessageRequest(rating=-1)
        assert r.rating == -1

    def test_rating_none_passes(self):
        r = RateMessageRequest(rating=None)
        assert r.rating is None


class TestUpdateNotificationSettingsValidation:
    def test_frequency_6_fails(self):
        """UpdateNotificationSettingsRequest with frequency=6 (max is 5) should fail."""
        with pytest.raises(ValidationError) as exc_info:
            UpdateNotificationSettingsRequest(frequency=6)
        assert 'frequency' in str(exc_info.value)

    def test_frequency_5_passes(self):
        r = UpdateNotificationSettingsRequest(frequency=5)
        assert r.frequency == 5

    def test_frequency_0_passes(self):
        r = UpdateNotificationSettingsRequest(frequency=0)
        assert r.frequency == 0


class TestRecordDesktopLlmUsageValidation:
    def test_negative_tokens_fails(self):
        """RecordDesktopLlmUsageRequest with negative tokens should fail."""
        with pytest.raises(ValidationError) as exc_info:
            RecordDesktopLlmUsageRequest(input_tokens=-1)
        assert 'input_tokens' in str(exc_info.value)

    def test_negative_output_tokens_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            RecordDesktopLlmUsageRequest(output_tokens=-5)
        assert 'output_tokens' in str(exc_info.value)

    def test_default_account_is_omi(self):
        """RecordDesktopLlmUsageRequest default account is 'omi'."""
        r = RecordDesktopLlmUsageRequest()
        assert r.account == 'omi'

    def test_all_defaults_zero(self):
        """All token fields default to 0."""
        r = RecordDesktopLlmUsageRequest()
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.cache_read_tokens == 0
        assert r.total_tokens == 0
        assert r.cost_usd == 0.0


class TestCreateFocusSessionValidation:
    def test_invalid_status_fails(self):
        """CreateFocusSessionRequest with status not focused/distracted should fail."""
        with pytest.raises(ValidationError) as exc_info:
            CreateFocusSessionRequest(status='idle', app_or_site='Chrome', description='browsing')
        assert 'status' in str(exc_info.value)

    def test_valid_focused(self):
        r = CreateFocusSessionRequest(status='focused', app_or_site='VSCode', description='coding')
        assert r.status == 'focused'

    def test_valid_distracted(self):
        r = CreateFocusSessionRequest(status='distracted', app_or_site='Twitter', description='scrolling')
        assert r.status == 'distracted'


class TestCreateAdviceValidation:
    def test_confidence_above_1_fails(self):
        """CreateAdviceRequest with confidence > 1.0 should fail."""
        with pytest.raises(ValidationError) as exc_info:
            CreateAdviceRequest(content='take a break', confidence=1.5)
        assert 'confidence' in str(exc_info.value)

    def test_confidence_below_0_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateAdviceRequest(content='take a break', confidence=-0.1)
        assert 'confidence' in str(exc_info.value)

    def test_confidence_1_passes(self):
        r = CreateAdviceRequest(content='take a break', confidence=1.0)
        assert r.confidence == 1.0

    def test_confidence_default_is_half(self):
        r = CreateAdviceRequest(content='take a break')
        assert r.confidence == 0.5


# ===========================================================================
# 2. WIRE-COMPATIBILITY TESTS (mock Firestore)
# ===========================================================================


class TestNotificationSettingsWireCompat:
    """Verify notification settings return Swift-compatible field names."""

    def _mock_user_doc(self, data, exists=True):
        """Create a mock user doc snapshot."""
        snap = MagicMock()
        snap.exists = exists
        snap.to_dict.return_value = data
        return snap

    def test_returns_enabled_and_frequency_keys(self):
        """get_notification_settings returns 'enabled'/'frequency' not 'notifications_enabled'."""
        snap = self._mock_user_doc({'notifications_enabled': False, 'notification_frequency': 2})
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db.get_notification_settings('test-uid')

        assert 'enabled' in result
        assert 'frequency' in result
        assert 'notifications_enabled' not in result
        assert 'notification_frequency' not in result
        assert result['enabled'] is False
        assert result['frequency'] == 2

    def test_defaults_frequency_to_3_when_unset(self):
        """Frequency defaults to 3 when the user doc has no notification_frequency."""
        snap = self._mock_user_doc({})
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db.get_notification_settings('test-uid')

        assert result['frequency'] == 3
        assert result['enabled'] is True

    def test_defaults_when_doc_missing(self):
        """Returns defaults when user doc doesn't exist."""
        snap = self._mock_user_doc({}, exists=False)
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db.get_notification_settings('test-uid')

        assert result == {'enabled': True, 'frequency': 3}


class TestAssistantSettingsWireCompat:
    """Verify assistant settings deep-merge and update_channel handling."""

    def _mock_user_doc(self, data, exists=True):
        snap = MagicMock()
        snap.exists = exists
        snap.to_dict.return_value = data
        return snap

    def test_get_includes_update_channel(self):
        """get_assistant_settings includes top-level update_channel from user doc."""
        snap = self._mock_user_doc(
            {
                'assistant_settings': {'focus': {'enabled': True}},
                'update_channel': 'beta',
            }
        )
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db.get_assistant_settings('test-uid')

        assert result['update_channel'] == 'beta'
        assert result['focus'] == {'enabled': True}

    def test_deep_merge_preserves_sibling_sections(self):
        """update_assistant_settings deep-merges without destroying sibling sections."""
        existing_data = {
            'assistant_settings': {
                'focus': {'enabled': True, 'cooldown_interval': 30},
                'task': {'enabled': False},
            },
        }
        snap = self._mock_user_doc(existing_data)
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db.update_assistant_settings('test-uid', {'focus': {'enabled': False}})

        # focus.enabled should be updated, but focus.cooldown_interval preserved
        assert result['focus']['enabled'] is False
        assert result['focus']['cooldown_interval'] == 30
        # task section should be untouched
        assert result['task'] == {'enabled': False}

    def test_update_channel_written_to_top_level(self):
        """update_assistant_settings writes update_channel to top-level, not inside assistant_settings."""
        snap = self._mock_user_doc({'assistant_settings': {}})
        # Capture the update dict at call-time (Mock stores references, not copies,
        # and the code mutates `existing` after the Firestore write for the return value).
        captured_updates = {}

        def capture_update(data):
            import copy

            captured_updates.update(copy.deepcopy(data))

        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ref = mock_ud.return_value
            mock_ref.get.return_value = snap
            mock_ref.update.side_effect = capture_update
            desktop_db.update_assistant_settings('test-uid', {'update_channel': 'beta'})

        # Verify the update call includes update_channel at top level
        assert 'update_channel' in captured_updates
        assert captured_updates['update_channel'] == 'beta'
        # update_channel should NOT be inside assistant_settings at write time
        assert 'update_channel' not in captured_updates.get('assistant_settings', {})

    def test_raw_assistant_settings_excludes_update_channel(self):
        """_get_raw_assistant_settings does NOT include update_channel."""
        snap = self._mock_user_doc(
            {
                'assistant_settings': {'focus': {'enabled': True}},
                'update_channel': 'beta',
            }
        )
        with patch.object(desktop_db, '_user_doc') as mock_ud:
            mock_ud.return_value.get.return_value = snap
            result = desktop_db._get_raw_assistant_settings('test-uid')

        assert 'update_channel' not in result
        assert result == {'focus': {'enabled': True}}


class TestDesktopMessagesWireCompat:
    """Verify message field names match cross-platform expectations."""

    def test_get_desktop_messages_always_filters_by_plugin_id(self):
        """get_desktop_messages always filters by plugin_id, even when app_id is None."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.order_by.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        # Track FieldFilter calls via desktop_db's bound reference
        captured_ff_calls = []
        original_ff = desktop_db.FieldFilter

        def tracking_ff(field, op, value):
            captured_ff_calls.append((field, op, value))
            return original_ff(field, op, value)

        with patch.object(desktop_db, '_user_col', return_value=mock_col), patch.object(
            desktop_db, 'FieldFilter', side_effect=tracking_ff
        ):
            desktop_db.get_desktop_messages('test-uid', app_id=None)

        # Verify that FieldFilter was called with plugin_id == None
        plugin_id_filters = [(f, o, v) for f, o, v in captured_ff_calls if f == 'plugin_id']
        assert len(plugin_id_filters) >= 1, f"Expected plugin_id filter, got: {captured_ff_calls}"
        assert plugin_id_filters[0] == ('plugin_id', '==', None)

    def test_save_desktop_message_writes_expected_fields(self):
        """save_desktop_message writes plugin_id, chat_session_id, type='text', from_external_integration=False."""
        mock_col = MagicMock()
        mock_doc_ref = MagicMock()
        mock_col.document.return_value = mock_doc_ref
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = True

        # Mock acquire_chat_session to return a known session id
        with patch.object(desktop_db, '_user_col', return_value=mock_col), patch.object(
            desktop_db, 'acquire_chat_session', return_value='session-123'
        ):
            result = desktop_db.save_desktop_message('test-uid', text='hello', sender='human', app_id='my-app')

        # Verify the doc written to Firestore
        set_call = mock_doc_ref.set.call_args[0][0]
        assert set_call['plugin_id'] == 'my-app'
        assert set_call['app_id'] == 'my-app'
        assert set_call['chat_session_id'] == 'session-123'
        assert set_call['type'] == 'text'
        assert set_call['from_external_integration'] is False
        assert set_call['text'] == 'hello'
        assert set_call['sender'] == 'human'


# ===========================================================================
# 3. SCORE COMPUTATION TESTS (mock Firestore)
# ===========================================================================


class TestScoreComputation:
    """Verify score computation logic."""

    def _make_mock_doc(self, data):
        doc = MagicMock()
        doc.to_dict.return_value = data
        doc.id = data.get('id', 'doc-1')
        return doc

    def test_weekly_uses_created_at_not_due_at(self):
        """get_scores weekly query uses created_at field, not due_at."""
        mock_col = MagicMock()

        # Daily query (due_at) returns empty
        daily_query = MagicMock()
        daily_query.where.return_value = daily_query
        daily_query.stream.return_value = []

        # Weekly query (created_at) returns 1 completed task
        weekly_query = MagicMock()
        weekly_query.where.return_value = weekly_query
        weekly_doc = self._make_mock_doc({'completed': True, 'created_at': datetime.now(timezone.utc)})
        weekly_query.stream.return_value = [weekly_doc]

        # Overall stream returns same
        mock_col.stream.return_value = [weekly_doc]

        # Track which field filters are created.  FieldFilter is imported into
        # desktop.py's namespace, so patch it there (not on the stub module).
        captured_filters = []
        original_ff = desktop_db.FieldFilter

        def tracking_filter(field, op, value):
            captured_filters.append(field)
            return original_ff(field, op, value)

        call_count = [0]

        def col_where(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return daily_query
            else:
                return weekly_query

        mock_col.where = col_where

        with patch.object(desktop_db, '_user_col', return_value=mock_col), patch.object(
            desktop_db, 'FieldFilter', side_effect=tracking_filter
        ):
            result = desktop_db.get_scores('test-uid', date='2025-01-15')

        # Verify created_at was used in filter calls (for weekly query)
        assert 'created_at' in captured_filters, f"Expected created_at in filters, got: {captured_filters}"

    def test_default_tab_daily_when_highest(self):
        """default_tab is 'daily' when daily has tasks and highest score."""
        mock_col = MagicMock()

        # Daily: 2/2 completed = 100%
        daily_docs = [
            self._make_mock_doc({'completed': True}),
            self._make_mock_doc({'completed': True}),
        ]
        daily_query = MagicMock()
        daily_query.where.return_value = daily_query
        daily_query.stream.return_value = daily_docs

        # Weekly: 1/2 = 50%
        weekly_docs = [
            self._make_mock_doc({'completed': True}),
            self._make_mock_doc({'completed': False}),
        ]
        weekly_query = MagicMock()
        weekly_query.where.return_value = weekly_query
        weekly_query.stream.return_value = weekly_docs

        # Overall: same as weekly
        mock_col.stream.return_value = weekly_docs

        # get_scores calls col.where() once for daily, once for weekly
        # (the chained .where() calls go to the returned query object, not col)
        call_count = [0]

        def col_where(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return daily_query
            else:
                return weekly_query

        mock_col.where = col_where

        with patch.object(desktop_db, '_user_col', return_value=mock_col):
            result = desktop_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'daily'

    def test_default_tab_weekly_when_no_daily_tasks(self):
        """default_tab is 'weekly' when daily has no tasks."""
        mock_col = MagicMock()

        # Daily: 0 tasks
        daily_query = MagicMock()
        daily_query.where.return_value = daily_query
        daily_query.stream.return_value = []

        # Weekly: 1/1 = 100%
        weekly_doc = self._make_mock_doc({'completed': True})
        weekly_query = MagicMock()
        weekly_query.where.return_value = weekly_query
        weekly_query.stream.return_value = [weekly_doc]

        # Overall: 1/2 = 50%
        overall_docs = [
            self._make_mock_doc({'completed': True}),
            self._make_mock_doc({'completed': False}),
        ]
        mock_col.stream.return_value = overall_docs

        call_count = [0]

        def col_where(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return daily_query
            else:
                return weekly_query

        mock_col.where = col_where

        with patch.object(desktop_db, '_user_col', return_value=mock_col):
            result = desktop_db.get_scores('test-uid', date='2025-01-15')

        # daily score is 0 (no tasks), weekly is 100, overall is 50
        # weekly >= overall, so default_tab = 'weekly'
        assert result['default_tab'] == 'weekly'

    def test_default_tab_overall_when_lowest_weekly(self):
        """default_tab is 'overall' when overall score exceeds weekly."""
        mock_col = MagicMock()

        # Daily: 0 tasks
        daily_query = MagicMock()
        daily_query.where.return_value = daily_query
        daily_query.stream.return_value = []

        # Weekly: 0/1 = 0%
        weekly_query = MagicMock()
        weekly_query.where.return_value = weekly_query
        weekly_query.stream.return_value = [self._make_mock_doc({'completed': False})]

        # Overall: 1/1 = 100%
        mock_col.stream.return_value = [self._make_mock_doc({'completed': True})]

        call_count = [0]

        def col_where(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return daily_query
            else:
                return weekly_query

        mock_col.where = col_where

        with patch.object(desktop_db, '_user_col', return_value=mock_col):
            result = desktop_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'overall'


# ===========================================================================
# 4. LLM USAGE TESTS (mock Firestore)
# ===========================================================================


class TestLlmUsage:
    """Verify LLM usage dual-write and cost summation."""

    def test_record_dual_writes_desktop_chat_and_account(self):
        """record_desktop_llm_usage dual-writes both 'desktop_chat' and 'desktop_chat_{account}'."""
        mock_ref = MagicMock()
        with patch.object(desktop_db, '_user_col') as mock_col:
            mock_col.return_value.document.return_value = mock_ref
            desktop_db.record_desktop_llm_usage(
                'test-uid',
                input_tokens=100,
                output_tokens=50,
                account='anthropic',
            )

        # Verify set(merge=True) was called
        mock_ref.set.assert_called_once()
        update_data = mock_ref.set.call_args[0][0]
        assert mock_ref.set.call_args[1] == {'merge': True}

        # Must have both desktop_chat and desktop_chat_anthropic keys
        desktop_chat_keys = [k for k in update_data if k.startswith('desktop_chat.')]
        desktop_chat_acct_keys = [k for k in update_data if k.startswith('desktop_chat_anthropic.')]
        assert len(desktop_chat_keys) > 0, "Missing desktop_chat.* keys"
        assert len(desktop_chat_acct_keys) > 0, "Missing desktop_chat_anthropic.* keys"

        # Verify input_tokens increment is present for both buckets
        assert 'desktop_chat.input_tokens' in update_data
        assert 'desktop_chat_anthropic.input_tokens' in update_data

    def test_record_default_account_omi(self):
        """Default account produces desktop_chat_omi keys."""
        mock_ref = MagicMock()
        with patch.object(desktop_db, '_user_col') as mock_col:
            mock_col.return_value.document.return_value = mock_ref
            desktop_db.record_desktop_llm_usage('test-uid', input_tokens=10, output_tokens=5)

        update_data = mock_ref.set.call_args[0][0]
        assert 'desktop_chat_omi.input_tokens' in update_data

    def test_get_total_cost_only_sums_desktop_chat_bucket(self):
        """get_total_desktop_llm_cost only sums the desktop_chat bucket, not desktop_chat_{account}."""
        # Create mock docs that have both desktop_chat and desktop_chat_anthropic
        doc1 = MagicMock()
        doc1.to_dict.return_value = {
            'desktop_chat': {'cost_usd': 0.05, 'call_count': 10},
            'desktop_chat_anthropic': {'cost_usd': 0.05, 'call_count': 10},
        }
        doc2 = MagicMock()
        doc2.to_dict.return_value = {
            'desktop_chat': {'cost_usd': 0.03, 'call_count': 5},
            'desktop_chat_omi': {'cost_usd': 0.03, 'call_count': 5},
        }

        mock_col = MagicMock()
        mock_col.stream.return_value = [doc1, doc2]

        with patch.object(desktop_db, '_user_col', return_value=mock_col):
            total = desktop_db.get_total_desktop_llm_cost('test-uid')

        # Should only sum desktop_chat: 0.05 + 0.03 = 0.08
        assert total == round(0.08, 6)

    def test_get_total_cost_ignores_non_dict_desktop_chat(self):
        """get_total_desktop_llm_cost handles docs where desktop_chat is not a dict."""
        doc1 = MagicMock()
        doc1.to_dict.return_value = {'desktop_chat': 'corrupted', 'other_key': 123}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {'desktop_chat': {'cost_usd': 0.01}}

        mock_col = MagicMock()
        mock_col.stream.return_value = [doc1, doc2]

        with patch.object(desktop_db, '_user_col', return_value=mock_col):
            total = desktop_db.get_total_desktop_llm_cost('test-uid')

        assert total == 0.01


# ===========================================================================
# 5. BATCH LIMIT TEST
# ===========================================================================


class TestBatchLimit:
    """Verify _commit_batch triggers commit at BATCH_LIMIT=500."""

    def test_commit_at_batch_limit(self):
        """_commit_batch commits and returns fresh batch when count >= BATCH_LIMIT."""
        mock_batch = MagicMock()
        new_batch = MagicMock()
        desktop_db.db.batch.return_value = new_batch

        result_batch, result_count = desktop_db._commit_batch(mock_batch, 500)

        mock_batch.commit.assert_called_once()
        assert result_batch is new_batch
        assert result_count == 0

    def test_no_commit_below_limit(self):
        """_commit_batch does NOT commit when count < BATCH_LIMIT."""
        mock_batch = MagicMock()

        result_batch, result_count = desktop_db._commit_batch(mock_batch, 499)

        mock_batch.commit.assert_not_called()
        assert result_batch is mock_batch
        assert result_count == 499

    def test_batch_limit_is_500(self):
        """BATCH_LIMIT constant is 500."""
        assert desktop_db.BATCH_LIMIT == 500
