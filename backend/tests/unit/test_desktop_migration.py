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


def _remove_module_tree(prefix):
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            sys.modules.pop(name, None)


def _ensure_package_path(name, path):
    mod = sys.modules.get(name)
    if not isinstance(mod, types.ModuleType):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    mod.__path__ = [str(path)]
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies before any production imports
# ---------------------------------------------------------------------------
for module_prefix in [
    "database",
    "models",
    "utils",
    "routers.chat_sessions",
    "routers.focus_sessions",
    "routers.advice",
    "routers.staged_tasks",
]:
    _remove_module_tree(module_prefix)

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
    "utils.chat",
    "utils.llm",
    "utils.llm.clients",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

sys.modules["utils.chat"].initial_message_util = MagicMock()
sys.modules["utils.llm.clients"].get_llm = MagicMock()
usage_tracker_stub = _stub_module("utils.llm.usage_tracker")


class _Features:
    CHAT = "chat"


usage_tracker_stub.Features = _Features
usage_tracker_stub.track_usage = MagicMock()

# Stub google.cloud.firestore sentinels
firestore_stub = sys.modules["google.cloud.firestore"]
firestore_stub.Increment = lambda x: f"__increment_{x}__"
firestore_stub.ArrayRemove = lambda values: ("__array_remove__", tuple(values))
firestore_stub.Query = MagicMock()
firestore_stub.Query.ASCENDING = "ASCENDING"
firestore_stub.Query.DESCENDING = "DESCENDING"
firestore_stub.Client = MagicMock

# Stub FieldFilter
field_filter_stub = sys.modules["google.cloud.firestore_v1.base_query"]
field_filter_stub.FieldFilter = MagicMock()
sys.modules["google.cloud.firestore_v1"].FieldFilter = field_filter_stub.FieldFilter
sys.modules["google.cloud.firestore_v1"].transactional = lambda f: f

redis_stub = sys.modules["database.redis_db"]
redis_stub.r = MagicMock()
redis_stub.delete_cached_user_geolocation = MagicMock()
setattr(redis_stub, 'try_acquire_client_device_write_lock', MagicMock(return_value=True))
redis_stub.try_acquire_user_platform_write_lock = MagicMock(return_value=True)

# Add backend dir to sys.path
sys.path.insert(0, str(BACKEND_DIR))

# Stub database package and _client
_ensure_package_path("database", BACKEND_DIR / "database")

client_stub = _stub_module("database._client")
mock_db = MagicMock()
client_stub.db = mock_db
client_stub.delete_collection_recursive = MagicMock()
client_stub.run_transactional = MagicMock()  # imported by the Firestore adapter (get_document_store path)
client_stub.document_id_from_seed = MagicMock(return_value="seed-id")
client_stub.get_firestore_client = MagicMock(return_value=mock_db)

# Stub database.helpers (used by chat.py)
helpers_stub = _stub_module("database.helpers")
helpers_stub.set_data_protection_level = lambda **kw: (lambda f: f)
helpers_stub.prepare_for_write = lambda **kw: (lambda f: f)
helpers_stub.prepare_for_read = lambda **kw: (lambda f: f)

# Stub models and utils needed by database.users and database.chat
_ensure_package_path("models", BACKEND_DIR / "models")
models_users_stub = _stub_module("models.users")
models_users_stub.Subscription = MagicMock()
models_users_stub.PlanLimits = MagicMock()
models_users_stub.PlanType = MagicMock()
models_users_stub.SubscriptionStatus = MagicMock()
models_users_stub.LocationContextConsent = MagicMock()
models_users_stub.LocationContextConsentStatus = MagicMock()
models_users_stub.LOCATION_CONTEXT_DISCLOSED_PROVIDERS = ()
models_users_stub.LOCATION_CONTEXT_PURPOSE = "city_context"

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
endpoints_stub.with_rate_limit_context = lambda dep, policy: dep
endpoints_stub.timeit = lambda f: f
_stub_module("utils.observability")
fallback_stub = _stub_module("utils.observability.fallback")
fallback_stub.record_fallback = MagicMock()
task_intelligence_stub = _stub_package("utils.task_intelligence")
candidate_service_stub = _stub_module("utils.task_intelligence.candidate_service")
candidate_service_stub.create_candidate = MagicMock()
task_intelligence_stub.candidate_service = candidate_service_stub
staged_migration_stub = _stub_module("utils.task_intelligence.staged_migration")
staged_migration_stub.proposal_from_legacy_staged = MagicMock()
staged_migration_stub.migrate_staged_tasks = MagicMock()
rollout_stub = _stub_module("utils.task_intelligence.rollout")
setattr(rollout_stub, "effective_task_workflow_control", lambda control, rollout: control)
setattr(rollout_stub, "resolve_task_intelligence_for_user", MagicMock())
request_validation_stub = _stub_module("utils.request_validation")
request_validation_stub.validate_calendar_date = lambda value, field_name='date': value
redis_stub = _stub_module("database.redis_db")
redis_stub.r = MagicMock()
redis_stub.delete_cached_user_geolocation = MagicMock()
setattr(redis_stub, 'try_acquire_client_device_write_lock', MagicMock(return_value=True))
redis_stub.try_acquire_user_platform_write_lock = MagicMock(return_value=True)

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
import routers.staged_tasks as staged_router  # noqa: E402

_ensure_package_path("models", BACKEND_DIR / "models")
_ensure_package_path("utils", BACKEND_DIR / "utils")
_ensure_package_path("utils.other", BACKEND_DIR / "utils" / "other")

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
# 2. STORAGE BEHAVIOR (WP2 port) — inject an in-memory FakeDocumentStore via the
#    _store() seam and assert on observable behavior/state (ADR-0002), rather than
#    on raw-Firestore call patterns.
# ===========================================================================

from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(users_db, '_store', lambda: fake)
    monkeypatch.setattr(chat_db, '_store', lambda: fake)
    monkeypatch.setattr(llm_usage_db, '_store', lambda: fake)
    return fake


def _llm_usage_today_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


