from datetime import datetime, timedelta, timezone
from pathlib import Path
from config.memory_rollout import PASSED, MemoryRolloutCapabilities, MemoryRolloutMode, MemoryRolloutStageGate
from models.memory_search_gateway import SearchMode, SearchVectorHit
from models.product_memory import MemoryTier, ProcessingState
from tests.unit.fixtures.memory_adapter_fakes import (
    FirestoreFake as _FirestoreFake,
    VectorCandidateResult as _VectorCandidateResult,
    enabled_rollout_doc,
    memory_item,
    stored_item as _stored_item,
)
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    assert_legacy_memory_write_allowed_for_default_read_decision,
    legacy_safe_default_read_rollout_decision,
    read_default_read_rollout,
)
from utils.mcp_memories import (
    McpMemoryListResult,
    McpMemorySearchResult,
    list_default_mcp_memories,
    search_default_mcp_memories,
    search_default_mcp_memories_vector,
)


def _legacy_branch_after_canonical(route_contents: str, *, marker: str | None = None) -> str:
    """Return the legacy rollout/guard branch after the canonical early-return block."""
    if marker is None:
        marker = "memory_rollout = read_default_read_rollout(uid=uid, db_client=db, consumer='mcp')"
    return route_contents[route_contents.index(marker) :]


def test_mcp_rest_search_route_wires_app_key_scope_grant_before_memory_vector_adapter_and_legacy_search():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')
    search_route = contents[
        contents.index('@router.get("/v1/mcp/memories/search"') : contents.index('@router.get("/v1/mcp/memories"')
    ]
    context_dependency = (
        'auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context)'
    )
    grant_call = 'authorize_memory_external_default_memory_read(auth_context, db_client=db)'
    uid_assignment = 'uid = auth_context.uid'
    rollout_call = "read_default_read_rollout(uid=uid, db_client=db, consumer='mcp')"
    vector_adapter_call = 'search_default_mcp_memories_vector('
    legacy_safe_call = 'return memory_service.search_mcp(uid, query, limit=limit)'
    assert context_dependency in search_route
    assert grant_call in search_route
    assert uid_assignment in search_route
    assert rollout_call in search_route
    assert vector_adapter_call in search_route
    assert legacy_safe_call in search_route
    assert search_route.index(grant_call) < search_route.index(rollout_call)
    assert search_route.index(grant_call) < search_route.index(vector_adapter_call)
    assert search_route.index(grant_call) < search_route.rindex(legacy_safe_call)
    assert (
        search_route.index(rollout_call)
        < search_route.index(vector_adapter_call)
        < search_route.rindex(legacy_safe_call)
    )


def test_mcp_rest_memory_list_derives_uid_from_single_authorization_context():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')
    profile_route = contents[contents.index('@router.get("/v1/mcp/profile"') : contents.index('class CleanerMemory')]
    list_route = contents[contents.index('@router.get("/v1/mcp/memories"') : contents.index('class SimpleStructured')]
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' in profile_route
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' not in list_route
    assert 'get_mcp_memory_default_memory_read_context' not in profile_route
    assert (
        'auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context)' in list_route
    )
    assert 'uid = auth_context.uid' in list_route


def test_mcp_sse_search_tool_wires_app_key_scope_grant_before_memory_vector_adapter_and_legacy_search():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    search_tool = contents[
        contents.index('elif tool_name == "search_memories":') : contents.index(
            'elif tool_name == "search_conversations":'
        )
    ]
    grant_call = 'authorize_memory_external_default_memory_read(auth_context, db_client=db)'
    rollout_call = "read_default_read_rollout(uid=user_id, db_client=db, consumer='mcp')"
    vector_adapter_call = 'search_default_mcp_memories_vector('
    legacy_call = 'vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)'
    assert 'auth_context: Optional[ProductAuthorizationContext] = None' in contents
    assert 'auth_context=auth_context' in contents
    assert grant_call in search_tool
    assert rollout_call in search_tool
    assert vector_adapter_call in search_tool
    assert legacy_call in search_tool
    assert search_tool.index(grant_call) < search_tool.index(rollout_call)
    assert search_tool.index(grant_call) < search_tool.index(vector_adapter_call)
    assert search_tool.index(grant_call) < search_tool.index(legacy_call)
    assert search_tool.index(rollout_call) < search_tool.index(vector_adapter_call) < search_tool.index(legacy_call)


