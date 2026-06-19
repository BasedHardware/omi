from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.v17_memory import PASSED, V17Capabilities, V17Mode, V17StageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory.v17_default_read_rollout import (
    V17ReadDecision,
    assert_legacy_memory_write_allowed_for_default_read_decision,
    legacy_safe_v17_default_read_rollout_decision,
)
from utils.mcp_memories import (
    V17McpMemorySearchResult,
    read_v17_mcp_default_memory_rollout,
    search_v17_default_mcp_memories,
    search_v17_default_mcp_memories_vector,
)


def test_mcp_rest_search_route_wires_app_key_scope_grant_before_v17_vector_adapter_and_legacy_search():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')
    search_route = contents[
        contents.index('@router.get("/v1/mcp/memories/search"') : contents.index('@router.get("/v1/mcp/memories"')
    ]

    context_dependency = (
        'auth_context: V17ProductAuthorizationContext = Depends(get_mcp_v17_default_memory_read_context)'
    )
    grant_call = 'authorize_v17_external_default_memory_read(auth_context, db_client=db)'
    uid_assignment = 'uid = auth_context.uid'
    rollout_call = 'read_v17_mcp_default_memory_rollout(uid=uid, db_client=db)'
    vector_adapter_call = 'search_v17_default_mcp_memories_vector('
    legacy_call = 'vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)'
    assert context_dependency in search_route
    assert grant_call in search_route
    assert uid_assignment in search_route
    assert rollout_call in search_route
    assert vector_adapter_call in search_route
    assert legacy_call in search_route
    assert search_route.index(grant_call) < search_route.index(rollout_call)
    assert search_route.index(grant_call) < search_route.index(vector_adapter_call)
    assert search_route.index(grant_call) < search_route.index(legacy_call)
    assert search_route.index(rollout_call) < search_route.index(vector_adapter_call) < search_route.index(legacy_call)


def test_mcp_rest_uid_only_routes_keep_legacy_mcp_api_key_dependency():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')

    profile_route = contents[contents.index('@router.get("/v1/mcp/profile"') : contents.index('class CleanerMemory')]
    list_route = contents[contents.index('@router.get("/v1/mcp/memories"') : contents.index('class SimpleStructured')]
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' in profile_route
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' in list_route
    assert 'get_mcp_v17_default_memory_read_context' not in profile_route
    assert 'get_mcp_v17_default_memory_read_context' not in list_route


def test_mcp_sse_search_tool_wires_app_key_scope_grant_before_v17_vector_adapter_and_legacy_search():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')
    search_tool = contents[
        contents.index('elif tool_name == "search_memories":') : contents.index(
            'elif tool_name == "search_conversations":'
        )
    ]

    grant_call = 'authorize_v17_external_default_memory_read(auth_context, db_client=db)'
    rollout_call = 'read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)'
    vector_adapter_call = 'search_v17_default_mcp_memories_vector('
    legacy_call = 'vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)'
    assert 'auth_context: Optional[V17ProductAuthorizationContext] = None' in contents
    assert 'auth_context=auth_context' in contents
    assert grant_call in search_tool
    assert rollout_call in search_tool
    assert vector_adapter_call in search_tool
    assert legacy_call in search_tool
    assert search_tool.index(grant_call) < search_tool.index(rollout_call)
    assert search_tool.index(grant_call) < search_tool.index(vector_adapter_call)
    assert search_tool.index(grant_call) < search_tool.index(legacy_call)
    assert search_tool.index(rollout_call) < search_tool.index(vector_adapter_call) < search_tool.index(legacy_call)


def test_mcp_sse_transport_authenticates_full_mcp_api_key_context_without_inferred_scopes():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')

    assert (
        'def authenticate_api_key_auth_context(authorization: Optional[str]) -> Optional[V17ProductAuthorizationContext]:'
        in contents
    )
    assert 'mcp_api_key_db.get_user_and_scopes_by_api_key(token)' in contents
    assert 'McpV17VerifiedAuth(' in contents
    assert 'scopes=tuple(user_data.get("scopes") or ())' in contents
    assert 'auth_context = authenticate_api_key_auth_context(authorization)' in contents
    assert 'user_id = auth_context.uid' in contents
    assert (
        'user_id = authenticate_api_key(authorization)'
        not in contents[contents.index('@router.post("/v1/mcp/sse"') : contents.index('@router.get("/v1/mcp/sse"')]
    )


