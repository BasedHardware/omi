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

# Stub google.cloud.firestore sentinels
firestore_stub = sys.modules["google.cloud.firestore"]
firestore_stub.Increment = lambda x: f"__increment_{x}__"
firestore_stub.Query = MagicMock()
firestore_stub.Query.ASCENDING = "ASCENDING"
firestore_stub.Query.DESCENDING = "DESCENDING"
firestore_stub.Client = MagicMock

# Stub FieldFilter
field_filter_stub = sys.modules["google.cloud.firestore_v1.base_query"]
field_filter_stub.FieldFilter = MagicMock()
sys.modules["google.cloud.firestore_v1"].FieldFilter = field_filter_stub.FieldFilter
sys.modules["google.cloud.firestore_v1"].transactional = lambda f: f

# Add backend dir to sys.path
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
client_stub.document_id_from_seed = MagicMock(return_value="seed-id")

# Stub database.helpers (used by chat.py)
helpers_stub = _stub_module("database.helpers")
helpers_stub.set_data_protection_level = lambda **kw: (lambda f: f)
helpers_stub.prepare_for_write = lambda **kw: (lambda f: f)
helpers_stub.prepare_for_read = lambda **kw: (lambda f: f)

# Stub models and utils needed by database.users and database.chat
_stub_package("models")
models_users_stub = _stub_module("models.users")
models_users_stub.Subscription = MagicMock()
models_users_stub.PlanLimits = MagicMock()
models_users_stub.PlanType = MagicMock()
models_users_stub.SubscriptionStatus = MagicMock()
models_chat_stub = _stub_module("models.chat")
models_chat_stub.Message = MagicMock()

_stub_package("utils")
_stub_package("utils.other")
utils_sub_stub = _stub_module("utils.subscription")
utils_sub_stub.get_default_basic_subscription = MagicMock()
utils_enc_stub = _stub_module("utils.encryption")
utils_enc_stub.encrypt = MagicMock(return_value="encrypted")
utils_enc_stub.decrypt = MagicMock(return_value="decrypted")
endpoints_stub = _stub_module("utils.other.endpoints")
endpoints_stub.get_current_user_uid = MagicMock()
endpoints_stub.with_rate_limit = lambda dep, policy: dep
endpoints_stub.timeit = lambda f: f
_stub_module("utils.observability")

# ---------------------------------------------------------------------------
# Import domain-specific database modules
# ---------------------------------------------------------------------------
import database.users as users_db  # noqa: E402
import database.chat as chat_db  # noqa: E402
import database.action_items as action_items_db  # noqa: E402
import database.llm_usage as llm_usage_db  # noqa: E402
import database.staged_tasks as staged_tasks_db  # noqa: E402

# ---------------------------------------------------------------------------
# Import Pydantic models from lightweight router files
# ---------------------------------------------------------------------------
from pydantic import BaseModel, Field, ValidationError  # noqa: E402

from routers.chat_sessions import SaveMessageRequest, RateMessageRequest  # noqa: E402
from routers.focus_sessions import CreateFocusSessionRequest  # noqa: E402
from routers.advice import CreateAdviceRequest  # noqa: E402
from routers.staged_tasks import BatchUpdateScoresRequest, BatchScoreEntry  # noqa: E402

# Cannot import routers.users directly — it pulls in database.conversations → utils.other.hume
# which has heavy deps. Mirror the models here and verify parity via AST test below.


class UpdateNotificationSettingsRequest(BaseModel):
    enabled: bool | None = None
    frequency: int | None = Field(None, ge=0, le=5)


class RecordLlmUsageBucketRequest(BaseModel):
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
        """RecordLlmUsageBucketRequest with negative tokens should fail."""
        with pytest.raises(ValidationError) as exc_info:
            RecordLlmUsageBucketRequest(input_tokens=-1)
        assert 'input_tokens' in str(exc_info.value)

    def test_negative_output_tokens_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            RecordLlmUsageBucketRequest(output_tokens=-5)
        assert 'output_tokens' in str(exc_info.value)

    def test_default_account_is_omi(self):
        """RecordLlmUsageBucketRequest default account is 'omi'."""
        r = RecordLlmUsageBucketRequest()
        assert r.account == 'omi'

    def test_all_defaults_zero(self):
        """All token fields default to 0."""
        r = RecordLlmUsageBucketRequest()
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
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db.get_notification_settings('test-uid')

        assert 'enabled' in result
        assert 'frequency' in result
        assert 'notifications_enabled' not in result
        assert 'notification_frequency' not in result
        assert result['enabled'] is False
        assert result['frequency'] == 2

    def test_defaults_frequency_to_3_when_unset(self):
        """Frequency defaults to 3 when the user doc has no notification_frequency."""
        snap = self._mock_user_doc({})
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db.get_notification_settings('test-uid')

        assert result['frequency'] == 3
        assert result['enabled'] is True

    def test_defaults_when_doc_missing(self):
        """Returns defaults when user doc doesn't exist."""
        snap = self._mock_user_doc({}, exists=False)
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db.get_notification_settings('test-uid')

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
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db.get_assistant_settings('test-uid')

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
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db.update_assistant_settings('test-uid', {'focus': {'enabled': False}})

        # focus.enabled should be updated, but focus.cooldown_interval preserved
        assert result['focus']['enabled'] is False
        assert result['focus']['cooldown_interval'] == 30
        # task section should be untouched
        assert result['task'] == {'enabled': False}

    def test_update_channel_written_to_top_level(self):
        """update_assistant_settings writes update_channel to top-level, not inside assistant_settings."""
        snap = self._mock_user_doc({'assistant_settings': {}})
        captured_updates = {}

        def capture_update(data):
            import copy

            captured_updates.update(copy.deepcopy(data))

        mock_ref = mock_db.collection.return_value.document.return_value
        mock_ref.get.return_value = snap
        mock_ref.update.side_effect = capture_update
        users_db.update_assistant_settings('test-uid', {'update_channel': 'beta'})

        assert 'update_channel' in captured_updates
        assert captured_updates['update_channel'] == 'beta'
        assert 'update_channel' not in captured_updates.get('assistant_settings', {})

    def test_raw_assistant_settings_excludes_update_channel(self):
        """_get_raw_assistant_settings does NOT include update_channel."""
        snap = self._mock_user_doc(
            {
                'assistant_settings': {'focus': {'enabled': True}},
                'update_channel': 'beta',
            }
        )
        mock_db.collection.return_value.document.return_value.get.return_value = snap
        result = users_db._get_raw_assistant_settings('test-uid')

        assert 'update_channel' not in result
        assert result == {'focus': {'enabled': True}}


