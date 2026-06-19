from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.v17_memory import PASSED, V17Mode, V17StageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory.v17_developer_memory_adapter import (
    V17DeveloperMemorySearchResult,
    read_v17_developer_default_memory_rollout,
    search_v17_default_developer_memories,
    search_v17_default_developer_memories_vector,
)
from utils.memory.v17_default_read_rollout import (
    V17ReadDecision,
    assert_legacy_memory_write_allowed_for_default_read_decision,
    legacy_safe_v17_default_read_rollout_decision,
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
            if path.startswith(prefix) and '/' not in path[len(prefix) :]:
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


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concrete developer memory reads.'}],
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


def _hit(item, *, score, projection_commit_id='projection-1'):
    return SearchVectorHit(
        memory_id=item.memory_id,
        score=score,
        projection_commit_id=projection_commit_id,
        vector_updated_at=item.updated_at + timedelta(minutes=1),
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
        source_commit_id=item.source_commit_id,
        content_hash=item.content_hash,
    )


def _enabled_rollout_doc(uid='u1'):
    return {
        'schema_version': 1,
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
            'developer_api': {
                'default_memory': True,
                'archive': True,
            }
        },
    }


def test_developer_route_wires_adapter_before_legacy_memory_reads():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    rollout_call = 'read_v17_developer_default_memory_rollout(uid=uid, db_client=db)'
    adapter_call = 'search_v17_default_developer_memories('
    legacy_call = 'memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])'
    assert rollout_call in contents
    assert adapter_call in contents
    assert legacy_call in contents
    assert contents.index(rollout_call) < contents.index(adapter_call) < contents.index(legacy_call)


def test_developer_vector_route_wires_app_key_scope_grant_before_v17_vector_reads():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    route = '@router.get("/v1/dev/user/memories/vector/search", tags=["developer"])'
    auth_context_dependency = (
        'auth_context: V17ProductAuthorizationContext = Depends(get_developer_v17_default_memory_read_context)'
    )
    uid_from_context = 'uid = auth_context.uid'
    app_key_grant_call = 'v17_app_key_grant = authorize_v17_external_default_memory_read(auth_context, db_client=db)'
    app_key_deny_check = 'if not v17_app_key_grant.allowed:'
    rollout_call = 'read_v17_developer_default_memory_rollout(uid=uid, db_client=db)'
    vector_adapter_call = 'search_v17_default_developer_memories_vector('
    vector_side_effect = 'fetch_default_v17_vector_memory_search('
    assert route in contents
    assert auth_context_dependency in contents
    assert app_key_grant_call in contents
    assert vector_adapter_call in contents
    assert (
        vector_side_effect
        not in contents[contents.index(route) : contents.index(vector_adapter_call, contents.index(route))]
    )
    route_index = contents.index(route)
    assert (
        route_index
        < contents.index(auth_context_dependency, route_index)
        < contents.index(uid_from_context, route_index)
        < contents.index(app_key_grant_call, route_index)
        < contents.index(app_key_deny_check, route_index)
        < contents.index(rollout_call, route_index)
        < contents.index(vector_adapter_call, route_index)
    )


def test_developer_create_route_checks_split_brain_guard_before_legacy_write():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    route = '@router.post("/v1/dev/user/memories", response_model=MemoryResponse, tags=["developer"])'
    guard_call = "assert_legacy_memory_write_allowed_for_default_read_decision("
    legacy_write = "memories_db.create_memory(uid, memory_db.dict())"
    assert guard_call in contents
    assert legacy_write in contents
    route_index = contents.index(route)
    assert route_index < contents.index(guard_call, route_index) < contents.index(legacy_write, route_index)


