"""Tests for Developer API and Knowledge Graph locked data bypass fixes (#6146).

Verifies that is_locked conversations/memories/action_items are properly guarded
in the Developer API write endpoints and knowledge graph rebuild.
"""

from unittest.mock import patch, MagicMock
import os
import pytest
import sys
from types import ModuleType, SimpleNamespace

from tests.unit.memory_import_isolation import (
    restore_sys_modules,
    snapshot_sys_modules,
)

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
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
    'database.dev_api_key',
]


def _install_dev_api_lock_bypass_stubs() -> None:
    for mod_name in _stubs:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = _AutoMockModule(mod_name)

    sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
    sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
    sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
    sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
    sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})


def _repair_polluted_dev_api_lock_bypass_stubs() -> None:
    for name in _DEV_API_REAL_IMPORT_MODULES:
        sys.modules.pop(name, None)
    for name in (
        *_DEV_API_REAL_IMPORT_MODULES,
        'google.api_core',
        'google.api_core.exceptions',
        'google.cloud',
        'utils.cloud_tasks',
        'utils.other.storage',
        'utils.subscription',
    ):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, '__file__', None) is None:
            sys.modules.pop(name, None)
            if "." in name:
                parent_name, child_name = name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if isinstance(parent, ModuleType) and getattr(parent, child_name, None) is mod:
                    delattr(parent, child_name)
    _install_dev_api_lock_bypass_stubs()
    _rebind_memory_service_database_stubs()


def _rebind_memory_service_database_stubs() -> None:
    import importlib
    import utils.memory.memory_service as memory_service_mod

    memories = sys.modules.get('database.memories')
    if memories is not None:
        memory_service_mod.memories_db = memories
    vector_db = sys.modules.get('database.vector_db')
    if vector_db is not None:
        memory_service_mod.vector_db = vector_db
    importlib.reload(memory_service_mod)


_DEV_API_LOCK_BYPASS_STUB_MODULE_NAMES = tuple(_stubs)

_DEV_API_REAL_IMPORT_MODULES = (
    'routers.developer',
    'routers.knowledge_graph',
    'utils.conversations.process_conversation',
    'utils.llm.knowledge_graph',
)


@pytest.fixture(scope="module", autouse=True)
def _dev_api_lock_bypass_import_isolation():
    saved = snapshot_sys_modules(_DEV_API_LOCK_BYPASS_STUB_MODULE_NAMES)
    _install_dev_api_lock_bypass_stubs()
    yield
    restore_sys_modules(saved)


@pytest.fixture(autouse=True)
def _reinstall_dev_api_lock_bypass_stubs():
    _repair_polluted_dev_api_lock_bypass_stubs()


@pytest.fixture(autouse=True)
def _authorized_memory_developer_for_lock_tests(monkeypatch):
    import routers.developer as developer_module

    monkeypatch.setattr(
        developer_module,
        'authorize_memory_external_default_memory_write',
        MagicMock(return_value=SimpleNamespace(allowed=True, status_code=200, observability={'reason': 'test'})),
        raising=False,
    )


def _developer_memory_write_context(uid='test-uid'):
    from utils.memory.product_authorization import ProductAuthorizationContext

    return ProductAuthorizationContext(
        uid=uid,
        consumer='developer_api',
        surface='developer_api',
        app_id='test-app',
        key_id='test-key',
        scopes=('memories.write',),
    )


def _allow_developer_memory_write_grant():
    import routers.developer as developer_module

    developer_module.authorize_memory_external_default_memory_write = MagicMock(
        return_value=SimpleNamespace(allowed=True, status_code=200, observability={'reason': 'test'})
    )


def _make_conversation(locked=False, conversation_id='conv-1'):
    return {
        'id': conversation_id,
        'is_locked': locked,
        'structured': {
            'title': 'Test Conversation',
            'overview': 'Test overview',
            'action_items': [],
            'events': [],
            'category': 'personal',
        },
        'transcript_segments': [],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
        'visibility': 'private',
        'geolocation': None,
        'language': 'en',
        'status': 'completed',
        'source': 'friend',
    }


def _make_memory(locked=False, memory_id='mem-1'):
    return {
        'id': memory_id,
        'uid': 'test-uid',
        'is_locked': locked,
        'content': 'Secret memory content',
        'category': 'interesting',
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
        'visibility': 'private',
        'tags': [],
        'manually_added': False,
        'scoring': 'none',
        'reviewed': False,
        'user_review': None,
        'edited': False,
    }


