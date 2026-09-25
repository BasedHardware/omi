"""Firestore single-document read-site attribution (omi_firestore_document_reads_by_site_total).

Regression coverage for the NOT_FOUND attribution metric: a `read_site` passed into
`conversations_db.get_conversation` (and the batch helper `_get_conversations_by_id`)
must survive the `@prepare_for_read` / `@with_photos` decorator chain and land on the
right outcome (hit/miss) with the right count, without changing what the helpers
return. Also covers the `record_document_read` primitive itself (hit vs miss labeling,
and that an internal failure never propagates) and the uncached account-deletion fence
in `database/account_deletion_marker.py`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import database.conversations as conversations_db
import database.users as users_db
from database import account_deletion_marker as deletion_marker
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite

# ---------------------------------------------------------------------------
# record_document_read primitive
# ---------------------------------------------------------------------------


class _RecordingChild:
    def __init__(self, key):
        self.key = key
        self.inc_calls: List[float] = []

    def inc(self, amount=1):
        self.inc_calls.append(amount)


def test_record_document_read_labels_hit_and_miss_distinctly(monkeypatch):
    from database import firestore_read_metrics as metrics

    children: Dict[tuple, _RecordingChild] = {}

    def _labels(**kwargs):
        key = (kwargs['site'], kwargs['outcome'])
        return children.setdefault(key, _RecordingChild(key))

    monkeypatch.setattr(metrics.FIRESTORE_DOCUMENT_READS, 'labels', _labels)

    metrics.record_document_read(metrics.FirestoreReadSite.UNATTRIBUTED, metrics.FirestoreReadOutcome.HIT)
    metrics.record_document_read(metrics.FirestoreReadSite.UNATTRIBUTED, metrics.FirestoreReadOutcome.MISS, count=3)

    assert children[('unattributed', 'hit')].inc_calls == [1]
    assert children[('unattributed', 'miss')].inc_calls == [3]


def test_record_document_read_swallows_internal_error(monkeypatch):
    """A metrics failure must never break the read path it observes."""
    from database import firestore_read_metrics as metrics

    def _boom(**_kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(metrics.FIRESTORE_DOCUMENT_READS, 'labels', _boom)

    # Must not raise.
    metrics.record_document_read(metrics.FirestoreReadSite.UNATTRIBUTED, metrics.FirestoreReadOutcome.MISS)


# ---------------------------------------------------------------------------
# get_conversation — proves the read_site label survives
# @prepare_for_read + @with_photos, per call site.
# ---------------------------------------------------------------------------


class _Snapshot:
    def __init__(self, data: Optional[Dict[str, Any]]):
        self._data = data
        self.update_time = None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _DocRef:
    def __init__(self, data: Optional[Dict[str, Any]]):
        self._data = data

    def get(self):
        return _Snapshot(self._data)


class _ConversationsCollection:
    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self._docs = docs

    def document(self, doc_id: str):
        return _DocRef(self._docs.get(doc_id))


class _UserRef:
    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self._docs = docs

    def collection(self, name: str):
        assert name == 'conversations'
        return _ConversationsCollection(self._docs)


class _FakeSingleDocDB:
    """Enough of the Firestore client surface for get_conversation.

    Every conversation carries ``has_photos: False`` so @with_photos takes its
    authoritative-marker shortcut instead of reaching for a photos subcollection
    this fake does not implement.
    """

    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self._docs = docs

    def collection(self, name: str):
        assert name == 'users'

        class _Users:
            def __init__(self, docs):
                self._docs = docs

            def document(self, _uid):
                return _UserRef(self._docs)

        return _Users(self._docs)


def _spy_record_document_read(monkeypatch, module):
    recorded: List[tuple] = []
    monkeypatch.setattr(
        module,
        'record_document_read',
        lambda site, outcome, count=1: recorded.append((site, outcome, count)),
    )
    return recorded


def test_get_conversation_hit_records_the_passed_site_through_decorators(monkeypatch):
    docs = {'conv-1': {'id': 'conv-1', 'has_photos': False, 'title': 'hello'}}
    monkeypatch.setattr(conversations_db, 'db', _FakeSingleDocDB(docs))
    recorded = _spy_record_document_read(monkeypatch, conversations_db)

    result = conversations_db.get_conversation('user-1', 'conv-1', read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE)

    assert result is not None
    assert result['id'] == 'conv-1'
    assert recorded == [(FirestoreReadSite.LISTEN_CLIENT_ID_PROBE, FirestoreReadOutcome.HIT, 1)]


def test_get_conversation_miss_records_the_passed_site_through_decorators(monkeypatch):
    monkeypatch.setattr(conversations_db, 'db', _FakeSingleDocDB({}))
    recorded = _spy_record_document_read(monkeypatch, conversations_db)

    result = conversations_db.get_conversation(
        'user-1', 'does-not-exist', read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE
    )

    assert result is None
    assert recorded == [(FirestoreReadSite.LISTEN_CLIENT_ID_PROBE, FirestoreReadOutcome.MISS, 1)]


def test_get_conversation_defaults_to_unattributed_when_no_site_is_passed(monkeypatch):
    """Guards the honesty of the coverage gap: an un-migrated caller must not
    silently disappear from the metric, and must not silently claim a site
    either."""
    docs = {'conv-1': {'id': 'conv-1', 'has_photos': False}}
    monkeypatch.setattr(conversations_db, 'db', _FakeSingleDocDB(docs))
    recorded = _spy_record_document_read(monkeypatch, conversations_db)

    conversations_db.get_conversation('user-1', 'conv-1')

    assert recorded == [(FirestoreReadSite.UNATTRIBUTED, FirestoreReadOutcome.HIT, 1)]


def test_get_conversation_return_value_is_unaffected_by_read_site(monkeypatch):
    """No behaviour change: the site label must be purely observational."""
    docs = {'conv-1': {'id': 'conv-1', 'has_photos': False, 'title': 'hello'}}
    monkeypatch.setattr(conversations_db, 'db', _FakeSingleDocDB(docs))

    default_result = conversations_db.get_conversation('user-1', 'conv-1')
    explicit_result = conversations_db.get_conversation(
        'user-1', 'conv-1', read_site=FirestoreReadSite.MEETING_RECEIPT_RECONCILER
    )

    assert default_result == explicit_result


# ---------------------------------------------------------------------------
# _get_conversations_by_id (and the get_conversations_by_id_without_photos
# wrapper) — batch hit/miss counting for db.get_all.
# ---------------------------------------------------------------------------


class _BatchDoc:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _BatchDocRef:
    def __init__(self, doc_id: str):
        self.id = doc_id


class _BatchConversationsCollection:
    def document(self, doc_id: str):
        return _BatchDocRef(doc_id)


class _FakeBatchDB:
    def __init__(self, docs: Dict[str, Dict[str, Any]]):
        self._docs = docs

    def collection(self, name: str):
        assert name == 'users'

        class _Users:
            def document(_self, _uid):
                class _UserRefBatch:
                    def collection(_self2, coll_name):
                        assert coll_name == 'conversations'
                        return _BatchConversationsCollection()

                return _UserRefBatch()

        return _Users()

    def get_all(self, refs):
        return [_BatchDoc(ref.id, self._docs.get(ref.id)) for ref in refs]


def test_batch_helper_records_hit_and_miss_counts_for_mixed_ids(monkeypatch):
    docs = {
        'a': {'id': 'a', 'has_photos': False},
        'b': {'id': 'b', 'has_photos': False},
    }
    monkeypatch.setattr(conversations_db, 'db', _FakeBatchDB(docs))
    recorded = _spy_record_document_read(monkeypatch, conversations_db)

    result = conversations_db.get_conversations_by_id_without_photos(
        'user-1',
        ['a', 'b', 'missing-1', 'missing-2', 'missing-3'],
        read_site=FirestoreReadSite.RAG_HYDRATION,
    )

    assert sorted(c['id'] for c in result) == ['a', 'b']
    assert (FirestoreReadSite.RAG_HYDRATION, FirestoreReadOutcome.HIT, 2) in recorded
    assert (FirestoreReadSite.RAG_HYDRATION, FirestoreReadOutcome.MISS, 3) in recorded


def test_batch_helper_omits_zero_outcome_bucket(monkeypatch):
    """All hits should not emit a spurious miss(count=0) sample, and vice versa."""
    docs = {'a': {'id': 'a', 'has_photos': False}}
    monkeypatch.setattr(conversations_db, 'db', _FakeBatchDB(docs))
    recorded = _spy_record_document_read(monkeypatch, conversations_db)

    conversations_db.get_conversations_by_id_without_photos('user-1', ['a'], read_site=FirestoreReadSite.RAG_HYDRATION)

    assert recorded == [(FirestoreReadSite.RAG_HYDRATION, FirestoreReadOutcome.HIT, 1)]


def test_batch_helper_return_value_is_unaffected_by_read_site(monkeypatch):
    docs = {'a': {'id': 'a', 'has_photos': False}}
    monkeypatch.setattr(conversations_db, 'db', _FakeBatchDB(docs))

    default_result = conversations_db.get_conversations_by_id_without_photos('user-1', ['a'])
    explicit_result = conversations_db.get_conversations_by_id_without_photos(
        'user-1', ['a'], read_site=FirestoreReadSite.RAG_HYDRATION
    )

    assert default_result == explicit_result


# ---------------------------------------------------------------------------
# database/account_deletion_marker.py: get_user_deletion_wipe_status — the uncached deletion
# fence. Instrumentation must not touch its caching/behaviour.
# ---------------------------------------------------------------------------


class _DeletionSnapshot:
    def __init__(self, exists: bool, data: Optional[Dict[str, Any]] = None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class _DeletionDocRef:
    def __init__(self, snapshot: _DeletionSnapshot):
        self._snapshot = snapshot

    def get(self):
        return self._snapshot


class _DeletionCollection:
    def __init__(self, snapshot: _DeletionSnapshot):
        self._snapshot = snapshot

    def document(self, _uid):
        return _DeletionDocRef(self._snapshot)


class _DeletionClient:
    def __init__(self, snapshot: _DeletionSnapshot):
        self._snapshot = snapshot

    def collection(self, name):
        assert name == 'account_deletions'
        return _DeletionCollection(self._snapshot)


def test_user_deletion_wipe_status_hit_records_hit_and_keeps_behaviour(monkeypatch):
    recorded = _spy_record_document_read(monkeypatch, deletion_marker)
    client = _DeletionClient(_DeletionSnapshot(exists=True, data={'wipe_status': 'running'}))

    status = users_db.get_user_deletion_wipe_status('uid-1', firestore_client=client)

    assert status == 'running'
    assert recorded == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.HIT, 1)]


def test_user_deletion_wipe_status_miss_records_miss_and_keeps_behaviour(monkeypatch):
    recorded = _spy_record_document_read(monkeypatch, deletion_marker)
    client = _DeletionClient(_DeletionSnapshot(exists=False))

    status = users_db.get_user_deletion_wipe_status('uid-1', firestore_client=client)

    assert status is None
    assert recorded == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.MISS, 1)]
