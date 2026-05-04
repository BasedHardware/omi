"""Tests for Developer API folder filters and folders endpoint.

Verifies that:
1. GET /v1/dev/user/folders returns folder list (with system folder initialization)
2. GET /v1/dev/user/conversations passes folder_id / starred to DB
"""

import os
import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# ---- Stub heavy deps before importing application code ----


class _AutoMockModule(ModuleType):
    """Module stub that returns MagicMock for any missing attribute."""

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_stubs = [
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
    'database.knowledge_graph',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
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
    'utils.conversations.location',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _AutoMockModule(mod_name)

# Override specific attributes for firebase_admin.auth
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})

# ---- Mock populate_folder_names / populate_speaker_names ----
# We patch these directly on routers.developer in each test class's setup_method,
# so that the real utils.conversations.render module is never polluted regardless
# of test execution order. This makes tests fully order-independent.
_mock_populate_folder_names = MagicMock()
_mock_populate_speaker_names = MagicMock()

# ---- Prepare controllable mocks for database modules ----

import database.conversations as conversations_db
import database.folders as folders_db

_mock_get_conversations = MagicMock(return_value=[])
conversations_db.get_conversations = _mock_get_conversations

_mock_get_folders = MagicMock(return_value=[])
_mock_initialize_system_folders = MagicMock(return_value=[])
folders_db.get_folders = _mock_get_folders
folders_db.initialize_system_folders = _mock_initialize_system_folders


# ---- Helper factories ----


def _make_folder(folder_id='f1', name='Work'):
    now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    return {
        'id': folder_id,
        'name': name,
        'description': 'Work folder',
        'color': '#3B82F6',
        'icon': '💼',
        'created_at': now,
        'updated_at': now,
        'order': 0,
        'is_default': False,
        'is_system': True,
        'category_mapping': 'work',
        'conversation_count': 5,
    }


def _make_conversation(conv_id='conv-1'):
    return {
        'id': conv_id,
        'is_locked': False,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [],
            'events': [],
            'category': 'personal',
        },
        'transcript_segments': [],
        'started_at': '2025-01-01T00:00:00',
        'finished_at': '2025-01-01T01:00:00',
        'created_at': 1735689600,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
        'language': 'en',
        'status': 'completed',
        'source': 'friend',
        'folder_id': None,
        'folder_name': None,
    }


# ============================================================================
# Unit tests — handler functions called directly
# ============================================================================


class TestDevGetFolders:
    """Unit tests for the get_folders handler (direct call)."""

    def setup_method(self):
        _mock_get_folders.reset_mock()
        _mock_initialize_system_folders.reset_mock()

    def test_dev_get_folders_returns_folder_list(self):
        """Handler returns folder list from DB when folders exist."""
        folder_list = [_make_folder('f1', 'Work'), _make_folder('f2', 'Personal')]
        _mock_get_folders.return_value = folder_list

        from routers.developer import get_user_folders

        result = get_user_folders(uid='uid1')

        assert result == folder_list
        _mock_get_folders.assert_called_once_with('uid1')
        _mock_initialize_system_folders.assert_not_called()

    def test_dev_get_folders_returns_empty_list_without_initialization(self):
        """Handler returns an empty list when the user has no folders, and never
        triggers `initialize_system_folders`.

        This is intentional: the Developer API runs under a `conversations:read`
        scope, so it must stay strictly read-only. Lazy initialization happens
        through the internal `/v1/folders` endpoint and the conversation
        post-processing pipeline instead.
        """
        _mock_get_folders.return_value = []

        from routers.developer import get_user_folders

        result = get_user_folders(uid='uid1')

        assert result == []
        _mock_get_folders.assert_called_once_with('uid1')
        _mock_initialize_system_folders.assert_not_called()

    def test_dev_get_folders_does_not_initialize_when_nonempty(self):
        """Handler never calls initialize_system_folders, regardless of folder count."""
        _mock_get_folders.return_value = [_make_folder('f1', 'Work')]

        from routers.developer import get_user_folders

        get_user_folders(uid='uid1')

        _mock_initialize_system_folders.assert_not_called()