class TestNotificationSettingsWireCompat:
    """Verify notification settings return Swift-compatible field names."""

    def test_returns_enabled_and_frequency_keys(self, store):
        store.set('users/test-uid', {'notifications_enabled': False, 'notification_frequency': 2})
        result = users_db.get_notification_settings('test-uid')
        assert result == {'enabled': False, 'frequency': 2}

    def test_defaults_frequency_to_off_when_unset(self, store):
        store.set('users/test-uid', {})
        result = users_db.get_notification_settings('test-uid')
        assert result == {'enabled': True, 'frequency': 0}

    def test_defaults_when_doc_missing(self, store):
        result = users_db.get_notification_settings('test-uid')
        assert result == {'enabled': True, 'frequency': 0}


class TestAssistantSettingsWireCompat:
    """Verify assistant settings deep-merge and update_channel handling."""

    def test_get_includes_update_channel(self, store):
        store.set('users/test-uid', {'assistant_settings': {'focus': {'enabled': True}}, 'update_channel': 'beta'})
        result = users_db.get_assistant_settings('test-uid')
        assert result['update_channel'] == 'beta'
        assert result['focus'] == {'enabled': True}

    def test_deep_merge_preserves_sibling_sections(self, store):
        store.set(
            'users/test-uid',
            {'assistant_settings': {'focus': {'enabled': True, 'cooldown_interval': 30}, 'task': {'enabled': False}}},
        )
        result = users_db.update_assistant_settings('test-uid', {'focus': {'enabled': False}})
        assert result['focus']['enabled'] is False
        assert result['focus']['cooldown_interval'] == 30
        assert result['task'] == {'enabled': False}
        # Persisted deep-merge (sibling sections intact).
        stored = store.get('users/test-uid').to_dict()['assistant_settings']
        assert stored == {'focus': {'enabled': False, 'cooldown_interval': 30}, 'task': {'enabled': False}}

    def test_update_channel_written_to_top_level(self, store):
        store.set('users/test-uid', {'assistant_settings': {}})
        users_db.update_assistant_settings('test-uid', {'update_channel': 'beta'})
        stored = store.get('users/test-uid').to_dict()
        assert stored['update_channel'] == 'beta'
        assert 'update_channel' not in stored.get('assistant_settings', {})

    def test_raw_assistant_settings_excludes_update_channel(self, store):
        store.set('users/test-uid', {'assistant_settings': {'focus': {'enabled': True}}, 'update_channel': 'beta'})
        result = users_db._get_raw_assistant_settings('test-uid')
        assert 'update_channel' not in result
        assert result == {'focus': {'enabled': True}}


def _msg(store, uid, doc_id, **fields):
    fields.setdefault('id', doc_id)
    fields.setdefault('created_at', datetime.now(timezone.utc))
    store.set(f'users/{uid}/messages/{doc_id}', fields)


class TestDesktopMessagesWireCompat:
    """Verify message field names match cross-platform expectations."""

    def test_save_message_writes_expected_fields(self, store, monkeypatch):
        monkeypatch.setattr(chat_db, 'acquire_chat_session', lambda uid, app_id=None: 'session-123')
        store.set('users/test-uid/chat_sessions/session-123', {'id': 'session-123'})
        result = chat_db.save_message('test-uid', text='hello', sender='human', app_id='my-app')

        stored = store.get(f"users/test-uid/messages/{result['id']}").to_dict()
        assert stored['plugin_id'] == 'my-app'
        assert stored['app_id'] == 'my-app'
        assert stored['chat_session_id'] == 'session-123'
        assert stored['type'] == 'text'
        assert stored['from_external_integration'] is False
        assert stored['text'] == 'hello'
        assert stored['sender'] == 'human'


class TestSessionScopedQueries:
    """Verify session-scoped reads/deletes are scoped by chat_session_id, app-scoped by plugin_id."""

    def test_get_messages_session_scoped_filters_by_session_not_plugin(self, store):
        _msg(store, 'uid', 'm1', chat_session_id='sess-1', plugin_id='app-x', text='a')
        _msg(store, 'uid', 'm2', chat_session_id='other', plugin_id='app-x', text='b')
        result = chat_db.get_messages('uid', chat_session_id='sess-1', app_id='some-app')
        assert [m['id'] for m in result] == ['m1']

    def test_get_messages_app_scoped_filters_by_plugin_id(self, store):
        _msg(store, 'uid', 'm1', plugin_id='my-app', text='a')
        _msg(store, 'uid', 'm2', plugin_id='other', text='b')
        result = chat_db.get_messages('uid', app_id='my-app')
        assert [m['id'] for m in result] == ['m1']

    def test_delete_messages_session_scoped_filters_by_session_not_plugin(self, store):
        _msg(store, 'uid', 'm1', chat_session_id='sess-1', plugin_id='app-x')
        _msg(store, 'uid', 'm2', chat_session_id='other', plugin_id='app-x')
        chat_db.delete_messages('uid', session_id='sess-1')
        assert store.exists('users/uid/messages/m1') is False
        assert store.exists('users/uid/messages/m2') is True

    def test_delete_messages_app_scoped_filters_by_plugin_id(self, store):
        _msg(store, 'uid', 'm1', plugin_id='my-app')
        _msg(store, 'uid', 'm2', plugin_id='other')
        chat_db.delete_messages('uid', app_id='my-app')
        assert store.exists('users/uid/messages/m1') is False
        assert store.exists('users/uid/messages/m2') is True


