from datetime import datetime, timedelta, timezone

import pytest

from jobs.short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    ShortTermLifecycleTransitionRecord,
    fetch_short_term_memory_items_firestore,
    run_short_term_lifecycle_firestore,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, transaction=None):
        return _Snapshot(self._db_client.docs.get(self.path))


class _CollectionRef:
    def __init__(self, db_client, path, filters=None, limit_count=None):
        self._db_client = db_client
        self.path = path
        self._filters = list(filters or [])
        self._limit_count = limit_count

    def where(self, field_path, op_string, value):
        return _CollectionRef(
            self._db_client,
            self.path,
            [*self._filters, (field_path, op_string, value)],
            limit_count=self._limit_count,
        )

    def limit(self, limit_count):
        return _CollectionRef(self._db_client, self.path, self._filters, limit_count=limit_count)

    def stream(self):
        prefix = f'{self.path}/'
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            if all(self._matches(data, field_path, op_string, value) for field_path, op_string, value in self._filters):
                snapshots.append(_Snapshot(data))
        if self._limit_count is not None:
            snapshots = snapshots[: self._limit_count]
        return snapshots

    def _matches(self, data, field_path, op_string, value):
        if op_string != '==':
            raise AssertionError(f'unexpected query operator {op_string}')
        return data.get(field_path) == value


class _Transaction:
    def __init__(self, db_client):
        self._db_client = db_client
        self._read_only = False
        self._max_attempts = 1
        self._id = None
        self._sets = []

    def set(self, document_ref, payload):
        self._sets.append((document_ref.path, dict(payload)))

    def _begin(self, retry_id=None):
        self._id = retry_id or 'txn-1'
        self._sets = []

    def _commit(self):
        for path, payload in self._sets:
            self._db_client.docs[path] = payload
        self._sets = []

    def _rollback(self):
        self._sets = []
        self._id = None

    def _clean_up(self):
        self._id = None


class _FirestoreFake:
    def __init__(self):
        self.docs = {}

    def transaction(self):
        return _Transaction(self)

    def document(self, path):
        return _DocumentRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)


def _record(**overrides):
    data = {
        'uid': 'u1',
        'memory_item_id': 'stale-short-term',
        'outcome': 'remain_short_term',
        'reason': 'short_term_expired_requires_lifecycle_decision',
        'run_id': 'lifecycle-run-1',
        'evaluated_at': '2026-06-19T12:00:00+00:00',
        'audit_metadata': {
            'policy_version': 'short_term_lifecycle_v1',
            'source_refs': [
                {
                    'evidence_id': 'ev1',
                    'source_id': 'conversation-1',
                    'source_type': 'conversation',
                    'source_version': 'v1',
                    'source_state': 'active',
                }
            ],
            'default_access_allowed': False,
            'requires_lifecycle_decision': True,
        },
        'idempotency_key': 'short-term-lifecycle:u1:stale-short-term:remain_short_term:abc',
        'fingerprint': 'f' * 64,
    }
    data.update(overrides)
    return ShortTermLifecycleTransitionRecord(**data)


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise lifecycle audits.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, captured_at=None, **overrides) -> MemoryItem:
    captured_at = captured_at or datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending if tier == MemoryTier.short_term else ProcessingState.processed,
        'content': f'{memory_id} content',
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
    return MemoryItem(**data)


def _stored_item(item: MemoryItem):
    return item.model_dump(mode='json')


def test_firestore_lifecycle_transition_store_creates_deterministic_idempotent_record():
    db_client = _FirestoreFake()
    store = FirestoreShortTermLifecycleTransitionStore(
        db_client=db_client,
        now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
    )
    record = _record()

    first = store.persist_short_term_lifecycle_transition(record)
    second = store.persist_short_term_lifecycle_transition(record)

    assert first.created is True
    assert second.created is False
    assert second.record == record
    assert len(db_client.docs) == 1
    [(path, payload)] = list(db_client.docs.items())
    assert path.startswith('users/u1/short_term_lifecycle_transitions/stl_')
    assert payload['uid'] == 'u1'
    assert payload['memory_item_id'] == 'stale-short-term'
    assert payload['outcome'] == 'remain_short_term'
    assert payload['reason'] == 'short_term_expired_requires_lifecycle_decision'
    assert payload['run_id'] == 'lifecycle-run-1'
    assert payload['source_refs'] == record.audit_metadata['source_refs']
    assert payload['audit_metadata'] == record.audit_metadata
    assert payload['idempotency_key'] == record.idempotency_key
    assert payload['fingerprint'] == record.fingerprint
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False
    assert payload['created_at'] == datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc).isoformat()