class TestDevGetConversationsFolderFilters:
    """Unit tests for get_conversations handler — folder_id / starred params."""

    def setup_method(self):
        _mock_get_conversations.reset_mock()
        _mock_get_conversations.return_value = []
        _mock_populate_folder_names.reset_mock()
        _mock_populate_speaker_names.reset_mock()
        # Ensure routers.developer uses the mocks regardless of import order
        import routers.developer as _dev_router

        _dev_router.populate_folder_names = _mock_populate_folder_names
        _dev_router.populate_speaker_names = _mock_populate_speaker_names

    def test_dev_get_conversations_passes_folder_id_to_db(self):
        """folder_id is forwarded to conversations_db.get_conversations."""
        from routers.developer import get_conversations

        get_conversations(
            uid='uid1',
            folder_id='f1',
            starred=None,
        )

        call_kwargs = _mock_get_conversations.call_args[1]
        assert call_kwargs.get('folder_id') == 'f1'
        assert call_kwargs.get('starred') is None

    def test_dev_get_conversations_passes_starred_true(self):
        """starred=True is forwarded to DB."""
        from routers.developer import get_conversations

        get_conversations(
            uid='uid1',
            folder_id=None,
            starred=True,
        )

        call_kwargs = _mock_get_conversations.call_args[1]
        assert call_kwargs.get('starred') is True
        assert call_kwargs.get('folder_id') is None

    def test_dev_get_conversations_passes_starred_false(self):
        """starred=False (not None) is forwarded to DB — tests database.conversations if-not-None path."""
        from routers.developer import get_conversations

        get_conversations(
            uid='uid1',
            folder_id=None,
            starred=False,
        )

        call_kwargs = _mock_get_conversations.call_args[1]
        assert call_kwargs.get('starred') is False
        assert call_kwargs.get('folder_id') is None

    def test_dev_get_conversations_combines_folder_id_and_starred(self):
        """Both folder_id and starred are forwarded when both are specified."""
        from routers.developer import get_conversations

        get_conversations(
            uid='uid1',
            folder_id='f1',
            starred=True,
        )

        call_kwargs = _mock_get_conversations.call_args[1]
        assert call_kwargs.get('folder_id') == 'f1'
        assert call_kwargs.get('starred') is True

    def test_dev_get_conversations_default_passes_none_for_folder_filters(self):
        """When folder_id/starred are not specified via HTTP, DB receives None for both.

        This test uses the HTTP layer (TestClient) so FastAPI resolves Query(None) -> None.
        """
        _, client = _build_test_app()

        client.get('/v1/dev/user/conversations')

        call_kwargs = _mock_get_conversations.call_args[1]
        assert call_kwargs.get('folder_id') is None
        assert call_kwargs.get('starred') is None

    def test_dev_get_conversations_preserves_existing_params(self):
        """Regression: all 8 params (6 existing + 2 new) are forwarded to DB."""
        from routers.developer import get_conversations
        from datetime import datetime, timezone

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 31, tzinfo=timezone.utc)

        get_conversations(
            uid='uid1',
            start_date=start,
            end_date=end,
            categories='work,personal',
            include_transcript=True,
            limit=10,
            offset=5,
            folder_id='f1',
            starred=True,
        )

        call_args = _mock_get_conversations.call_args
        call_positional = call_args[0]  # (uid, limit, offset)
        call_kwargs = call_args[1]

        # Positional args: uid, limit, offset
        assert call_positional[0] == 'uid1'
        assert call_positional[1] == 10
        assert call_positional[2] == 5

        # Keyword args: all existing + new params
        assert call_kwargs.get('start_date') == start
        assert call_kwargs.get('end_date') == end
        assert call_kwargs.get('categories') == ['work', 'personal']
        assert call_kwargs.get('include_discarded') is False
        assert call_kwargs.get('statuses') == ['completed']
        assert call_kwargs.get('folder_id') == 'f1'
        assert call_kwargs.get('starred') is True
        # include_transcript=True triggers populate_speaker_names
        _mock_populate_speaker_names.assert_called_once()

    def test_dev_get_conversations_with_unknown_folder_id_returns_empty(self):
        """When DB returns empty for unknown folder_id, handler returns empty list."""
        _mock_get_conversations.return_value = []

        from routers.developer import get_conversations

        result = get_conversations(uid='uid1', folder_id='nonexistent-folder')

        assert result == []