class TestMessageReconcileKeyset:
    """Keyset journal pagination (WP2 tie-safe start_after, ADR-0018).

    With the port, ties on created_at order deterministically by document id, so pages neither skip
    nor duplicate rows. (Rigorous tie-safety is proven in the storage-port contract test.)
    """

    @staticmethod
    def _seed(store, doc_id, created_at, *, reported=False, plugin_id=None):
        store.set(
            f'users/uid/messages/{doc_id}',
            {
                'id': doc_id,
                'text': doc_id,
                'sender': 'human',
                'type': 'text',
                'created_at': created_at,
                'plugin_id': plugin_id,
                'app_id': plugin_id,
                'reported': reported,
            },
        )

    def test_insert_between_pages_does_not_skip_or_duplicate(self, store):
        now = datetime.now(timezone.utc)
        for doc_id in ('remote-4', 'remote-3', 'remote-2', 'remote-1'):
            self._seed(store, doc_id, now)

        first, cursor, has_more = chat_db.get_messages_reconcile_page('uid', limit=2)
        self._seed(store, 'remote-new', now)  # a newer row arrives between pages
        second, next_cursor, _ = chat_db.get_messages_reconcile_page('uid', limit=2, cursor_message_id=cursor)

        # created_at ties -> deterministic desc-by-id order: remote-4, remote-3, remote-2, remote-1.
        assert [row['id'] for row in first] == ['remote-4', 'remote-3']
        assert cursor == 'remote-3'
        assert has_more is True
        assert [row['id'] for row in second] == ['remote-2', 'remote-1']  # remote-new not duplicated/skipped
        assert next_cursor == 'remote-1'

    def test_reported_rows_advance_cursor_without_consuming_page_capacity(self, store):
        now = datetime.now(timezone.utc)
        self._seed(store, 'visible-2', now)
        self._seed(store, 'visible-1', now)
        self._seed(store, 'reported', now, reported=True)

        rows, cursor, has_more = chat_db.get_messages_reconcile_page('uid', limit=2)
        tail_rows, tail_cursor, tail_has_more = chat_db.get_messages_reconcile_page(
            'uid', limit=2, cursor_message_id=cursor
        )

        assert [row['id'] for row in rows] == ['visible-2', 'visible-1']
        assert cursor == 'visible-1'
        assert has_more is True
        # Tail scans only the reported row (skipped): no visible rows, and no further page.
        assert tail_rows == []
        assert tail_has_more is False

    def test_cursor_must_exist_in_authenticated_filter_scope(self, store):
        now = datetime.now(timezone.utc)
        self._seed(store, 'other-app', now, plugin_id='other')
        with pytest.raises(chat_db.MessageReconcileCursorError):
            chat_db.get_messages_reconcile_page('uid', limit=2, cursor_message_id='other-app', app_id='requested')


def _session(store, uid, sid, **fields):
    fields.setdefault('id', sid)
    fields.setdefault('updated_at', datetime.now(timezone.utc))
    fields.setdefault('title', sid)
    fields.setdefault('message_count', 0)
    fields.setdefault('starred', False)
    store.set(f'users/{uid}/chat_sessions/{sid}', fields)