def test_mcp_sse_get_memories_tool_wires_app_key_scope_grant_before_canonical_memory_branch():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    get_tool = contents[
        contents.index('elif tool_name == "get_memories":') : contents.index('elif tool_name == "create_memory":')
    ]
    grant_call = 'authorize_memory_external_default_memory_read(auth_context, db_client=db)'
    canonical_branch = 'if memory_system == MemorySystem.CANONICAL:'
    legacy_rollout = "read_default_read_rollout(uid=user_id, db_client=db, consumer='mcp')"
    assert grant_call in get_tool
    assert canonical_branch in get_tool
    assert legacy_rollout in get_tool
    # Grant must be checked before the canonical early-return so a legacy key
    # without a persisted memories.read grant cannot list canonical memories.
    assert get_tool.index(grant_call) < get_tool.index(canonical_branch)
    assert get_tool.index(grant_call) < get_tool.index(legacy_rollout)
    # Fail-closed: missing auth context and denied grant must raise before any
    # memory-system access.
    assert 'auth_context is None' in get_tool
    assert 'app_key_grant.allowed' in get_tool


def test_mcp_sse_transport_authenticates_full_mcp_api_key_context_without_inferred_scopes():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    assert (
        'def authenticate_api_key_auth_context(authorization: Optional[str]) -> Optional[ProductAuthorizationContext]:'
        in contents
    )
    assert 'def authenticate_mcp_request(authorization: Optional[str]) -> Optional[MCPAuthContext]:' in contents
    assert 'mcp_api_key_db.get_api_key_auth_result(token)' in contents
    assert 'record_api_key_repairs(key_kind="mcp", operation="auth"' in contents
    assert 'McpVerifiedAuth(' in contents
    assert 'scopes=tuple(user_data.get("scopes") or ())' in contents
    assert 'memory_context=_mcp_memory_context_from_api_key_user_data(user_data)' in contents
    assert 'auth_context = await run_blocking(db_executor, authenticate_mcp_request, authorization)' in contents
    assert 'user_id = auth_context.uid' in contents
    assert (
        'user_id = authenticate_api_key(authorization)'
        not in contents[contents.index('@router.post("/v1/mcp/sse"') : contents.index('@router.get("/v1/mcp/sse"')]
    )


def test_mcp_rest_search_route_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')
    search_route = contents[
        contents.index('@router.get("/v1/mcp/memories/search"') : contents.index('@router.get("/v1/mcp/memories"')
    ]
    assert 'MemoryReadDecision.USE_MEMORY' in search_route
    assert 'MemoryReadDecision.USE_LEGACY_SAFE' in search_route
    assert 'if vector_search_results.read_decision == MemoryReadDecision.USE_MEMORY:' in search_route
    assert 'if vector_search_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:' in search_route
    assert search_route.index(
        'if vector_search_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:'
    ) < search_route.rindex('return memory_service.search_mcp(uid, query, limit=limit)')


def test_mcp_rest_get_route_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')
    get_route = contents[contents.index('@router.get("/v1/mcp/memories"') : contents.index('class SimpleStructured')]
    assert 'list_default_mcp_memories(' in get_route
    assert 'if memory_list_results.read_decision == MemoryReadDecision.USE_MEMORY:' in get_route
    assert 'if memory_list_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:' in get_route
    assert get_route.index("read_default_read_rollout(uid=uid, db_client=db, consumer='mcp')") < get_route.index(
        'list_default_mcp_memories('
    )
    assert get_route.index(
        'if memory_list_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:'
    ) < get_route.index('memories_db.get_memories(')