# ============================================================================
# HTTP layer tests — FastAPI TestClient
# ============================================================================


def _build_test_app():
    """Build a minimal FastAPI app with developer router for HTTP layer tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.developer import router as developer_router
    from dependencies import get_uid_with_conversations_read

    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_uid_with_conversations_read] = lambda: 'uid1'
    return app, TestClient(app)


class TestDevApiHttpLayer:
    """HTTP layer tests using FastAPI TestClient."""

    def setup_method(self):
        _mock_get_conversations.reset_mock()
        _mock_get_conversations.return_value = []
        _mock_get_folders.reset_mock()
        _mock_get_folders.return_value = [_make_folder('f1', 'Work')]
        _mock_initialize_system_folders.reset_mock()
        _mock_populate_folder_names.reset_mock()
        _mock_populate_speaker_names.reset_mock()
        # Ensure routers.developer uses the mocks regardless of import order
        import routers.developer as _dev_router

        _dev_router.populate_folder_names = _mock_populate_folder_names
        _dev_router.populate_speaker_names = _mock_populate_speaker_names

    def test_starred_invalid_string_returns_422(self):
        """starred=notabool should return 422 (FastAPI bool validation)."""
        _, client = _build_test_app()

        resp = client.get('/v1/dev/user/conversations?starred=notabool')

        assert resp.status_code == 422

    def test_folder_id_empty_string_returns_422(self):
        """folder_id= (empty) should return 422 (min_length=1)."""
        _, client = _build_test_app()

        resp = client.get('/v1/dev/user/conversations?folder_id=')

        assert resp.status_code == 422

    def test_folder_id_string_passes_validation(self):
        """Valid folder_id with starred=true should pass validation and return 200."""
        _, client = _build_test_app()

        resp = client.get('/v1/dev/user/conversations?folder_id=anything&starred=true')

        assert resp.status_code == 200

    def test_dev_get_folders_without_scope_returns_403(self):
        """Requests without CONVERSATIONS_READ scope should get 403 from get_folders."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.developer import router as developer_router
        from dependencies import get_api_key_auth, ApiKeyAuth

        app = FastAPI()
        app.include_router(developer_router)

        # Override get_api_key_auth to return ApiKeyAuth with insufficient scope
        def _low_scope_auth():
            return ApiKeyAuth(uid='uid1', scopes=['memories:read'])

        app.dependency_overrides[get_api_key_auth] = _low_scope_auth
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get('/v1/dev/user/folders')

        assert resp.status_code == 403

    def test_dev_get_conversations_without_scope_returns_403(self):
        """Requests without CONVERSATIONS_READ scope should get 403 from get_conversations."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.developer import router as developer_router
        from dependencies import get_api_key_auth, ApiKeyAuth

        app = FastAPI()
        app.include_router(developer_router)

        def _low_scope_auth():
            return ApiKeyAuth(uid='uid1', scopes=['memories:read'])

        app.dependency_overrides[get_api_key_auth] = _low_scope_auth
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get('/v1/dev/user/conversations?folder_id=f1')

        assert resp.status_code == 403

    def test_dev_get_folders_returns_200_with_list_body(self):
        """GET /v1/dev/user/folders returns 200 with a JSON list body when uid is injected.

        Note: this test overrides ``get_uid_with_conversations_read`` directly via
        ``_build_test_app``, so it does NOT exercise the scope-checking code path.
        Scope enforcement is covered by ``test_dev_get_folders_without_scope_returns_403``,
        which overrides ``get_api_key_auth`` instead.
        """
        _, client = _build_test_app()

        resp = client.get('/v1/dev/user/folders')

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]['id'] == 'f1'
        assert body[0]['name'] == 'Work'