class TestGetChatSessionsQuery:
    """Verify get_chat_sessions ordering (updated_at desc) and plugin_id scoping."""

    def test_orders_by_updated_at_descending(self, store):
        _session(store, 'uid', 's1', plugin_id=None, updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        _session(store, 'uid', 's2', plugin_id=None, updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
        _session(store, 'uid', 's3', plugin_id=None, updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        result = chat_db.get_chat_sessions('uid')
        assert [s['id'] for s in result] == ['s2', 's3', 's1']

    def test_filters_by_plugin_id_field(self, store):
        _session(store, 'uid', 's1', plugin_id='test-app')
        _session(store, 'uid', 's2', plugin_id='other')
        result = chat_db.get_chat_sessions('uid', app_id='test-app')
        assert [s['id'] for s in result] == ['s1']


class TestCreateChatSession:
    """Verify create_chat_session writes correct fields."""

    def test_default_title_and_counters(self, store):
        result = chat_db.create_chat_session('uid')
        assert result['title'] == 'New Chat'
        assert result['message_count'] == 0
        assert result['starred'] is False
        assert result['preview'] is None
        assert store.exists(f"users/uid/chat_sessions/{result['id']}")

    def test_plugin_id_matches_app_id(self, store):
        result = chat_db.create_chat_session('uid', app_id='my-plugin')
        assert result['plugin_id'] == 'my-plugin'
        assert result['app_id'] == 'my-plugin'

    def test_custom_title(self, store):
        result = chat_db.create_chat_session('uid', title='My Custom Chat')
        assert result['title'] == 'My Custom Chat'


class TestAcquireChatSession:
    """Verify acquire_chat_session reuse vs create logic."""

    def test_reuses_existing_session(self, store):
        _session(store, 'uid', 'existing-session-id', plugin_id='my-app')
        assert chat_db.acquire_chat_session('uid', app_id='my-app') == 'existing-session-id'

    def test_creates_new_session_when_none_exists(self, store, monkeypatch):
        created = {}

        def _fake_create(uid, app_id=None):
            created['args'] = (uid, app_id)
            return {'id': 'new-session-id'}

        monkeypatch.setattr(chat_db, 'create_chat_session', _fake_create)
        assert chat_db.acquire_chat_session('uid', app_id='my-app') == 'new-session-id'
        assert created['args'] == ('uid', 'my-app')


class TestUpdateChatSession:
    """Verify update_chat_session behavior."""

    def test_not_found_returns_none(self, store):
        assert chat_db.update_chat_session('uid', 'nonexistent-session', title='New Title') is None

    def test_title_only_update(self, store):
        _session(store, 'uid', 'sess-1', title='Old')
        chat_db.update_chat_session('uid', 'sess-1', title='Updated Title')
        stored = store.get('users/uid/chat_sessions/sess-1').to_dict()
        assert stored['title'] == 'Updated Title'
        assert 'updated_at' in stored

    def test_starred_only_update(self, store):
        store.set('users/uid/chat_sessions/sess-1', {'id': 'sess-1', 'starred': False})
        chat_db.update_chat_session('uid', 'sess-1', starred=True)
        stored = store.get('users/uid/chat_sessions/sess-1').to_dict()
        assert stored['starred'] is True
        assert 'updated_at' in stored
        assert 'title' not in stored


class TestDeleteChatSessionCascade:
    """Verify delete_chat_session with cascade_messages."""

    def test_cascade_deletes_messages_then_session(self, store):
        _session(store, 'uid', 'sess-1')
        _msg(store, 'uid', 'msg-1', chat_session_id='sess-1')
        _msg(store, 'uid', 'msg-2', chat_session_id='sess-1')
        chat_db.delete_chat_session('uid', 'sess-1', cascade_messages=True)
        assert store.exists('users/uid/chat_sessions/sess-1') is False
        assert store.list_ids('users/uid/messages') == []

    def test_cascade_nonexistent_session_short_circuits(self, store):
        assert chat_db.delete_chat_session('uid', 'nonexistent', cascade_messages=True) is False


class TestSaveMessageSessionBehavior:
    """Verify save_message idempotency, journal-revision arbitration, and session behavior."""

    def test_client_message_id_retry_returns_same_row_without_second_write(self, store):
        payload_hash = chat_db._message_idempotency_payload_hash(
            text='hello', sender='human', app_id=None, session_id=None,
            metadata='{"origin":"typed_chat"}', message_source='desktop_chat',
        )
        seeded = {
            'id': 'turn-1', 'text': 'hello', 'sender': 'human', 'metadata': '{"origin":"typed_chat"}',
            'message_source': 'desktop_chat', 'chat_session_id': 'session-1',
            'client_message_payload_hash': payload_hash,
        }
        store.set('users/uid/messages/turn-1', dict(seeded))

        result = chat_db.save_message(
            'uid', text='hello', sender='human', metadata='{"origin":"typed_chat"}', client_message_id='turn-1'
        )

        assert result['id'] == 'turn-1'
        assert result['created'] is False
        assert store.get('users/uid/messages/turn-1').to_dict() == seeded  # unchanged (no second write)

    def test_newer_journal_revision_atomically_enriches_delivered_message(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'Agent started.', 'sender': 'ai', 'app_id': None, 'plugin_id': None,
            'metadata': '{"content_blocks":[{"type":"agent_spawn"}]}', 'message_source': 'desktop_chat',
            'chat_session_id': 'session-1', 'session_id': 'session-1', 'journal_revision': 10,
            'client_message_payload_hash': 'sha256:old',
        })
        enriched_metadata = (
            '{"content_blocks":[{"type":"agent_spawn"},{"type":"agent_completion"}],'
            '"resources":[{"id":"artifact-1","type":"file"}]}'
        )
        result = chat_db.save_message(
            'uid', text='Agent started.', sender='ai', session_id='session-1',
            metadata=enriched_metadata, client_message_id='turn-1', journal_revision=11,
        )

        assert result['created'] is False
        assert result['updated'] is True
        assert result['journal_revision'] == 11
        stored = store.get('users/uid/messages/turn-1').to_dict()
        assert stored['metadata'] == enriched_metadata
        assert stored['journal_revision'] == 11

    def test_equal_journal_revision_with_different_payload_fails_closed(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'original', 'sender': 'ai', 'app_id': None, 'plugin_id': None,
            'metadata': None, 'message_source': 'desktop_chat', 'chat_session_id': 'session-1',
            'session_id': 'session-1', 'journal_revision': 7, 'client_message_payload_hash': 'sha256:original',
        })
        with pytest.raises(chat_db.ClientMessageIdPayloadConflict):
            chat_db.save_message(
                'uid', text='collision', sender='ai', session_id='session-1',
                client_message_id='turn-1', journal_revision=7,
            )
        assert store.get('users/uid/messages/turn-1').to_dict()['text'] == 'original'  # unchanged

    def test_older_journal_revision_is_ignored_without_rollback(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'newest', 'sender': 'ai', 'app_id': None, 'plugin_id': None,
            'metadata': '{"resources":[{"id":"new"}]}', 'message_source': 'desktop_chat',
            'chat_session_id': 'session-1', 'session_id': 'session-1', 'journal_revision': 12,
            'client_message_payload_hash': 'sha256:newest',
        })
        result = chat_db.save_message(
            'uid', text='stale', sender='ai', session_id='session-1',
            metadata='{"resources":[]}', client_message_id='turn-1', journal_revision=11,
        )
        assert result['updated'] is False
        assert result['journal_revision'] == 12
        assert store.get('users/uid/messages/turn-1').to_dict()['text'] == 'newest'  # unchanged

    def test_lost_ack_then_newer_journal_revision_converges_without_remote_receipt(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'original', 'sender': 'ai', 'app_id': None, 'plugin_id': None,
            'metadata': None, 'message_source': 'desktop_chat', 'chat_session_id': 'session-1',
            'session_id': 'session-1', 'journal_revision': 2, 'client_message_payload_hash': 'sha256:original',
        })
        result = chat_db.save_message(
            'uid', text='enriched after lost ack', sender='ai', session_id='session-1',
            metadata='{"content_blocks":[{"type":"agent_completion"}]}', client_message_id='turn-1', journal_revision=3,
        )
        assert result['updated'] is True
        assert result['journal_revision'] == 3

    def test_client_message_id_fingerprint_distinguishes_omitted_from_explicit_session(self, store):
        payload_hash = chat_db._message_idempotency_payload_hash(
            text='hello', sender='human', app_id=None, session_id=None, metadata=None, message_source='desktop_chat',
        )
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'hello', 'sender': 'human', 'metadata': None, 'message_source': 'desktop_chat',
            'chat_session_id': 'session-1', 'client_message_payload_hash': payload_hash,
        })
        with pytest.raises(chat_db.ClientMessageIdPayloadConflict):
            chat_db.save_message('uid', text='hello', sender='human', session_id='session-1', client_message_id='turn-1')

    def test_client_message_id_payload_collision_is_rejected(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'original', 'sender': 'human', 'metadata': None,
            'message_source': 'desktop_chat', 'chat_session_id': 'session-1',
        })
        with pytest.raises(chat_db.ClientMessageIdPayloadConflict):
            chat_db.save_message('uid', text='different', sender='human', session_id='session-1', client_message_id='turn-1')

    def test_legacy_client_message_id_rejects_different_app_when_retry_omits_app(self, store):
        store.set('users/uid/messages/turn-1', {
            'id': 'turn-1', 'text': 'hello', 'sender': 'human', 'app_id': 'different-app', 'plugin_id': 'different-app',
            'metadata': None, 'message_source': 'desktop_chat', 'chat_session_id': 'session-1',
        })
        with pytest.raises(chat_db.ClientMessageIdPayloadConflict):
            chat_db.save_message('uid', text='hello', sender='human', client_message_id='turn-1')

    def test_legacy_race_validates_the_requested_session_not_the_locally_acquired_session(self, store, monkeypatch):
        monkeypatch.setattr(chat_db, 'acquire_chat_session', lambda uid, app_id=None: 'locally-acquired-session')
        winner = {
            'id': 'turn-1', 'text': 'hello', 'sender': 'human', 'app_id': None, 'plugin_id': None, 'metadata': None,
            'message_source': 'desktop_chat', 'chat_session_id': 'winner-session', 'session_id': 'winner-session',
        }

        # Simulate a concurrent writer winning the create: absent at the exists-check, then create
        # loses the race (AlreadyExists) and a re-read sees the winner's row (a different session).
        def racing_create(path, data):
            store.set(path, winner)
            raise chat_db.AlreadyExists('concurrent writer won')

        monkeypatch.setattr(store, 'create', racing_create)

        result = chat_db.save_message('uid', text='hello', sender='human', client_message_id='turn-1')

        assert result['id'] == 'turn-1'
        assert result['session_id'] == 'winner-session'
        assert result['created'] is False

    def test_explicit_session_id_skips_acquire(self, store, monkeypatch):
        calls = []
        monkeypatch.setattr(chat_db, 'acquire_chat_session', lambda *a, **k: calls.append(1) or 'x')
        store.set('users/uid/chat_sessions/my-session', {'id': 'my-session'})
        chat_db.save_message('uid', text='hello', sender='human', session_id='my-session')
        assert calls == []

    def test_preview_truncated_to_100_chars(self, store, monkeypatch):
        monkeypatch.setattr(chat_db, 'acquire_chat_session', lambda uid, app_id=None: 'sess-1')
        store.set('users/uid/chat_sessions/sess-1', {'id': 'sess-1'})
        chat_db.save_message('uid', text='x' * 200, sender='human')
        stored_session = store.get('users/uid/chat_sessions/sess-1').to_dict()
        assert len(stored_session['preview']) == 100