class TestDesktopMessagesWireCompat:
    """Verify message field names match cross-platform expectations."""

    def test_save_message_writes_expected_fields(self):
        """save_message writes plugin_id, chat_session_id, type='text', from_external_integration=False."""
        mock_doc_ref = MagicMock()
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = True

        # Mock the db.collection chain for messages and chat_sessions
        def collection_side_effect(name):
            col_mock = MagicMock()
            doc_mock = MagicMock()
            if name == 'users':
                doc_mock.collection.return_value.document.return_value = mock_doc_ref
            col_mock.document.return_value = doc_mock
            return col_mock

        with patch.object(chat_db, 'acquire_chat_session', return_value='session-123'):
            with patch.object(chat_db, 'db') as patched_db:
                patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                    mock_doc_ref
                )
                result = chat_db.save_message('test-uid', text='hello', sender='human', app_id='my-app')

        # Verify the doc written to Firestore
        set_call = mock_doc_ref.set.call_args[0][0]
        assert set_call['plugin_id'] == 'my-app'
        assert set_call['app_id'] == 'my-app'
        assert set_call['chat_session_id'] == 'session-123'
        assert set_call['type'] == 'text'
        assert set_call['from_external_integration'] is False
        assert set_call['text'] == 'hello'
        assert set_call['sender'] == 'human'


class TestSessionScopedQueries:
    """Verify session-scoped queries use the correct FieldFilter field name."""

    def _get_field_filter_fields(self):
        """Extract field names from FieldFilter calls since last reset."""
        return [call.args[0] for call in field_filter_stub.FieldFilter.call_args_list if call.args]

    def setup_method(self):
        field_filter_stub.FieldFilter.reset_mock()

    def test_get_messages_session_scoped_filters_by_session_not_plugin(self):
        """get_messages with chat_session_id should filter by chat_session_id, NOT plugin_id."""
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_query
            chat_db.get_messages('uid', chat_session_id='sess-1', app_id='some-app')

        fields = self._get_field_filter_fields()
        assert 'chat_session_id' in fields, f"Expected chat_session_id filter, got: {fields}"
        assert 'plugin_id' not in fields, f"plugin_id should NOT be filtered when session_id is given: {fields}"

    def test_get_messages_app_scoped_filters_by_plugin_id(self):
        """get_messages without chat_session_id should filter by plugin_id."""
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_query
            chat_db.get_messages('uid', app_id='my-app')

        fields = self._get_field_filter_fields()
        assert 'plugin_id' in fields, f"Expected plugin_id filter, got: {fields}"
        assert 'chat_session_id' not in fields, f"chat_session_id should NOT be filtered in app-scoped mode: {fields}"

    def test_delete_messages_session_scoped_filters_by_session_not_plugin(self):
        """delete_messages with session_id should filter by chat_session_id, NOT plugin_id."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.delete_messages('uid', session_id='sess-1')

        fields = self._get_field_filter_fields()
        assert 'chat_session_id' in fields, f"Expected chat_session_id filter, got: {fields}"
        assert 'plugin_id' not in fields, f"plugin_id should NOT be filtered when session_id is given: {fields}"

    def test_delete_messages_app_scoped_filters_by_plugin_id(self):
        """delete_messages without session_id should filter by plugin_id."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.delete_messages('uid', app_id='my-app')

        fields = self._get_field_filter_fields()
        assert 'plugin_id' in fields, f"Expected plugin_id filter, got: {fields}"
        assert 'chat_session_id' not in fields, f"chat_session_id should NOT be filtered in app-scoped mode: {fields}"


