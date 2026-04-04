"""Unit tests for the new MCP data endpoints/tools: action items, goals, chat,
people, screen activity, and daily summaries.

Tests both the REST handlers (routers/mcp.py) and the MCP tool dispatch
(routers/mcp_sse.py) with mocked database calls, following the heavy-dep
stubbing pattern in test_mcp_search_memories.py.
"""

from datetime import datetime, timezone
import json
from unittest.mock import patch, MagicMock
import os
import sys
from types import ModuleType, SimpleNamespace

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
    'database.mcp_oauth',
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

if not isinstance(getattr(sys.modules['database._client'], '__file__', None), str):
    sys.modules['database._client'].document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
sys.modules['dependencies'].get_uid_from_mcp_api_key = MagicMock(return_value='user-1')
sys.modules['dependencies'].get_current_user_id = MagicMock(return_value='user-1')
sys.modules['utils.other.endpoints'].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
sys.modules['utils.other.endpoints'].with_rate_limit_context = MagicMock(
    side_effect=lambda dependency, _policy: dependency
)
sys.modules['utils.other.endpoints'].check_rate_limit_inline = MagicMock()
sys.modules['utils.other.endpoints'].check_api_key_rate_limit = MagicMock()
sys.modules['utils.apps'].update_personas_async = MagicMock()
sys.modules['utils.executors'].db_executor = MagicMock()
sys.modules['utils.executors'].postprocess_executor = MagicMock()
sys.modules['utils.llm.memories'].identify_category_for_memory = MagicMock(return_value='other')
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})
# AutoMockModule invents MagicMocks for missing attrs; those cannot be caught.
# Reuse an existing Exception subclass if another test already installed one.
_api_core_exc = sys.modules['google.api_core.exceptions']
_existing_fp = getattr(_api_core_exc, 'FailedPrecondition', None)
if not (isinstance(_existing_fp, type) and issubclass(_existing_fp, BaseException)):
    _api_core_exc.FailedPrecondition = type('FailedPrecondition', (Exception,), {})

from routers import mcp as rest  # noqa: E402
from routers import mcp_sse as sse  # noqa: E402

NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
UID = "user-1"


def test_memory_list_has_one_auth_dependency_and_uses_its_authorized_uid():
    route = next(
        route
        for route in rest.router.routes
        if getattr(route, "path", None) == "/v1/mcp/memories" and "GET" in getattr(route, "methods", set())
    )
    dependency_calls = [dependency.call for dependency in route.dependant.dependencies]
    assert dependency_calls == [rest.get_mcp_memory_default_memory_read_context]
    assert rest.get_uid_from_mcp_api_key not in dependency_calls

    auth_context = SimpleNamespace(uid="auth-user")
    authorization = SimpleNamespace(allowed=True)
    memory_service = MagicMock()
    memory_service.read.return_value = []
    with (
        patch.object(rest, "authorize_memory_external_default_memory_read", return_value=authorization) as authorize,
        patch.object(rest, "pin_memory_system", return_value=rest.MemorySystem.CANONICAL) as pin,
        patch.object(rest, "MemoryService", return_value=memory_service),
    ):
        assert rest.get_memories(auth_context=auth_context) == []

    pin.assert_called_once_with("auth-user", db_client=rest.db)
    authorize.assert_called_once_with(auth_context, db_client=rest.db)
    memory_service.read.assert_called_once_with("auth-user", limit=100, offset=0)