class TestDeleteMessagesCount:
    """Verify delete_messages returns correct count."""

    def test_returns_zero_when_no_messages(self, store):
        assert chat_db.delete_messages('uid', app_id='my-app') == 0

    def test_returns_count_of_deleted_messages(self, store):
        """delete_messages returns the total count of deleted messages."""
        for i in range(3):
            _msg(store, 'uid', f'msg-{i}', plugin_id='my-app')

        assert chat_db.delete_messages('uid', app_id='my-app') == 3
        assert chat_db.get_messages('uid', app_id='my-app') == []

    def test_delete_applies_inverse_session_metadata_in_same_transaction(self, store):
        """Source deletion and inverse count/ID/preview updates commit together (ADR-0002)."""
        _msg(store, 'uid', 'msg-1', id='logical-1', plugin_id=None, chat_session_id='sess-1', text='older')
        _msg(store, 'uid', 'msg-2', id='logical-2', plugin_id=None, chat_session_id='sess-1', text='latest')
        _session(
            store, 'uid', 'sess-1',
            message_count=5, message_ids=['logical-1', 'logical-2', 'older-id'], preview='latest',
        )

        result = chat_db.delete_messages('uid', app_id=None)

        assert result == 2
        session = store.get('users/uid/chat_sessions/sess-1').to_dict()
        assert session['message_count'] == 3
        assert session['message_ids'] == ['older-id']
        assert session['preview'] is None
        assert not store.exists('users/uid/messages/msg-1')
        assert not store.exists('users/uid/messages/msg-2')

    def test_decrement_is_bounded_by_stored_count(self, store):
        """message_count never goes negative even if the stored counter understates reality."""
        _msg(store, 'uid', 'msg-1', id='logical-1', plugin_id=None, chat_session_id='sess-1', text='a')
        _msg(store, 'uid', 'msg-2', id='logical-2', plugin_id=None, chat_session_id='sess-1', text='b')
        _session(store, 'uid', 'sess-1', message_count=1)  # understated vs the 2 messages present

        assert chat_db.delete_messages('uid', app_id=None) == 2
        assert store.get('users/uid/chat_sessions/sess-1').to_dict()['message_count'] == 0

    def test_paginates_across_batches_and_terminates(self, store):
        """A backlog larger than one batch is drained fully, and the requery loop terminates."""
        total = chat_db.DELETE_MESSAGES_BATCH_LIMIT + 5
        for i in range(total):
            _msg(store, 'uid', f'msg-{i}', plugin_id='bulk')

        assert chat_db.delete_messages('uid', app_id='bulk') == total
        assert chat_db.get_messages('uid', app_id='bulk', limit=total) == []


class TestLlmUsageBucketParam:
    """Verify configurable bucket parameter in LLM usage functions."""

    def test_custom_bucket_dual_writes(self, store):
        """record_llm_usage_bucket with custom bucket writes to both bucket and bucket_account."""
        llm_usage_db.record_llm_usage_bucket(
            'uid',
            input_tokens=10,
            output_tokens=20,
            bucket='custom_feature',
            account='openai',
        )

        data = store.get(f'users/uid/llm_usage/{_llm_usage_today_id()}').to_dict()
        # Primary bucket
        assert data['custom_feature']['input_tokens'] == 10
        assert data['custom_feature']['output_tokens'] == 20
        assert data['custom_feature']['call_count'] == 1
        # Per-account bucket
        assert data['custom_feature_openai']['input_tokens'] == 10
        assert data['custom_feature_openai']['output_tokens'] == 20

    def test_get_total_llm_cost_custom_bucket(self, store):
        """get_total_llm_cost with custom bucket reads from the specified bucket only."""
        store.set(
            'users/uid/llm_usage/2025-01-15',
            {
                'custom_feature': {'cost_usd': 0.5},
                'custom_feature_openai': {'cost_usd': 0.5},  # Should NOT be double-counted
                'desktop_chat': {'cost_usd': 1.0},  # Different bucket, should be excluded
            },
        )

        result = llm_usage_db.get_total_llm_cost('uid', bucket='custom_feature')

        assert result == 0.5  # Only custom_feature, not custom_feature_openai or desktop_chat


