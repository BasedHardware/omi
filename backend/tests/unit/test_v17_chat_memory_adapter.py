from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.v17_memory import PASSED, V17Mode, V17StageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory.v17_chat_memory_adapter import (
    V17ChatMemorySearchResult,
    read_v17_chat_default_memory_rollout,
    search_v17_default_chat_memories_vector_decision_text,
    search_v17_default_chat_memories_text,
    search_v17_default_chat_memories_vector_text,
)
from utils.memory.v17_default_read_rollout import V17ReadDecision


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
        quote_refs=[{'text': 'User likes safe chat memory reads.'}],
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
            'omi_chat': {
                'default_memory': True,
                'archive': True,
            }
        },
    }


def test_chat_memory_tool_wires_v17_adapter_before_legacy_vector_search():
    memory_tools_py = Path(__file__).resolve().parents[2] / 'utils' / 'retrieval' / 'tools' / 'memory_tools.py'
    contents = memory_tools_py.read_text(encoding='utf-8')

    rollout_call = 'search_v17_default_chat_memories_vector_decision_text('
    legacy_call = 'vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)'
    assert rollout_call in contents
    assert legacy_call in contents
    assert contents.index(rollout_call) < contents.index(legacy_call)
    assert 'if v17_default_memories is not None:' not in contents
    assert 'V17ReadDecision.USE_LEGACY_SAFE' in contents


def test_chat_rollout_reader_supports_omi_chat_grant_without_reading_memory_items():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})

    decision = read_v17_chat_default_memory_rollout(uid='u1', db_client=db_client)

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert decision.rollout_capabilities.v17_reads_enabled is True
    assert decision.app_has_default_memory_grant is True
    assert decision.archive_capability is False
    assert decision.v17_default_enabled is True
    assert decision.consumer == 'omi_chat'


def test_chat_rollout_reader_fails_closed_without_memory_item_reads_for_missing_malformed_or_grantless_state():
    missing = _FirestoreFake()
    assert read_v17_chat_default_memory_rollout(uid='u1', db_client=missing).v17_default_enabled is False
    assert missing.collection_paths == []

    malformed = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}})
    malformed_decision = read_v17_chat_default_memory_rollout(uid='u1', db_client=malformed)
    assert malformed_decision.v17_default_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []

    no_grant = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'omi_chat': {}}}})
    no_grant_decision = read_v17_chat_default_memory_rollout(uid='u1', db_client=no_grant)
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_enabled is False
    assert no_grant.collection_paths == []


def test_chat_default_v17_adapter_uses_product_search_and_excludes_stale_short_term_and_archive():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    docs = {'users/u1/memory_control/state': _enabled_rollout_doc()}
    docs.update(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )
    db_client = _FirestoreFake(docs)

    result = search_v17_default_chat_memories_text(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        now=now,
    )

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert result is not None
    assert result.startswith("Found 2 V17 default memories matching 'coffee':")
    assert '- coffee fresh short term (tier: short_term, date: 2026-06-18)' in result
    assert '- coffee long term (tier: long_term, date: 2026-06-18)' in result
    assert 'coffee stale short term' not in result
    assert 'coffee archive memory' not in result
    assert 'archive_default_visible=False' in result


def test_chat_default_v17_adapter_returns_none_when_rollout_or_grant_disabled_without_firestore_read():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    disabled_db = _FirestoreFake(
        {
            'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value},
            f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        }
    )
    grantless_db = _FirestoreFake(
        {
            'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'omi_chat': {}}},
            f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        }
    )

    assert (
        search_v17_default_chat_memories_text(uid='u1', query='coffee', limit=10, db_client=disabled_db, now=now)
        is None
    )
    assert (
        search_v17_default_chat_memories_text(uid='u1', query='coffee', limit=10, db_client=grantless_db, now=now)
        is None
    )
    assert disabled_db.collection_paths == []
    assert grantless_db.collection_paths == []