def _make_action_item(locked=False, action_item_id='ai-1'):
    return {
        'id': action_item_id,
        'is_locked': locked,
        'description': 'Secret action item',
        'completed': False,
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
        'due_at': None,
        'completed_at': None,
        'conversation_id': None,
    }


# =============================================================================
# Developer API — Conversation write endpoints
# =============================================================================


class TestDevApiConversationLockEnforcement:
    """D1-D2: Dev API conversation PATCH/DELETE must return 402 for locked."""

    def test_patch_conversation_rejects_locked(self):
        """D1: PATCH /v1/dev/user/conversations/{id} must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.developer import update_conversation_endpoint, UpdateConversationRequest
        from fastapi import HTTPException

        request = UpdateConversationRequest(title='New Title')
        with pytest.raises(HTTPException) as exc_info:
            update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_patch_conversation_allows_unlocked(self):
        """D1: PATCH should proceed for unlocked conversations."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))
        conversations_db.update_conversation_title = MagicMock()

        from routers.developer import update_conversation_endpoint, UpdateConversationRequest

        request = UpdateConversationRequest(title='New Title')
        update_conversation_endpoint(conversation_id='conv-1', request=request, uid='test-uid')
        conversations_db.update_conversation_title.assert_called_once_with('test-uid', 'conv-1', 'New Title')

    def test_delete_conversation_rejects_locked(self):
        """D2: DELETE /v1/dev/user/conversations/{id} must raise 402 for locked."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=True))

        from routers.developer import delete_conversation_endpoint
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_delete_conversation_allows_unlocked(self):
        """D2: DELETE should proceed for unlocked conversations."""
        import database.conversations as conversations_db

        conversations_db.get_conversation = MagicMock(return_value=_make_conversation(locked=False))
        conversations_db.delete_conversation = MagicMock()

        from routers.developer import delete_conversation_endpoint

        result = delete_conversation_endpoint(conversation_id='conv-1', uid='test-uid')
        assert result == {"success": True}
        conversations_db.delete_conversation.assert_called_once_with('test-uid', 'conv-1')


# =============================================================================
# Developer API — Memory write endpoints
# =============================================================================


class TestDevApiActionItemLockEnforcement:
    """D5-D6: Dev API action-item PATCH/DELETE must return 402 for locked."""

    def test_patch_action_item_rejects_locked(self):
        """D5: PATCH /v1/dev/user/action-items/{id} must raise 402 for locked."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=True))

        from routers.developer import update_action_item, UpdateActionItemRequest
        from fastapi import HTTPException

        request = UpdateActionItemRequest(description='New desc')
        with pytest.raises(HTTPException) as exc_info:
            update_action_item(action_item_id='ai-1', request=request, uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_patch_action_item_allows_unlocked(self):
        """D5: PATCH should proceed for unlocked action items."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=False))
        action_items_db.update_action_item = MagicMock(return_value=True)

        from routers.developer import update_action_item, UpdateActionItemRequest

        request = UpdateActionItemRequest(description='New desc')
        update_action_item(action_item_id='ai-1', request=request, uid='test-uid')
        action_items_db.update_action_item.assert_called_once()

    def test_delete_action_item_rejects_locked(self):
        """D6: DELETE /v1/dev/user/action-items/{id} must raise 402 for locked."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=True))

        from routers.developer import delete_action_item
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_action_item(action_item_id='ai-1', uid='test-uid')
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_delete_action_item_allows_unlocked(self):
        """D6: DELETE should proceed for unlocked action items."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=_make_action_item(locked=False))
        action_items_db.delete_action_item = MagicMock(return_value=True)

        from routers.developer import delete_action_item

        result = delete_action_item(action_item_id='ai-1', uid='test-uid')
        assert result == {"success": True}
        action_items_db.delete_action_item.assert_called_once_with('test-uid', 'ai-1')

    def test_delete_action_item_returns_404_when_not_found(self):
        """D6: DELETE should return 404 when action item doesn't exist."""
        import database.action_items as action_items_db

        action_items_db.get_action_item = MagicMock(return_value=None)

        from routers.developer import delete_action_item
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            delete_action_item(action_item_id='ai-missing', uid='test-uid')
        assert exc_info.value.status_code == 404


# =============================================================================
# Knowledge Graph — Rebuild must filter locked memories