# ===========================================================================
# 3. SCORE COMPUTATION TESTS (storage port)
# ===========================================================================

from types import SimpleNamespace  # noqa: E402


class _ScriptedScoreStore:
    """Minimal DocumentStore stand-in for get_daily_score / get_scores.

    Dispatches each ``query`` by the field it filters on — ``due_at`` (daily window),
    ``created_at`` (weekly window), or no filter (overall) — to a scripted list of task dicts,
    and records the filters so a test can assert which field/bounds the score query used.
    """

    def __init__(self, *, daily=None, weekly=None, overall=None):
        self.daily = list(daily or [])
        self.weekly = list(weekly or [])
        self.overall = list(overall or [])
        self.filters = []

    def query(self, collection, *, filters=None, **kwargs):
        filters = list(filters or [])
        self.filters.extend(filters)
        fields = {field for field, _op, _value in filters}
        if 'due_at' in fields:
            rows = self.daily
        elif 'created_at' in fields:
            rows = self.weekly
        else:
            rows = self.overall
        return [SimpleNamespace(id=row.get('id', 'doc-1'), to_dict=(lambda row=row: dict(row))) for row in rows]


class TestDailyScoreWireCompat:
    """Verify daily-score returns Swift DailyScore-compatible fields."""

    def test_daily_score_uses_completed_tasks_and_total_tasks(self, monkeypatch):
        """get_daily_score returns completed_tasks/total_tasks, not completed/total."""
        store = _ScriptedScoreStore(daily=[{'completed': True}, {'completed': False}])
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
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

    def test_weekly_uses_created_at_not_due_at(self, monkeypatch):
        """get_scores weekly query uses created_at field, not due_at."""
        store = _ScriptedScoreStore(
            daily=[],
            weekly=[{'completed': True, 'created_at': datetime.now(timezone.utc)}],
            overall=[{'completed': True}],
        )
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
        action_items_db.get_scores('test-uid', date='2025-01-15')

        captured_fields = [field for field, _op, _value in store.filters]
        # Verify created_at was used in filter calls (for the weekly window).
        assert 'created_at' in captured_fields, f"Expected created_at in filters, got: {captured_fields}"

    def test_weekly_window_spans_seven_days_ending_on_date(self, monkeypatch):
        """The weekly window is the 7 days ending on `date`, i.e. [date-6, date+1).

        Regression: it was [date-7, date+1) — 8 calendar days — which over-counted
        every task created on the date-7 day, inconsistent with the docstring and
        with the one-day daily window [date, date+1).
        """
        from datetime import timedelta

        store = _ScriptedScoreStore()
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
        action_items_db.get_scores('test-uid', date='2026-07-19')

        day = datetime(2026, 7, 19, tzinfo=timezone.utc)
        created_at_lower = [value for (field, op, value) in store.filters if field == 'created_at' and op == '>=']
        assert created_at_lower, f"no created_at >= filter captured: {store.filters}"
        # 7 days ending on 2026-07-19 -> lower bound is 2026-07-13 (day-6), not 2026-07-12 (day-7).
        assert created_at_lower[0] == day - timedelta(days=6), created_at_lower[0]

    def test_default_tab_daily_when_highest(self, monkeypatch):
        """default_tab is 'daily' when daily has tasks and highest score."""
        store = _ScriptedScoreStore(
            daily=[{'completed': True}, {'completed': True}],  # 2/2 = 100%
            weekly=[{'completed': True}, {'completed': False}],  # 1/2 = 50%
            overall=[{'completed': True}, {'completed': False}],  # 1/2 = 50%
        )
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
        result = action_items_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'daily'

    def test_default_tab_weekly_when_no_daily_tasks(self, monkeypatch):
        """default_tab is 'weekly' when daily has no tasks."""
        store = _ScriptedScoreStore(
            daily=[],  # 0 tasks
            weekly=[{'completed': True}],  # 1/1 = 100%
            overall=[{'completed': True}, {'completed': False}],  # 1/2 = 50%
        )
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
        result = action_items_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'weekly'

    def test_default_tab_overall_when_lowest_weekly(self, monkeypatch):
        """default_tab is 'overall' when overall score exceeds weekly."""
        store = _ScriptedScoreStore(
            daily=[],  # 0 tasks
            weekly=[{'completed': False}],  # 0/1 = 0%
            overall=[{'completed': True}],  # 1/1 = 100%
        )
        monkeypatch.setattr(action_items_db, '_store', lambda: store)
        result = action_items_db.get_scores('test-uid', date='2025-01-15')

        assert result['default_tab'] == 'overall'


# ===========================================================================
# 4. LLM USAGE TESTS (mock Firestore)
# ===========================================================================


class TestLlmUsage:
    """Verify LLM usage dual-write and cost summation."""

    def test_record_dual_writes_desktop_chat_and_account(self, store):
        """record_llm_usage_bucket dual-writes both 'desktop_chat' and 'desktop_chat_{account}'."""
        llm_usage_db.record_llm_usage_bucket(
            'test-uid',
            input_tokens=100,
            output_tokens=50,
            account='anthropic',
        )

        data = store.get(f'users/test-uid/llm_usage/{_llm_usage_today_id()}').to_dict()
        # Both desktop_chat and desktop_chat_anthropic buckets are written.
        assert 'desktop_chat' in data
        assert 'desktop_chat_anthropic' in data
        # input_tokens increment is present for both buckets
        assert data['desktop_chat']['input_tokens'] == 100
        assert data['desktop_chat_anthropic']['input_tokens'] == 100

    def test_record_default_account_omi(self, store):
        """Default account produces desktop_chat_omi keys."""
        llm_usage_db.record_llm_usage_bucket('test-uid', input_tokens=10, output_tokens=5)

        data = store.get(f'users/test-uid/llm_usage/{_llm_usage_today_id()}').to_dict()
        assert data['desktop_chat_omi']['input_tokens'] == 10

    def test_get_total_cost_only_sums_desktop_chat_bucket(self, store):
        """get_total_llm_cost only sums the desktop_chat bucket, not desktop_chat_{account}."""
        store.set(
            'users/test-uid/llm_usage/day-1',
            {
                'desktop_chat': {'cost_usd': 0.05, 'call_count': 10},
                'desktop_chat_anthropic': {'cost_usd': 0.05, 'call_count': 10},
            },
        )
        store.set(
            'users/test-uid/llm_usage/day-2',
            {
                'desktop_chat': {'cost_usd': 0.03, 'call_count': 5},
                'desktop_chat_omi': {'cost_usd': 0.03, 'call_count': 5},
            },
        )

        total = llm_usage_db.get_total_llm_cost('test-uid')

        # Should only sum desktop_chat: 0.05 + 0.03 = 0.08
        assert total == round(0.08, 6)

    def test_get_total_cost_ignores_non_dict_desktop_chat(self, store):
        """get_total_llm_cost handles docs where desktop_chat is not a dict."""
        store.set('users/test-uid/llm_usage/day-1', {'desktop_chat': 'corrupted', 'other_key': 123})
        store.set('users/test-uid/llm_usage/day-2', {'desktop_chat': {'cost_usd': 0.01}})

        total = llm_usage_db.get_total_llm_cost('test-uid')

        assert total == 0.01