def test_mcp_sse_search_tool_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    assert 'MemoryReadDecision.USE_MEMORY' in contents
    assert 'MemoryReadDecision.USE_LEGACY_SAFE' in contents
    assert 'if vector_search_results.read_decision == MemoryReadDecision.USE_MEMORY:' in contents
    assert 'if vector_search_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:' in contents
    assert contents.index(
        'if vector_search_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:'
    ) < contents.index('vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)')


def test_mcp_sse_get_tool_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    get_tool = contents[
        contents.index('elif tool_name == "get_memories":') : contents.index('elif tool_name == "create_memory":')
    ]
    assert 'list_default_mcp_memories(' in get_tool
    assert 'if memory_list_results.read_decision == MemoryReadDecision.USE_MEMORY:' in get_tool
    assert 'if memory_list_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:' in get_tool
    assert get_tool.index("read_default_read_rollout(uid=user_id, db_client=db, consumer='mcp')") < get_tool.index(
        'list_default_mcp_memories('
    )
    assert get_tool.index(
        'if memory_list_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:'
    ) < get_tool.index('memories_db.get_memories(')


def test_mcp_rest_write_routes_guard_legacy_mutation_before_side_effects():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    memory_service_py = Path(__file__).resolve().parents[2] / 'utils' / 'memory' / 'memory_service.py'
    contents = mcp_py.read_text(encoding='utf-8')
    service_contents = memory_service_py.read_text(encoding='utf-8')
    guard = 'guard_legacy_memory_write(uid, db_client, consumer=consumer, operation=operation)'
    assert guard in service_contents
    create_route = contents[
        contents.index('@router.post("/v1/mcp/memories"') : contents.index('def _validate_mcp_memory')
    ]
    assert 'pin_memory_system(uid, db_client=db)' in create_route
    assert 'create_external_memory(' in create_route
    assert 'operation="mcp_memory_create"' in create_route
    assert create_route.index('pin_memory_system') < create_route.index('create_external_memory')
    assert 'memories_db.create_memory' in service_contents
    delete_route = contents[
        contents.index('@router.delete("/v1/mcp/memories/{memory_id}"') : contents.index(
            '@router.patch("/v1/mcp/memories/{memory_id}"'
        )
    ]
    assert 'delete_external_memory(' in delete_route
    assert 'operation="mcp_memory_delete"' in delete_route
    edit_route = contents[
        contents.index('@router.patch("/v1/mcp/memories/{memory_id}"') : contents.index('class UserProfile')
    ]
    assert 'update_external_memory_content(' in edit_route
    assert 'operation="mcp_memory_edit"' in edit_route
    assert 'memories_db.edit_memory' in service_contents


def test_mcp_sse_write_tools_guard_legacy_mutation_before_side_effects():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    memory_service_py = Path(__file__).resolve().parents[2] / 'utils' / 'memory' / 'memory_service.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    service_contents = memory_service_py.read_text(encoding='utf-8')
    assert '_canonical_external_write_enabled_or_fail_closed' in service_contents
    assert 'guard_legacy_memory_write(uid, db_client, consumer=consumer, operation=operation)' in service_contents
    create_tool = contents[
        contents.index('elif tool_name == "create_memory":') : contents.index('elif tool_name == "delete_memory":')
    ]
    assert 'create_external_memory(' in create_tool
    assert 'operation="mcp_tool_memory_create"' in create_tool
    assert 'resolve_external_memory_write_context(' in create_tool
    assert 'raise_if_legacy_write_blocked(write_context)' in create_tool
    assert create_tool.index('resolve_external_memory_write_context(') < create_tool.index(
        'identify_category_for_memory'
    )
    assert create_tool.index('raise_if_legacy_write_blocked(write_context)') < create_tool.index(
        'identify_category_for_memory'
    )
    assert 'memories_db.create_memory(user_id, memory_db.model_dump())' not in create_tool
    delete_tool = contents[
        contents.index('elif tool_name == "delete_memory":') : contents.index('elif tool_name == "edit_memory":')
    ]
    assert 'delete_external_memory(' in delete_tool
    assert 'operation="mcp_tool_memory_delete"' in delete_tool
    assert 'memories_db.delete_memory(user_id, memory_id)' not in delete_tool
    edit_tool = contents[
        contents.index('elif tool_name == "edit_memory":') : contents.index('elif tool_name == "get_conversations":')
    ]
    assert 'update_external_memory_content(' in edit_tool
    assert 'operation="mcp_tool_memory_edit"' in edit_tool
    assert 'memories_db.edit_memory(user_id, memory_id, content)' not in edit_tool


