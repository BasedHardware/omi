"""Historical source index: retraction skips the legacy scan only when no live row can name the donor."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from google.cloud.firestore_v1.transforms import Increment

from database import memories
from database import memory_source_index as msi
from utils.memory import memory_service as service_mod

UID = 'index-owner'
INDEX_PATH = ('users', UID, 'memory_state', msi.DOC)


class _Snapshot:
    def __init__(self, data, update_time):
        self.exists = data is not None
        self._data = data
        self.update_time = update_time

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def collection(self, name):
        return _Collection(self.db, self.path + (name,))

    def get(self, *args, **kwargs):
        self.db.reads.append(self.path)
        return _Snapshot(self.db.docs.get(self.path), self.db.update_times.get(self.path))

    def _commit(self, data):
        if self.db.fail_writes_to == self.path:
            raise RuntimeError('index datastore unavailable')
        self.db.clock += 1
        self.db.docs[self.path] = data
        self.db.update_times[self.path] = self.db.clock

    def set(self, data, merge=False):
        writers = data.get('writers')
        if self.db.fail_release and isinstance(writers, Increment) and writers.value < 0:
            raise RuntimeError('release lost')
        current = dict(self.db.docs.get(self.path) or {}) if merge else {}
        for key, value in data.items():
            current[key] = current.get(key, 0) + value.value if isinstance(value, Increment) else value
        self._commit(current)

    def update(self, data, option=None):
        if self.path not in self.db.docs:
            raise memories.FirestoreNotFound('missing')
        if option is not None and option.last_update_time != self.db.update_times.get(self.path):
            raise FailedPrecondition('stale')
        self._commit({**self.db.docs[self.path], **data})

    def create(self, data):
        if self.path in self.db.docs:
            raise AlreadyExists('exists')
        self._commit(dict(data))

    def delete(self):
        self.db.clock += 1
        self.db.docs.pop(self.path, None)


class _Collection:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def document(self, name):
        return _Ref(self.db, self.path + (name,))


class _Db:
    def __init__(self):
        self.docs = {}
        self.update_times = {}
        self.reads = []
        self.clock = 0
        self.fail_writes_to = None
        self.fail_release = False

    def collection(self, name):
        return _Collection(self, (name,))

    @staticmethod
    def write_option(*, last_update_time):
        return SimpleNamespace(last_update_time=last_update_time)


def _record(memory_id, conversation_id=None, evidence=()):
    return SimpleNamespace(
        memory=SimpleNamespace(
            id=memory_id,
            conversation_id=conversation_id,
            evidence=[SimpleNamespace(source_type=kind, source_id=source) for kind, source in evidence],
        )
    )


class _History:
    def __init__(self, records):
        self.records = records
        self.scans = 0
        self.during_scan = None

    def all_live(self, uid):
        assert uid == UID
        # The index must describe pages read after its epoch: never a memo replay.
        assert memories._historical_scan_memo.get() is None
        self.scans += 1
        if self.during_scan is not None:
            self.during_scan()
        return list(self.records)


@pytest.fixture
def world(monkeypatch):
    monkeypatch.delenv(msi.ENV, raising=False)
    db = _Db()
    for row_id in ('legacy-1', 'legacy-2', 'legacy-3'):
        db.docs[('users', UID, 'memories', row_id)] = {'id': row_id}
    history = _History(
        [
            _record('legacy-1', 'conv-old'),
            _record('legacy-2', None, [('conversation', 'conv-evidence'), ('chat', 'chat-1')]),
            _record('legacy-3', None),
        ]
    )
    service = service_mod.MemoryService(db_client=db)
    service.history = history
    return SimpleNamespace(db=db, history=history, service=service)


def _ids(world, conversation_id):
    return msi.retraction_historical_ids(
        UID,
        conversation_id,
        scan=lambda: world.history.all_live(UID),
        fresh_pages=memories.historical_scan_memo_suspended,
        firestore_client=world.db,
    )


def _events(event, outcome):
    return msi.EVENTS.labels(event=event, outcome=outcome)._value.get()


def test_first_retraction_scans_and_indexes_then_fresh_donors_skip_the_scan(world):
    skipped = _events('retraction_scan', 'skipped')
    unindexed = _events('retraction_scan', 'scanned_unindexed')

    assert _ids(world, 'donor-1') == []
    assert world.history.scans == 1
    stored = world.db.docs[INDEX_PATH]
    assert stored['indexed_epoch'] == stored['epoch'] == 0
    assert stored['key_count'] == 2
    # Content-free: short hashes only, never the conversation ids themselves.
    assert 'conv-old' not in stored['keys'] and 'chat-1' not in stored['keys']

    for donor in ('donor-2', 'donor-3', 'donor-4'):
        assert _ids(world, donor) == []
    assert world.history.scans == 1
    assert _events('retraction_scan', 'skipped') - skipped == 3
    assert _events('retraction_scan', 'scanned_unindexed') - unindexed == 1


def test_donor_named_by_live_rows_is_still_scanned_and_matched(world):
    _ids(world, 'donor-1')

    assert _ids(world, 'conv-old') == ['legacy-1']
    assert _ids(world, 'conv-evidence') == ['legacy-2']
    # Non-conversation evidence never matches, so it is not indexed either.
    assert _ids(world, 'chat-1') == []
    assert world.history.scans == 3


def test_retraction_still_cleans_up_rows_of_an_indexed_donor(world, monkeypatch):
    cleaned = []
    overrides = []
    monkeypatch.setattr(service_mod, 'retract_conversation_sourced_memories', lambda *a, **k: None)
    monkeypatch.setattr(service_mod, '_purge_required_canonical_projections', lambda *a, **k: None)
    monkeypatch.setattr(service_mod, 'purge_stale_review_conflicts_for_memories', lambda *a, **k: None)
    monkeypatch.setattr(service_mod, '_delete_historical_privacy_overrides', lambda *a, **k: None)
    monkeypatch.setattr(
        service_mod.HistoricalMemoryAdapter, 'cleanup', staticmethod(lambda uid, mid, **k: cleaned.append(mid))
    )
    monkeypatch.setattr(
        world.service, '_write_historical_overrides', lambda uid, ids, status: overrides.append(list(ids))
    )

    world.service.retract_conversation_memories(UID, 'fresh-donor', claim_destructive_gate=False)
    world.service.retract_conversation_memories(UID, 'conv-old', claim_destructive_gate=False)

    assert world.history.scans == 2  # the fresh donor built the index; the named donor still scanned
    assert cleaned == ['legacy-1']
    assert overrides == [['legacy-1']]


def test_a_write_that_can_add_a_source_invalidates_the_index(world):
    _ids(world, 'donor-1')
    world.history.records.append(_record('legacy-4', 'conv-new'))
    world.db.docs[('users', UID, 'memories', 'legacy-4')] = {'id': 'legacy-4'}

    # A real decorated writer bumps the epoch before and after its write.
    memories.change_memory_visibility(UID, 'legacy-4', 'private', firestore_client=world.db)
    assert world.db.docs[INDEX_PATH]['epoch'] == 2

    assert _ids(world, 'conv-new') == ['legacy-4']
    assert world.history.scans == 2
    assert world.db.docs[INDEX_PATH]['indexed_epoch'] == 2
    assert _ids(world, 'donor-2') == []
    assert world.history.scans == 2


def test_deletes_keep_the_index_valid_because_they_only_shrink_it(world):
    _ids(world, 'donor-1')
    memories.delete_memory(UID, 'legacy-1', firestore_client=world.db)

    assert world.db.docs[INDEX_PATH]['epoch'] == 0
    assert _ids(world, 'donor-2') == []
    assert world.history.scans == 1


def test_failed_pre_write_bump_aborts_the_write(world):
    world.db.fail_writes_to = INDEX_PATH
    with pytest.raises(RuntimeError):
        memories.change_memory_visibility(UID, 'legacy-1', 'private', firestore_client=world.db)
    assert 'visibility' not in world.db.docs[('users', UID, 'memories', 'legacy-1')]


def test_write_during_the_scan_prevents_storing_a_stale_index(world):
    _ids(world, 'donor-1')
    msi.bump(UID, world.db, 0)  # stale existing index
    raced = _events('build', 'raced')
    world.history.during_scan = lambda: msi.bump(UID, world.db, 0)

    assert _ids(world, 'donor-2') == []
    assert _events('build', 'raced') - raced == 1
    world.history.during_scan = None
    assert _ids(world, 'donor-3') == []
    assert world.history.scans == 3  # the raced build was never trusted


def test_first_build_loses_to_a_writer_that_created_the_document(world):
    raced = _events('build', 'raced')
    world.history.during_scan = lambda: msi.bump(UID, world.db, 0)

    assert _ids(world, 'donor-1') == []
    assert _events('build', 'raced') - raced == 1
    assert 'keys' not in world.db.docs[INDEX_PATH]


def test_kill_switch_scans_every_time_without_touching_the_index(world, monkeypatch):
    monkeypatch.setenv(msi.ENV, 'off')
    for donor in ('donor-1', 'donor-2'):
        assert _ids(world, donor) == []
    assert world.history.scans == 2
    assert INDEX_PATH not in world.db.docs
    assert INDEX_PATH not in world.db.reads


def test_unreadable_index_falls_back_to_the_scan(world, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError('index unavailable')

    monkeypatch.setattr(msi, 'read', broken)
    assert _ids(world, 'conv-old') == ['legacy-1']
    assert world.history.scans == 1


def test_oversized_index_is_not_stored(world, monkeypatch):
    monkeypatch.setattr(msi, 'MAX_KEYS', 1)
    _ids(world, 'donor-1')
    assert INDEX_PATH not in world.db.docs
    _ids(world, 'donor-2')
    assert world.history.scans == 2


def test_scan_during_an_in_flight_writer_is_never_stored(world):
    writer_active = _events('build', 'writer_active')
    msi.bump(UID, world.db, 1)  # a writer claimed and is mid-write

    assert _ids(world, 'donor-1') == []
    assert _events('build', 'writer_active') - writer_active == 1
    assert 'keys' not in world.db.docs[INDEX_PATH]


def test_lost_writer_release_keeps_the_owner_on_the_full_scan(world):
    _ids(world, 'donor-1')
    world.db.fail_release = True
    memories.change_memory_visibility(UID, 'legacy-1', 'private', firestore_client=world.db)
    world.db.fail_release = False
    assert world.db.docs[INDEX_PATH]['writers'] == 1

    # No build may claim the post-write state: a lost release and a write still
    # in flight look the same, so the counter is never reset by a reader.
    for donor in ('donor-2', 'donor-3', 'donor-4'):
        assert _ids(world, donor) == []
    assert world.history.scans == 4
    assert world.db.docs[INDEX_PATH]['writers'] == 1

    # Deleting the document is the operator recovery; the next scan rebuilds.
    del world.db.docs[INDEX_PATH]
    _ids(world, 'donor-5')
    assert _ids(world, 'donor-6') == []
    assert world.history.scans == 5


def test_subject_reassignment_holds_the_fence(monkeypatch):
    from database import entities

    bumps = []
    monkeypatch.setattr(entities.kg_db, 'db', MagicMock())
    monkeypatch.setattr(msi, 'bump', lambda uid, _client, writers: bumps.append(writers))
    monkeypatch.setattr(entities.memory_ledger, 'append_commit', lambda *a, **k: bumps.append('commit') or 'ok')

    assert entities.reassign_fact_subject(UID, 'fact-1', None, 'person:p1') == 'ok'
    assert bumps == [1, 'commit', -1]


def test_account_wipe_drops_a_late_index_document(monkeypatch):
    from database import batch_pipeline_purge, user_data_deletion

    monkeypatch.setattr(batch_pipeline_purge, 'purge_batch_owner', lambda uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: MagicMock())
    deleted = []
    user_ref = SimpleNamespace(
        get=lambda: SimpleNamespace(exists=False),
        collections=lambda: [],
        collection=lambda name: SimpleNamespace(
            document=lambda doc: SimpleNamespace(delete=lambda: deleted.append((name, doc)))
        ),
    )
    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda uid: user_ref))
    user_data_deletion.purge_user_subtree(UID, client, lambda *a, **k: None)
    assert ('memory_state', msi.DOC) in deleted


def test_scan_inside_a_memo_scope_reads_fresh_pages(world, monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"historical_scan_memo":100}')
    with memories.historical_scan_memo_scope(UID):
        assert memories._historical_scan_memo.get() is not None
        assert _ids(world, 'donor-1') == []
        assert memories._historical_scan_memo.get() is not None
    assert world.history.scans == 1