def test_developer_batch_create_route_checks_split_brain_guard_before_categorization_and_legacy_writes():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    route = '@router.post("/v1/dev/user/memories/batch", response_model=BatchMemoriesResponse, tags=["developer"])'
    guard_call = "assert_legacy_memory_write_allowed_for_default_read_decision("
    categorization = "identify_category_for_memory(mem_req.content.strip())"
    legacy_write = "memories_db.save_memories(uid, [mem.dict() for mem in memory_dbs])"
    vector_write = "upsert_memory_vectors_batch("
    assert guard_call in contents
    assert categorization in contents
    assert legacy_write in contents
    assert vector_write in contents
    route_index = contents.index(route)
    guard_index = contents.index(guard_call, route_index)
    assert route_index < guard_index < contents.index(categorization, route_index)
    assert guard_index < contents.index(legacy_write, route_index) < contents.index(vector_write, route_index)


def test_developer_delete_route_checks_split_brain_guard_before_reads_and_legacy_delete():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    route = '@router.delete("/v1/dev/user/memories/{memory_id}", tags=["developer"])'
    guard_call = "assert_legacy_memory_write_allowed_for_default_read_decision("
    legacy_read = "memory = memories_db.get_memory(uid, memory_id)"
    legacy_delete = "memories_db.delete_memory(uid, memory_id)"
    assert guard_call in contents
    assert legacy_read in contents
    assert legacy_delete in contents
    route_index = contents.index(route)
    guard_index = contents.index(guard_call, route_index)
    assert (
        route_index
        < guard_index
        < contents.index(legacy_read, route_index)
        < contents.index(legacy_delete, route_index)
    )


def test_developer_update_route_checks_split_brain_guard_before_reads_and_legacy_mutations():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    route = '@router.patch("/v1/dev/user/memories/{memory_id}", response_model=CleanerMemory, tags=["developer"])'
    guard_call = "assert_legacy_memory_write_allowed_for_default_read_decision("
    legacy_read = "memory = memories_db.get_memory(uid, memory_id)"
    legacy_edit = "memories_db.edit_memory(uid, memory_id, request.content.strip())"
    legacy_update = "memories_db.update_memory_fields(uid, memory_id, update_data)"
    assert guard_call in contents
    assert legacy_read in contents
    assert legacy_edit in contents
    assert legacy_update in contents
    route_index = contents.index(route)
    guard_index = contents.index(guard_call, route_index)
    assert route_index < guard_index < contents.index(legacy_read, route_index)
    assert guard_index < contents.index(legacy_edit, route_index) < contents.index(legacy_update, route_index)


def test_developer_routes_only_reach_legacy_after_explicit_legacy_safe_decision():
    developer_py = Path(__file__).resolve().parents[2] / 'routers' / 'developer.py'
    contents = developer_py.read_text(encoding='utf-8')

    denied_check = 'if v17_result.read_decision in {V17ReadDecision.DENY_MEMORY, V17ReadDecision.SHADOW_ONLY}:'
    legacy_safe_check = 'if v17_result.should_use_legacy_fallback:'
    legacy_call = 'memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])'
    assert denied_check in contents
    assert legacy_safe_check in contents
    assert legacy_call in contents
    assert contents.index(denied_check) < contents.index(legacy_safe_check) < contents.index(legacy_call)

    route = '@router.get("/v1/dev/user/memories/vector/search", tags=["developer"])'
    route_index = contents.index(route)
    assert contents.index(denied_check, route_index) < contents.index(legacy_safe_check, route_index)


def test_developer_rollout_reader_derives_default_memory_grant_without_reading_memory_items():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})

    decision = read_v17_developer_default_memory_rollout(uid='u1', db_client=db_client)

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert decision.rollout_capabilities.v17_reads_enabled is True
    assert decision.app_has_default_memory_grant is True
    assert decision.archive_capability is False
    assert decision.v17_default_developer_enabled is True