# ===========================================================================
# 5. BATCH LIMIT TEST
# ===========================================================================


class TestBatchLimit:
    """Verify _commit_batch triggers commit at BATCH_LIMIT=500."""

    def test_commit_at_batch_limit(self, monkeypatch):
        """_commit_batch commits and returns a fresh port batch when count >= BATCH_LIMIT."""
        mock_batch = MagicMock()
        new_batch = object()  # sentinel: the fresh batch comes from the store port
        store = MagicMock()
        store.batch.return_value = new_batch
        monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

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

        result = migrate_ai_tasks(uid='test-uid')

        assert 'status' in result
        assert isinstance(result['status'], str)
        assert result['status'].startswith('legacy task migration retired')

    def test_migrate_conversation_items_returns_status_migrated_deleted(self):
        """migrate-conversation-items returns {status, migrated, deleted} matching Swift MigrateResponse."""
        from routers.staged_tasks import migrate_conversation_items

        with patch.object(
            staged_router,
            '_restore_all_legacy_conversation_items',
            return_value={'restored': 3, 'skipped_existing': 0, 'has_more': False, 'next_cursor': None},
        ):
            result = migrate_conversation_items(uid='test-uid', limit=50, cursor=None)

        assert result['status'] == 'ok'
        assert result['migrated'] == 0
        assert 'deleted' in result
        assert result['restored'] == 3


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

        source = (BACKEND_DIR / 'routers' / 'users.py').read_text(encoding='utf-8')
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

        source = (BACKEND_DIR / 'routers' / 'users.py').read_text(encoding='utf-8')
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


class TestLegacyConversationRecovery:
    """Exercise the recovery path for rows moved by the retired migration."""

    def test_restore_legacy_conversation_items_recreates_exact_marked_rows(self, monkeypatch):
        """Recovery restores only marker rows: recreate the action item, drop the marker."""
        store = FakeDocumentStore()
        store.set(
            'users/test-uid/staged_tasks/legacy-task',
            {
                'id': 'legacy-task',
                'description': 'Call supplier',
                'conversation_id': 'conversation-1',
                'completed': False,
                'source': 'conversation_migration',
            },
        )
        store.set(
            'users/test-uid/staged_tasks/ordinary-staged-task',
            {
                'id': 'ordinary-staged-task',
                'description': 'Keep this staged task',
                'completed': False,
                'source': 'screenshot',
            },
        )
        monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

        result = staged_tasks_db.restore_legacy_conversation_items('test-uid')

        assert result == {'restored': 1, 'skipped_existing': 0, 'has_more': False, 'next_cursor': None}
        # The marker row became an action item without `id`/`source`, its staged
        # row is gone, and the ordinary staged row is untouched.
        assert store.get('users/test-uid/action_items/legacy-task').to_dict() == {
            'description': 'Call supplier',
            'conversation_id': 'conversation-1',
            'completed': False,
        }
        assert not store.get('users/test-uid/staged_tasks/legacy-task').exists
        assert store.get('users/test-uid/staged_tasks/ordinary-staged-task').exists

    def test_restore_legacy_conversation_items_does_not_overwrite_an_existing_task(self, monkeypatch):
        """An identity collision preserves both copies instead of overwriting current data."""
        store = FakeDocumentStore()
        store.set('users/test-uid/action_items/legacy-task', {'description': 'Current authoritative task'})
        store.set(
            'users/test-uid/staged_tasks/legacy-task',
            {
                'id': 'legacy-task',
                'description': 'Call supplier',
                'completed': False,
                'source': 'conversation_migration',
            },
        )
        monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

        result = staged_tasks_db.restore_legacy_conversation_items('test-uid')

        assert result == {'restored': 0, 'skipped_existing': 1, 'has_more': False, 'next_cursor': None}
        # The current action item wins the identity; the staged row is preserved.
        assert store.get('users/test-uid/action_items/legacy-task').to_dict() == {
            'description': 'Current authoritative task'
        }
        assert store.get('users/test-uid/staged_tasks/legacy-task').exists

    def test_restore_legacy_conversation_items_pages_by_document_id(self, monkeypatch):
        """Recovery bounds each request and returns an exclusive continuation cursor."""
        store = FakeDocumentStore()
        for index in range(3):
            store.set(
                f'users/test-uid/staged_tasks/legacy-{index}',
                {
                    'id': f'legacy-{index}',
                    'description': f'Call supplier {index}',
                    'completed': False,
                    'source': 'conversation_migration',
                },
            )
        monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

        result = staged_tasks_db.restore_legacy_conversation_items('test-uid', limit=2)

        assert result == {'restored': 2, 'skipped_existing': 0, 'has_more': True, 'next_cursor': 'legacy-1'}
        # First two ids (document-id order) restored; the third remains staged.
        assert store.get('users/test-uid/action_items/legacy-0').exists
        assert store.get('users/test-uid/action_items/legacy-1').exists
        assert not store.get('users/test-uid/action_items/legacy-2').exists
        assert store.get('users/test-uid/staged_tasks/legacy-2').exists

    def test_restore_legacy_conversation_items_applies_exclusive_cursor(self, monkeypatch):
        """A continuation skips already-scanned rows instead of retrying them forever."""
        store = FakeDocumentStore()
        for index in range(2):
            store.set(
                f'users/test-uid/staged_tasks/legacy-{index}',
                {
                    'id': f'legacy-{index}',
                    'description': f'Call supplier {index}',
                    'completed': False,
                    'source': 'conversation_migration',
                },
            )
        monkeypatch.setattr(staged_tasks_db, '_store', lambda: store)

        # The cursor is exclusive: legacy-0 and legacy-1 are both <= 'legacy-1'.
        result = staged_tasks_db.restore_legacy_conversation_items('test-uid', cursor='legacy-1')

        assert result == {'restored': 0, 'skipped_existing': 0, 'has_more': False, 'next_cursor': None}
        assert store.get('users/test-uid/staged_tasks/legacy-0').exists
        assert store.get('users/test-uid/staged_tasks/legacy-1').exists

    def test_released_recovery_route_completes_every_page_before_success(self):
        """Released single-call clients must never receive an acknowledged partial recovery."""
        first_page = {'restored': 50, 'skipped_existing': 1, 'has_more': True, 'next_cursor': 'legacy-49'}
        second_page = {'restored': 2, 'skipped_existing': 0, 'has_more': False, 'next_cursor': None}

        with patch.object(
            staged_router.staged_tasks_db,
            'restore_legacy_conversation_items',
            side_effect=[first_page, second_page],
        ) as restore_page:
            result = staged_router._restore_all_legacy_conversation_items('test-uid')

        assert result == {'restored': 52, 'skipped_existing': 1, 'has_more': False, 'next_cursor': None}
        assert [call.args for call in restore_page.call_args_list] == [('test-uid',), ('test-uid',)]
        assert [call.kwargs['cursor'] for call in restore_page.call_args_list] == [None, 'legacy-49']
        assert all(
            call.kwargs['limit'] == staged_router.staged_tasks_db.LEGACY_CONVERSATION_RECOVERY_PAGE_SIZE
            for call in restore_page.call_args_list
        )


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
    """Verify session_id takes precedence over app_id in get_messages/delete_messages.

    Behavioral discriminator: the seeded message belongs to session ``sess-123`` but to a
    *different* app (``plugin_id='other-app'``). A caller passing both ``app_id='some-app'`` and
    the session id must still see/delete it — proof the session filter wins and the app filter
    (which would exclude it) is not applied.
    """

    def test_get_messages_session_id_ignores_app_id(self, store):
        _msg(store, 'uid', 'msg-1', plugin_id='other-app', chat_session_id='sess-123')

        messages = chat_db.get_messages('uid', app_id='some-app', chat_session_id='sess-123')

        assert [m['id'] for m in messages] == ['msg-1']

    def test_delete_messages_session_id_ignores_app_id(self, store):
        _msg(store, 'uid', 'msg-1', plugin_id='other-app', chat_session_id='sess-123')

        assert chat_db.delete_messages('uid', app_id='some-app', session_id='sess-123') == 1
        assert not store.exists('users/uid/messages/msg-1')


