"""Unit tests for the MCP SSE get_conversations tool branch limit/offset clamping.

The get_conversations dispatch branch in routers/mcp_sse.py previously read
``limit``/``offset`` raw from the tool arguments and passed them straight to
``conversations_db.get_conversations(...)``. A negative or huge value therefore
reached Firestore unguarded (negative offset -> 500), unlike every sibling
branch which clamps via ``parse_mcp_int``. These tests drive the tool branch
directly and assert the values handed to the DB are clamped into range.

Follows the heavy-dep stubbing pattern used in test_mcp_data_endpoints.py.
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


def _offset_passed_to_db(mock_db):
    """Return the offset positionally handed to conversations_db.get_conversations."""
    args, kwargs = mock_db.get_conversations.call_args
    if 'offset' in kwargs:
        return kwargs['offset']
    # Signature: get_conversations(user_id, limit, offset, ...)
    return args[2]


def _limit_passed_to_db(mock_db):
    args, kwargs = mock_db.get_conversations.call_args
    if 'limit' in kwargs:
        return kwargs['limit']
    return args[1]


class TestGetConversationsClamp:
    @patch('routers.mcp_sse.conversations_db')
    def test_negative_offset_is_clamped_not_passed_to_firestore(self, mock_db):
        mock_db.get_conversations.return_value = []
        # Drive the get_conversations tool branch with a negative offset.
        sse.execute_tool(UID, 'get_conversations', {'offset': -5})
        # A negative offset must never reach Firestore (would 500).
        assert _offset_passed_to_db(mock_db) >= 0
        assert _offset_passed_to_db(mock_db) == 0

    @patch('routers.mcp_sse.conversations_db')
    def test_negative_limit_is_clamped_to_minimum(self, mock_db):
        mock_db.get_conversations.return_value = []
        sse.execute_tool(UID, 'get_conversations', {'limit': -5})
        assert _limit_passed_to_db(mock_db) == 1

    @patch('routers.mcp_sse.conversations_db')
    def test_huge_offset_is_clamped_to_maximum(self, mock_db):
        mock_db.get_conversations.return_value = []
        sse.execute_tool(UID, 'get_conversations', {'offset': 10_000_000})
        assert _offset_passed_to_db(mock_db) == 100000

    @patch('routers.mcp_sse.conversations_db')
    def test_huge_limit_is_clamped_to_maximum(self, mock_db):
        mock_db.get_conversations.return_value = []
        sse.execute_tool(UID, 'get_conversations', {'limit': 99999})
        assert _limit_passed_to_db(mock_db) == 500

    @patch('routers.mcp_sse.conversations_db')
    def test_non_integer_limit_raises_clean_invalid_params(self, mock_db):
        mock_db.get_conversations.return_value = []
        with pytest.raises(sse.ToolExecutionError) as exc:
            sse.execute_tool(UID, 'get_conversations', {'limit': 'not-an-int'})
        # Clean JSON-RPC -32602 (invalid params) instead of a 500.
        assert exc.value.code == -32602