def test_developer_rollout_reader_fails_closed_without_memory_item_reads_for_missing_malformed_or_grantless_state():
    missing = _FirestoreFake()
    assert read_v17_developer_default_memory_rollout(uid='u1', db_client=missing).v17_default_developer_enabled is False
    assert missing.collection_paths == []

    malformed = _FirestoreFake(
        {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}}
    )
    malformed_decision = read_v17_developer_default_memory_rollout(uid='u1', db_client=malformed)
    assert malformed_decision.v17_default_developer_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []

    no_grant = _FirestoreFake(
        {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
    )
    no_grant_decision = read_v17_developer_default_memory_rollout(uid='u1', db_client=no_grant)
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_developer_enabled is False
    assert no_grant.collection_paths == []


def test_split_brain_guard_blocks_v17_enabled_developer_legacy_write_without_mutation():
    read_decision = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )

    decision = assert_legacy_memory_write_allowed_for_default_read_decision(
        read_decision,
        operation='create_memory',
        allow_write_convergence=False,
    )

    assert decision.allowed is False
    assert decision.status_code == 409
    assert decision.detail == {
        'enabled': False,
        'reason': 'v17_default_read_legacy_write_blocked',
        'consumer': 'developer_api',
        'operation': 'create_memory',
        'read_decision': V17ReadDecision.USE_V17.value,
        'source_path': 'users/u1/memory_control/state',
        'convergence_reason': None,
    }


def test_split_brain_guard_blocks_v17_enabled_developer_batch_create_without_mutation():
    read_decision = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )

    decision = assert_legacy_memory_write_allowed_for_default_read_decision(
        read_decision,
        operation='batch_create_memories',
        allow_write_convergence=False,
    )

    assert decision.allowed is False
    assert decision.status_code == 409
    assert decision.detail['reason'] == 'v17_default_read_legacy_write_blocked'
    assert decision.detail['consumer'] == 'developer_api'
    assert decision.detail['operation'] == 'batch_create_memories'
    assert decision.detail['read_decision'] == V17ReadDecision.USE_V17.value


def test_split_brain_guard_blocks_v17_enabled_developer_edit_and_delete_without_mutation():
    read_decision = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )

    for operation in ['update_memory', 'delete_memory']:
        decision = assert_legacy_memory_write_allowed_for_default_read_decision(
            read_decision,
            operation=operation,
            allow_write_convergence=False,
        )

        assert decision.allowed is False
        assert decision.status_code == 409
        assert decision.detail['reason'] == 'v17_default_read_legacy_write_blocked'
        assert decision.detail['consumer'] == 'developer_api'
        assert decision.detail['operation'] == operation
        assert decision.detail['read_decision'] == V17ReadDecision.USE_V17.value


def test_split_brain_guard_blocks_missing_or_malformed_developer_config_fail_safe():
    missing = read_v17_developer_default_memory_rollout(uid='u1', db_client=_FirestoreFake())
    malformed = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}}
        ),
    )

    for read_decision in [missing, malformed]:
        decision = assert_legacy_memory_write_allowed_for_default_read_decision(
            read_decision,
            operation='create_memory',
        )
        assert decision.allowed is False
        assert decision.status_code == 409
        assert decision.detail['reason'] == 'v17_default_read_legacy_write_blocked'


def test_split_brain_guard_allows_disabled_but_ignores_legacy_boolean_convergence_override():
    disabled = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value}}
        ),
    )
    enabled = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )

    disabled_allowed = assert_legacy_memory_write_allowed_for_default_read_decision(disabled, operation='create_memory')
    boolean_override_blocked = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled,
        operation='create_memory',
        allow_write_convergence=True,
    )

    assert disabled_allowed.allowed is True
    assert boolean_override_blocked.allowed is False
    assert boolean_override_blocked.detail['convergence_reason'] == 'legacy_boolean_convergence_override_ignored'


def test_developer_default_v17_adapter_uses_product_search_and_excludes_stale_short_term_and_archive():
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
    decision = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )

    result = search_v17_default_developer_memories(
        uid='u1',
        query='coffee',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_decision=decision,
        now=now,
    )

    assert isinstance(result, V17DeveloperMemorySearchResult)
    assert result.read_decision == V17ReadDecision.USE_V17
    assert result.fallback_reason is None
    results = result.memories
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all(item['category'] == 'other' for item in results)
    assert all(item['visibility'] == 'private' for item in results)
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'developer_api' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_developer_default_v17_adapter_returns_denied_decision_when_rollout_or_grant_disabled_without_firestore_read():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    disabled_decision = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value}}
        ),
    )
    grantless_decision = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
        ),
    )

    disabled_result = search_v17_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=disabled_decision, now=now
    )
    grantless_result = search_v17_default_developer_memories(
        uid='u1', query='coffee', limit=10, offset=0, db_client=db_client, rollout_decision=grantless_decision, now=now
    )

    assert disabled_result.memories == []
    assert disabled_result.read_decision == V17ReadDecision.DENY_MEMORY
    assert disabled_result.fallback_reason == 'v17_reads_disabled'
    assert grantless_result.memories == []
    assert grantless_result.read_decision == V17ReadDecision.DENY_MEMORY
    assert grantless_result.fallback_reason == 'missing_developer_default_memory_grant'
    assert db_client.collection_paths == []


