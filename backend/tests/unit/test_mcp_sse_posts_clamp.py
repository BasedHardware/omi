"""Unit tests for limit clamping in the MCP SSE x-posts/search tool branches.

The get_x_posts / search_x_posts / search_conversations branches of
routers/mcp_sse.py:execute_tool previously read `limit` straight from the
client arguments and passed it unguarded to Firestore / the vector DB. A
negative, huge, or non-integer limit therefore reached the data layer
(500-ing the request or hammering the backing store). These tests assert the
value is now clamped via parse_mcp_int (or rejected as a clean -32602
ToolExecutionError) before it reaches the DB.

Reuses the heavy-dependency stubbing harness from test_mcp_data_endpoints.py.
"""

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
_drop_stale_module(
    'utils.retrieval.hybrid',
    os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'hybrid.py'),
)
_drop_stale_module('models.memories', os.path.join(_BACKEND_DIR, 'models', 'memories.py'))
_drop_stale_module('models.conversation_enums', os.path.join(_BACKEND_DIR, 'models', 'conversation_enums.py'))
_drop_stale_module('models.mcp_api_key', os.path.join(_BACKEND_DIR, 'models', 'mcp_api_key.py'))

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
sys.modules['utils.apps'].update_personas_async = MagicMock()
sys.modules['utils.executors'].db_executor = MagicMock()
sys.modules['utils.executors'].postprocess_executor = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})

from routers import mcp_sse as sse  # noqa: E402

UID = "user-1"


class TestGetXPostsLimitClamp:
    @patch('routers.mcp_sse.x_posts_db')
    def test_negative_limit_clamped_to_minimum(self, mock_db):
        mock_db.get_x_posts.return_value = []
        sse.execute_tool(UID, 'get_x_posts', {'limit': -5})
        _, kwargs = mock_db.get_x_posts.call_args
        # Without the fix, raw -5 reaches Firestore.
        assert kwargs['limit'] == 1

    @patch('routers.mcp_sse.x_posts_db')
    def test_huge_limit_clamped_to_maximum(self, mock_db):
        mock_db.get_x_posts.return_value = []
        sse.execute_tool(UID, 'get_x_posts', {'limit': 100000})
        _, kwargs = mock_db.get_x_posts.call_args
        assert kwargs['limit'] == 500

    @patch('routers.mcp_sse.x_posts_db')
    def test_non_integer_limit_rejected(self, mock_db):
        mock_db.get_x_posts.return_value = []
        with pytest.raises(sse.ToolExecutionError) as e:
            sse.execute_tool(UID, 'get_x_posts', {'limit': 'not-an-int'})
        assert e.value.code == -32602
        mock_db.get_x_posts.assert_not_called()

    @patch('routers.mcp_sse.x_posts_db')
    def test_default_limit_when_absent(self, mock_db):
        mock_db.get_x_posts.return_value = []
        sse.execute_tool(UID, 'get_x_posts', {})
        _, kwargs = mock_db.get_x_posts.call_args
        assert kwargs['limit'] == 50


class TestSearchXPostsLimitClamp:
    @patch('routers.mcp_sse.x_posts_db')
    @patch('routers.mcp_sse.vector_db')
    def test_negative_limit_clamped_to_minimum(self, mock_vector_db, mock_x_posts_db):
        mock_vector_db.find_similar_x_posts.return_value = []
        sse.execute_tool(UID, 'search_x_posts', {'query': 'hi', 'limit': -5})
        _, kwargs = mock_vector_db.find_similar_x_posts.call_args
        # Without the fix, raw -5 reaches the vector DB.
        assert kwargs['limit'] == 1


class TestSearchConversationsLimitClamp:
    @patch('routers.mcp_sse.conversations_db')
    @patch('routers.mcp_sse.vector_db')
    def test_negative_limit_clamped_to_minimum(self, mock_vector_db, mock_conversations_db):
        mock_vector_db.query_vectors.return_value = []
        sse.execute_tool(UID, 'search_conversations', {'query': 'hi', 'limit': -5})
        _, kwargs = mock_vector_db.query_vectors.call_args
        # query_vectors is called with k=limit; without the fix raw -5 reaches it.
        assert kwargs['k'] == 1