def test_firestore_lifecycle_transition_store_rejects_same_key_different_fingerprint():
    db_client = _FirestoreFake()
    store = FirestoreShortTermLifecycleTransitionStore(
        db_client=db_client,
        now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
    )
    record = _record()
    store.persist_short_term_lifecycle_transition(record)

    with pytest.raises(ValueError, match='idempotency key payload mismatch'):
        store.persist_short_term_lifecycle_transition(_record(fingerprint='e' * 64))

    assert len(db_client.docs) == 1
    [payload] = db_client.docs.values()
    assert payload['fingerprint'] == record.fingerprint


def test_fetch_short_term_memory_items_firestore_queries_authoritative_short_term_items_only():
    db_client = _FirestoreFake()
    stale_short_term = _memory_item('stale-short-term', captured_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))
    fresh_short_term = _memory_item('fresh-short-term')
    archive = _memory_item('archive', tier=MemoryTier.archive)
    long_term = _memory_item('long-term', tier=MemoryTier.long_term)
    db_client.docs = {
        f'users/u1/memory_items/{stale_short_term.memory_id}': _stored_item(stale_short_term),
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        f'users/u1/memory_items/{archive.memory_id}': _stored_item(archive),
        f'users/u1/memory_items/{long_term.memory_id}': _stored_item(long_term),
    }

    items = fetch_short_term_memory_items_firestore(uid='u1', db_client=db_client)

    assert [item.memory_id for item in items] == ['fresh-short-term', 'stale-short-term']
    assert all(item.tier == MemoryTier.short_term for item in items)


def test_fetch_short_term_memory_items_firestore_applies_bounded_limit_before_runner_persistence():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    stale_a = _memory_item('a-stale-short-term', captured_at=now - timedelta(days=45))
    stale_b = _memory_item('b-stale-short-term', captured_at=now - timedelta(days=45))
    db_client.docs = {
        f'users/u1/memory_items/{stale_a.memory_id}': _stored_item(stale_a),
        f'users/u1/memory_items/{stale_b.memory_id}': _stored_item(stale_b),
    }

    report = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1', limit=1)

    transition_docs = {
        path: payload
        for path, payload in db_client.docs.items()
        if path.startswith('users/u1/short_term_lifecycle_transitions/')
    }
    assert report.created_count == 1
    assert len(transition_docs) == 1
    [payload] = transition_docs.values()
    assert payload['memory_item_id'] == 'a-stale-short-term'
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False


def test_concrete_firestore_lifecycle_runner_persists_only_required_short_term_transitions_idempotently():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    stale_short_term = _memory_item('stale-short-term', captured_at=now - timedelta(days=45))
    fresh_short_term = _memory_item('fresh-short-term', captured_at=now - timedelta(days=1))
    archive = _memory_item('archive', tier=MemoryTier.archive)
    db_client.docs = {
        f'users/u1/memory_items/{stale_short_term.memory_id}': _stored_item(stale_short_term),
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        f'users/u1/memory_items/{archive.memory_id}': _stored_item(archive),
    }

    first = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1')
    second = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1')

    transition_docs = {
        path: payload
        for path, payload in db_client.docs.items()
        if path.startswith('users/u1/short_term_lifecycle_transitions/')
    }
    assert first.created_count == 1
    assert first.existing_count == 0
    assert first.skipped_memory_ids == ['fresh-short-term']
    assert second.created_count == 0
    assert second.existing_count == 1
    assert second.skipped_memory_ids == ['fresh-short-term']
    assert len(transition_docs) == 1
    [payload] = transition_docs.values()
    assert payload['memory_item_id'] == 'stale-short-term'
    assert payload['outcome'] == 'remain_short_term'
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False