def test_developer_default_v17_adapter_classifies_explicit_legacy_safe_without_firestore_read():
    db_client = _FirestoreFake()
    legacy_safe = legacy_safe_v17_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='developer_api',
        reason='developer_category_legacy_safe_fallback_explicit',
    )

    result = search_v17_default_developer_memories(
        uid='u1', query='', limit=10, offset=0, db_client=db_client, rollout_decision=legacy_safe
    )

    assert result.memories == []
    assert result.read_decision == V17ReadDecision.USE_LEGACY_SAFE
    assert result.fallback_reason == 'developer_category_legacy_safe_fallback_explicit'
    assert result.should_use_legacy_fallback is True
    assert db_client.collection_paths == []


def test_developer_vector_adapter_uses_hydrated_vector_service_and_preserves_ranking_without_archive_default():
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
    decision = read_v17_developer_default_memory_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    )
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(
            hits=[
                _hit(stale_short_term, score=0.99),
                _hit(archive, score=0.98),
                _hit(long_term, score=0.92),
                _hit(fresh_short_term, score=0.80),
            ],
            rejected_count=1,
        )

    result = search_v17_default_developer_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=decision,
        vector_query=vector_query,
    )

    assert result.read_decision == V17ReadDecision.USE_V17
    assert result.fallback_reason is None
    results = result.memories
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert db_client.collection_paths == []
    assert [item['id'] for item in results] == ['long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.92, 0.8]
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'developer_api' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_developer_vector_adapter_returns_denied_decision_before_vector_or_memory_reads_when_rollout_or_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult([_hit(fresh_short_term, score=0.9)])

    disabled_decision = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value}}
        ),
    )
    grantless_decision = read_v17_developer_default_memory_rollout(
        uid='u1',
        db_client=_FirestoreFake(
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
        ),
    )

    disabled_result = search_v17_default_developer_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=disabled_decision,
        vector_query=vector_query,
    )
    grantless_result = search_v17_default_developer_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_decision=grantless_decision,
        vector_query=vector_query,
    )

    assert disabled_result.memories == []
    assert disabled_result.read_decision == V17ReadDecision.DENY_MEMORY
    assert disabled_result.fallback_reason == 'v17_reads_disabled'
    assert grantless_result.memories == []
    assert grantless_result.read_decision == V17ReadDecision.DENY_MEMORY
    assert grantless_result.fallback_reason == 'missing_developer_default_memory_grant'
    assert vector_calls == []
    assert db_client.collection_paths == []


def test_developer_vector_adapter_classifies_explicit_legacy_safe_without_vector_or_memory_reads():
    db_client = _FirestoreFake()
    vector_calls = []

    def vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult([])

    legacy_safe = legacy_safe_v17_default_read_rollout_decision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='developer_api',
        reason='developer_vector_legacy_safe_fallback_explicit',
    )

    result = search_v17_default_developer_memories_vector(
        uid='u1', query='coffee', limit=10, db_client=db_client, rollout_decision=legacy_safe, vector_query=vector_query
    )

    assert result.memories == []
    assert result.read_decision == V17ReadDecision.USE_LEGACY_SAFE
    assert result.fallback_reason == 'developer_vector_legacy_safe_fallback_explicit'
    assert result.should_use_legacy_fallback is True
    assert vector_calls == []
    assert db_client.collection_paths == []
