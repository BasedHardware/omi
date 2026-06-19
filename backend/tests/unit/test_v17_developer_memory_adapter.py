from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.v17_memory import PASSED, V17Mode, V17StageGate
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS
from utils.memory.v17_developer_memory_adapter import (
    read_v17_developer_default_memory_rollout,
    search_v17_default_developer_memories,
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
            'developer': {
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

    malformed = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}})
    malformed_decision = read_v17_developer_default_memory_rollout(uid='u1', db_client=malformed)
    assert malformed_decision.v17_default_developer_enabled is False
    assert malformed_decision.app_has_default_memory_grant is False
    assert malformed.collection_paths == []

    no_grant = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer': {}}}})
    no_grant_decision = read_v17_developer_default_memory_rollout(uid='u1', db_client=no_grant)
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_developer_enabled is False
    assert no_grant.collection_paths == []


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

    results = search_v17_default_developer_memories(
        uid='u1',
        query='coffee',
        limit=10,
        offset=0,
        db_client=db_client,
        rollout_capabilities=decision.rollout_capabilities,
        app_has_default_memory_grant=decision.app_has_default_memory_grant,
        now=now,
    )

    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['id'] for item in results] == ['fresh-short-term', 'long-term']
    assert [item['content'] for item in results] == ['coffee fresh short term', 'coffee long term']
    assert all(item['category'] == 'other' for item in results)
    assert all(item['visibility'] == 'private' for item in results)
    assert all(item['v17_default_memory'] is True for item in results)
    assert all(item['archive_default_visible'] is False for item in results)
    assert all(item['policy']['consumer'] == 'developer_api' for item in results)
    assert all(item['policy']['archive_capability'] is False for item in results)


def test_developer_default_v17_adapter_returns_none_when_rollout_or_grant_disabled_without_firestore_read():
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
            {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer': {}}}}
        ),
    )

    assert (
        search_v17_default_developer_memories(
            uid='u1',
            query='coffee',
            limit=10,
            offset=0,
            db_client=db_client,
            rollout_capabilities=disabled_decision.rollout_capabilities,
            app_has_default_memory_grant=disabled_decision.app_has_default_memory_grant,
            now=now,
        )
        is None
    )
    assert (
        search_v17_default_developer_memories(
            uid='u1',
            query='coffee',
            limit=10,
            offset=0,
            db_client=db_client,
            rollout_capabilities=grantless_decision.rollout_capabilities,
            app_has_default_memory_grant=grantless_decision.app_has_default_memory_grant,
            now=now,
        )
        is None
    )
    assert db_client.collection_paths == []
