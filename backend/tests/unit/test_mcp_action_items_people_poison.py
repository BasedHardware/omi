"""Unit test for MCP action items and people poison-page guards (routers/mcp.py).

Malformed action item or person documents (e.g. missing required description or name)
must not cause an unhandled ResponseValidationError (HTTP 500) that poisons the entire
REST list page for the user.

Heavy dependencies are stubbed following the proven pattern in test_mcp_conversations_poison.py.
"""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import ast
import inspect
import os
import sys
from types import ModuleType, SimpleNamespace

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
    'database.mcp_conversation_pages',
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

from routers import mcp as rest  # noqa: E402
from routers.mcp import SimpleActionItem, SimplePerson  # noqa: E402

NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def _response():
    return SimpleNamespace(headers={})


class TestGetActionItemsPoisonPage:
    """One malformed action item record must not 500 the /v1/mcp/action-items page."""

    def test_get_action_items_skips_malformed_records(self):
        records = [
            {"id": "ai-1", "description": "Review PR", "completed": False, "created_at": NOW},
            {"id": "ai-corrupted-no-desc"},  # Missing required 'description'
            {"description": "No id"},  # Missing required 'id'
            {"id": "ai-2", "description": "Submit report", "completed": True, "created_at": NOW},
        ]
        with patch.object(
            rest.mcp_action_item_handlers,
            "action_items_list_page_core",
            return_value=(records, "cursor-123"),
        ):
            resp = _response()
            result = rest.get_action_items(resp, uid=UID)

        assert len(result) == 2
        assert [item.id for item in result] == ["ai-1", "ai-2"]
        assert result[0].description == "Review PR"
        assert result[1].description == "Submit report"
        assert resp.headers.get("X-Next-Cursor") == "cursor-123"

    def test_get_action_items_sync_feed_skips_malformed_records(self):
        records = [
            {"id": "ai-sync-1", "description": "Sync task", "completed": False, "updated_at": NOW},
            {"id": "ai-sync-bad", "description": None},  # None description fails Pydantic validation
        ]
        with patch.object(
            rest.mcp_action_item_handlers,
            "action_items_sync_page_core",
            return_value=(records, "next-sync-cursor"),
        ):
            resp = _response()
            result = rest.get_action_items(resp, updated_since="2026-06-01T00:00:00Z", uid=UID)

        assert len(result) == 1
        assert result[0].id == "ai-sync-1"
        assert resp.headers.get("X-Next-Cursor") == "next-sync-cursor"

    def test_get_action_items_all_valid(self):
        records = [
            {"id": "ai-1", "description": "Item 1", "completed": False},
            {"id": "ai-2", "description": "Item 2", "completed": True},
        ]
        with patch.object(
            rest.mcp_action_item_handlers,
            "action_items_list_page_core",
            return_value=(records, None),
        ):
            result = rest.get_action_items(_response(), uid=UID)

        assert len(result) == 2
        assert [item.id for item in result] == ["ai-1", "ai-2"]


class TestSearchActionItemsPoisonPage:
    """Malformed search hits must not 500 the /v1/mcp/action-items/search endpoint."""

    def test_search_action_items_skips_malformed_hits(self):
        hits = [
            {"id": "ai-search-1", "description": "Buy groceries", "completed": False},
            {"id": "ai-search-broken"},  # Missing description
            None,  # Non-dict row
        ]
        with patch.object(
            rest,
            "_call_action_item_handler",
            return_value={"action_items": hits},
        ):
            result = rest.search_action_items("groceries", uid=UID)

        assert len(result) == 1
        assert result[0].id == "ai-search-1"
        assert result[0].description == "Buy groceries"


class TestGetPeoplePoisonPage:
    """One malformed person record must not 500 the /v1/mcp/people endpoint."""

    def test_get_people_skips_malformed_records(self):
        records = [
            {"id": "person-1", "name": "Bob", "speech_sample_transcripts": ["Hello world"]},
            {"id": "person-corrupted"},  # Missing required 'name'
            {"name": "No ID person"},  # Missing required 'id'
            {"id": "person-2", "name": "Charlie", "speech_sample_transcripts": []},
        ]
        fake_spec = SimpleNamespace(handler=MagicMock(return_value={"people": records}))
        with patch.object(rest, "spec_for_tool", return_value=fake_spec):
            result = rest.get_people(uid=UID)

        assert len(result) == 2
        assert [p.id for p in result] == ["person-1", "person-2"]
        assert result[0].name == "Bob"
        assert result[1].name == "Charlie"

    def test_get_people_all_valid(self):
        records = [
            {"id": "p-1", "name": "Alice"},
            {"id": "p-2", "name": "David"},
        ]
        fake_spec = SimpleNamespace(handler=MagicMock(return_value={"people": records}))
        with patch.object(rest, "spec_for_tool", return_value=fake_spec):
            result = rest.get_people(uid=UID)

        assert len(result) == 2
        assert [p.id for p in result] == ["p-1", "p-2"]


class TestASTValidationGuards:
    """Verify statically that routers/mcp.py validates records before returning them."""

    def test_action_items_and_people_use_model_validate(self):
        source = inspect.getsource(rest)
        tree = ast.parse(source)

        handler_names = {"get_action_items", "search_action_items", "get_people"}
        validated_funcs = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in handler_names:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        # Matches either _validate_simple_action_items(...) or model_validate(...)
                        if isinstance(sub.func, ast.Name) and "validate" in sub.func.id.lower():
                            validated_funcs.add(node.name)
                        elif isinstance(sub.func, ast.Attribute) and "validate" in sub.func.attr.lower():
                            validated_funcs.add(node.name)

        assert (
            validated_funcs == handler_names
        ), f"Expected all handlers to call validation: {handler_names - validated_funcs}"