_MCP_QUOTE_TEXT = 'User prefers deterministic MCP memory reads.'


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    return memory_item(
        memory_id, tier=tier, now=now, captured_at=captured_at, content=content, quote_text=_MCP_QUOTE_TEXT, **overrides
    )


def _enabled_rollout_doc(uid='u1'):
    return enabled_rollout_doc(uid, grant_consumer='mcp')


def _read_capabilities(uid='u1', *, enabled=True):
    return MemoryRolloutCapabilities(
        uid=uid,
        mode=MemoryRolloutMode.read if enabled else MemoryRolloutMode.off,
        legacy_only=not enabled,
        shadow_artifacts_enabled=enabled,
        memory_writes_enabled=enabled,
        memory_reads_enabled=enabled,
        legacy_reads_authoritative=not enabled,
        account_generation=3,
    )


def test_mcp_default_memory_rollout_reader_derives_capability_and_default_grant_from_memory_control_state():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert decision.rollout_capabilities.memory_reads_enabled is True
    assert decision.app_has_default_memory_grant is True
    assert decision.archive_capability is False
    assert decision.source_path == 'users/u1/memory_control/state'


def test_mcp_legacy_write_guard_blocks_memory_and_shadow_reads_but_preserves_disabled_legacy_behavior():
    enabled_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled_decision, operation='mcp_memory_create'
    )
    assert blocked.allowed is False
    assert blocked.status_code == 409
    assert blocked.detail['consumer'] == 'mcp'
    assert blocked.detail['read_decision'] == MemoryReadDecision.USE_MEMORY.value
    missing_decision = read_default_read_rollout(uid='u1', db_client=_FirestoreFake(), consumer='mcp')
    missing_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        missing_decision, operation='mcp_memory_delete'
    )
    assert missing_blocked.allowed is False
    assert missing_blocked.detail['reason'] == 'memory_default_read_legacy_write_blocked'
    shadow_doc = _enabled_rollout_doc() | {
        'mode': MemoryRolloutMode.shadow.value,
        'fallback_projection_ready': False,
        'stage_gates': {MemoryRolloutStageGate.shadow.value: PASSED},
    }
    shadow_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': shadow_doc}), consumer='mcp'
    )
    shadow_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        shadow_decision, operation='mcp_memory_edit'
    )
    assert shadow_decision.read_decision == MemoryReadDecision.SHADOW_ONLY
    assert shadow_blocked.allowed is False
    disabled_doc = _enabled_rollout_doc() | {'mode': MemoryRolloutMode.off.value, 'grants': {}}
    disabled_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': disabled_doc}), consumer='mcp'
    )
    allowed = assert_legacy_memory_write_allowed_for_default_read_decision(
        disabled_decision, operation='mcp_memory_edit'
    )
    assert allowed.allowed is True