def test_mcp_rest_search_route_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')

    assert 'V17ReadDecision.USE_V17' in contents
    assert 'V17ReadDecision.USE_LEGACY_SAFE' in contents
    assert 'if v17_vector_results.read_decision == V17ReadDecision.USE_V17:' in contents
    assert 'if v17_vector_results.read_decision != V17ReadDecision.USE_LEGACY_SAFE:' in contents
    assert contents.index('if v17_vector_results.read_decision != V17ReadDecision.USE_LEGACY_SAFE:') < contents.index(
        'vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)'
    )


def test_mcp_sse_search_tool_only_reaches_legacy_after_explicit_legacy_safe_decision():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')

    assert 'V17ReadDecision.USE_V17' in contents
    assert 'V17ReadDecision.USE_LEGACY_SAFE' in contents
    assert 'if v17_vector_results.read_decision == V17ReadDecision.USE_V17:' in contents
    assert 'if v17_vector_results.read_decision != V17ReadDecision.USE_LEGACY_SAFE:' in contents
    assert contents.index('if v17_vector_results.read_decision != V17ReadDecision.USE_LEGACY_SAFE:') < contents.index(
        'vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)'
    )


def test_mcp_rest_write_routes_guard_legacy_mutation_before_side_effects():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')

    assert 'assert_legacy_memory_write_allowed_for_default_read_decision' in contents

    create_route = contents[
        contents.index('@router.post("/v1/mcp/memories"') : contents.index('def _validate_mcp_memory')
    ]
    assert 'operation="mcp_memory_create"' in create_route
    assert create_route.index('read_v17_mcp_default_memory_rollout(uid=uid, db_client=db)') < create_route.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert create_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < create_route.index(
        'identify_category_for_memory(memory.content)'
    )
    assert create_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < create_route.index(
        'memories_db.create_memory(uid, memory_db.model_dump())'
    )

    delete_route = contents[
        contents.index('@router.delete("/v1/mcp/memories/{memory_id}"') : contents.index(
            '@router.patch("/v1/mcp/memories/{memory_id}"'
        )
    ]
    assert 'operation="mcp_memory_delete"' in delete_route
    assert delete_route.index('read_v17_mcp_default_memory_rollout(uid=uid, db_client=db)') < delete_route.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert delete_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < delete_route.index(
        '_validate_mcp_memory(uid, memory_id)'
    )
    assert delete_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < delete_route.index(
        'memories_db.delete_memory(uid, memory_id)'
    )

    edit_route = contents[
        contents.index('@router.patch("/v1/mcp/memories/{memory_id}"') : contents.index('class UserProfile')
    ]
    assert 'operation="mcp_memory_edit"' in edit_route
    assert edit_route.index('read_v17_mcp_default_memory_rollout(uid=uid, db_client=db)') < edit_route.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert edit_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < edit_route.index(
        '_validate_mcp_memory(uid, memory_id)'
    )
    assert edit_route.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < edit_route.index(
        'memories_db.edit_memory(uid, memory_id, value)'
    )


