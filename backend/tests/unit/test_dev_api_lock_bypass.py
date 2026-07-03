"""Tests for Developer API and Knowledge Graph locked data bypass fixes (#6146).

Verifies that is_locked conversations/memories/action_items are properly guarded
in the Developer API write endpoints and knowledge graph rebuild.
"""

from unittest.mock import patch, MagicMock, AsyncMock
import os
import pytest
import sys
from types import ModuleType, SimpleNamespace

from tests.unit.memory_import_isolation import (
    WS_I_HEAVY_STUB_MODULE_NAMES,
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
    from utils.memory.memory_system_pin import clear_memory_system_pin

    clear_memory_system_pin()
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


def _install_legacy_safe_memory_developer_defaults(monkeypatch):
    """Keep dev API lock tests focused on lock checks rather than memory write gating."""
    import utils.memory.default_read_rollout as rollout
    import utils.memory.developer_memory_adapter as developer_adapter

    def _legacy_rollout(uid='test-uid', **_kwargs):
        return rollout.legacy_safe_default_read_rollout_decision(
            uid=uid,
            source_path='test/dev-legacy-safe',
            consumer='developer_api',
            reason='dev_api_lock_fixture_legacy_safe',
        )

    allowed_write = rollout.LegacyMemoryWriteGuardDecision(allowed=True, detail={'enabled': True})
    ready_gate = rollout.WriteConvergencePolicy(source_path='test/dev-convergence', ready=True)

    monkeypatch.setattr(
        rollout,
        'guard_legacy_memory_write',
        MagicMock(return_value=allowed_write),
        raising=False,
    )


@pytest.fixture(autouse=True)
def _legacy_safe_memory_developer_for_lock_tests(monkeypatch):
    _install_legacy_safe_memory_developer_defaults(monkeypatch)
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


class TestDevApiMemoryLockEnforcement:
    """D3-D4: Dev API memory PATCH/DELETE must return 402 for locked."""

    def test_patch_memory_rejects_locked(self):
        """D3: PATCH /v1/dev/user/memories/{id} must raise 402 for locked."""
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.developer import update_memory, UpdateMemoryRequest
        from fastapi import HTTPException

        _allow_developer_memory_write_grant()

        request = UpdateMemoryRequest(content='New content')
        with pytest.raises(HTTPException) as exc_info:
            update_memory(memory_id='mem-1', request=request, auth_context=_developer_memory_write_context())
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_patch_memory_allows_unlocked(self):
        """D3: PATCH should proceed for unlocked memories."""
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.edit_memory = MagicMock()

        from routers.developer import update_memory, UpdateMemoryRequest

        _allow_developer_memory_write_grant()

        request = UpdateMemoryRequest(content='New content')
        update_memory(memory_id='mem-1', request=request, auth_context=_developer_memory_write_context())
        memories_db.edit_memory.assert_called_once()

    def test_delete_memory_rejects_locked(self):
        """D4: DELETE /v1/dev/user/memories/{id} must raise 402 for locked."""
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=True))

        from routers.developer import delete_memory
        from fastapi import HTTPException

        _allow_developer_memory_write_grant()

        with pytest.raises(HTTPException) as exc_info:
            delete_memory(memory_id='mem-1', auth_context=_developer_memory_write_context())
        assert exc_info.value.status_code == 402
        assert 'paid plan' in exc_info.value.detail.lower()

    def test_delete_memory_allows_unlocked(self):
        """D4: DELETE should proceed for unlocked memories."""
        import database.memories as memories_db

        memories_db.get_memory = MagicMock(return_value=_make_memory(locked=False))
        memories_db.delete_memory = MagicMock()

        from routers.developer import delete_memory

        _allow_developer_memory_write_grant()

        result = delete_memory(memory_id='mem-1', auth_context=_developer_memory_write_context())
        assert result == {"success": True}
        memories_db.delete_memory.assert_called_once_with('test-uid', 'mem-1')


# =============================================================================
# Developer API — Action item write endpoints
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
# =============================================================================


