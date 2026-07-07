from pathlib import Path

from utils.mcp_memories import McpVerifiedAuth, build_mcp_default_memory_read_context
from utils.memory.product_authorization import authorize_memory_external_default_memory_read

ROOT = Path(__file__).resolve().parents[2]


class _GrantStateRead:
    def __init__(self, state):
        self.state = state
        self.reason = 'ok'
        self.source_path = 'users/u1/memory_control/app_key_memory_grants'


def _grant_reader(*, uid, db_client):
    assert uid == 'u1'
    assert db_client == 'fake-db'
    return _GrantStateRead(
        {
            'grants': {
                'mcp': {
                    'apps': {
                        'mcp-app-1': {
                            'keys': {
                                'mcp-key-1': {
                                    'enabled': True,
                                    'scopes': ['memories.read'],
                                    'default_read': True,
                                    'archive_read': False,
                                    'write': False,
                                }
                            }
                        }
                    }
                }
            }
        }
    )


def test_existing_mcp_uid_only_dependency_remains_available():
    dependencies_source = (ROOT / 'dependencies.py').read_text()

    assert 'async def get_uid_from_mcp_api_key' in dependencies_source
    assert 'return user_id' in dependencies_source


def test_mcp_memory_context_fails_closed_without_app_or_key_identity():
    auth = McpVerifiedAuth(uid='u1', scopes=('memories.read',))

    context = build_mcp_default_memory_read_context(auth)
    decision = authorize_memory_external_default_memory_read(
        context,
        db_client='fake-db',
        read_app_key_grants_state=_grant_reader,
    )

    assert decision.allowed is False
    assert decision.reason == 'missing_app_or_key_identity'


def test_mcp_memory_context_fails_closed_without_verified_memories_read_scope():
    auth = McpVerifiedAuth(uid='u1', app_id='mcp-app-1', key_id='mcp-key-1', scopes=())

    context = build_mcp_default_memory_read_context(auth)
    decision = authorize_memory_external_default_memory_read(
        context,
        db_client='fake-db',
        read_app_key_grants_state=_grant_reader,
    )

    assert decision.allowed is False
    assert decision.reason == 'missing_authenticated_scope_memories.read'


def test_valid_injected_mcp_context_composes_with_stored_default_read_grant_without_archive():
    auth = McpVerifiedAuth(uid='u1', app_id='mcp-app-1', key_id='mcp-key-1', scopes=('memories.read',))
    context = build_mcp_default_memory_read_context(auth)

    decision = authorize_memory_external_default_memory_read(
        context,
        db_client='fake-db',
        read_app_key_grants_state=_grant_reader,
    )

    assert decision.allowed is True
    assert decision.context.consumer == 'mcp'
    assert decision.context.surface == 'mcp_default_memory_read'
    assert decision.policy is not None
    assert decision.policy.app_has_default_memory_grant is True
    assert decision.policy.archive_capability is False
    assert decision.reason == 'ok'


def test_mcp_routes_advertise_memories_read_and_wire_memory_context_only_on_memory_search_paths():
    rest_source = (ROOT / 'routers' / 'mcp.py').read_text()
    sse_source = (ROOT / 'routers' / 'mcp_sse.py').read_text()

    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' in rest_source
    assert 'MEMORIES_READ_SECURITY = [{"type": "oauth2", "scopes": ["memories.read"]}]' in sse_source
    assert 'auth_context: Optional[ProductAuthorizationContext] = None' in sse_source
    assert 'authenticate_api_key_auth_context' in sse_source
    assert 'authorize_memory_external_default_memory_read(auth_context, db_client=db)' in sse_source
    assert 'get_mcp_memory_default_memory_read_context' in rest_source
    assert 'build_mcp_default_memory_read_context' in sse_source