def test_mcp_sse_write_tools_guard_legacy_mutation_before_side_effects():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')

    assert 'assert_legacy_memory_write_allowed_for_default_read_decision' in contents

    create_tool = contents[
        contents.index('elif tool_name == "create_memory":') : contents.index('elif tool_name == "delete_memory":')
    ]
    assert 'operation="mcp_tool_memory_create"' in create_tool
    assert create_tool.index('read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)') < create_tool.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert create_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < create_tool.index(
        'identify_category_for_memory(content)'
    )
    assert create_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < create_tool.index(
        'memories_db.create_memory(user_id, memory_db.model_dump())'
    )

    delete_tool = contents[
        contents.index('elif tool_name == "delete_memory":') : contents.index('elif tool_name == "edit_memory":')
    ]
    assert 'operation="mcp_tool_memory_delete"' in delete_tool
    assert delete_tool.index('read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)') < delete_tool.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert delete_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < delete_tool.index(
        'memories_db.get_memory(user_id, memory_id)'
    )
    assert delete_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < delete_tool.index(
        'memories_db.delete_memory(user_id, memory_id)'
    )

    edit_tool = contents[
        contents.index('elif tool_name == "edit_memory":') : contents.index('elif tool_name == "get_conversations":')
    ]
    assert 'operation="mcp_tool_memory_edit"' in edit_tool
    assert edit_tool.index('read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)') < edit_tool.index(
        'assert_legacy_memory_write_allowed_for_default_read_decision('
    )
    assert edit_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < edit_tool.index(
        'memories_db.get_memory(user_id, memory_id)'
    )
    assert edit_tool.index('assert_legacy_memory_write_allowed_for_default_read_decision(') < edit_tool.index(
        'memories_db.edit_memory(user_id, memory_id, content)'
    )


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self):
        self._db_client.document_get_paths.append(self.path)
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


class _CollectionRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def stream(self):
        prefix = f'{self.path}/'
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            snapshots.append(_Snapshot(data))
        return snapshots


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.collection_paths = []
        self.document_paths = []
        self.document_get_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)

    def document(self, path):
        self.document_paths.append(path)
        return _DocumentRef(self, path)


class _VectorCandidateResult:
    def __init__(self, hits, rejected_count=0):
        self.hits = hits
        self.rejected_count = rejected_count


def _read_capabilities(uid='u1', *, enabled=True):
    return V17Capabilities(
        uid=uid,
        mode=V17Mode.read if enabled else V17Mode.off,
        legacy_only=not enabled,
        shadow_artifacts_enabled=enabled,
        v17_writes_enabled=enabled,
        v17_reads_enabled=enabled,
        legacy_reads_authoritative=not enabled,
        account_generation=3,
    )


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers deterministic MCP memory reads.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    now = now or datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    captured_at = captured_at or (now - timedelta(days=1))
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending if tier == MemoryTier.short_term else ProcessingState.processed,
        'content': content or f'{memory_id} coffee preference',
        'evidence': [_evidence(f'{memory_id}-source')],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': (
            captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryTier.short_term else None
        ),
        'ledger_commit_id': 'commit-1' if tier == MemoryTier.long_term else None,
        'ledger_sequence': 1 if tier == MemoryTier.long_term else None,
        'item_revision': 1,
        'source_commit_id': f'source-commit-{memory_id}',
        'content_hash': f'content-hash-{memory_id}',
        'account_generation': 3,
    }
    data.update(overrides)
    return V17MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def _enabled_rollout_doc(uid='u1'):
    return {
        'uid': uid,
        'mode': V17Mode.read.value,
        'mode_epoch': 7,
        'cutover_epoch': 7,
        'account_generation': 3,
        'vector_projection_commit_id': 'projection-1',
        'fallback_projection_ready': True,
        'persistent_v17_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {
            V17StageGate.shadow.value: PASSED,
            V17StageGate.write.value: PASSED,
            V17StageGate.read.value: PASSED,
        },
        'grants': {
            'mcp': {
                'default_memory': True,
                'archive': True,
            }
        },
    }


def test_mcp_default_v17_rollout_reader_derives_capability_and_default_grant_from_memory_control_state():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})

    decision = read_v17_mcp_default_memory_rollout(uid='u1', db_client=db_client)

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert decision.rollout_capabilities.v17_reads_enabled is True
    assert decision.app_has_default_memory_grant is True
    assert decision.archive_capability is False
    assert decision.source_path == 'users/u1/memory_control/state'


