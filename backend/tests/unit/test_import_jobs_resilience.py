"""Unit tests for import_jobs database resilience, input sanitization, and error boundaries."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import NotFound

import database.import_jobs as import_jobs_db


class _FakeSnapshot:
    def __init__(self, doc_id: str, data: object, exists: bool = True):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeTransaction:
    def update(self, doc_ref, updates: dict):
        doc_ref.update(updates)


class _FakeDocRef:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self.id = doc_id

    def set(self, data: dict):
        self._store[self.id] = dict(data)

    def get(self, transaction=None):
        if self.id in self._store:
            return _FakeSnapshot(self.id, self._store[self.id], exists=True)
        return _FakeSnapshot(self.id, None, exists=False)

    def update(self, updates: dict):
        if self.id not in self._store:
            raise NotFound(f'Job {self.id} not found')
        if isinstance(self._store[self.id], dict):
            self._store[self.id].update(updates)

    def delete(self):
        if self.id not in self._store:
            raise NotFound(f'Job {self.id} not found')
        self._store.pop(self.id, None)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store
        self._limit = 50
        self.last_limit = None

    def document(self, doc_id: str):
        return _FakeDocRef(self._store, doc_id)

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count: int):
        self._limit = count
        self.last_limit = count
        return self

    def stream(self):
        items = list(self._store.items())[: self._limit]
        for doc_id, data in items:
            yield _FakeSnapshot(doc_id, data, exists=True)


class _FakeFirestoreClient:
    def __init__(self):
        self.store = {}
        self.collection_ref = _FakeCollection(self.store)

    def collection(self, name: str):
        assert name == 'import_jobs'
        return self.collection_ref

    def transaction(self):
        return _FakeTransaction()


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(import_jobs_db.firestore, 'transactional', lambda fn: fn)
    return _FakeFirestoreClient()


def test_create_import_job_trims_identifiers_and_writes(fake_client):
    job_id = import_jobs_db.create_import_job(
        {'id': '  job_123  ', 'uid': '  user_456  ', 'status': 'pending'},
        firestore_client=fake_client,
    )
    assert job_id == 'job_123'
    stored = fake_client.store['job_123']
    assert stored['id'] == 'job_123'
    assert stored['uid'] == 'user_456'
    assert stored['status'] == 'pending'


@pytest.mark.parametrize('bad_id', [None, '', '   ', 'job/sub', 'job\\sub', 'job..1', 'a' * 129, 123])
def test_create_import_job_rejects_invalid_id(fake_client, bad_id):
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.create_import_job({'id': bad_id, 'status': 'pending'}, firestore_client=fake_client)


def test_create_import_job_rejects_non_dict_payload(fake_client):
    with pytest.raises(ValueError, match='job_data must be a dictionary'):
        import_jobs_db.create_import_job(None, firestore_client=fake_client)  # type: ignore[arg-type]


def test_update_import_job_handles_missing_and_empty_updates(fake_client):
    assert (
        import_jobs_db.update_import_job('missing_job', {'status': 'completed'}, firestore_client=fake_client) is False
    )
    fake_client.store['job_1'] = {'id': 'job_1', 'status': 'pending'}
    assert import_jobs_db.update_import_job('  job_1  ', {}, firestore_client=fake_client) is False
    assert import_jobs_db.update_import_job('  job_1  ', {'status': 'processing'}, firestore_client=fake_client) is True
    assert fake_client.store['job_1']['status'] == 'processing'


@pytest.mark.parametrize('bad_id', ['', '   ', 'a/b', '../etc'])
def test_write_operations_reject_unsafe_job_id(fake_client, bad_id):
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.update_import_job(bad_id, {'status': 'completed'}, firestore_client=fake_client)
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.update_import_job_unless_cancelled(bad_id, {'status': 'completed'}, firestore_client=fake_client)
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.cancel_import_job_if_active(bad_id, firestore_client=fake_client)
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.update_import_job_progress(bad_id, {'processed_files': 1}, firestore_client=fake_client)
    with pytest.raises(ValueError, match='job_id'):
        import_jobs_db.delete_import_job(bad_id, firestore_client=fake_client)


def test_update_import_job_unless_cancelled_with_injected_client(fake_client):
    fake_client.store['job_active'] = {'id': 'job_active', 'status': 'processing'}
    fake_client.store['job_cancelled'] = {'id': 'job_cancelled', 'status': 'cancelled'}

    assert (
        import_jobs_db.update_import_job_unless_cancelled(
            '  job_active  ', {'status': 'completed'}, firestore_client=fake_client
        )
        is True
    )
    assert fake_client.store['job_active']['status'] == 'completed'

    assert (
        import_jobs_db.update_import_job_unless_cancelled(
            'job_cancelled', {'status': 'completed'}, firestore_client=fake_client
        )
        is False
    )
    assert fake_client.store['job_cancelled']['status'] == 'cancelled'


def test_cancel_import_job_if_active_handles_corrupted_non_dict_snapshot(fake_client):
    fake_client.store['job_corrupt'] = 'not-a-dict'
    assert import_jobs_db.cancel_import_job_if_active('job_corrupt', firestore_client=fake_client) is False

    fake_client.store['job_pending'] = {'id': 'job_pending', 'status': 'pending'}
    assert import_jobs_db.cancel_import_job_if_active('  job_pending  ', firestore_client=fake_client) is True
    assert fake_client.store['job_pending']['status'] == 'cancelled'


def test_update_import_job_progress_validates_fields_and_trims_id(fake_client):
    fake_client.store['job_1'] = {'id': 'job_1', 'status': 'processing'}
    assert import_jobs_db.update_import_job_progress('  job_1  ', {}, firestore_client=fake_client) is False
    assert (
        import_jobs_db.update_import_job_progress(
            '  job_1  ', {'processed_files': 5, 'conversations_created': 4}, firestore_client=fake_client
        )
        is True
    )
    assert fake_client.store['job_1']['processed_files'] == 5


def test_get_import_job_handles_empty_id_store_failure_and_backfills_id(fake_client):
    assert import_jobs_db.get_import_job('', firestore_client=fake_client) is None
    assert import_jobs_db.get_import_job('   ', firestore_client=fake_client) is None
    assert import_jobs_db.get_import_job('bad/id', firestore_client=fake_client) is None

    # Legacy doc without 'id' key inside payload gets hydrated from snapshot.id
    fake_client.store['job_legacy'] = {'status': 'completed'}
    fetched = import_jobs_db.get_import_job('  job_legacy  ', firestore_client=fake_client)
    assert fetched == {'id': 'job_legacy', 'status': 'completed'}

    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError('Firestore down')
    assert import_jobs_db.get_import_job('job_legacy', firestore_client=broken_client) is None


def test_get_import_jobs_clamps_limit_skips_corrupt_docs_and_handles_store_error(fake_client):
    assert import_jobs_db.get_import_jobs('', firestore_client=fake_client) == []
    assert import_jobs_db.get_import_jobs('   ', firestore_client=fake_client) == []

    fake_client.store['job_1'] = {'status': 'pending'}
    fake_client.store['job_corrupt'] = 'not-a-dict'
    fake_client.store['job_2'] = {'id': 'job_2', 'status': 'completed'}

    jobs = import_jobs_db.get_import_jobs('  user_1  ', limit=-5, firestore_client=fake_client)
    assert fake_client.collection_ref.last_limit == 1
    assert len(jobs) == 1
    assert jobs[0]['id'] == 'job_1'

    jobs_all = import_jobs_db.get_import_jobs('user_1', limit=5000, firestore_client=fake_client)
    assert fake_client.collection_ref.last_limit == 1000
    assert [j['id'] for j in jobs_all] == ['job_1', 'job_2']

    broken_client = MagicMock()
    broken_client.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.side_effect = RuntimeError(
        'Stream error'
    )
    assert import_jobs_db.get_import_jobs('user_1', firestore_client=broken_client) == []


def test_delete_import_job_handles_not_found_gracefully(fake_client):
    assert import_jobs_db.delete_import_job('missing_job', firestore_client=fake_client) is False
    fake_client.store['job_del'] = {'id': 'job_del'}
    assert import_jobs_db.delete_import_job('  job_del  ', firestore_client=fake_client) is True
    assert 'job_del' not in fake_client.store