def test_mcp_default_memory_rollout_reader_fails_closed_for_missing_malformed_or_missing_grant_without_memory_reads():
    missing = _FirestoreFake()
    assert read_default_read_rollout(uid='u1', db_client=missing, consumer='mcp').memory_default_mcp_enabled is False
    assert missing.document_get_paths == ['users/u1/memory_control/state']
    assert missing.collection_paths == []
    malformed = _FirestoreFake(
        {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}}
    )
    malformed_decision = read_default_read_rollout(uid='u1', db_client=malformed, consumer='mcp')
    assert malformed_decision.memory_default_mcp_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []
    no_grant = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'mcp': {}}}})
    no_grant_decision = read_default_read_rollout(uid='u1', db_client=no_grant, consumer='mcp')
    assert no_grant_decision.rollout_capabilities.memory_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.memory_default_mcp_enabled is False
    assert no_grant.collection_paths == []


def test_mcp_default_memory_memory_adapter_uses_product_search_when_read_rollout_enabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )
    results = search_default_mcp_memories(
        uid='u1', query='coffee', limit=10, db_client=db_client, rollout_capabilities=_read_capabilities(), now=now
    )
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all((item['category'] == 'other' for item in results))
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'mcp' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_mcp_default_memory_adapter_excludes_pending_admission_text():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    pending = _memory_item(
        'pending-explicit',
        now=now,
        content='coffee pending explicit memory',
        processing_state=ProcessingState.pending,
    )
    db_client = _FirestoreFake({f'users/u1/memory_items/{pending.memory_id}': _stored_item(pending)})

    results = search_default_mcp_memories(
        uid='u1', query='coffee', limit=10, db_client=db_client, rollout_capabilities=_read_capabilities(), now=now
    )

    assert results == []


def test_mcp_default_memory_memory_adapter_returns_none_when_rollout_or_default_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    assert (
        search_default_mcp_memories(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(enabled=False),
            now=now,
        )
        is None
    )
    assert (
        search_default_mcp_memories(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(),
            app_has_default_memory_grant=False,
            now=now,
        )
        is None
    )
    assert db_client.collection_paths == []


def test_mcp_vector_adapter_uses_hydrated_vector_service_and_preserves_ranking_without_archive_default():
    now = datetime.now(timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(
            [
                SearchVectorHit(
                    memory_id='archive',
                    score=0.99,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid=archive.uid,
                    account_generation=archive.account_generation,
                    item_revision=archive.item_revision,
                    source_commit_id=archive.source_commit_id,
                    content_hash=archive.content_hash,
                ),
                SearchVectorHit(
                    memory_id='long-term',
                    score=0.88,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid=long_term.uid,
                    account_generation=long_term.account_generation,
                    item_revision=long_term.item_revision,
                    source_commit_id=long_term.source_commit_id,
                    content_hash=long_term.content_hash,
                ),
                SearchVectorHit(
                    memory_id='stale-short-term',
                    score=0.77,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid=stale_short_term.uid,
                    account_generation=stale_short_term.account_generation,
                    item_revision=stale_short_term.item_revision,
                    source_commit_id=stale_short_term.source_commit_id,
                    content_hash=stale_short_term.content_hash,
                ),
                SearchVectorHit(
                    memory_id='fresh-short-term',
                    score=0.66,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid=fresh_short_term.uid,
                    account_generation=fresh_short_term.account_generation,
                    item_revision=fresh_short_term.item_revision,
                    source_commit_id=fresh_short_term.source_commit_id,
                    content_hash=fresh_short_term.content_hash,
                ),
            ],
            rejected_count=1,
        )

    result = search_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        vector_query=vector_query,
        required_projection_commit_id='projection-1',
    )
    assert isinstance(result, McpMemorySearchResult)
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    results = result.memories
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert db_client.collection_paths == []
    assert [item['id'] for item in results] == ['long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.88, 0.66]
    assert all((item['memory_default_memory'] is True for item in results))
    assert all((item['archive_default_visible'] is False for item in results))
    assert all((item['policy']['consumer'] == 'mcp' for item in results))
    assert all((item['policy']['archive_capability'] is False for item in results))


def test_mcp_vector_adapter_returns_explicit_denial_before_vector_or_memory_reads_when_rollout_or_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    vector_calls = []

    def vector_query(*args, **kwargs):
        vector_calls.append((args, kwargs))
        return _VectorCandidateResult([])

    disabled_result = search_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(enabled=False),
        vector_query=vector_query,
    )
    no_grant_result = search_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        app_has_default_memory_grant=False,
        vector_query=vector_query,
    )
    assert disabled_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert disabled_result.memories == []
    assert disabled_result.fallback_reason == 'memory_reads_disabled'
    assert no_grant_result.read_decision == MemoryReadDecision.DENY_MEMORY
    assert no_grant_result.memories == []
    assert no_grant_result.fallback_reason == 'missing_mcp_default_memory_grant'
    assert vector_calls == []
    assert db_client.collection_paths == []


