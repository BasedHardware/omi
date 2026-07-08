"""Unit tests for the search_conversations MCP endpoint poison-page guard.

A single malformed conversation record (e.g. a category not in CategoryEnum)
must not 500 the whole /v1/mcp/conversations/search page. The endpoint
validates each record into SimpleConversation inline and skips the bad ones.

Follows the stub harness in test_mcp_search_memories.py so routers.mcp can be
imported without its heavy database/util dependencies.
"""

from unittest.mock import patch, MagicMock
import os
import sys
from types import ModuleType

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
    'utils.mcp_data',
    'utils.mcp_memories',
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
# redact_conversations_for_list mutates in place and returns None — keep it a harmless no-op.
sys.modules['utils.conversations.render'].redact_conversations_for_list = MagicMock(return_value=None)
sys.modules['utils.conversations.render'].populate_speaker_names = MagicMock(return_value=None)
sys.modules['utils.log_sanitizer'].sanitize_pii = MagicMock(side_effect=lambda x: x)
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})

from routers.mcp import search_conversations, SimpleConversation


def _valid_conversation(conv_id='conv-good'):
    return {
        'id': conv_id,
        'started_at': '2026-06-01T10:00:00+00:00',
        'finished_at': '2026-06-01T10:30:00+00:00',
        'structured': {
            'title': 'Standup',
            'overview': 'Daily standup notes',
            'category': 'business',  # valid CategoryEnum member
        },
        'language': 'en',
    }


def _malformed_conversation(conv_id='conv-bad'):
    # category 'totally-not-a-category' is NOT in CategoryEnum -> SimpleConversation
    # validation fails. On the unguarded endpoint this poisons the whole page (500).
    return {
        'id': conv_id,
        'started_at': '2026-06-01T11:00:00+00:00',
        'finished_at': '2026-06-01T11:30:00+00:00',
        'structured': {
            'title': 'Mystery',
            'overview': 'Has a bogus category',
            'category': 'totally-not-a-category',
        },
        'language': 'en',
    }


class TestSearchConversationsPoisonPage:
    @patch('routers.mcp.conversations_db')
    @patch('routers.mcp.vector_db')
    def test_malformed_record_skipped_returns_only_valid(self, mock_vector_db, mock_conversations_db):
        mock_vector_db.query_vectors.return_value = ['conv-good', 'conv-bad']
        mock_conversations_db.get_conversations_by_id.return_value = [
            _valid_conversation('conv-good'),
            _malformed_conversation('conv-bad'),
        ]

        result = search_conversations(query="standup", limit=10, uid="user-1")

        # Only the valid record survives; the bad one is skipped, not a 500.
        assert len(result) == 1
        assert isinstance(result[0], SimpleConversation)
        assert result[0].id == 'conv-good'

    @patch('routers.mcp.conversations_db')
    @patch('routers.mcp.vector_db')
    def test_all_valid_returns_all(self, mock_vector_db, mock_conversations_db):
        mock_vector_db.query_vectors.return_value = ['conv-a', 'conv-b']
        mock_conversations_db.get_conversations_by_id.return_value = [
            _valid_conversation('conv-a'),
            _valid_conversation('conv-b'),
        ]

        result = search_conversations(query="standup", limit=10, uid="user-1")

        assert [c.id for c in result] == ['conv-a', 'conv-b']
        assert all(isinstance(c, SimpleConversation) for c in result)

    @patch('routers.mcp.conversations_db')
    @patch('routers.mcp.vector_db')
    def test_empty_when_no_vector_hits(self, mock_vector_db, mock_conversations_db):
        mock_vector_db.query_vectors.return_value = []

        result = search_conversations(query="nothing", limit=10, uid="user-1")

        assert result == []
        mock_conversations_db.get_conversations_by_id.assert_not_called()