def test_mcp_legacy_write_guard_blocks_v17_and_shadow_reads_but_preserves_disabled_legacy_behavior():
    enabled_decision = read_v17_mcp_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )
    blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled_decision,
        operation='mcp_memory_create',
    )
    assert blocked.allowed is False
    assert blocked.status_code == 409
    assert blocked.detail['consumer'] == 'mcp'
    assert blocked.detail['read_decision'] == V17ReadDecision.USE_V17.value

    missing_decision = read_v17_mcp_default_memory_rollout(uid='u1', db_client=_FirestoreFake())
    missing_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        missing_decision,
        operation='mcp_memory_delete',
    )
    assert missing_blocked.allowed is False
    assert missing_blocked.detail['reason'] == 'v17_default_read_legacy_write_blocked'

    shadow_doc = _enabled_rollout_doc() | {
        'mode': V17Mode.shadow.value,
        'fallback_projection_ready': False,
        'stage_gates': {V17StageGate.shadow.value: PASSED},
    }
    shadow_decision = read_v17_mcp_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': shadow_doc})
    )
    shadow_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        shadow_decision,
        operation='mcp_memory_edit',
    )
    assert shadow_decision.read_decision == V17ReadDecision.SHADOW_ONLY
    assert shadow_blocked.allowed is False

    disabled_doc = _enabled_rollout_doc() | {'mode': V17Mode.off.value, 'grants': {}}
    disabled_decision = read_v17_mcp_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': disabled_doc})
    )
    allowed = assert_legacy_memory_write_allowed_for_default_read_decision(
        disabled_decision,
        operation='mcp_memory_edit',
    )
    assert allowed.allowed is True


def test_mcp_default_v17_rollout_reader_fails_closed_for_missing_malformed_or_missing_grant_without_memory_reads():
    missing = _FirestoreFake()
    assert read_v17_mcp_default_memory_rollout(uid='u1', db_client=missing).v17_default_mcp_enabled is False
    assert missing.document_get_paths == ['users/u1/memory_control/state']
    assert missing.collection_paths == []

    malformed = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}})
    malformed_decision = read_v17_mcp_default_memory_rollout(uid='u1', db_client=malformed)
    assert malformed_decision.v17_default_mcp_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []

    no_grant = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'mcp': {}}}})
    no_grant_decision = read_v17_mcp_default_memory_rollout(uid='u1', db_client=no_grant)
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_mcp_enabled is False
    assert no_grant.collection_paths == []


def test_mcp_default_v17_memory_adapter_uses_product_search_when_read_rollout_enabled():
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

    results = search_v17_default_mcp_memories(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        now=now,
    )

    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all(item['category'] == 'other' for item in results)
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'mcp' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_mcp_default_v17_memory_adapter_returns_none_when_rollout_or_default_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})

    assert (
        search_v17_default_mcp_memories(
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
        search_v17_default_mcp_memories(
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

    result = search_v17_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        vector_query=vector_query,
        required_projection_commit_id='projection-1',
    )

    assert isinstance(result, V17McpMemorySearchResult)
    assert result.read_decision == V17ReadDecision.USE_V17
    results = result.memories
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert db_client.collection_paths == []
    assert [item['id'] for item in results] == ['long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.88, 0.66]
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'mcp' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_mcp_vector_adapter_returns_explicit_denial_before_vector_or_memory_reads_when_rollout_or_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    vector_calls = []

    def vector_query(*args, **kwargs):
        vector_calls.append((args, kwargs))
        return _VectorCandidateResult([])

    disabled_result = search_v17_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(enabled=False),
        vector_query=vector_query,
    )
    no_grant_result = search_v17_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        app_has_default_memory_grant=False,
        vector_query=vector_query,
    )
    assert disabled_result.read_decision == V17ReadDecision.DENY_MEMORY
    assert disabled_result.memories == []
    assert disabled_result.fallback_reason == 'v17_reads_disabled'
    assert no_grant_result.read_decision == V17ReadDecision.DENY_MEMORY
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

    result = search_v17_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=legacy_safe_v17_default_read_rollout_decision(
            uid='u1', source_path='compatibility/mcp', consumer='mcp', reason='legacy_mcp_compatibility'
        ),
        vector_query=vector_query,
    )

    assert result.read_decision == V17ReadDecision.USE_LEGACY_SAFE
    assert result.memories == []
    assert result.fallback_reason == 'legacy_mcp_compatibility'
    assert result.should_use_legacy_fallback is True
    assert vector_calls == []
    assert db_client.collection_paths == []