def test_mcp_vector_adapter_preserves_only_explicit_legacy_safe_classification():
    db_client = _FirestoreFake()
    vector_calls = []

    def vector_query(*args, **kwargs):
        vector_calls.append((args, kwargs))
        return _VectorCandidateResult([])

    result = search_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=legacy_safe_default_read_rollout_decision(
            uid='u1', source_path='compatibility/mcp', consumer='mcp', reason='legacy_mcp_compatibility'
        ),
        vector_query=vector_query,
    )
    assert result.read_decision == MemoryReadDecision.USE_LEGACY_SAFE
    assert result.memories == []
    assert result.fallback_reason == 'legacy_mcp_compatibility'
    assert result.should_use_legacy_fallback is True
    assert vector_calls == []
    assert db_client.collection_paths == []


def test_mcp_memory_search_and_list_format_mark_compatibility_derived_category_review_manual_fields():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{long_term.memory_id}': _stored_item(long_term)})
    rollout = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    list_result = list_default_mcp_memories(
        uid='u1', limit=10, offset=0, db_client=db_client, rollout_decision=rollout, now=now
    )
    vector_result = search_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=rollout,
        vector_query=lambda *args, **kwargs: _VectorCandidateResult(
            [
                SearchVectorHit(
                    memory_id='long-term',
                    score=0.88,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid=long_term.uid,
                    account_generation=long_term.account_generation,
                    item_revision=long_term.item_revision,
                    source_commit_id=long_term.source_commit_id,
                    content_hash=long_term.content_hash,
                )
            ]
        ),
    )
    for memory in [list_result.memories[0], vector_result.memories[0]]:
        assert memory['category'] == 'other'
        assert memory['category_source'] == 'mcp_memory_compatibility_default_no_source_category'
        assert memory['reviewed'] is False
        assert memory['reviewed_source'] == 'mcp_memory_compatibility_default_no_review_state'
        assert memory['manually_added'] is False
        assert memory['manually_added_source'] == 'mcp_memory_compatibility_default_no_manual_state'
        assert memory['memory_default_memory'] is True
        assert memory['archive_default_visible'] is False


def test_mcp_memory_list_adapter_applies_category_review_manual_filters_to_explicit_compatibility_fields():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{long_term.memory_id}': _stored_item(long_term)})
    rollout = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    matching = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=rollout,
        categories=['other'],
        reviewed=False,
        manually_added=False,
        now=now,
    )
    mismatched = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=rollout,
        categories=['personal'],
        reviewed=True,
        manually_added=True,
        now=now,
    )
    assert [item['id'] for item in matching.memories] == ['long-term']
    assert mismatched.memories == []