# ============================================================================
# TESTER-REQUESTED: LLM dual-write full payload parity
# ============================================================================


class TestLlmDualWritePayloadParity:
    """Verify all fields are written to both primary and per-account buckets."""

    def test_all_fields_written_to_both_buckets(self, store):
        """record_llm_usage_bucket writes all fields to both desktop_chat and desktop_chat_omi."""
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

        data = store.get(f'users/uid/llm_usage/{_llm_usage_today_id()}').to_dict()

        # Check all fields are present under both the primary and per-account buckets.
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
            assert field in data['desktop_chat'], f"Missing desktop_chat.{field}"
            assert field in data['desktop_chat_omi'], f"Missing desktop_chat_omi.{field}"

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

        with patch('routers.chat_sessions.initial_message_util', return_value=mock_msg):
            result = create_initial_message(InitialMessageRequest(session_id='s1', app_id='app1'), uid='u1')

        assert result == {'message': 'Hello! How can I help?', 'message_id': 'msg-123'}

    def test_app_id_defaults_to_none(self):
        from routers.chat_sessions import create_initial_message, InitialMessageRequest

        mock_msg = MagicMock()
        mock_msg.text = 'Hi'
        mock_msg.id = 'msg-456'
        mock_util = MagicMock(return_value=mock_msg)

        with patch('routers.chat_sessions.initial_message_util', mock_util):
            create_initial_message(InitialMessageRequest(session_id='s1'), uid='u1')
            mock_util.assert_called_once_with('u1', None, chat_session_id='s1')

    def test_session_id_passed_to_util(self):
        from routers.chat_sessions import create_initial_message, InitialMessageRequest

        mock_msg = MagicMock()
        mock_msg.text = 'Hi'
        mock_msg.id = 'msg-789'
        mock_util = MagicMock(return_value=mock_msg)

        with patch('routers.chat_sessions.initial_message_util', mock_util):
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
        mock_get_llm = MagicMock(return_value=mock_llm)
        with patch('routers.chat_sessions.get_llm', mock_get_llm):
            result = generate_session_title(request, uid='u1')

        assert result == {'title': 'Project Discussion'}
        mock_get_llm.assert_called_once_with('session_titles')
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
        mock_get_llm = MagicMock(return_value=mock_llm)
        with patch('routers.chat_sessions.get_llm', mock_get_llm):
            result = generate_session_title(request, uid='u1')

        assert result == {'title': 'New Chat'}
        mock_get_llm.assert_called_once_with('session_titles')


class TestChatMessageCount:
    """Test v1/users/stats/chat-messages endpoint."""

    @patch('database.chat.get_message_count')
    def test_returns_count(self, mock_count):
        from routers.chat_sessions import get_chat_message_count

        mock_count.return_value = 42
        result = get_chat_message_count(uid='u1')

        assert result == {'count': 42}
        mock_count.assert_called_once_with('u1')