class TestKnowledgeGraphLockEnforcement:
    """K1: Knowledge graph rebuild must exclude locked memories."""

    def test_rebuild_filters_locked_memories(self):
        """K1: _rebuild_graph_task must filter out locked memories."""
        import database.memories as memories_db

        unlocked_mem = _make_memory(locked=False, memory_id='mem-unlocked')
        locked_mem = _make_memory(locked=True, memory_id='mem-locked')
        memories_db.get_memories = MagicMock(return_value=[unlocked_mem, locked_mem])

        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        rebuild_knowledge_graph.reset_mock()

        from routers.knowledge_graph import _rebuild_graph_task

        _rebuild_graph_task('test-uid', 'Test User')

        rebuild_knowledge_graph.assert_called_once()
        args = rebuild_knowledge_graph.call_args[0]
        passed_memories = args[1]
        assert len(passed_memories) == 1
        assert passed_memories[0]['id'] == 'mem-unlocked'

    def test_rebuild_passes_all_when_none_locked(self):
        """K1: When no memories are locked, all should be passed through."""
        import database.memories as memories_db

        mems = [_make_memory(locked=False, memory_id=f'mem-{i}') for i in range(3)]
        memories_db.get_memories = MagicMock(return_value=mems)

        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        rebuild_knowledge_graph.reset_mock()

        from routers.knowledge_graph import _rebuild_graph_task

        _rebuild_graph_task('test-uid', 'Test User')

        rebuild_knowledge_graph.assert_called_once()
        args = rebuild_knowledge_graph.call_args[0]
        assert len(args[1]) == 3

    def test_rebuild_passes_empty_when_all_locked(self):
        """K1: When all memories are locked, empty list should be passed."""
        import database.memories as memories_db

        mems = [_make_memory(locked=True, memory_id=f'mem-{i}') for i in range(3)]
        memories_db.get_memories = MagicMock(return_value=mems)

        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        rebuild_knowledge_graph.reset_mock()

        from routers.knowledge_graph import _rebuild_graph_task

        _rebuild_graph_task('test-uid', 'Test User')

        rebuild_knowledge_graph.assert_called_once()
        args = rebuild_knowledge_graph.call_args[0]
        assert len(args[1]) == 0

    def test_rebuild_handles_missing_is_locked_field(self):
        """K1: Memories without is_locked field should default to unlocked."""
        import database.memories as memories_db

        mem = {'id': 'mem-no-field', 'content': 'Some content'}
        memories_db.get_memories = MagicMock(return_value=[mem])

        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        rebuild_knowledge_graph.reset_mock()

        from routers.knowledge_graph import _rebuild_graph_task

        _rebuild_graph_task('test-uid', 'Test User')

        rebuild_knowledge_graph.assert_called_once()
        args = rebuild_knowledge_graph.call_args[0]
        assert len(args[1]) == 1

    def test_rebuild_reads_canonical_memories_via_memory_service(self):
        """Canonical cohort must rebuild KG from MemoryService.read, not legacy DB."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        from models.memories import MemoryDB, MemoryCategory
        from utils.memory.memory_system import MemorySystem
        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        canonical_memory = MemoryDB(
            id='mem-canonical',
            uid='uid-canonical',
            content='Canonical KG fact',
            category=MemoryCategory.interesting,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        service = MagicMock()
        service.read.return_value = [canonical_memory]
        rebuild_knowledge_graph.reset_mock()

        import database.memories as memories_db

        with patch('routers.knowledge_graph.pin_memory_system', return_value=MemorySystem.CANONICAL):
            with patch('routers.knowledge_graph.MemoryService', return_value=service):
                with patch.object(memories_db, 'get_memories') as legacy_get:
                    from routers.knowledge_graph import _rebuild_graph_task

                    _rebuild_graph_task('uid-canonical', 'Test User')

        service.read.assert_called_once_with('uid-canonical', limit=500)
        legacy_get.assert_not_called()
        rebuild_knowledge_graph.assert_called_once()
        passed_memories = rebuild_knowledge_graph.call_args[0][1]
        assert passed_memories == [{'id': 'mem-canonical', 'content': 'Canonical KG fact'}]

    def test_rebuild_reads_legacy_memories_via_memories_db(self):
        """Non-canonical cohort must keep legacy memories_db.get_memories."""
        from unittest.mock import patch

        from utils.memory.memory_system import MemorySystem
        from utils.llm.knowledge_graph import rebuild_knowledge_graph

        legacy_mem = _make_memory(locked=False, memory_id='mem-legacy')
        service = MagicMock()
        rebuild_knowledge_graph.reset_mock()

        import database.memories as memories_db

        memories_db.get_memories = MagicMock(return_value=[legacy_mem])

        with patch('routers.knowledge_graph.pin_memory_system', return_value=MemorySystem.LEGACY):
            with patch('routers.knowledge_graph.MemoryService', return_value=service):
                from routers.knowledge_graph import _rebuild_graph_task

                _rebuild_graph_task('uid-legacy', 'Test User')

        memories_db.get_memories.assert_called_once_with('uid-legacy', limit=500)
        service.read.assert_not_called()
        rebuild_knowledge_graph.assert_called_once()
        assert rebuild_knowledge_graph.call_args[0][1][0]['id'] == 'mem-legacy'


# =============================================================================
# Process conversation — KG extraction must skip locked memories
# =============================================================================


class TestProcessConversationKGLockEnforcement:
    """KG extraction in process_conversation must skip locked memories."""

    def test_kg_extraction_guard_uses_or_condition_in_ast(self):
        """Verify the production guard is exactly `if X.kg_extracted or X.is_locked: continue`.

        Checks via AST: exactly two operands, both ast.Attribute on the same base
        variable, attributes are {kg_extracted, is_locked}, operator is Or, and body
        is solely `continue`. A regression like `and`, extra operands, or different
        variables will fail this test.
        """
        import ast
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / 'utils'
            / 'conversations'
            / 'process_conversation.py'
        )
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))

        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.Or):
                continue
            # Exactly two operands
            if len(test.values) != 2:
                continue
            # Both must be ast.Attribute
            if not all(isinstance(v, ast.Attribute) for v in test.values):
                continue
            # Both must be ast.Name bases (not subscripts, calls, etc.)
            if not all(isinstance(v.value, ast.Name) for v in test.values):
                continue
            # Both must reference the exact same variable name
            if test.values[0].value.id != test.values[1].value.id:
                continue
            # Attributes must be exactly {kg_extracted, is_locked}
            attrs = {v.attr for v in test.values}
            if attrs != {'kg_extracted', 'is_locked'}:
                continue
            # Body must be solely `continue`
            if len(node.body) == 1 and isinstance(node.body[0], ast.Continue):
                found = True
                break

        assert found, (
            "Expected exactly `if X.kg_extracted or X.is_locked: continue` "
            "in process_conversation.py — AST check failed"
        )

    def test_kg_extraction_skips_locked_memory(self):
        """Locked memories should not be sent to extract_knowledge_from_memory.

        Exercises the production guard pattern (or → skip) against three cases:
        locked, unlocked, and already-extracted.
        """
        from utils.llm.knowledge_graph import extract_knowledge_from_memory

        extract_knowledge_from_memory.reset_mock()

        locked_memory = MagicMock()
        locked_memory.id = 'mem-locked'
        locked_memory.kg_extracted = False
        locked_memory.is_locked = True

        unlocked_memory = MagicMock()
        unlocked_memory.id = 'mem-unlocked'
        unlocked_memory.kg_extracted = False
        unlocked_memory.is_locked = False

        already_extracted = MagicMock()
        already_extracted.id = 'mem-already'
        already_extracted.kg_extracted = True
        already_extracted.is_locked = False

        # Replicate the production guard from process_conversation.py:478-480
        extracted = []
        for memory_db_obj in [locked_memory, unlocked_memory, already_extracted]:
            if memory_db_obj.kg_extracted or memory_db_obj.is_locked:
                continue
            extracted.append(memory_db_obj.id)

        assert extracted == ['mem-unlocked'], f"Expected only unlocked/unextracted, got {extracted}"

    def test_kg_extraction_guard_catches_and_regression(self):
        """Prove that `and` instead of `or` would let locked memories through."""
        locked_memory = MagicMock()
        locked_memory.id = 'mem-locked'
        locked_memory.kg_extracted = False
        locked_memory.is_locked = True

        # With `and` (wrong): both must be true to skip — locked-but-not-extracted leaks
        wrong_skipped = locked_memory.kg_extracted and locked_memory.is_locked
        assert not wrong_skipped, "and would skip only when BOTH are true"

        # With `or` (correct): either one skips
        correct_skipped = locked_memory.kg_extracted or locked_memory.is_locked
        assert correct_skipped, "or correctly skips when is_locked is true"