def test_chat_vector_adapter_uses_hydrated_vector_search_and_preserves_ranking_without_archive_default():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archive memory')
    docs = {'users/u1/memory_control/state': _enabled_rollout_doc()}
    docs.update(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [archive, stale_short_term, fresh_short_term, long_term]
        }
    )
    db_client = _FirestoreFake(docs)
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
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

    result = search_v17_default_chat_memories_vector_text(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=db_client,
        vector_query=fake_vector_query,
        required_projection_commit_id='projection-1',
    )

    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert result is not None
    assert result.startswith("Found 2 V17 vector memories matching 'coffee':")
    assert result.index('coffee long term') < result.index('coffee fresh short term')
    assert '(relevance: 0.92, tier: long_term' in result
    assert '(relevance: 0.80, tier: short_term' in result
    assert 'coffee stale short term' not in result
    assert 'coffee archive memory' not in result
    assert 'archive_default_visible=False' in result


def test_chat_vector_adapter_returns_none_without_rollout_or_grant_before_vector_or_memory_item_reads():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    disabled_db = _FirestoreFake(
        {
            'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value},
            f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        }
    )
    grantless_db = _FirestoreFake(
        {
            'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'omi_chat': {}}},
            f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        }
    )
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[_hit(fresh_short_term, score=0.9)])

    assert (
        search_v17_default_chat_memories_vector_text(
            uid='u1', query='coffee', limit=10, db_client=disabled_db, vector_query=fake_vector_query
        )
        is None
    )
    assert (
        search_v17_default_chat_memories_vector_text(
            uid='u1', query='coffee', limit=10, db_client=grantless_db, vector_query=fake_vector_query
        )
        is None
    )
    assert vector_calls == []
    assert disabled_db.collection_paths == []
    assert grantless_db.collection_paths == []


def test_chat_vector_decision_adapter_classifies_enabled_denied_and_legacy_safe_without_unsafe_reads():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    enabled_docs = {
        'users/u1/memory_control/state': _enabled_rollout_doc(),
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
    }
    disabled_docs = {
        'users/u1/memory_control/state': _enabled_rollout_doc() | {'mode': V17Mode.off.value},
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
    }
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[_hit(fresh_short_term, score=0.9)])

    enabled_db = _FirestoreFake(enabled_docs)
    enabled = search_v17_default_chat_memories_vector_decision_text(
        uid='u1', query='coffee', limit=10, db_client=enabled_db, vector_query=fake_vector_query
    )
    assert isinstance(enabled, V17ChatMemorySearchResult)
    assert enabled.read_decision == V17ReadDecision.USE_V17
    assert enabled.should_use_legacy_fallback is False
    assert enabled.text is not None and "Found 1 V17 vector memories matching 'coffee':" in enabled.text
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert enabled_db.collection_paths == ['users/u1/memory_items']

    denied_db = _FirestoreFake(disabled_docs)
    denied = search_v17_default_chat_memories_vector_decision_text(
        uid='u1', query='coffee', limit=10, db_client=denied_db, vector_query=fake_vector_query
    )
    assert denied.read_decision == V17ReadDecision.DENY_MEMORY
    assert denied.should_use_legacy_fallback is False
    assert denied.fallback_reason == 'v17_reads_disabled'
    assert denied.text == "No memories available for this request."
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert denied_db.collection_paths == []

    legacy_safe_db = _FirestoreFake(disabled_docs)
    legacy_safe = search_v17_default_chat_memories_vector_decision_text(
        uid='u1',
        query='coffee',
        limit=10,
        db_client=legacy_safe_db,
        vector_query=fake_vector_query,
        allow_legacy_safe_fallback=True,
    )
    assert legacy_safe.read_decision == V17ReadDecision.USE_LEGACY_SAFE
    assert legacy_safe.should_use_legacy_fallback is True
    assert legacy_safe.text is None
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert legacy_safe_db.collection_paths == []