async def _run_blocking_inline(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


class _JsonRequest:
    def __init__(self, body):
        self.headers = {"content-type": "application/json"}
        self.body = body

    async def json(self):
        return self.body

    async def is_disconnected(self):
        return False


class _FormRequest:
    def __init__(self, body):
        self.headers = {"content-type": "application/x-www-form-urlencoded"}
        self.body = body

    async def form(self):
        return self.body


@pytest.mark.asyncio
async def test_token_request_parser_reads_json_body():
    body = {
        'grant_type': 'authorization_code',
        'client_id': 'omi-chatgpt-prod',
        'code': 'omi_code_test',
    }

    assert await sse._get_token_request_data(_JsonRequest(body)) == body


@pytest.mark.asyncio
async def test_token_request_parser_reads_form_body():
    body = {
        'grant_type': 'authorization_code',
        'client_id': 'omi-chatgpt-prod',
        'code': 'omi_code_test',
    }

    assert await sse._get_token_request_data(_FormRequest(body)) == body


def test_sse_tools_list_filters_by_oauth_scopes():
    auth_context = sse.MCPAuthContext(uid=UID, auth_type='oauth', scopes=['memories.read'])
    response, session_id = sse.handle_mcp_message(auth_context, {'id': 1, 'method': 'tools/list'})
    names = {tool['name'] for tool in response['result']['tools']}

    assert session_id is None
    assert 'get_memories' in names
    assert 'search_memories' in names
    assert 'create_memory' not in names
    assert 'get_conversations' not in names


@pytest.mark.asyncio
async def test_sse_post_tools_list_accepts_missing_session_id():
    auth_context = sse.MCPAuthContext(uid=UID, auth_type='oauth', scopes=['memories.read'])
    request = _JsonRequest({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})

    with (
        patch.object(sse, 'run_blocking', side_effect=_run_blocking_inline),
        patch.object(sse, 'authenticate_mcp_request', return_value=auth_context),
    ):
        response = await sse.mcp_streamable_http(request, authorization='Bearer token', accept=None)

    payload = json.loads(response.body)
    names = {tool['name'] for tool in payload['result']['tools']}
    assert response.status_code == 200
    assert 'get_memories' in names


@pytest.mark.asyncio
async def test_sse_post_tools_list_ignores_stale_session_id():
    auth_context = sse.MCPAuthContext(uid=UID, auth_type='oauth', scopes=['memories.read'])
    request = _JsonRequest({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})

    with (
        patch.object(sse, 'run_blocking', side_effect=_run_blocking_inline),
        patch.object(sse, 'authenticate_mcp_request', return_value=auth_context),
    ):
        response = await sse.mcp_streamable_http(
            request,
            authorization='Bearer token',
            mcp_session_id='session-from-another-instance',
            accept=None,
        )

    payload = json.loads(response.body)
    names = {tool['name'] for tool in payload['result']['tools']}
    assert response.status_code == 200
    assert 'get_memories' in names


@pytest.mark.asyncio
async def test_sse_get_keepalive_uses_transport_rate_limit():
    auth_context = sse.MCPAuthContext(uid=UID, auth_type='oauth', scopes=['memories.read'])
    request = _JsonRequest({})

    with (
        patch.object(sse, 'run_blocking', side_effect=_run_blocking_inline),
        patch.object(sse, 'authenticate_mcp_request', return_value=auth_context),
        patch.object(sse, 'check_rate_limit_inline') as check_rate_limit,
    ):
        response = await sse.mcp_sse_get(request, authorization='Bearer token')

    assert response.status_code == 200
    check_rate_limit.assert_called_once_with(UID, 'mcp:sse')


def test_sse_tool_security_schemes_match_runtime_scope_map():
    for tool in sse.MCP_TOOLS:
        advertised_scopes = tool['securitySchemes'][0]['scopes']
        assert advertised_scopes == [sse.TOOL_REQUIRED_SCOPE[tool['name']]]


def test_sse_tool_call_returns_mcp_auth_challenge_when_scope_missing():
    auth_context = sse.MCPAuthContext(uid=UID, auth_type='oauth', scopes=['memories.read'])
    response, _ = sse.handle_mcp_message(
        auth_context, {'id': 1, 'method': 'tools/call', 'params': {'name': 'create_memory', 'arguments': {}}}
    )

    assert response['error']['code'] == -32003
    assert 'memories.write' in response['error']['data']['_meta']['mcp/www_authenticate']


def test_authorize_redirect_builder_preserves_existing_query():
    redirect_uri = sse._redirect_with_code(
        'https://chatgpt.com/connector_platform_oauth_redirect?client=chatgpt', 'code-1', 's1'
    )
    assert redirect_uri == 'https://chatgpt.com/connector_platform_oauth_redirect?client=chatgpt&code=code-1&state=s1'


def test_authorize_request_accepts_chatgpt_public_client():
    client = {
        'id': 'omi-chatgpt-prod',
        'allowed_redirect_uris': ['https://chatgpt.com/connector_platform_oauth_redirect'],
        'allowed_resources': [sse.MCP_RESOURCE_URL],
        'allowed_scopes': ['memories.read'],
        'token_endpoint_auth_method': 'none',
    }
    with (
        patch('routers.mcp_sse.mcp_oauth_db.get_client', return_value=client),
        patch('routers.mcp_sse.mcp_oauth_db.validate_redirect_uri', return_value=True),
        patch('routers.mcp_sse.mcp_oauth_db.validate_resource', return_value=True),
        patch('routers.mcp_sse.mcp_oauth_db.validate_pkce_challenge', return_value=True),
        patch('routers.mcp_sse.mcp_oauth_db.normalize_scopes', return_value=['memories.read']),
    ):
        validated_client, scopes = sse._validate_authorize_request(
            'code',
            'omi-chatgpt-prod',
            'https://chatgpt.com/connector_platform_oauth_redirect',
            sse.MCP_RESOURCE_URL,
            'memories.read',
            'a' * 64,
            'S256',
        )

    assert validated_client == client
    assert scopes == ['memories.read']


def test_authorize_request_rejects_legacy_omi_client_id():
    with patch('routers.mcp_sse.mcp_oauth_db.get_client', return_value=None):
        with pytest.raises(ValueError, match='Unknown OAuth client'):
            sse._validate_authorize_request(
                'code',
                'omi',
                'https://chatgpt.com/connector_platform_oauth_redirect',
                sse.MCP_RESOURCE_URL,
                'memories.read',
                'a' * 64,
                'S256',
            )


def test_legacy_api_key_helper_rejects_oauth_tokens():
    with patch('routers.mcp_sse.mcp_oauth_db.validate_access_token') as validate_access_token:
        validate_access_token.return_value = {
            'uid': UID,
            'scopes': ['memories.read'],
            'client_id': 'omi',
            'resource': sse.MCP_RESOURCE_URL,
            'grant_id': 'grant-1',
        }

        assert sse.authenticate_api_key('Bearer omi_oat_test') is None


def _action_item(item_id='a1', desc='Email Bob', completed=False, deleted=False, locked=False):
    return {
        'id': item_id,
        'description': desc,
        'completed': completed,
        'created_at': NOW,
        'due_at': NOW,
        'completed_at': None,
        'conversation_id': 'conv-1',
        'deleted': deleted,
        'is_locked': locked,
    }


class TestActionItems:
    @patch('routers.mcp.action_items_db')
    def test_rest_returns_items_and_drops_deleted(self, mock_db):
        mock_db.get_action_items.return_value = [_action_item('a1'), _action_item('a2', deleted=True)]
        result = rest.get_action_items(uid=UID)
        assert [i['id'] for i in result] == ['a1']
        assert result[0]['description'] == 'Email Bob'

    @patch('routers.mcp.action_items_db')
    def test_rest_limit_clamped(self, mock_db):
        mock_db.get_action_items.return_value = []
        rest.get_action_items(limit=99999, uid=UID)
        _, kwargs = mock_db.get_action_items.call_args
        assert kwargs['limit'] == 500

    @patch('routers.mcp_sse.action_items_db')
    def test_tool_dispatch(self, mock_db):
        mock_db.get_action_items.return_value = [_action_item('a1'), _action_item('a2', deleted=True)]
        result = sse.execute_tool(UID, 'get_action_items', {'completed': False})
        assert [i['id'] for i in result['action_items']] == ['a1']

    @patch('routers.mcp_sse.action_items_db')
    def test_tool_rejects_bad_date(self, mock_db):
        with pytest.raises(sse.ToolExecutionError):
            sse.execute_tool(UID, 'get_action_items', {'due_start_date': 'not-a-date'})

    @patch('routers.mcp_sse.action_items_db')
    def test_locked_description_truncated(self, mock_db):
        long_desc = 'x' * 200
        mock_db.get_action_items.return_value = [_action_item('a1', desc=long_desc, locked=True)]
        result = sse.execute_tool(UID, 'get_action_items', {})
        assert result['action_items'][0]['description'].endswith('...')
        assert len(result['action_items'][0]['description']) == 73


class TestGoals:
    @patch('routers.mcp.goals_db')
    def test_rest(self, mock_db):
        mock_db.get_all_goals.return_value = [{'id': 'g1', 'title': 'Ship MCP', 'is_active': True}]
        result = rest.get_goals(uid=UID)
        assert result[0]['title'] == 'Ship MCP'
        mock_db.get_all_goals.assert_called_once_with(UID, include_inactive=False)

    @patch('routers.mcp_sse.goals_db')
    def test_tool(self, mock_db):
        mock_db.get_all_goals.return_value = [{'id': 'g1', 'title': 'Ship MCP'}]
        result = sse.execute_tool(UID, 'get_goals', {'include_inactive': True})
        assert result['goals'][0]['id'] == 'g1'
        mock_db.get_all_goals.assert_called_once_with(UID, include_inactive=True)


class TestChat:
    @patch('routers.mcp.chat_db')
    def test_rest_shapes_message(self, mock_db):
        mock_db.get_messages.return_value = [
            {'id': 'm1', 'text': 'hi', 'sender': 'human', 'type': 'text', 'created_at': NOW, 'files_id': []}
        ]
        result = rest.get_chat_messages(uid=UID)
        assert result == [{'id': 'm1', 'text': 'hi', 'sender': 'human', 'type': 'text', 'created_at': NOW}]

    @patch('routers.mcp_sse.chat_db')
    def test_tool(self, mock_db):
        mock_db.get_messages.return_value = [{'id': 'm1', 'text': 'hi', 'sender': 'ai', 'type': 'text'}]
        result = sse.execute_tool(UID, 'get_chat_messages', {'limit': 10})
        assert result['messages'][0]['sender'] == 'ai'


class TestPeople:
    def _person(self):
        return {
            'id': 'p1',
            'name': 'Bob',
            'created_at': NOW,
            'speech_sample_transcripts': ['hello there', 'how are you'],
            'speech_samples': ['gs://bucket/secret.wav'],
            'speaker_embedding': [0.1, 0.2, 0.3],
        }

    @patch('routers.mcp.users_db')
    def test_rest_drops_audio_and_embeddings(self, mock_db):
        mock_db.get_people.return_value = [self._person()]
        result = rest.get_people(uid=UID)
        assert result[0]['name'] == 'Bob'
        assert 'speech_samples' not in result[0]
        assert 'speaker_embedding' not in result[0]
        assert result[0]['speech_sample_transcripts'] == ['hello there', 'how are you']

    @patch('routers.mcp_sse.users_db')
    def test_tool(self, mock_db):
        mock_db.get_people.return_value = [self._person()]
        result = sse.execute_tool(UID, 'get_people', {})
        assert result['people'][0]['id'] == 'p1'
        assert 'speech_samples' not in result['people'][0]


class TestScreenActivity:
    def _row(self):
        return {
            'id': 's1',
            'timestamp': '2026-06-11 10:00:00.000',
            'appName': 'Cursor',
            'windowTitle': 'mcp.py',
            'ocrText': 'def foo',
            'deviceName': 'Mac Studio',
            'clientDeviceId': 'macos_abc12345',
        }

    @patch('routers.mcp.screen_activity_db')
    def test_rest_rows(self, mock_db):
        mock_db.get_screen_activity.return_value = [self._row()]
        result = rest.get_screen_activity(uid=UID)
        assert result == [
            {
                'id': 's1',
                'timestamp': '2026-06-11 10:00:00.000',
                'app_name': 'Cursor',
                'window_title': 'mcp.py',
                'ocr_text': 'def foo',
                'device_name': 'Mac Studio',
                'client_device_id': 'macos_abc12345',
            }
        ]

    @patch('routers.mcp.screen_activity_db')
    def test_rest_summary_mode(self, mock_db):
        mock_db.get_screen_activity_summary.return_value = {'apps': {'Cursor': {'count': 1}}, 'total_screenshots': 1}
        result = rest.get_screen_activity(summary=True, uid=UID)
        assert result['total_screenshots'] == 1
        mock_db.get_screen_activity.assert_not_called()

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_rows(self, mock_db):
        mock_db.get_screen_activity.return_value = [self._row()]
        result = sse.execute_tool(UID, 'get_screen_activity', {'limit': 5})
        assert result['screen_activity'][0]['app_name'] == 'Cursor'

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_summary(self, mock_db):
        mock_db.get_screen_activity_summary.return_value = {'apps': {}, 'total_screenshots': 0}
        result = sse.execute_tool(UID, 'get_screen_activity', {'summary': True})
        assert result['total_screenshots'] == 0

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_rows_missing_index_returns_typed_error(self, mock_db):
        # Regression for #9189: a missing Firestore index must surface as a typed,
        # actionable ToolExecutionError, not an opaque 500.
        from google.api_core.exceptions import FailedPrecondition

        mock_db.get_screen_activity.side_effect = FailedPrecondition('query requires an index')
        with pytest.raises(sse.ToolExecutionError) as exc_info:
            sse.execute_tool(UID, 'get_screen_activity', {'app': 'Cursor'})
        assert exc_info.value.code == -32009
        assert 'index' in exc_info.value.message.lower()

    @patch('routers.mcp_sse.screen_activity_db')
    def test_tool_summary_missing_index_returns_typed_error(self, mock_db):
        from google.api_core.exceptions import FailedPrecondition

        mock_db.get_screen_activity_summary.side_effect = FailedPrecondition('query requires an index')
        with pytest.raises(sse.ToolExecutionError) as exc_info:
            sse.execute_tool(UID, 'get_screen_activity', {'summary': True})
        assert exc_info.value.code == -32009


class TestDailySummaries:
    @patch('routers.mcp.daily_summaries_db')
    def test_rest(self, mock_db):
        mock_db.get_daily_summaries.return_value = [{'date': '2026-06-11', 'content': 'Worked on MCP'}]
        result = rest.get_daily_summaries(uid=UID)
        assert result[0]['date'] == '2026-06-11'

    @patch('routers.mcp_sse.daily_summaries_db')
    def test_tool(self, mock_db):
        mock_db.get_daily_summaries.return_value = [{'date': '2026-06-11', 'content': 'x'}]
        result = sse.execute_tool(UID, 'get_daily_summaries', {'limit': 5})
        assert result['daily_summaries'][0]['date'] == '2026-06-11'


class TestToolRegistry:
    def test_new_tools_registered(self):
        names = {t['name'] for t in sse.MCP_TOOLS}
        for expected in [
            'get_action_items',
            'get_goals',
            'get_chat_messages',
            'get_people',
            'get_screen_activity',
            'get_daily_summaries',
        ]:
            assert expected in names, f"{expected} missing from MCP_TOOLS"

    def test_every_tool_has_a_dispatch_branch(self):
        # Each declared read-only data tool must dispatch (not fall through to "Unknown tool").
        for name in ['get_action_items', 'get_goals', 'get_chat_messages', 'get_people', 'get_daily_summaries']:
            with (
                patch.object(sse, 'action_items_db'),
                patch.object(sse, 'goals_db'),
                patch.object(sse, 'chat_db'),
                patch.object(sse, 'users_db'),
                patch.object(sse, 'daily_summaries_db'),
            ):
                try:
                    sse.execute_tool(UID, name, {})
                except sse.ToolExecutionError as e:
                    assert 'Unknown tool' not in e.message
