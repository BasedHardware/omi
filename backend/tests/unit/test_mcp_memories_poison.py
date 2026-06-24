"""Unit tests for the get_memories MCP endpoint poison-page guard.

A single malformed memory record (e.g. a category not in MemoryCategory) must
not 500 the whole /v1/mcp/memories page via FastAPI's response_model coercion.
get_memories validates each record into CleanerMemory in the function body and
skips the bad ones, returning only the valid memories.

Follows the import harness in test_mcp_search_memories.py.
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

from routers.mcp import get_memories, CleanerMemory


class TestGetMemoriesPoisonPage:
    """One malformed record must be skipped, not 500 the whole page."""

    def _valid(self, memory_id='mem-good', content='valid memory', category='other'):
        return {'id': memory_id, 'content': content, 'category': category, 'is_locked': False}

    def _malformed(self, memory_id='mem-bad', content='poison', category='health'):
        # 'health' is NOT a MemoryCategory member, and CleanerMemory has no
        # legacy-mapping validator -> CleanerMemory.model_validate raises.
        return {'id': memory_id, 'content': content, 'category': category, 'is_locked': False}

    @patch('routers.mcp.collect_filtered_memories')
    @patch('routers.mcp.memories_db')
    def test_malformed_record_is_skipped(self, mock_memories_db, mock_collect):
        mock_collect.return_value = {'memories': [self._valid(), self._malformed()]}

        result = get_memories(uid='user-1')

        # Only the valid memory survives; the bad-category one is skipped.
        assert len(result) == 1
        assert all(isinstance(m, CleanerMemory) for m in result)
        assert result[0].id == 'mem-good'
        assert result[0].category == 'other'

    @patch('routers.mcp.collect_filtered_memories')
    @patch('routers.mcp.memories_db')
    def test_all_valid_records_returned(self, mock_memories_db, mock_collect):
        mock_collect.return_value = {
            'memories': [
                self._valid('mem-1', 'first', 'other'),
                self._valid('mem-2', 'second', 'work'),
            ]
        }

        result = get_memories(uid='user-1')

        assert len(result) == 2
        assert {m.id for m in result} == {'mem-1', 'mem-2'}

    @patch('routers.mcp.collect_filtered_memories')
    @patch('routers.mcp.memories_db')
    def test_locked_content_truncated_and_still_validated(self, mock_memories_db, mock_collect):
        long_content = 'x' * 200
        locked = {'id': 'mem-lock', 'content': long_content, 'category': 'other', 'is_locked': True}
        mock_collect.return_value = {'memories': [locked]}

        result = get_memories(uid='user-1')

        assert len(result) == 1
        assert isinstance(result[0], CleanerMemory)
        # 70 chars + '...'
        assert result[0].content == ('x' * 70 + '...')
