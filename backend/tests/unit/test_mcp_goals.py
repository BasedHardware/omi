"""Unit tests for the MCP goals write surface: create, update, log progress,
delete, and history.

Exercises the shared orchestration (utils/mcp_goals.py) plus both transports —
the REST handlers (routers/mcp.py) and the MCP tool dispatch (routers/mcp_sse.py)
— with the goals database mocked, following the heavy-dep stubbing pattern in
test_mcp_data_endpoints.py.
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
# utils.mcp_data and utils.mcp_goals are the real modules under test — never stub them.
_drop_stale_module('utils.mcp_data', os.path.join(_BACKEND_DIR, 'utils', 'mcp_data.py'))
_drop_stale_module('utils.mcp_goals', os.path.join(_BACKEND_DIR, 'utils', 'mcp_goals.py'))

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

if not isinstance(getattr(sys.modules['database._client'], '__file__', None), str):
    sys.modules['database._client'].document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
sys.modules['dependencies'].get_uid_from_mcp_api_key = MagicMock(return_value='user-1')
sys.modules['dependencies'].get_current_user_id = MagicMock(return_value='user-1')
sys.modules['utils.other.endpoints'].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
sys.modules['utils.other.endpoints'].check_rate_limit_inline = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

from fastapi import HTTPException  # noqa: E402

import utils.mcp_goals as goals  # noqa: E402  (module under test)
from routers import mcp as rest  # noqa: E402
from routers import mcp_sse as sse  # noqa: E402

NOW = datetime(2026, 6, 27, tzinfo=timezone.utc)
UID = "user-1"


def _goal(goal_id='g1', title='Read 12 books', current=3, target=12, active=True):
    return {
        'id': goal_id,
        'title': title,
        'goal_type': 'numeric',
        'target_value': target,
        'current_value': current,
        'min_value': 0,
        'max_value': 12,
        'unit': 'books',
        'is_active': active,
        'created_at': NOW,
        'updated_at': NOW,
    }


# ---------------------------------------------------------------------------
# Shared orchestration (utils/mcp_goals.py)
# ---------------------------------------------------------------------------
class TestGoalOrchestration:
    @patch('utils.mcp_goals.goals_db')
    def test_create_builds_goal_and_returns_clean_shape(self, mock_db):
        mock_db.create_goal.return_value = _goal()
        out = goals.create_goal(UID, '  Read 12 books  ', 12, goal_type='numeric', unit='books')
        args, _ = mock_db.create_goal.call_args
        assert args[0] == UID
        assert args[1]['title'] == 'Read 12 books'  # trimmed
        assert args[1]['target_value'] == 12.0
        assert args[1]['goal_type'] == 'numeric'
        assert out['id'] == 'g1' and out['current_value'] == 3 and out['title'] == 'Read 12 books'

    @patch('utils.mcp_goals.goals_db')
    def test_create_rejects_blank_title(self, _mock_db):
        with pytest.raises(ValueError):
            goals.create_goal(UID, '   ', 10)

    @patch('utils.mcp_goals.goals_db')
    def test_create_rejects_bad_goal_type(self, _mock_db):
        with pytest.raises(ValueError):
            goals.create_goal(UID, 'Run more', 10, goal_type='weird')

    @patch('utils.mcp_goals.goals_db')
    def test_create_rejects_non_numeric_target(self, _mock_db):
        with pytest.raises(ValueError):
            goals.create_goal(UID, 'Run more', 'lots')

    @patch('utils.mcp_goals.goals_db')
    def test_update_only_passes_provided_fields(self, mock_db):
        mock_db.update_goal.return_value = _goal(title='New title')
        goals.update_goal(UID, 'g1', title='New title')
        updates = mock_db.update_goal.call_args[0][2]
        assert updates == {'title': 'New title'}

    @patch('utils.mcp_goals.goals_db')
    def test_update_requires_a_field(self, _mock_db):
        with pytest.raises(ValueError):
            goals.update_goal(UID, 'g1')

    @patch('utils.mcp_goals.goals_db')
    def test_update_not_found(self, mock_db):
        mock_db.update_goal.return_value = None
        with pytest.raises(goals.GoalNotFound):
            goals.update_goal(UID, 'missing', title='x')

    @patch('utils.mcp_goals.goals_db')
    def test_update_progress_returns_clean(self, mock_db):
        mock_db.update_goal_progress.return_value = _goal(current=5)
        out = goals.update_goal_progress(UID, 'g1', 5)
        mock_db.update_goal_progress.assert_called_once_with(UID, 'g1', 5.0)
        assert out['current_value'] == 5

    @patch('utils.mcp_goals.goals_db')
    def test_update_progress_not_found(self, mock_db):
        mock_db.update_goal_progress.return_value = None
        with pytest.raises(goals.GoalNotFound):
            goals.update_goal_progress(UID, 'missing', 5)

    @patch('utils.mcp_goals.goals_db')
    def test_delete_ok_and_not_found(self, mock_db):
        mock_db.delete_goal.return_value = True
        goals.delete_goal(UID, 'g1')
        mock_db.delete_goal.assert_called_once_with(UID, 'g1')
        mock_db.delete_goal.return_value = False
        with pytest.raises(goals.GoalNotFound):
            goals.delete_goal(UID, 'missing')

    @patch('utils.mcp_goals.goals_db')
    def test_history_clamps_days(self, mock_db):
        mock_db.get_goal_history.return_value = [{'date': '2026-06-27', 'value': 3}]
        goals.get_goal_history(UID, 'g1', days=9999)
        assert mock_db.get_goal_history.call_args.kwargs['days'] == 365


# ---------------------------------------------------------------------------
# REST transport (routers/mcp.py)
# ---------------------------------------------------------------------------
class TestRestTransport:
    @patch('utils.mcp_goals.goals_db')
    def test_rest_create(self, mock_db):
        mock_db.create_goal.return_value = _goal()
        out = rest.create_goal(body=rest.McpCreateGoal(title='Read 12 books', target_value=12), uid=UID)
        assert out['id'] == 'g1'

    @patch('utils.mcp_goals.goals_db')
    def test_rest_create_blank_is_422(self, _mock_db):
        with pytest.raises(HTTPException) as ei:
            rest.create_goal(body=rest.McpCreateGoal(title='  ', target_value=12), uid=UID)
        assert ei.value.status_code == 422

    @patch('utils.mcp_goals.goals_db')
    def test_rest_update_not_found_is_404(self, mock_db):
        mock_db.update_goal.return_value = None
        with pytest.raises(HTTPException) as ei:
            rest.update_goal('missing', body=rest.McpUpdateGoal(title='x'), uid=UID)
        assert ei.value.status_code == 404

    @patch('utils.mcp_goals.goals_db')
    def test_rest_progress(self, mock_db):
        mock_db.update_goal_progress.return_value = _goal(current=7)
        out = rest.update_goal_progress('g1', current_value=7, uid=UID)
        assert out['current_value'] == 7

    @patch('utils.mcp_goals.goals_db')
    def test_rest_delete_ok(self, mock_db):
        mock_db.delete_goal.return_value = True
        assert rest.delete_goal('g1', uid=UID) == {"status": "ok"}

    @patch('utils.mcp_goals.goals_db')
    def test_rest_history(self, mock_db):
        mock_db.get_goal_history.return_value = [{'date': '2026-06-27', 'value': 3}]
        assert rest.get_goal_history('g1', uid=UID) == [{'date': '2026-06-27', 'value': 3}]


# ---------------------------------------------------------------------------
# MCP tool dispatch (routers/mcp_sse.py)
# ---------------------------------------------------------------------------
class TestSseDispatch:
    @patch('utils.mcp_goals.goals_db')
    def test_tool_create(self, mock_db):
        mock_db.create_goal.return_value = _goal()
        result = sse.execute_tool(UID, 'create_goal', {'title': 'Read 12 books', 'target_value': 12})
        assert result['success'] is True and result['goal']['id'] == 'g1'

    @patch('utils.mcp_goals.goals_db')
    def test_tool_create_bad_type_is_invalid_params(self, _mock_db):
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'create_goal', {'title': 'x', 'target_value': 1, 'goal_type': 'nope'})
        assert ei.value.code == -32602

    @patch('utils.mcp_goals.goals_db')
    def test_tool_update_not_found(self, mock_db):
        mock_db.update_goal.return_value = None
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'update_goal', {'goal_id': 'missing', 'title': 'x'})
        assert ei.value.code == -32001

    @patch('utils.mcp_goals.goals_db')
    def test_tool_update_progress(self, mock_db):
        mock_db.update_goal_progress.return_value = _goal(current=9)
        result = sse.execute_tool(UID, 'update_goal_progress', {'goal_id': 'g1', 'current_value': 9})
        assert result['goal']['current_value'] == 9

    @patch('utils.mcp_goals.goals_db')
    def test_tool_delete(self, mock_db):
        mock_db.delete_goal.return_value = True
        assert sse.execute_tool(UID, 'delete_goal', {'goal_id': 'g1'})['success'] is True

    def test_tool_update_progress_requires_id(self):
        with pytest.raises(sse.ToolExecutionError) as ei:
            sse.execute_tool(UID, 'update_goal_progress', {'current_value': 5})
        assert ei.value.code == -32602

    @patch('utils.mcp_goals.goals_db')
    def test_tool_history(self, mock_db):
        mock_db.get_goal_history.return_value = [{'date': '2026-06-27', 'value': 3}]
        result = sse.execute_tool(UID, 'get_goal_history', {'goal_id': 'g1'})
        assert result['history'][0]['value'] == 3


class TestToolRegistration:
    def test_write_tools_listed_with_scopes(self):
        by_name = {t['name']: t for t in sse.MCP_TOOLS}
        for name in ['create_goal', 'update_goal', 'update_goal_progress', 'delete_goal']:
            assert name in by_name
            assert by_name[name]['securitySchemes'] == sse.GOALS_WRITE_SECURITY
        assert by_name['get_goal_history']['securitySchemes'] == sse.GOALS_READ_SECURITY

    def test_write_scope_advertised(self):
        assert 'goals.write' in sse.MCP_SCOPES_SUPPORTED
