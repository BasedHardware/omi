"""Unit tests for name/email/phone on the MCP user profile (routers/mcp.py).

`/v1/mcp/profile` now augments the cached AI profile with the user's contact
identity (name/email from Firebase Auth, phone from Auth or the phone_numbers
subcollection). Contact lookup must be best-effort: a Firebase/Firestore failure
must NOT break the profile response.

Heavy deps are stubbed following the proven pattern in test_mcp_data_endpoints.py.
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
_drop_stale_module('utils.retrieval.hybrid', os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'hybrid.py'))
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
    'database.phone_calls',
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
sys.modules['utils.other.endpoints'].with_rate_limit_context = MagicMock(
    side_effect=lambda dependency, _policy: dependency
)
sys.modules['utils.apps'].update_personas_async = MagicMock()
sys.modules['utils.executors'].db_executor = MagicMock()
sys.modules['utils.executors'].postprocess_executor = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')

from routers import mcp as rest  # noqa: E402

UID = "user-1"


def _firebase_user(display_name=None, email=None, phone_number=None):
    user = MagicMock()
    user.display_name = display_name
    user.email = email
    user.phone_number = phone_number
    return user


class TestProfileContact:
    @patch('routers.mcp.phone_calls_db')
    @patch('routers.mcp.firebase_auth')
    @patch('routers.mcp.users_db')
    def test_includes_name_email_phone_from_auth(self, mock_users, mock_auth, mock_phone):
        mock_users.get_ai_user_profile.return_value = {'profile_text': 'builds AI', 'data_sources_used': 3}
        mock_auth.get_user.return_value = _firebase_user('Nik Shevchenko', 'nik@example.com', '+15551234567')
        result = rest.get_user_profile(uid=UID)
        assert result.name == 'Nik Shevchenko'
        assert result.email == 'nik@example.com'
        assert result.phone_number == '+15551234567'
        assert result.profile_text == 'builds AI'
        # Auth had a phone, so the subcollection must not be consulted.
        mock_phone.get_phone_numbers.assert_not_called()

    @patch('routers.mcp.phone_calls_db')
    @patch('routers.mcp.firebase_auth')
    @patch('routers.mcp.users_db')
    def test_phone_falls_back_to_subcollection(self, mock_users, mock_auth, mock_phone):
        mock_users.get_ai_user_profile.return_value = {}
        mock_auth.get_user.return_value = _firebase_user('Nik', 'nik@example.com', None)
        mock_phone.get_phone_numbers.return_value = [{'phone_number': '+15559998888'}]
        result = rest.get_user_profile(uid=UID)
        assert result.email == 'nik@example.com'
        assert result.phone_number == '+15559998888'

    @patch('routers.mcp.phone_calls_db')
    @patch('routers.mcp.firebase_auth')
    @patch('routers.mcp.users_db')
    def test_phone_fallback_prefers_primary(self, mock_users, mock_auth, mock_phone):
        mock_users.get_ai_user_profile.return_value = {}
        mock_auth.get_user.return_value = _firebase_user('Nik', 'nik@example.com', None)
        mock_phone.get_phone_numbers.return_value = [
            {'phone_number': '+15550000000', 'is_primary': False},
            {'phone_number': '+15551111111', 'is_primary': True},
        ]
        result = rest.get_user_profile(uid=UID)
        assert result.phone_number == '+15551111111'

    @patch('routers.mcp.phone_calls_db')
    @patch('routers.mcp.firebase_auth')
    @patch('routers.mcp.users_db')
    def test_contact_failure_does_not_break_profile(self, mock_users, mock_auth, mock_phone):
        mock_users.get_ai_user_profile.return_value = {'profile_text': 'still here'}
        mock_auth.get_user.side_effect = RuntimeError("firebase down")
        mock_phone.get_phone_numbers.side_effect = RuntimeError("firestore down")
        result = rest.get_user_profile(uid=UID)
        # Contact lookups failed, but the profile itself still returns cleanly.
        assert result.profile_text == 'still here'
        assert result.name is None
        assert result.email is None
        assert result.phone_number is None

    @patch('routers.mcp.phone_calls_db')
    @patch('routers.mcp.firebase_auth')
    @patch('routers.mcp.users_db')
    def test_empty_strings_become_none(self, mock_users, mock_auth, mock_phone):
        mock_users.get_ai_user_profile.return_value = {}
        mock_auth.get_user.return_value = _firebase_user('', '', '')
        mock_phone.get_phone_numbers.return_value = []
        result = rest.get_user_profile(uid=UID)
        assert result.name is None
        assert result.email is None
        assert result.phone_number is None