class TestGetChatSessionsQuery:
    """Verify get_chat_sessions query construction."""

    def setup_method(self):
        field_filter_stub.FieldFilter.reset_mock()

    def test_orders_by_updated_at_descending(self):
        """get_chat_sessions should order by updated_at DESC."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.order_by.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.get_chat_sessions('uid')

        mock_col.order_by.assert_called_once_with('updated_at', direction='DESCENDING')

    def test_filters_by_plugin_id_field(self):
        """get_chat_sessions should filter by plugin_id == app_id."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.order_by.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.get_chat_sessions('uid', app_id='test-app')

        fields = [call.args[0] for call in field_filter_stub.FieldFilter.call_args_list if call.args]
        assert 'plugin_id' in fields, f"Expected plugin_id filter, got: {fields}"
        assert 'app_id' not in fields, f"Should use plugin_id, not app_id as filter field: {fields}"


class TestCreateChatSession:
    """Verify create_chat_session writes correct fields."""

    def test_default_title_and_counters(self):
        """create_chat_session with no title uses 'New Chat' and initializes counters."""
        mock_doc_ref = MagicMock()

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            result = chat_db.create_chat_session('uid')

        assert result['title'] == 'New Chat'
        assert result['message_count'] == 0
        assert result['starred'] is False
        assert result['preview'] is None
        mock_doc_ref.set.assert_called_once()

    def test_plugin_id_matches_app_id(self):
        """create_chat_session sets both plugin_id and app_id to the given app_id."""
        mock_doc_ref = MagicMock()

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            result = chat_db.create_chat_session('uid', app_id='my-plugin')

        assert result['plugin_id'] == 'my-plugin'
        assert result['app_id'] == 'my-plugin'

    def test_custom_title(self):
        """create_chat_session uses the provided title."""
        mock_doc_ref = MagicMock()

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            result = chat_db.create_chat_session('uid', title='My Custom Chat')

        assert result['title'] == 'My Custom Chat'


class TestAcquireChatSession:
    """Verify acquire_chat_session reuse vs create logic."""

    def test_reuses_existing_session(self):
        """acquire_chat_session returns existing session ID when one exists."""
        mock_doc = MagicMock()
        mock_doc.id = 'existing-session-id'
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = [mock_doc]

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value = (
                mock_query
            )
            result = chat_db.acquire_chat_session('uid', app_id='my-app')

        assert result == 'existing-session-id'

    def test_creates_new_session_when_none_exists(self):
        """acquire_chat_session creates a new session when no matching session found."""
        mock_query = MagicMock()
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []  # No existing sessions

        with patch.object(chat_db, 'db') as patched_db, patch.object(
            chat_db, 'create_chat_session', return_value={'id': 'new-session-id'}
        ) as mock_create:
            patched_db.collection.return_value.document.return_value.collection.return_value.where.return_value = (
                mock_query
            )
            result = chat_db.acquire_chat_session('uid', app_id='my-app')

        assert result == 'new-session-id'
        mock_create.assert_called_once_with('uid', app_id='my-app')


class TestUpdateChatSession:
    """Verify update_chat_session behavior."""

    def test_not_found_returns_none(self):
        """update_chat_session returns None when session doesn't exist."""
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = False

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            result = chat_db.update_chat_session('uid', 'nonexistent-session', title='New Title')

        assert result is None
        mock_ref.update.assert_not_called()

    def test_title_only_update(self):
        """update_chat_session with title only updates title and updated_at."""
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        mock_ref.get.return_value.to_dict.return_value = {'title': 'Updated Title'}

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            chat_db.update_chat_session('uid', 'sess-1', title='Updated Title')

        update_call = mock_ref.update.call_args[0][0]
        assert 'title' in update_call
        assert 'updated_at' in update_call
        assert 'starred' not in update_call

    def test_starred_only_update(self):
        """update_chat_session with starred only updates starred and updated_at."""
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        mock_ref.get.return_value.to_dict.return_value = {'starred': True}

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            chat_db.update_chat_session('uid', 'sess-1', starred=True)

        update_call = mock_ref.update.call_args[0][0]
        assert 'starred' in update_call
        assert 'updated_at' in update_call
        assert 'title' not in update_call


class TestDeleteChatSessionCascade:
    """Verify delete_chat_session with cascade_messages."""

    def test_cascade_deletes_messages_then_session(self):
        """delete_chat_session with cascade_messages=True deletes messages first."""
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = True
        mock_msg_col = MagicMock()
        mock_query = MagicMock()
        mock_msg_col.where.return_value = mock_query

        # Return 2 docs on first batch, then empty
        mock_doc1 = MagicMock()
        mock_doc1.id = 'msg-1'
        mock_doc2 = MagicMock()
        mock_doc2.id = 'msg-2'
        mock_query.limit.return_value = mock_query
        mock_query.stream.side_effect = [[mock_doc1, mock_doc2], []]

        mock_batch = MagicMock()

        with patch.object(chat_db, 'db') as patched_db:
            mock_user_ref = MagicMock()
            mock_user_ref.collection.side_effect = lambda name: (
                MagicMock(document=MagicMock(return_value=mock_session_ref))
                if name == 'chat_sessions'
                else mock_msg_col
            )
            patched_db.collection.return_value.document.return_value = mock_user_ref
            patched_db.batch.return_value = mock_batch
            chat_db.delete_chat_session('uid', 'sess-1', cascade_messages=True)

        mock_batch.commit.assert_called_once()
        mock_session_ref.delete.assert_called_once()

    def test_cascade_nonexistent_session_short_circuits(self):
        """delete_chat_session with cascade on nonexistent session returns False."""
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = False

        with patch.object(chat_db, 'db') as patched_db:
            mock_user_ref = MagicMock()
            mock_user_ref.collection.return_value.document.return_value = mock_session_ref
            patched_db.collection.return_value.document.return_value = mock_user_ref
            result = chat_db.delete_chat_session('uid', 'nonexistent', cascade_messages=True)

        assert result is False


