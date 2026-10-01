"""Regression test: deleting a conversation must purge every subcollection under it.

``delete_conversation`` used to purge only the ``photos`` subcollection before
deleting the document. A conversation owns more children than that — the
per-provider post-processing transcripts (``deepgram_streaming``,
``soniox_streaming``, ``speechmatics_streaming``, ``fal_whisperx``, ``prerecorded``, which store
verbatim ``TranscriptSegment`` text), the Hume emotion predictions, and the
``analytics_markers`` marker written by the memory-extraction telemetry. Firestore
does not cascade, so those survived the delete as documents no query can reach:
the account-deletion wipe walks *existing* documents, and the deleted conversation
is not one, so its orphans could never be removed either.
"""

from __future__ import annotations

import pytest

from database import conversations as conversations_db
from utils.conversations import merge_conversations


@pytest.fixture(scope="module", autouse=True)
def warm_merge_cleanup():
    from utils.conversations import merge_conversations


class _FakeBatch:
    def __init__(self, store: "_FakeFirestore"):
        self._store = store
        self._pending: list[_FakeDocumentReference] = []

    def delete(self, doc_ref: "_FakeDocumentReference") -> None:
        self._pending.append(doc_ref)

    def commit(self) -> None:
        for doc_ref in self._pending:
            doc_ref.delete()
        self._pending = []


class _FakeQuery:
    def __init__(self, collection: "_FakeCollectionReference", limit: int | None = None):
        self._collection = collection
        self._limit = limit

    def limit(self, count: int) -> "_FakeQuery":
        return _FakeQuery(self._collection, count)

    def stream(self):
        docs = [doc for doc in self._collection.documents.values() if doc.exists]
        return docs if self._limit is None else docs[: self._limit]


class _FakeDocumentReference:
    def __init__(self, path: str, store: "_FakeFirestore"):
        self.path = path
        self._store = store
        self.exists = True
        self.data = {}
        self.subcollections: dict[str, _FakeCollectionReference] = {}

    # Snapshots streamed out of a query carry `.reference`; the fake document is
    # its own snapshot so the production loop reads the same attribute it does
    # against the real SDK.
    @property
    def reference(self) -> "_FakeDocumentReference":
        return self

    def collection(self, name: str) -> "_FakeCollectionReference":
        if name not in self.subcollections:
            self.subcollections[name] = _FakeCollectionReference(f"{self.path}/{name}", self._store)
        return self.subcollections[name]

    def collections(self):
        # Firestore only lists subcollections that still hold documents.
        return [sub for sub in self.subcollections.values() if any(d.exists for d in sub.documents.values())]

    def get(self):
        return self

    def to_dict(self):
        return self.data if self.exists else None

    def delete(self) -> None:
        self.exists = False
        self._store.deleted.append(self.path)


class _FakeCollectionReference:
    def __init__(self, path: str, store: "_FakeFirestore"):
        self.path = path
        self._store = store
        self.documents: dict[str, _FakeDocumentReference] = {}

    def document(self, doc_id: str) -> _FakeDocumentReference:
        if doc_id not in self.documents:
            self.documents[doc_id] = _FakeDocumentReference(f"{self.path}/{doc_id}", self._store)
        return self.documents[doc_id]

    def limit(self, count: int) -> _FakeQuery:
        return _FakeQuery(self, count)

    def stream(self):
        return _FakeQuery(self).stream()


class _FakeFirestore:
    def __init__(self):
        self.root: dict[str, _FakeCollectionReference] = {}
        self.deleted: list[str] = []

    def collection(self, name: str) -> _FakeCollectionReference:
        if name not in self.root:
            self.root[name] = _FakeCollectionReference(name, self)
        return self.root[name]

    def batch(self) -> _FakeBatch:
        return _FakeBatch(self)


def _seed_conversation(store: _FakeFirestore) -> _FakeDocumentReference:
    conversation = store.collection('users').document('uid-1').collection('conversations').document('conv-1')
    conversation.collection('photos').document('photo-1')
    conversation.collection('deepgram_streaming').document('seg-1')
    conversation.collection('deepgram_streaming').document('seg-2')
    conversation.collection('fal_whisperx').document('seg-1')
    conversation.collection('prerecorded').document('seg-1')
    conversation.collection('analytics_markers').document('conversation_memories_extracted')
    return conversation


@pytest.fixture
def store(monkeypatch) -> _FakeFirestore:
    fake = _FakeFirestore()
    monkeypatch.setattr(conversations_db, 'db', fake)
    return fake


def test_delete_conversation_purges_every_subcollection(store):
    """Before the fix only `photos` was purged; the transcript segments and the
    analytics marker survived as unreachable documents."""
    conversation = _seed_conversation(store)

    conversations_db.delete_conversation('uid-1', 'conv-1')

    assert not conversation.exists
    survivors = [
        doc.path for sub in conversation.subcollections.values() for doc in sub.documents.values() if doc.exists
    ]
    assert survivors == []


def test_delete_conversation_descends_into_nested_subcollections(store):
    """A child document with its own children is purged depth-first, so nothing is
    left dangling under a document that is itself about to be deleted."""
    conversation = _seed_conversation(store)
    nested = conversation.collection('photos').document('photo-1').collection('ocr').document('line-1')

    conversations_db.delete_conversation('uid-1', 'conv-1')

    assert not nested.exists
    # Depth-first: the nested document goes before the parent that owns it.
    assert store.deleted.index(nested.path) < store.deleted.index('users/uid-1/conversations/conv-1/photos/photo-1')


