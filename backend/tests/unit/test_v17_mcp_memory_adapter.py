from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.v17_memory import PASSED, V17Capabilities, V17Mode, V17StageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.mcp_memories import (
    read_v17_mcp_default_memory_rollout,
    search_v17_default_mcp_memories,
    search_v17_default_mcp_memories_vector,
)


def test_mcp_rest_search_route_wires_v17_vector_adapter_before_legacy_vector_search():
    mcp_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp.py'
    contents = mcp_py.read_text(encoding='utf-8')

    rollout_call = 'read_v17_mcp_default_memory_rollout(uid=uid, db_client=db)'
    vector_adapter_call = 'search_v17_default_mcp_memories_vector('
    read_adapter_call = 'search_v17_default_mcp_memories('
    legacy_call = 'vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)'
    assert rollout_call in contents
    assert vector_adapter_call in contents
    assert read_adapter_call in contents
    assert legacy_call in contents
    assert contents.index(rollout_call) < contents.index(vector_adapter_call) < contents.index(read_adapter_call)
    assert contents.index(vector_adapter_call) < contents.index(legacy_call)


def test_mcp_sse_search_tool_wires_v17_vector_adapter_before_legacy_vector_search():
    mcp_sse_py = Path(__file__).resolve().parents[2] / 'routers' / 'mcp_sse.py'
    contents = mcp_sse_py.read_text(encoding='utf-8')

    rollout_call = 'read_v17_mcp_default_memory_rollout(uid=user_id, db_client=db)'
    vector_adapter_call = 'search_v17_default_mcp_memories_vector('
    legacy_call = 'vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)'
    assert rollout_call in contents
    assert vector_adapter_call in contents
    assert legacy_call in contents
    assert contents.index(rollout_call) < contents.index(vector_adapter_call) < contents.index(legacy_call)


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
                    uid='u1',
                ),
                SearchVectorHit(
                    memory_id='long-term',
                    score=0.88,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid='u1',
                ),
                SearchVectorHit(
                    memory_id='stale-short-term',
                    score=0.77,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid='u1',
                ),
                SearchVectorHit(
                    memory_id='fresh-short-term',
                    score=0.66,
                    projection_commit_id='projection-1',
                    vector_updated_at=now,
                    uid='u1',
                ),
            ],
            rejected_count=1,
        )

    results = search_v17_default_mcp_memories_vector(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        rollout_capabilities=_read_capabilities(),
        vector_query=vector_query,
    )

    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['long-term', 'fresh-short-term']
    assert [item['relevance_score'] for item in results] == [0.88, 0.66]
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'mcp' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_mcp_vector_adapter_returns_none_before_vector_or_memory_reads_when_rollout_or_grant_disabled():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    db_client = _FirestoreFake({f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term)})
    vector_calls = []

    def vector_query(*args, **kwargs):
        vector_calls.append((args, kwargs))
        return _VectorCandidateResult([])

    assert (
        search_v17_default_mcp_memories_vector(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(enabled=False),
            vector_query=vector_query,
        )
        is None
    )
    assert (
        search_v17_default_mcp_memories_vector(
            uid='u1',
            query='coffee',
            limit=10,
            db_client=db_client,
            rollout_capabilities=_read_capabilities(),
            app_has_default_memory_grant=False,
            vector_query=vector_query,
        )
        is None
    )
    assert vector_calls == []
    assert db_client.collection_paths == []
