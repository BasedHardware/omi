"""Unit tests for the MCP action-item write surface: create, complete, update,
delete, and semantic search.

Exercises the shared orchestration (utils/mcp_action_items.py) plus both
transports — the REST handlers (routers/mcp.py) and the MCP tool dispatch
(routers/mcp_sse.py) — with the database and vector layers mocked, following the
heavy-dep stubbing pattern in test_mcp_data_endpoints.py.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import os
import sys
from types import ModuleType

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, ModuleType):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]
    if '.' in name:
        parent_name, child_name = name.rsplit('.', 1)
        parent = sys.modules.setdefault(parent_name, ModuleType(parent_name))
        setattr(parent, child_name, module)
    return module


def _drop_stale_module(module_name, expected_file):
    module = sys.modules.get(module_name)
    if module is None:
        return
    module_file = getattr(module, '__file__', None)
    if isinstance(module_file, str) and os.path.abspath(module_file) == expected_file:
        return
    sys.modules.pop(module_name, None)
    parent_name, child_name = module_name.rsplit('.', 1)
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType) and getattr(parent, child_name, None) is module:
        delattr(parent, child_name)


_ensure_package_path('utils', os.path.join(_BACKEND_DIR, 'utils'))
_ensure_package_path('utils.retrieval', os.path.join(_BACKEND_DIR, 'utils', 'retrieval'))
_ensure_package_path('models', os.path.join(_BACKEND_DIR, 'models'))
_drop_stale_module('utils.retrieval.hybrid', os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'hybrid.py'))
_drop_stale_module('models.memories', os.path.join(_BACKEND_DIR, 'models', 'memories.py'))
_drop_stale_module('models.conversation_enums', os.path.join(_BACKEND_DIR, 'models', 'conversation_enums.py'))
_drop_stale_module('models.mcp_api_key', os.path.join(_BACKEND_DIR, 'models', 'mcp_api_key.py'))
# utils.mcp_data and utils.mcp_action_items are the real modules under test — never stub them.
_drop_stale_module('utils.mcp_data', os.path.join(_BACKEND_DIR, 'utils', 'mcp_data.py'))
_drop_stale_module('utils.mcp_action_items', os.path.join(_BACKEND_DIR, 'utils', 'mcp_action_items.py'))

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
    'database.screen_activity',
    'database.x_posts',
    'database.fair_use',
    'database.auth',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
    'google',
    'google.cloud',
    # mcp_sse imports FailedPrecondition from google.api_core.exceptions; the
    # bare 'google' AutoMock is not a package unless __path__ is set below.
    'google.api_core',
    'google.api_core.exceptions',
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
    'dependencies',
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _AutoMockModule(mod_name)

# Make stubbed google.* packages importable as packages (submodule imports).
for _pkg_name in ('google', 'google.cloud', 'google.api_core'):
    _pkg = sys.modules.get(_pkg_name)
    if isinstance(_pkg, ModuleType) and not hasattr(_pkg, '__path__'):
        _pkg.__path__ = []  # type: ignore[attr-defined]
# AutoMockModule.__getattr__ invents MagicMocks for any name; those cannot be
# used in except clauses. Reuse an existing Exception subclass if another test
# already installed one so mcp_sse's bound name stays catchable.
_api_core_exc = sys.modules['google.api_core.exceptions']
_existing_fp = getattr(_api_core_exc, 'FailedPrecondition', None)
if not (isinstance(_existing_fp, type) and issubclass(_existing_fp, BaseException)):
    _api_core_exc.FailedPrecondition = type('FailedPrecondition', (Exception,), {})

if not isinstance(getattr(sys.modules['database._client'], '__file__', None), str):
    sys.modules['database._client'].document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
sys.modules['dependencies'].get_uid_from_mcp_api_key = MagicMock(return_value='user-1')
sys.modules['dependencies'].get_current_user_id = MagicMock(return_value='user-1')
sys.modules['utils.other.endpoints'].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
sys.modules['utils.other.endpoints'].check_rate_limit_inline = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

from fastapi import HTTPException  # noqa: E402

import utils.mcp_action_items as actions  # noqa: E402  (module under test)
from routers import mcp as rest  # noqa: E402
from routers import mcp_sse as sse  # noqa: E402

NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def _action_item(item_id='a1', desc='Email Bob', completed=False, deleted=False, locked=False, due_at=NOW):
    return {
        'id': item_id,
        'description': desc,
        'completed': completed,
        'created_at': NOW,
        'due_at': due_at,
        'completed_at': None,
        'conversation_id': None,
        'deleted': deleted,
        'is_locked': locked,
    }


# ---------------------------------------------------------------------------
# Shared orchestration (utils/mcp_action_items.py)
# ---------------------------------------------------------------------------
class TestIdempotencyKey:
    def test_same_description_same_key(self):
        a = actions.content_idempotency_key(UID, 'Email Bob')
        b = actions.content_idempotency_key(UID, '  email bob  ')  # case + whitespace insensitive
        assert a == b

    def test_different_description_differs(self):
        assert actions.content_idempotency_key(UID, 'Email Bob') != actions.content_idempotency_key(UID, 'Call Bob')

    def test_uid_boundary_is_unambiguous(self):
        # Length-prefixing prevents a uid containing ':' from colliding across the boundary.
        assert actions.content_idempotency_key('a:b', 'c') != actions.content_idempotency_key('a', 'b:c')


class TestParseDueAt:
    def test_passthrough_datetime_and_none(self):
        assert actions.parse_due_at(None) is None
        assert actions.parse_due_at(NOW) == NOW

    def test_iso_and_date_strings(self):
        assert actions.parse_due_at('2026-07-01T17:00:00Z') == datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc)
        assert actions.parse_due_at('2026-07-01') == datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert actions.parse_due_at('   ') is None

    def test_bad_string_raises(self):
        with pytest.raises(ValueError):
            actions.parse_due_at('next tuesday')


class TestCreateOrchestration:
    @patch('utils.mcp_action_items.upsert_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_create_passes_idempotency_key_and_indexes(self, mock_db, mock_vec):
        mock_db.create_action_item.return_value = 'a1'
        mock_db.get_action_item.return_value = _action_item('a1', desc='Email Bob')
        out = actions.create_action_item(UID, '  Email Bob  ', due_at='2026-07-01')

        args, kwargs = mock_db.create_action_item.call_args
        assert args[0] == UID
        assert args[1]['description'] == 'Email Bob'  # trimmed
        assert args[1]['due_at'] == datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert kwargs['idempotency_key'] == actions.content_idempotency_key(UID, 'Email Bob')
        mock_vec.assert_called_once_with(UID, 'a1', 'Email Bob')
        assert out['id'] == 'a1' and out['description'] == 'Email Bob'

    @patch('utils.mcp_action_items.upsert_action_item_vector', side_effect=RuntimeError('pinecone down'))
    @patch('utils.mcp_action_items.action_items_db')
    def test_create_survives_vector_failure(self, mock_db, _mock_vec):
        mock_db.create_action_item.return_value = 'a1'
        mock_db.get_action_item.return_value = _action_item('a1')
        out = actions.create_action_item(UID, 'Email Bob')  # vector raises, task still returned
        assert out['id'] == 'a1'

    @patch('utils.mcp_action_items.action_items_db')
    def test_create_rejects_blank(self, _mock_db):
        with pytest.raises(ValueError):
            actions.create_action_item(UID, '   ')

    @patch('utils.mcp_action_items.action_items_db')
    def test_create_rejects_too_long(self, _mock_db):
        with pytest.raises(ValueError):
            actions.create_action_item(UID, 'x' * (actions.MAX_DESCRIPTION_CHARS + 1))


class TestMutationGuards:
    @patch('utils.mcp_action_items.action_items_db')
    def test_complete_not_found(self, mock_db):
        mock_db.get_action_item.return_value = None
        with pytest.raises(actions.ActionItemNotFound):
            actions.set_completed(UID, 'missing')

    @patch('utils.mcp_action_items.action_items_db')
    def test_complete_locked(self, mock_db):
        mock_db.get_action_item.return_value = _action_item('a1', locked=True)
        with pytest.raises(actions.ActionItemLocked):
            actions.set_completed(UID, 'a1')

    @patch('utils.mcp_action_items.action_items_db')
    def test_complete_marks_and_returns(self, mock_db):
        mock_db.get_action_item.side_effect = [_action_item('a1'), _action_item('a1', completed=True)]
        mock_db.mark_action_item_completed.return_value = True
        out = actions.set_completed(UID, 'a1', completed=True)
        mock_db.mark_action_item_completed.assert_called_once_with(UID, 'a1', completed=True)
        assert out['completed'] is True

    @patch('utils.mcp_action_items.upsert_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_update_reindexes_only_on_description_change(self, mock_db, mock_vec):
        mock_db.get_action_item.side_effect = [_action_item('a1'), _action_item('a1', due_at=NOW)]
        mock_db.update_action_item.return_value = True
        actions.update_action_item(UID, 'a1', due_at='2026-07-02')  # no description
        mock_vec.assert_not_called()

        mock_db.get_action_item.side_effect = [_action_item('a1'), _action_item('a1', desc='New')]
        actions.update_action_item(UID, 'a1', description='New')
        mock_vec.assert_called_once_with(UID, 'a1', 'New')

    @patch('utils.mcp_action_items.action_items_db')
    def test_update_requires_a_field(self, mock_db):
        mock_db.get_action_item.return_value = _action_item('a1')
        with pytest.raises(ValueError):
            actions.update_action_item(UID, 'a1')

    @patch('utils.mcp_action_items.delete_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_delete_removes_vector(self, mock_db, mock_vec):
        mock_db.get_action_item.return_value = _action_item('a1')
        mock_db.delete_action_item.return_value = True
        actions.delete_action_item(UID, 'a1')
        mock_db.delete_action_item.assert_called_once_with(UID, 'a1')
        mock_vec.assert_called_once_with(UID, 'a1')

    @patch('utils.mcp_action_items.delete_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_delete_noop_raises_not_found(self, mock_db, mock_vec):
        # Existed at the guard check, but the delete itself was a no-op (raced).
        mock_db.get_action_item.return_value = _action_item('a1')
        mock_db.delete_action_item.return_value = False
        with pytest.raises(actions.ActionItemNotFound):
            actions.delete_action_item(UID, 'a1')
        mock_vec.assert_not_called()

    @patch('utils.mcp_action_items.action_items_db')
    def test_set_completed_reload_missing_raises(self, mock_db):
        # Marked complete, then the item vanished before the reload (concurrent delete).
        mock_db.get_action_item.side_effect = [_action_item('a1'), None]
        mock_db.mark_action_item_completed.return_value = True
        with pytest.raises(actions.ActionItemNotFound):
            actions.set_completed(UID, 'a1')

    @patch('utils.mcp_action_items.action_items_db')
    def test_update_blank_due_at_does_not_clear(self, mock_db):
        # A blank due_at must not null the field, and on its own is "nothing to update".
        mock_db.get_action_item.return_value = _action_item('a1')
        with pytest.raises(ValueError):
            actions.update_action_item(UID, 'a1', due_at='')

        # With a real description, a blank due_at is simply dropped from the update.
        mock_db.get_action_item.side_effect = [_action_item('a1'), _action_item('a1', desc='New')]
        mock_db.update_action_item.return_value = True
        actions.update_action_item(UID, 'a1', description='New', due_at='')
        _, kwargs_or_args = mock_db.update_action_item.call_args
        update_data = mock_db.update_action_item.call_args[0][2]
        assert 'due_at' not in update_data
        assert update_data['description'] == 'New'


class TestSearchOrchestration:
    @patch('utils.mcp_action_items.search_action_items_by_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_search_preserves_relevance_order(self, mock_db, mock_vec):
        mock_vec.return_value = ['a2', 'a1']  # relevance order
        # DB returns them in a different (arbitrary) order
        mock_db.get_action_items_by_ids.return_value = [_action_item('a1'), _action_item('a2')]
        out = actions.search_action_items(UID, 'bob', limit=5)
        assert [i['id'] for i in out] == ['a2', 'a1']

    @patch('utils.mcp_action_items.search_action_items_by_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_search_empty(self, mock_db, mock_vec):
        mock_vec.return_value = []
        assert actions.search_action_items(UID, 'bob') == []
        mock_db.get_action_items_by_ids.assert_not_called()

    def test_search_rejects_blank_query(self):
        with pytest.raises(ValueError):
            actions.search_action_items(UID, '   ')


# ---------------------------------------------------------------------------
# REST transport (routers/mcp.py)
# ---------------------------------------------------------------------------
class TestRestTransport:
    @patch('utils.mcp_action_items.upsert_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_create(self, mock_db, _mock_vec):
        mock_db.create_action_item.return_value = 'a1'
        mock_db.get_action_item.return_value = _action_item('a1')
        body = rest.McpCreateActionItem(description='Email Bob', due_at=NOW)
        out = rest.create_action_item(body=body, uid=UID)
        assert out['id'] == 'a1'

    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_create_blank_is_422(self, _mock_db):
        with pytest.raises(HTTPException) as ei:
            rest.create_action_item(body=rest.McpCreateActionItem(description='  '), uid=UID)
        assert ei.value.status_code == 422

    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_complete_not_found_is_404(self, mock_db):
        mock_db.get_action_item.return_value = None
        with pytest.raises(HTTPException) as ei:
            rest.complete_action_item(action_item_id='missing', uid=UID)
        assert ei.value.status_code == 404

    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_complete_locked_is_402(self, mock_db):
        mock_db.get_action_item.return_value = _action_item('a1', locked=True)
        with pytest.raises(HTTPException) as ei:
            rest.complete_action_item(action_item_id='a1', uid=UID)
        assert ei.value.status_code == 402

    @patch('utils.mcp_action_items.delete_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_delete_ok(self, mock_db, _mock_vec):
        mock_db.get_action_item.return_value = _action_item('a1')
        mock_db.delete_action_item.return_value = True
        assert rest.delete_action_item(action_item_id='a1', uid=UID) == {"status": "ok"}

    @patch('utils.mcp_action_items.upsert_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_update(self, mock_db, _mock_vec):
        mock_db.get_action_item.side_effect = [_action_item('a1'), _action_item('a1', desc='New text')]
        mock_db.update_action_item.return_value = True
        out = rest.update_action_item('a1', body=rest.McpUpdateActionItem(description='New text'), uid=UID)
        assert out['description'] == 'New text'

    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_update_not_found_is_404(self, mock_db):
        mock_db.get_action_item.return_value = None
        with pytest.raises(HTTPException) as ei:
            rest.update_action_item('missing', body=rest.McpUpdateActionItem(description='x'), uid=UID)
        assert ei.value.status_code == 404

    @patch('utils.mcp_action_items.search_action_items_by_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_rest_search(self, mock_db, mock_vec):
        mock_vec.return_value = ['a1']
        mock_db.get_action_items_by_ids.return_value = [_action_item('a1')]
        out = rest.search_action_items(query='bob', uid=UID)
        assert [i['id'] for i in out] == ['a1']

    def test_rest_search_blank_is_422(self):
        with pytest.raises(HTTPException) as ei:
            rest.search_action_items(query='   ', uid=UID)
        assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# MCP tool dispatch (routers/mcp_sse.py)
# ---------------------------------------------------------------------------
class TestSseDispatch:
    @patch('utils.mcp_action_items.upsert_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_create(self, mock_db, _mock_vec):
        mock_db.create_action_item.return_value = 'a1'
        mock_db.get_action_item.return_value = _action_item('a1')
        result = sse.execute_tool(UID, 'create_action_item', {'description': 'Email Bob', 'due_at': '2026-07-01'})
        assert result['success'] is True
        assert result['action_item']['id'] == 'a1'

    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_create_bad_due_date_is_invalid_params(self, _mock_db):
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'create_action_item', {'description': 'x', 'due_at': 'whenever'})
        assert ei.value.code == -32602

    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_complete_requires_id(self, _mock_db):
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'complete_action_item', {})
        assert ei.value.code == -32602

    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_complete_not_found(self, mock_db):
        mock_db.get_action_item.return_value = None
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'complete_action_item', {'action_item_id': 'missing'})
        assert ei.value.code == -32001

    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_update_locked(self, mock_db):
        mock_db.get_action_item.return_value = _action_item('a1', locked=True)
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'update_action_item', {'action_item_id': 'a1', 'description': 'New'})
        assert ei.value.code == -32002

    @patch('utils.mcp_action_items.delete_action_item_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_delete(self, mock_db, _mock_vec):
        mock_db.get_action_item.return_value = _action_item('a1')
        result = sse.execute_tool(UID, 'delete_action_item', {'action_item_id': 'a1'})
        assert result['success'] is True

    @patch('utils.mcp_action_items.search_action_items_by_vector')
    @patch('utils.mcp_action_items.action_items_db')
    def test_tool_search(self, mock_db, mock_vec):
        mock_vec.return_value = ['a1']
        mock_db.get_action_items_by_ids.return_value = [_action_item('a1')]
        result = sse.execute_tool(UID, 'search_action_items', {'query': 'bob'})
        assert result['action_items'][0]['id'] == 'a1'


class TestToolRegistration:
    def test_write_tools_listed_with_scopes(self):
        by_name = {t['name']: t for t in sse.MCP_TOOLS}
        for name in ['create_action_item', 'complete_action_item', 'update_action_item', 'delete_action_item']:
            assert name in by_name
            assert by_name[name]['securitySchemes'] == sse.ACTION_ITEMS_WRITE_SECURITY
        # search is a read, guarded by the read scope
        assert by_name['search_action_items']['securitySchemes'] == sse.ACTION_ITEMS_READ_SECURITY

    def test_write_scope_advertised(self):
        assert 'action_items.write' in sse.MCP_SCOPES_SUPPORTED