def test_delete_conversation_without_children_still_deletes_the_document(store):
    conversation = store.collection('users').document('uid-1').collection('conversations').document('conv-1')

    conversations_db.delete_conversation('uid-1', 'conv-1')

    assert not conversation.exists
    assert store.deleted == ['users/uid-1/conversations/conv-1']


def test_delete_capture_cascades_retained_bridge_sources(store, monkeypatch):
    from utils.conversations import merge_conversations

    conversation = _seed_conversation(store)
    conversation.data['sync_merged_from'] = ['donor-a', 'donor-b']
    removed = []
    monkeypatch.setattr(
        merge_conversations, '_delete_conversation_and_related_data', lambda uid, cid, **kw: removed.append(cid)
    )
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: conversation.data)
    merge_conversations.delete_conversation_with_sync_sources('uid-1', 'conv-1')
    assert removed == ['donor-a', 'donor-b']
    assert not conversation.exists


def test_database_hard_delete_does_not_read_or_orchestrate_ancestors(store):
    conversation = _seed_conversation(store)

    def unexpected_read():
        raise AssertionError('DB hard delete must not inspect ancestor metadata')

    conversation.get = unexpected_read
    conversations_db.delete_conversation('uid-1', 'conv-1')
    assert not conversation.exists


def test_failed_ancestor_purge_keeps_survivor_for_retry(store, monkeypatch):
    from utils.conversations import merge_conversations

    conversation = _seed_conversation(store)
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda *a: {'sync_merged_from': ['donor']})

    def fail(*a, **kw):
        raise RuntimeError('retraction unavailable')

    monkeypatch.setattr(merge_conversations, '_delete_conversation_and_related_data', fail)
    with pytest.raises(RuntimeError, match='retraction unavailable'):
        merge_conversations.delete_conversation_with_sync_sources('uid-1', 'conv-1')
    assert conversation.exists


def test_smart_merge_audit_survives_real_survivor_and_donor_delete_primitives(store, monkeypatch):
    survivor = _seed_conversation(store)
    user = store.collection('users').document('uid-1')
    donor = user.collection('conversations').document('donor-a')
    donor.data = {'deleted': True, 'smart_merge': {'role': 'donor', 'survivor_id': 'conv-1'}}
    audit = user.collection('smart_merge_audit').document('donor-a')
    audit.data = {'donor_id': 'donor-a', 'survivor_id': 'conv-1', 'p_same': 0.5}
    survivor.data['sync_merged_from'] = ['donor-a']
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: survivor.data)
    monkeypatch.setattr(
        merge_conversations,
        '_delete_conversation_and_related_data',
        lambda uid, cid, **kw: conversations_db.delete_conversation(uid, cid),
    )
    merge_conversations.delete_conversation_with_sync_sources('uid-1', 'conv-1')
    assert not survivor.exists and not donor.exists
    assert audit.exists and audit.data['p_same'] == 0.5


def test_restored_donor_cleanup_runs_exactly_once_through_the_delegation(store, monkeypatch):
    """The inner _delete_conversation_and_related_data hook and the delegated
    delete_conversation_with_sync_sources must not both run the restored-donor
    cleanup: the second pass would rescan GCS and rebuild audio for a donor
    whose originals are already gone, and its failure would leave a visible
    but partially purged donor."""
    from types import SimpleNamespace

    from utils.conversations import merge_conversations

    conversation = _seed_conversation(store)
    conversation.data['smart_merge'] = {'role': 'unmerged', 'survivor_id': 'survivor-1'}
    conversation.data['id'] = 'conv-1'
    calls = []
    monkeypatch.setattr(merge_conversations, 'cleanup_restored_donor', lambda uid, donor: calls.append(donor['id']))
    # Keep the heavyweight inner seams inert; only the handoff is under test.
    monkeypatch.setattr(
        merge_conversations,
        'MemoryService',
        lambda **kw: SimpleNamespace(retract_conversation_memories=lambda *a, **kw: None),
    )
    monkeypatch.setattr(merge_conversations, 'retraction_can_be_skipped', lambda *a, **kw: True)
    monkeypatch.setattr(merge_conversations, 'delete_conversation_audio_files', lambda uid, cid: None)
    monkeypatch.setattr(merge_conversations, 'delete_vector', lambda uid, cid: None)
    monkeypatch.setattr(conversations_db, 'delete_conversation_photos', lambda uid, cid: None)
    import database.action_items as action_items_db

    monkeypatch.setattr(action_items_db, 'get_action_items_by_conversation', lambda uid, cid: [])
    monkeypatch.setattr(action_items_db, 'delete_action_items_for_conversation', lambda uid, cid: None)
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: conversation.data)

    # Direct route (router/frame evidence): the entry hook owns the cleanup.
    merge_conversations.delete_conversation_with_sync_sources('uid-1', 'conv-1')
    assert calls == ['conv-1']

    # Internal delegation from _delete_conversation_and_related_data: the inner
    # hook already ran; the delegated entry must not repeat it.
    delegated = []
    monkeypatch.setattr(
        merge_conversations,
        'delete_conversation_with_sync_sources',
        lambda uid, cid, **kw: delegated.append(kw.get('_restored_donor_cleaned')),
    )
    merge_conversations._delete_conversation_and_related_data('uid-1', 'conv-1')
    assert calls == ['conv-1', 'conv-1']
    assert delegated == [True]
