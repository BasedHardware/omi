from datetime import datetime, timezone

import pytest

from jobs.v17_short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    ShortTermLifecycleTransitionRecord,
)


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