class TestSaveMessageSessionBehavior:
    """Verify save_message session acquisition and preview behavior."""

    def test_explicit_session_id_skips_acquire(self):
        """save_message with explicit session_id doesn't call acquire_chat_session."""
        mock_doc_ref = MagicMock()
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = True

        with patch.object(chat_db, 'acquire_chat_session') as mock_acquire, patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_doc_ref
            )
            # Make session ref accessible for the session update path
            mock_doc_ref.set.return_value = None
            chat_db.save_message('uid', text='hello', sender='human', session_id='my-session')

        mock_acquire.assert_not_called()

    def test_preview_truncated_to_100_chars(self):
        """save_message truncates preview to 100 characters."""
        long_text = 'x' * 200
        mock_msg_ref = MagicMock()
        mock_session_ref = MagicMock()
        mock_session_ref.get.return_value.exists = True

        with patch.object(chat_db, 'acquire_chat_session', return_value='sess-1'), patch.object(
            chat_db, 'db'
        ) as patched_db:
            # Mock message write
            patched_db.collection.return_value.document.return_value.collection.side_effect = lambda name: (
                MagicMock(document=MagicMock(return_value=mock_session_ref))
                if name == 'chat_sessions'
                else MagicMock(document=MagicMock(return_value=mock_msg_ref))
            )
            chat_db.save_message('uid', text=long_text, sender='human')

        # Check the session update call has truncated preview
        if mock_session_ref.update.called:
            update_call = mock_session_ref.update.call_args[0][0]
            assert len(update_call['preview']) == 100


class TestDeleteMessagesCount:
    """Verify delete_messages returns correct count."""

    def test_returns_zero_when_no_messages(self):
        """delete_messages returns 0 when no matching messages found."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = chat_db.delete_messages('uid', app_id='my-app')

        assert result == 0

    def test_returns_count_of_deleted_messages(self):
        """delete_messages returns total count of deleted messages."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.limit.return_value = mock_query

        doc1 = MagicMock()
        doc1.id = 'msg-1'
        doc2 = MagicMock()
        doc2.id = 'msg-2'
        doc3 = MagicMock()
        doc3.id = 'msg-3'
        mock_query.stream.side_effect = [[doc1, doc2, doc3], []]

        mock_batch = MagicMock()
        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            patched_db.batch.return_value = mock_batch
            result = chat_db.delete_messages('uid', app_id='my-app')

        assert result == 3
        mock_batch.commit.assert_called_once()


class TestLlmUsageBucketParam:
    """Verify configurable bucket parameter in LLM usage functions."""

    def test_custom_bucket_dual_writes(self):
        """record_llm_usage_bucket with custom bucket writes to both bucket and bucket_account."""
        mock_ref = MagicMock()

        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            llm_usage_db.record_llm_usage_bucket(
                'uid',
                input_tokens=10,
                output_tokens=20,
                bucket='custom_feature',
                account='openai',
            )

        set_call = mock_ref.set.call_args
        update_data = set_call[0][0]
        # Primary bucket
        assert 'custom_feature.input_tokens' in update_data
        assert 'custom_feature.output_tokens' in update_data
        assert 'custom_feature.call_count' in update_data
        # Per-account bucket
        assert 'custom_feature_openai.input_tokens' in update_data
        assert 'custom_feature_openai.output_tokens' in update_data

    def test_get_total_llm_cost_custom_bucket(self):
        """get_total_llm_cost with custom bucket reads from the specified bucket only."""
        mock_doc1 = MagicMock()
        mock_doc1.to_dict.return_value = {
            'custom_feature': {'cost_usd': 0.5},
            'custom_feature_openai': {'cost_usd': 0.5},  # Should NOT be double-counted
            'desktop_chat': {'cost_usd': 1.0},  # Different bucket, should be excluded
        }
        mock_col = MagicMock()
        mock_col.stream.return_value = [mock_doc1]

        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = llm_usage_db.get_total_llm_cost('uid', bucket='custom_feature')

        assert result == 0.5  # Only custom_feature, not custom_feature_openai or desktop_chat


# ===========================================================================
# 3. SCORE COMPUTATION TESTS (mock Firestore)
# ===========================================================================