def test_mcp_rest_and_sse_get_paths_pass_filters_into_memory_list_adapter_and_rest_model_exposes_sources():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    mcp_contents = mcp_py.read_text(encoding='utf-8')
    rest_model = mcp_contents[mcp_contents.index('class CleanerMemory') : mcp_contents.index('class SearchedMemory')]
    get_route = mcp_contents[
        mcp_contents.index('@router.get("/v1/mcp/memories"') : mcp_contents.index('class SimpleStructured')
    ]
    assert 'category_source: Optional[str] = None' in rest_model
    assert 'reviewed: Optional[bool] = None' in rest_model
    assert 'reviewed_source: Optional[str] = None' in rest_model
    assert 'manually_added: Optional[bool] = None' in rest_model
    assert 'manually_added_source: Optional[str] = None' in rest_model
    assert 'categories=[category.value for category in category_list]' in get_route
    assert 'reviewed=reviewed' in get_route[get_route.index('list_default_mcp_memories(') :]
    assert 'manually_added=manually_added' in get_route[get_route.index('list_default_mcp_memories(') :]
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    sse_contents = mcp_sse_py.read_text(encoding='utf-8')
    get_tool = sse_contents[
        sse_contents.index('elif tool_name == "get_memories":') : sse_contents.index(
            'elif tool_name == "create_memory":'
        )
    ]
    assert 'categories=valid_categories' in get_tool
    assert 'reviewed=reviewed' in get_tool[get_tool.index('list_default_mcp_memories(') :]
    assert 'manually_added=manually_added' in get_tool[get_tool.index('list_default_mcp_memories(') :]


def test_mcp_list_adapter_uses_same_rollout_decisions_as_search_and_preserves_default_visibility():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )
    rollout = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    result = list_default_mcp_memories(
        uid='u1', limit=10, offset=0, db_client=db_client, rollout_decision=rollout, now=now
    )
    assert isinstance(result, McpMemoryListResult)
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in result.memories] == ['fresh-short-term', 'long-term']
    assert all((item['category'] == 'other' for item in result.memories))
    assert all((item['memory_default_memory'] is True for item in result.memories))
    assert all((item['archive_default_visible'] is False for item in result.memories))
    assert all((item['policy']['consumer'] == 'mcp' for item in result.memories))
    assert all((item['policy']['archive_capability'] is False for item in result.memories))


def test_mcp_list_adapter_denies_malformed_missing_or_no_grant_before_memory_reads_and_marks_legacy_safe_only_explicitly():
    db_client = _FirestoreFake({'users/u1/memory_items/fresh': _stored_item(_memory_item('fresh'))})
    missing = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=read_default_read_rollout(uid='u1', db_client=_FirestoreFake(), consumer='mcp'),
    )
    malformed = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=read_default_read_rollout(
            uid='u1',
            db_client=_FirestoreFake(
                {
                    'users/u1/memory_control/state': {
                        'schema_version': 1,
                        'uid': 'u1',
                        'mode': 'read',
                        'stage_gates': 'bad',
                    }
                }
            ),
            consumer='mcp',
        ),
    )
    no_grant = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=read_default_read_rollout(
            uid='u1',
            db_client=_FirestoreFake(
                {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'mcp': {}}}}
            ),
            consumer='mcp',
        ),
    )
    legacy_safe = list_default_mcp_memories(
        uid='u1',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=legacy_safe_default_read_rollout_decision(
            uid='u1', source_path='compatibility/mcp', consumer='mcp', reason='legacy_mcp_compatibility'
        ),
    )
    assert missing.read_decision == MemoryReadDecision.DENY_MEMORY
    assert malformed.read_decision == MemoryReadDecision.DENY_MEMORY
    assert no_grant.read_decision == MemoryReadDecision.DENY_MEMORY
    assert legacy_safe.read_decision == MemoryReadDecision.USE_LEGACY_SAFE
    assert legacy_safe.should_use_legacy_fallback is True
    assert missing.memories == malformed.memories == no_grant.memories == legacy_safe.memories == []
    assert db_client.collection_paths == []


def test_mcp_list_adapter_enabled_empty_returns_empty_memory_result_without_legacy_fallback():
    rollout = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    result = list_default_mcp_memories(
        uid='u1', limit=10, offset=0, db_client=_FirestoreFake(), rollout_decision=rollout
    )
    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert result.memories == []
    assert result.should_use_legacy_fallback is False
