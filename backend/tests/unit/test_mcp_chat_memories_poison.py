"""Unit test for MCP chat and memories poison-page guards (routers/mcp.py).

Malformed chat message or memory documents (e.g. missing required text/sender or content/category)
must not cause an unhandled ResponseValidationError (HTTP 500) that poisons the entire
REST list page for the user.

Heavy dependencies are stubbed following the proven pattern in test_mcp_action_items_people_poison.py.
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

rest = None
SimpleChatMessage = None
CleanerMemory = None
SearchedMemory = None


def _setup_stubs_and_import():
    global rest, SimpleChatMessage, CleanerMemory, SearchedMemory
    if rest is not None:
        return rest

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
    sys.modules['dependencies'].get_mcp_memory_default_memory_read_context = MagicMock()
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

    from routers import mcp as _mcp

    rest = _mcp
    SimpleChatMessage = _mcp.SimpleChatMessage
    CleanerMemory = _mcp.CleanerMemory
    SearchedMemory = _mcp.SearchedMemory
    return rest


def setup_module():
    _setup_stubs_and_import()


NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def _response():
    return SimpleNamespace(headers={})


def _auth_context():
    ctx = MagicMock()
    ctx.uid = UID
    return ctx


class TestGetChatMessagesPoisonPage:
    """One malformed chat message record must not 500 the /v1/mcp/chat page."""

    def test_get_chat_messages_skips_malformed_records(self):
        records = [
            {"id": "msg-1", "text": "Hello there", "sender": "user", "created_at": NOW},
            {"id": "msg-corrupted-no-text", "sender": "ai"},  # Missing required 'text'
            {"id": "msg-corrupted-none-text", "text": None, "sender": "ai"},  # None 'text' fails
            {"id": "msg-corrupted-no-sender", "text": "Who sent this?"},  # Missing required 'sender'
            {"text": "No ID message", "sender": "user"},  # Missing required 'id'
            None,  # Non-dict row
            {"id": "msg-2", "text": "General Kenobi!", "sender": "ai", "created_at": NOW},
        ]
        with patch.object(
            rest,
            "_call_tool_handler",
            return_value={"messages": records, "next_cursor": "chat-cursor-xyz"},
        ):
            resp = _response()
            result = rest.get_chat_messages(resp, uid=UID)

        assert len(result) == 2
        assert [msg["id"] for msg in result] == ["msg-1", "msg-2"]
        assert result[0]["text"] == "Hello there"
        assert result[1]["text"] == "General Kenobi!"
        assert resp.headers.get("X-Next-Cursor") == "chat-cursor-xyz"

    def test_get_chat_messages_all_valid(self):
        records = [
            {"id": "m-1", "text": "Msg 1", "sender": "user"},
            {"id": "m-2", "text": "Msg 2", "sender": "ai"},
        ]
        with patch.object(
            rest,
            "_call_tool_handler",
            return_value={"messages": records},
        ):
            resp = _response()
            result = rest.get_chat_messages(resp, uid=UID)

        assert len(result) == 2
        assert [m["id"] for m in result] == ["m-1", "m-2"]


class TestGetMemoriesPoisonPage:
    """One malformed memory document must not 500 the /v1/mcp/memories page."""

    def test_get_memories_skips_malformed_records(self):
        records = [
            {"id": "mem-1", "content": "Likes matcha latte", "category": "habits"},
            {"id": "mem-no-content", "category": "habits"},  # Missing required 'content'
            {"id": "mem-none-content", "content": None, "category": "habits"},  # None 'content'
            {"id": "mem-invalid-cat", "content": "Test", "category": "non_existent_category_xyz"},  # Bad category enum
            {"content": "No id memory", "category": "habits"},  # Missing required 'id'
            None,  # Non-dict
            {"id": "mem-2", "content": "Birthday is October 15", "category": "interesting"},
        ]
        with patch.object(
            rest.mcp_memory_handlers,
            "memories_page_core",
            return_value={"memories": records, "next_cursor": "mem-cursor-abc"},
        ), patch.object(
            rest,
            "authorize_memory_external_default_memory_read",
            return_value=SimpleNamespace(allowed=True),
        ):
            resp = _response()
            result = rest.get_memories(resp, auth_context=_auth_context())

        assert len(result) == 2
        assert [mem["id"] for mem in result] == ["mem-1", "mem-2"]
        assert result[0]["content"] == "Likes matcha latte"
        assert result[1]["content"] == "Birthday is October 15"
        assert resp.headers.get("X-Next-Cursor") == "mem-cursor-abc"

    def test_get_memories_all_valid(self):
        records = [
            {"id": "mem-a", "content": "Fact A", "category": "work"},
            {"id": "mem-b", "content": "Fact B", "category": "hobbies"},
        ]
        with patch.object(
            rest.mcp_memory_handlers,
            "memories_page_core",
            return_value={"memories": records},
        ), patch.object(
            rest,
            "authorize_memory_external_default_memory_read",
            return_value=SimpleNamespace(allowed=True),
        ):
            resp = _response()
            result = rest.get_memories(resp, auth_context=_auth_context())

        assert len(result) == 2
        assert [mem["id"] for mem in result] == ["mem-a", "mem-b"]


class TestSearchMemoriesPoisonPage:
    """One malformed searched memory hit must not 500 the /v1/mcp/memories/search endpoint."""

    def test_search_memories_skips_malformed_hits(self):
        hits = [
            {"id": "hit-1", "content": "Favorite food is sushi", "category": "habits", "relevance_score": 0.95},
            {"id": "hit-no-score", "content": "Sushi lover", "category": "habits"},  # Missing relevance_score
            {"id": "hit-bad-cat", "content": "Sushi", "category": "invalid_category", "relevance_score": 0.8},
            {"id": "hit-no-content", "category": "habits", "relevance_score": 0.7},  # Missing content
            None,
            {"id": "hit-2", "content": "Eats ramen on Tuesdays", "category": "lifestyle", "relevance_score": 0.88},
        ]
        with patch.object(
            rest,
            "_call_tool_handler",
            return_value={"memories": hits},
        ), patch.object(
            rest,
            "authorize_memory_external_default_memory_read",
            return_value=SimpleNamespace(allowed=True),
        ):
            result = rest.search_memories("sushi", auth_context=_auth_context())

        assert len(result) == 2
        assert [h["id"] for h in result] == ["hit-1", "hit-2"]
        assert result[0]["relevance_score"] == 0.95
        assert result[1]["relevance_score"] == 0.88

    def test_search_memories_all_valid(self):
        hits = [
            {"id": "hit-x", "content": "Memory X", "category": "work", "relevance_score": 0.9},
            {"id": "hit-y", "content": "Memory Y", "category": "interests", "relevance_score": 0.75},
        ]
        with patch.object(
            rest,
            "_call_tool_handler",
            return_value={"memories": hits},
        ), patch.object(
            rest,
            "authorize_memory_external_default_memory_read",
            return_value=SimpleNamespace(allowed=True),
        ):
            result = rest.search_memories("query", auth_context=_auth_context())

        assert len(result) == 2
        assert [h["id"] for h in result] == ["hit-x", "hit-y"]


class TestASTValidationGuards:
    """Verify statically that routers/mcp.py validates chat messages and memories before returning them."""

    def test_chat_and_memories_use_validation_guards(self):
        source = inspect.getsource(rest)
        tree = ast.parse(source)

        handler_names = {"get_chat_messages", "get_memories", "search_memories"}
        validated_funcs = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in handler_names:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        if isinstance(sub.func, ast.Name) and "validate" in sub.func.id.lower():
                            validated_funcs.add(node.name)
                        elif isinstance(sub.func, ast.Attribute) and "validate" in sub.func.attr.lower():
                            validated_funcs.add(node.name)

        assert (
            validated_funcs == handler_names
        ), f"Expected all handlers to call validation: {handler_names - validated_funcs}"