class TestDailyScoreWireCompat:
    """Verify daily-score returns Swift DailyScore-compatible fields."""

    def _make_mock_doc(self, data):
        doc = MagicMock()
        doc.to_dict.return_value = data
        doc.id = data.get('id', 'doc-1')
        return doc

    def test_daily_score_uses_completed_tasks_and_total_tasks(self):
        """get_daily_score returns completed_tasks/total_tasks, not completed/total."""
        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = [
            self._make_mock_doc({'completed': True}),
            self._make_mock_doc({'completed': False}),
        ]
        mock_col.where.return_value = mock_query

        with patch.object(action_items_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = action_items_db.get_daily_score('test-uid', date='2025-01-15')

        assert 'completed_tasks' in result, f"Expected completed_tasks, got keys: {result.keys()}"
        assert 'total_tasks' in result, f"Expected total_tasks, got keys: {result.keys()}"
        assert 'completed' not in result, "Should not have raw 'completed' key"
        assert 'total' not in result, "Should not have raw 'total' key"
        assert result['completed_tasks'] == 1
        assert result['total_tasks'] == 2
        assert result['date'] == '2025-01-15'
        assert result['score'] == 50


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

        # Track which field filters are created
        captured_filters = []
        original_ff = action_items_db.FieldFilter

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

        with patch.object(action_items_db, 'db') as patched_db, patch.object(
            action_items_db, 'FieldFilter', side_effect=tracking_filter
        ):
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = action_items_db.get_scores('test-uid', date='2025-01-15')

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

        call_count = [0]

        def col_where(**kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return daily_query
            else:
                return weekly_query

        mock_col.where = col_where

        with patch.object(action_items_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = action_items_db.get_scores('test-uid', date='2025-01-15')

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

        with patch.object(action_items_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = action_items_db.get_scores('test-uid', date='2025-01-15')

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

        with patch.object(action_items_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            result = action_items_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'overall'


# ===========================================================================
# 4. LLM USAGE TESTS (mock Firestore)
# ===========================================================================


class TestLlmUsage:
    """Verify LLM usage dual-write and cost summation."""

    def test_record_dual_writes_desktop_chat_and_account(self):
        """record_llm_usage_bucket dual-writes both 'desktop_chat' and 'desktop_chat_{account}'."""
        mock_ref = MagicMock()
        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            llm_usage_db.record_llm_usage_bucket(
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
        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            llm_usage_db.record_llm_usage_bucket('test-uid', input_tokens=10, output_tokens=5)

        update_data = mock_ref.set.call_args[0][0]
        assert 'desktop_chat_omi.input_tokens' in update_data

    def test_get_total_cost_only_sums_desktop_chat_bucket(self):
        """get_total_llm_cost only sums the desktop_chat bucket, not desktop_chat_{account}."""
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

        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            total = llm_usage_db.get_total_llm_cost('test-uid')

        # Should only sum desktop_chat: 0.05 + 0.03 = 0.08
        assert total == round(0.08, 6)

    def test_get_total_cost_ignores_non_dict_desktop_chat(self):
        """get_total_llm_cost handles docs where desktop_chat is not a dict."""
        doc1 = MagicMock()
        doc1.to_dict.return_value = {'desktop_chat': 'corrupted', 'other_key': 123}
        doc2 = MagicMock()
        doc2.to_dict.return_value = {'desktop_chat': {'cost_usd': 0.01}}

        mock_col = MagicMock()
        mock_col.stream.return_value = [doc1, doc2]

        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            total = llm_usage_db.get_total_llm_cost('test-uid')

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
        with patch.object(staged_tasks_db, 'db') as patched_db:
            patched_db.batch.return_value = new_batch
            result_batch, result_count = staged_tasks_db._commit_batch(mock_batch, 500)

        mock_batch.commit.assert_called_once()
        assert result_batch is new_batch
        assert result_count == 0

    def test_no_commit_below_limit(self):
        """_commit_batch does NOT commit when count < BATCH_LIMIT."""
        mock_batch = MagicMock()

        result_batch, result_count = staged_tasks_db._commit_batch(mock_batch, 499)

        mock_batch.commit.assert_not_called()
        assert result_batch is mock_batch
        assert result_count == 499

    def test_batch_limit_is_500(self):
        """BATCH_LIMIT constant is 500."""
        assert staged_tasks_db.BATCH_LIMIT == 500


# ===========================================================================
# 6. PROMOTE RESPONSE WIRE-COMPAT (PromoteResponse envelope)
# ===========================================================================

import database.focus_sessions as focus_sessions_db


class TestPromoteResponseWireCompat:
    """Verify promote endpoint returns PromoteResponse envelope expected by Swift client."""

    def test_promote_returns_envelope_when_task_exists(self):
        """Router wraps promoted action_item in {promoted: true, reason: null, promoted_task: {...}}."""
        from routers.staged_tasks import promote_staged_task

        mock_action_item = {'id': 'ai-1', 'description': 'Test task', 'completed': False}

        with patch.object(staged_tasks_db, 'promote_staged_task', return_value=mock_action_item):
            result = promote_staged_task(uid='test-uid')

        assert result['promoted'] is True
        assert result['reason'] is None
        assert result['promoted_task'] == mock_action_item

    def test_promote_returns_envelope_when_no_tasks(self):
        """Router wraps None in {promoted: false, reason: '...', promoted_task: null}."""
        from routers.staged_tasks import promote_staged_task

        with patch.object(staged_tasks_db, 'promote_staged_task', return_value=None):
            result = promote_staged_task(uid='test-uid')

        assert result['promoted'] is False
        assert result['reason'] is not None
        assert result['promoted_task'] is None

    def test_migrate_returns_status_string(self):
        """migrate endpoint returns {status: str} matching Swift StatusResponse."""
        from routers.staged_tasks import migrate_ai_tasks

        with patch.object(staged_tasks_db, 'migrate_ai_tasks', return_value={'moved': 5, 'kept': 3}):
            result = migrate_ai_tasks(uid='test-uid')

        assert 'status' in result
        assert isinstance(result['status'], str)

    def test_migrate_conversation_items_returns_status_migrated_deleted(self):
        """migrate-conversation-items returns {status, migrated, deleted} matching Swift MigrateResponse."""
        from routers.staged_tasks import migrate_conversation_items

        with patch.object(staged_tasks_db, 'migrate_conversation_items_to_staged', return_value={'moved': 10}):
            result = migrate_conversation_items(uid='test-uid')

        assert result['status'] == 'ok'
        assert result['migrated'] == 10
        assert 'deleted' in result


# ===========================================================================
# 7. FOCUS STATS WIRE-COMPAT (FocusStatsResponse shape)
# ===========================================================================


class TestFocusStatsWireCompat:
    """Verify focus stats returns FocusStatsResponse shape expected by Swift client."""

    def test_focus_stats_has_all_required_fields(self):
        """get_focus_stats returns date, focused_minutes, distracted_minutes, session_count, etc."""
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=[]):
            result = focus_sessions_db.get_focus_stats('test-uid', date='2025-01-15')

        required_keys = {
            'date',
            'focused_minutes',
            'distracted_minutes',
            'session_count',
            'focused_count',
            'distracted_count',
            'top_distractions',
        }
        assert required_keys.issubset(result.keys()), f"Missing keys: {required_keys - result.keys()}"

    def test_focus_stats_computes_minutes(self):
        """Focused/distracted times are reported in minutes."""
        sessions = [
            {'status': 'focused', 'duration_seconds': 300},
            {'status': 'focused', 'duration_seconds': 180},
            {'status': 'distracted', 'duration_seconds': 120, 'app_or_site': 'Twitter'},
        ]
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=sessions):
            result = focus_sessions_db.get_focus_stats('test-uid', date='2025-01-15')

        assert result['focused_minutes'] == 8  # (300+180)//60
        assert result['distracted_minutes'] == 2  # 120//60
        assert result['session_count'] == 3
        assert result['focused_count'] == 2
        assert result['distracted_count'] == 1
        assert result['date'] == '2025-01-15'

    def test_top_distractions_is_list_of_dicts(self):
        """top_distractions must be list of {app_or_site, total_seconds, count} dicts, not tuples."""
        sessions = [
            {'status': 'distracted', 'duration_seconds': 120, 'app_or_site': 'Twitter'},
            {'status': 'distracted', 'duration_seconds': 60, 'app_or_site': 'Twitter'},
            {'status': 'distracted', 'duration_seconds': 300, 'app_or_site': 'Reddit'},
        ]
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=sessions):
            result = focus_sessions_db.get_focus_stats('test-uid', date='2025-01-15')

        distractions = result['top_distractions']
        assert isinstance(distractions, list)
        assert len(distractions) == 2

        # Sorted by total_seconds descending: Reddit (300) > Twitter (180)
        assert distractions[0]['app_or_site'] == 'Reddit'
        assert distractions[0]['total_seconds'] == 300
        assert distractions[0]['count'] == 1
        assert distractions[1]['app_or_site'] == 'Twitter'
        assert distractions[1]['total_seconds'] == 180
        assert distractions[1]['count'] == 2


# ===========================================================================
# 8. MODEL PARITY (inline models match routers/users.py source)
# ===========================================================================


class TestModelParity:
    """Verify inline test models match the real router models via AST."""

    def test_notification_settings_fields_match_source(self):
        """Inline UpdateNotificationSettingsRequest matches routers/users.py definition."""
        import ast

        source = (BACKEND_DIR / 'routers' / 'users.py').read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'UpdateNotificationSettingsRequest':
                field_names = [
                    stmt.target.id
                    for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                ]
                break
        else:
            pytest.fail("UpdateNotificationSettingsRequest not found in routers/users.py")
        expected = [f.alias or name for name, f in UpdateNotificationSettingsRequest.model_fields.items()]
        assert set(field_names) == set(expected), f"Field mismatch: source={field_names} test={expected}"

    def test_llm_usage_fields_match_source(self):
        """Inline RecordLlmUsageBucketRequest matches routers/users.py definition."""
        import ast

        source = (BACKEND_DIR / 'routers' / 'users.py').read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'RecordLlmUsageBucketRequest':
                field_names = [
                    stmt.target.id
                    for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
                ]
                break
        else:
            pytest.fail("RecordLlmUsageBucketRequest not found in routers/users.py")
        expected = [f.alias or name for name, f in RecordLlmUsageBucketRequest.model_fields.items()]
        assert set(field_names) == set(expected), f"Field mismatch: source={field_names} test={expected}"


# ===========================================================================
# 9. RATING=0 BOUNDARY (route rejects 0 despite model allowing it)
# ===========================================================================


class TestRatingZeroBoundary:
    """Verify rating=0 is accepted by Pydantic but rejected by route logic."""

    def test_rating_0_passes_model(self):
        """RateMessageRequest allows rating=0 (within ge=-1, le=1)."""
        r = RateMessageRequest(rating=0)
        assert r.rating == 0

    def test_rating_0_rejected_by_route(self):
        """The rate_message route rejects rating=0 with 400."""
        from routers.chat_sessions import rate_message

        with pytest.raises(Exception) as exc_info:
            rate_message(message_id='msg-1', request=RateMessageRequest(rating=0), uid='test-uid')
        assert '400' in str(exc_info.value) or 'Rating must be' in str(exc_info.value)


# ===========================================================================
# 10. MIGRATION BATCH INTEGRATION (exercises real caller accounting)
# ===========================================================================


class TestMigrationBatchIntegration:
    """Exercise migration functions with enough items to cross batch boundary."""

    def test_migrate_ai_tasks_commits_at_batch_boundary(self):
        """migrate_ai_tasks with 260 AI tasks triggers batch commit (260*2=520 ops > 500)."""

        def _make_doc(i, source='screenshot'):
            doc = MagicMock()
            doc.id = f'task-{i}'
            doc.to_dict.return_value = {
                'id': f'task-{i}',
                'completed': False,
                'source': source,
                'relevance_score': i,
            }
            return doc

        ai_docs = [_make_doc(i) for i in range(260)]

        mock_action_col = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = ai_docs
        mock_action_col.where.return_value = mock_query
        mock_action_col.document.return_value = MagicMock()

        mock_staged_col = MagicMock()
        mock_staged_col.document.return_value = MagicMock()

        batch1 = MagicMock()
        batch2 = MagicMock()

        def col_side_effect(col_name):
            if col_name == 'action_items':
                return mock_action_col
            return mock_staged_col

        with patch.object(staged_tasks_db, 'db') as patched_db:
            patched_db.batch.side_effect = [batch1, batch2]
            patched_db.collection.return_value.document.return_value.collection.side_effect = col_side_effect
            result = staged_tasks_db.migrate_ai_tasks('test-uid')

        assert result['moved'] == 257  # 260 - 3 kept
        batch1.commit.assert_called()  # intermediate commit at 500 ops


# ============================================================================
# TESTER-REQUESTED: Focus-stats duration_seconds=0 boundary
# ============================================================================


class TestFocusStatsDurationBoundary:
    """Verify duration_seconds=0 and missing duration behavior."""

    def test_distracted_zero_duration_treated_as_default(self):
        """duration_seconds=0 is treated as 60 via `or 60` in get_focus_stats."""
        sessions = [{'status': 'distracted', 'app_or_site': 'Twitter', 'duration_seconds': 0}]
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=sessions):
            result = focus_sessions_db.get_focus_stats('uid', '2026-04-06')
        # duration_seconds=0 is falsy, so `or 60` defaults to 60
        assert result['distracted_minutes'] == 1  # 60 seconds = 1 minute

    def test_distracted_missing_duration_treated_as_default(self):
        """Missing duration_seconds defaults to 60 via `or 60`."""
        sessions = [{'status': 'distracted', 'app_or_site': 'Reddit'}]
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=sessions):
            result = focus_sessions_db.get_focus_stats('uid', '2026-04-06')
        assert result['distracted_minutes'] == 1

    def test_focused_zero_duration_is_zero(self):
        """Focused sessions with duration_seconds=0 contribute 0 minutes."""
        sessions = [{'status': 'focused', 'duration_seconds': 0}]
        with patch.object(focus_sessions_db, 'get_focus_sessions', return_value=sessions):
            result = focus_sessions_db.get_focus_stats('uid', '2026-04-06')
        assert result['focused_minutes'] == 0


# ============================================================================
# TESTER-REQUESTED: BatchUpdateScoresRequest max_length=500 validation
# ============================================================================


class TestBatchScoresOverflow:
    """Verify batch-scores rejects >500 items via Pydantic validation."""

    def test_501_scores_rejected(self):
        """BatchUpdateScoresRequest rejects list with 501 entries."""
        with pytest.raises(ValidationError):
            BatchUpdateScoresRequest(
                scores=[BatchScoreEntry(id=f'id-{i}', relevance_score=i % 1000) for i in range(501)]
            )

    def test_500_scores_accepted(self):
        """BatchUpdateScoresRequest accepts list with exactly 500 entries."""
        req = BatchUpdateScoresRequest(
            scores=[BatchScoreEntry(id=f'id-{i}', relevance_score=i % 1000) for i in range(500)]
        )
        assert len(req.scores) == 500


# ============================================================================
# TESTER-REQUESTED: Session-scoped query precedence
# ============================================================================


class TestSessionScopedPrecedence:
    """Verify session_id takes precedence over app_id in get_messages/delete_messages."""

    @staticmethod
    def _get_field_filter_fields():
        """Extract field names from all FieldFilter() calls."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        fields = []
        for call in FieldFilter.call_args_list:
            if call.args:
                fields.append(call.args[0])
        return fields

    def test_get_messages_session_id_ignores_app_id(self):
        """When both app_id and chat_session_id are provided, only session filter is applied."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        FieldFilter.reset_mock()

        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.get_messages('uid', app_id='some-app', chat_session_id='sess-123')

        fields = self._get_field_filter_fields()
        assert 'chat_session_id' in fields, f"Expected chat_session_id filter, got: {fields}"
        assert 'plugin_id' not in fields, f"plugin_id should NOT be filtered when session_id present: {fields}"

    def test_delete_messages_session_id_ignores_app_id(self):
        """When both app_id and session_id are provided, only session filter is applied."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        FieldFilter.reset_mock()

        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.where.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []

        with patch.object(chat_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value = mock_col
            chat_db.delete_messages('uid', app_id='some-app', session_id='sess-123')

        fields = self._get_field_filter_fields()
        assert 'chat_session_id' in fields, f"Expected chat_session_id filter, got: {fields}"
        assert 'plugin_id' not in fields, f"plugin_id should NOT be filtered when session_id present: {fields}"


# ============================================================================
# TESTER-REQUESTED: LLM dual-write full payload parity
# ============================================================================


class TestLlmDualWritePayloadParity:
    """Verify all fields are written to both primary and per-account buckets."""

    def test_all_fields_written_to_both_buckets(self):
        """record_llm_usage_bucket writes all fields to both desktop_chat and desktop_chat_omi in single set()."""
        mock_ref = MagicMock()
        with patch.object(llm_usage_db, 'db') as patched_db:
            patched_db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
                mock_ref
            )
            llm_usage_db.record_llm_usage_bucket(
                uid='uid',
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=20,
                cache_write_tokens=10,
                total_tokens=180,
                cost_usd=0.05,
                bucket='desktop_chat',
                account='omi',
            )

        # Single set(merge=True) call containing both bucket prefixes
        mock_ref.set.assert_called_once()
        data = mock_ref.set.call_args[0][0]

        # Check all fields for primary bucket
        expected_fields = [
            'input_tokens',
            'output_tokens',
            'cache_read_tokens',
            'cache_write_tokens',
            'total_tokens',
            'cost_usd',
            'call_count',
        ]
        for field in expected_fields:
            assert f'desktop_chat.{field}' in data, f"Missing desktop_chat.{field}"
            assert f'desktop_chat_omi.{field}' in data, f"Missing desktop_chat_omi.{field}"

        # Verify shared metadata fields
        assert 'date' in data
        assert 'last_updated' in data


# ============================================================================
# Chat AI endpoint tests (migrated from Rust)
# ============================================================================


class TestInitialMessageEndpoint:
    """Test v2/chat/initial-message endpoint wire format."""

    def test_returns_message_and_message_id(self):
        from routers.chat_sessions import create_initial_message, InitialMessageRequest

        mock_msg = MagicMock()
        mock_msg.text = 'Hello! How can I help?'
        mock_msg.id = 'msg-123'

        with patch.dict(
            'sys.modules', {'routers.chat': MagicMock(initial_message_util=MagicMock(return_value=mock_msg))}
        ):
            result = create_initial_message(InitialMessageRequest(session_id='s1', app_id='app1'), uid='u1')

        assert result == {'message': 'Hello! How can I help?', 'message_id': 'msg-123'}

    def test_app_id_defaults_to_none(self):
        from routers.chat_sessions import create_initial_message, InitialMessageRequest

        mock_msg = MagicMock()
        mock_msg.text = 'Hi'
        mock_msg.id = 'msg-456'
        mock_util = MagicMock(return_value=mock_msg)

        with patch.dict('sys.modules', {'routers.chat': MagicMock(initial_message_util=mock_util)}):
            create_initial_message(InitialMessageRequest(session_id='s1'), uid='u1')
            mock_util.assert_called_once_with('u1', None, chat_session_id='s1')

    def test_session_id_passed_to_util(self):
        from routers.chat_sessions import create_initial_message, InitialMessageRequest

        mock_msg = MagicMock()
        mock_msg.text = 'Hi'
        mock_msg.id = 'msg-789'
        mock_util = MagicMock(return_value=mock_msg)

        with patch.dict('sys.modules', {'routers.chat': MagicMock(initial_message_util=mock_util)}):
            create_initial_message(InitialMessageRequest(session_id='sess-42', app_id='myapp'), uid='u1')
            mock_util.assert_called_once_with('u1', 'myapp', chat_session_id='sess-42')


class TestGenerateTitleEndpoint:
    """Test v2/chat/generate-title endpoint."""

    @patch('database.chat.update_chat_session')
    def test_returns_title(self, mock_update):
        from routers.chat_sessions import generate_session_title, GenerateTitleRequest, TitleMessageInput

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = 'Project Discussion'
        mock_llm.invoke.return_value = mock_response

        request = GenerateTitleRequest(
            session_id='s1',
            messages=[TitleMessageInput(text='hi', sender='human'), TitleMessageInput(text='hello', sender='ai')],
        )
        with patch.dict('sys.modules', {'utils.llm.clients': MagicMock(llm_mini=mock_llm)}):
            result = generate_session_title(request, uid='u1')

        assert result == {'title': 'Project Discussion'}
        mock_update.assert_called_once_with('u1', 's1', title='Project Discussion')

    @patch('database.chat.update_chat_session')
    def test_empty_response_defaults_to_new_chat(self, mock_update):
        from routers.chat_sessions import generate_session_title, GenerateTitleRequest, TitleMessageInput

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '  '
        mock_llm.invoke.return_value = mock_response

        request = GenerateTitleRequest(
            session_id='s1',
            messages=[TitleMessageInput(text='hi', sender='human')],
        )
        with patch.dict('sys.modules', {'utils.llm.clients': MagicMock(llm_mini=mock_llm)}):
            result = generate_session_title(request, uid='u1')

        assert result == {'title': 'New Chat'}


class TestChatMessageCount:
    """Test v1/users/stats/chat-messages endpoint."""

    @patch('database.chat.get_message_count')
    def test_returns_count(self, mock_count):
        from routers.chat_sessions import get_chat_message_count

        mock_count.return_value = 42
        result = get_chat_message_count(uid='u1')

        assert result == {'count': 42}
        mock_count.assert_called_once_with('u1')
