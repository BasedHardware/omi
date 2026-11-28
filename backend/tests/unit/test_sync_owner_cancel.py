"""Owner-requested cancellation of uploaded, unprocessed batch recordings.

State-machine tests run on the scheduler's atomic snapshot store with the real
Scheduler, so every race is a real interleaving of committed transactions.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import owner_cancel
from utils.batch_pipeline.owner_cancel import Outcome
from utils.batch_pipeline.scheduler import Scheduler, owner_key

OWNER = 'owner-synthetic'
OTHER = 'other-synthetic'
JOB = 'bp_upload-1'
CONTENT = 'content-1'


class FakeEraser:
    """Erases only rows the fence marked, the way the real eraser re-proves it per unit."""

    def __init__(self, store, *, fail_units=0, fail_archives=0):
        self.store = store
        self.fail_units = fail_units
        self.fail_archives = fail_archives
        self.deleted_uris = []
        self.archive_calls = []

    def erase_unit(self, uid, segment_id):
        job = self.store.rows.get(('jobs', segment_id))
        if job is None:
            return
        if not owner_cancel.is_owner_cancelled(job) or job['owner_id'] != uid:
            raise AssertionError('eraser must never touch a unit the fence did not mark')
        if self.fail_units:
            self.fail_units -= 1
            raise RuntimeError('storage unavailable')
        self.deleted_uris.append(job['audio_uri'])
        for table in ('jobs', 'results'):
            self.store.rows.pop((table, segment_id), None)

    def erase_archives(self, uid, job_id, paths=()):
        if self.fail_archives:
            self.fail_archives -= 1
            raise RuntimeError('archive listing unavailable')
        self.archive_calls.append((uid, job_id))


def admit(store, segments, *, owner=OWNER, job_id=JOB, content=CONTENT, capture=10, ledger=None):
    """Admit one upload's units through the real scheduler, plus its intake and ledger."""
    queue = Scheduler(store)
    for index, segment in enumerate(segments):
        assert queue.enqueue(item(segment, owner=owner, capture=capture + index), 0)
    store.rows['intakes', job_id] = {
        'owner_id': owner,
        'owner_key': owner_key(owner),
        'content_id': content,
        'segment_ids': list(segments),
        'total_files': 1,
        'lane': 'backfill',
    }
    store.rows['content', f'{owner}/{content}'] = ledger or {
        'status': 'processing',
        'job_id': job_id,
        'dispatch_protocol': 'batch_v1',
    }
    return queue


def queue_of(store, owner=OWNER):
    job = next(v for (t, _), v in store.rows.items() if t == 'jobs' and v['owner_id'] == owner)
    return store.rows['queues', f"{job['priority']}_{owner_key(owner)}"]


def chain(store, owner=OWNER):
    """Walk the owner's FIFO from its head, asserting every link is a ready row."""
    key = owner_key(owner)
    queues = [v for (t, k), v in store.rows.items() if t == 'queues' and k.endswith(key)]
    assert len(queues) == 1
    order, cursor = [], queues[0]['head']
    while cursor:
        job = store.rows['jobs', cursor]
        assert job['state'] == 'ready'
        order.append(cursor)
        cursor = job['next']
    assert (order[-1] if order else '') == queues[0]['tail']
    return order


def cancel(store, eraser=None, *, uid=OWNER, job_id=JOB, now=100.0):
    return owner_cancel.cancel_owner_upload(uid, job_id, store=store, eraser=eraser or FakeEraser(store), now=now)


def test_foreign_and_unknown_handles_get_the_same_answer_and_write_nothing():
    store = MemoryStore()
    admit(store, ['a'])
    before = deepcopy(store.rows)
    assert cancel(store, uid=OTHER).outcome is Outcome.NOT_FOUND
    assert cancel(store, job_id='bp_unknown').outcome is Outcome.NOT_FOUND
    assert store.rows == before


def test_queued_upload_is_unlinked_fenced_and_erased_without_touching_later_work():
    store = MemoryStore()
    admit(store, ['a', 'b'])
    later = Scheduler(store)
    assert later.enqueue(item('later', owner=OWNER, capture=50), 0)
    eraser = FakeEraser(store)

    result = cancel(store, eraser)

    assert result.outcome is Outcome.CANCELLED
    assert result.erasure == 'complete'
    assert eraser.deleted_uris == ['gs://synthetic/a', 'gs://synthetic/b']
    assert eraser.archive_calls == [(OWNER, JOB)]
    assert ('jobs', 'a') not in store.rows and ('jobs', 'b') not in store.rows
    assert chain(store) == ['later']
    intake = store.rows['intakes', JOB]
    assert intake['owner_cancelled_at'] == 100.0 and intake['owner_cancel_erased_at'] == 100.0
    assert store.rows['content', f'{OWNER}/{CONTENT}']['status'] == owner_cancel.LEDGER_STATUS
    # The scheduler leases the owner's remaining work and nothing cancelled.
    pulled = Scheduler(store).pull(1, 10)
    assert [lease.item.segment_id for lease in pulled] == ['later']


def test_adjacent_siblings_inside_a_queue_relink_predecessor_and_tail():
    store = MemoryStore()
    queue = Scheduler(store)
    assert queue.enqueue(item('first', owner=OWNER, capture=1), 0)
    admit(store, ['a', 'b'], capture=5)
    assert queue.enqueue(item('last', owner=OWNER, capture=90), 0)
    assert chain(store) == ['first', 'a', 'b', 'last']

    assert cancel(store).outcome is Outcome.CANCELLED
    assert chain(store) == ['first', 'last']


def test_intake_order_can_differ_from_fifo_after_retry():
    store = MemoryStore()
    queue = admit(store, ['a', 'b'])
    lease = queue.pull(1, 1)[0]
    assert lease.item.segment_id == 'a'
    assert queue.defer('a', lease.token, 2, retry_after=4, held_reason='retry')
    assert queue.recover(store.rows['jobs', 'a']['available_at']) == 1
    assert chain(store) == ['b', 'a']

    # Keep the fenced rows present so the pull would find any stale link.
    assert cancel(store, FakeEraser(store, fail_units=1)).erasure == 'pending'
    assert chain(store) == []
    assert queue.pull(101, 1) == []


def test_upload_at_the_tail_moves_the_tail_back():
    store = MemoryStore()
    queue = Scheduler(store)
    assert queue.enqueue(item('first', owner=OWNER, capture=1), 0)
    admit(store, ['a', 'b'], capture=5)
    assert cancel(store).outcome is Outcome.CANCELLED
    assert chain(store) == ['first']


def test_only_upload_leaves_an_empty_queue_the_puller_skips():
    store = MemoryStore()
    admit(store, ['a'])
    assert cancel(store).outcome is Outcome.CANCELLED
    assert chain(store) == []
    assert Scheduler(store).pull(1, 5) == []


def test_allowance_held_upload_releases_its_hold_count():
    store = MemoryStore()
    admit(store, ['a', 'b'])
    key = owner_key(OWNER)
    # Park both units the way the allowance controller leaves them.
    for segment in ('a', 'b'):
        job = store.rows['jobs', segment]
        job.update(state='allowance_held', merge_pending=False, token='', lease_until=0.0)
    queue = queue_of(store)
    queue.update(head='', tail='')
    store.rows['allowance_holds', key] = {'owner_key': key, 'owner_id': OWNER, 'held_count': 3, 'active': True}

    assert cancel(store).outcome is Outcome.CANCELLED
    hold = store.rows['allowance_holds', key]
    assert hold['held_count'] == 1 and hold['active'] is True


def test_last_allowance_hold_deactivates_the_owner_hold():
    store = MemoryStore()
    admit(store, ['a'])
    key = owner_key(OWNER)
    store.rows['jobs', 'a'].update(state='allowance_held', merge_pending=False)
    queue_of(store).update(head='', tail='')
    store.rows['allowance_holds', key] = {'owner_key': key, 'owner_id': OWNER, 'held_count': 1, 'active': True}
    assert cancel(store).outcome is Outcome.CANCELLED
    assert store.rows['allowance_holds', key] == {'owner_key': key, 'owner_id': OWNER, 'held_count': 0, 'active': False}


@pytest.mark.parametrize(
    'state,extra',
    [
        ('retry', {'available_at': 500.0}),
        ('vendor_held', {}),
        ('quarantined', {'recovery_state': 'held'}),
        ('quarantined', {'recovery_state': 'failed_held'}),
        ('dead', {'dead_letter_reason': 'held_expired'}),
    ],
)
def test_detached_held_states_are_cancellable(state, extra):
    store = MemoryStore()
    admit(store, ['a'])
    store.rows['jobs', 'a'].update(state=state, merge_pending=False, **extra)
    queue_of(store).update(head='', tail='')
    assert cancel(store).outcome is Outcome.CANCELLED
    assert ('jobs', 'a') not in store.rows


@pytest.mark.parametrize(
    'state,extra',
    [
        ('leased', {'token': 'worker', 'lease_until': 220.0}),
        ('result_ready', {}),
        ('committed', {}),
        ('provider_running', {}),
        ('record_pending', {}),
        ('quarantined', {'recovery_state': 'running'}),
        ('quarantined', {'recovery_state': 'prepared'}),
        ('dead', {'speech_redrive': {'state': 'running'}}),
    ],
)
def test_in_flight_or_finishing_work_is_never_fenced(state, extra):
    store = MemoryStore()
    admit(store, ['a', 'b'])
    store.rows['jobs', 'b'].update(state=state, **extra)
    before = deepcopy(store.rows)
    eraser = FakeEraser(store)
    assert cancel(store, eraser).outcome is Outcome.IN_PROGRESS
    assert store.rows == before
    assert eraser.deleted_uris == [] and eraser.archive_calls == []


def test_source_alias_units_are_not_cancellable():
    store = MemoryStore()
    admit(store, ['a'])
    store.rows['jobs', 'a']['source_alias'] = {'segment_id': 'canonical'}
    before = deepcopy(store.rows)
    assert cancel(store).outcome is Outcome.NOT_CANCELLABLE
    assert store.rows == before


def test_coalesced_and_record_handoff_uploads_are_not_cancellable():
    store = MemoryStore()
    admit(store, ['a'])
    store.rows['intakes', JOB]['coalesce_group'] = 'group'
    assert cancel(store).outcome is Outcome.NOT_CANCELLABLE
    assert cancel(store, job_id='bp_wh_live').outcome is Outcome.NOT_CANCELLABLE
    assert ('jobs', 'a') in store.rows


@pytest.mark.parametrize(
    'ledger',
    [
        {
            'status': 'completed',
            'job_id': JOB,
            'result': {
                'new_memories': ['conv-1'],
                'updated_memories': ['conv-2'],
                'failed_segments': 0,
                'total_segments': 2,
                'errors': [],
            },
        },
        {
            'status': 'partial',
            'job_id': JOB,
            'result': {
                'outcome': 'partial',
                'new_memories': ['conv-1'],
                'updated_memories': ['conv-2'],
                'failed_segments': 1,
                'held_segments': 1,
                'total_segments': 2,
                'errors': [],
            },
        },
    ],
)
def test_processed_upload_reports_conversations_and_deletes_nothing(ledger):
    store = MemoryStore()
    admit(store, ['a', 'b'], ledger=ledger)
    store.rows['jobs', 'a'].update(state='committed')
    before = deepcopy(store.rows)
    result = cancel(store)
    assert result.outcome is Outcome.ALREADY_PROCESSED
    assert result.conversation_ids == ('conv-1', 'conv-2')
    assert store.rows == before


def test_a_job_that_wins_the_lease_race_is_reported_in_progress_then_processed():
    store = MemoryStore()
    admit(store, ['a'])
    # The worker's pull transaction commits first.
    leases = Scheduler(store).pull(1, 1)
    assert [lease.item.segment_id for lease in leases] == ['a']
    assert cancel(store).outcome is Outcome.IN_PROGRESS
    # Projection finishes: the owner deletes the conversation, never the job.
    store.rows['content', f'{OWNER}/{CONTENT}'] = {
        'status': 'completed',
        'job_id': JOB,
        'result': {
            'new_memories': ['conv-1'],
            'updated_memories': [],
            'failed_segments': 0,
            'total_segments': 1,
            'errors': [],
        },
    }
    store.rows['jobs', 'a']['state'] = 'committed'
    assert cancel(store).outcome is Outcome.ALREADY_PROCESSED


def test_a_fence_that_wins_the_race_leaves_nothing_for_workers_to_lease_or_recover():
    store = MemoryStore()
    admit(store, ['a', 'b'])
    store.rows['jobs', 'b'].update(state='retry', available_at=50.0, merge_pending=True)
    eraser = FakeEraser(store, fail_units=2)  # erasure lags: rows stay fenced
    result = cancel(store, eraser)
    assert result.outcome is Outcome.CANCELLED and result.erasure == 'pending'
    scheduler = Scheduler(store)
    assert scheduler.pull(200, 5) == []
    scheduler.recover(200)
    assert scheduler.pull(201, 5) == []
    for segment in ('a', 'b'):
        job = store.rows['jobs', segment]
        assert job['state'] == 'privacy_blocked' and job['privacy_blocked_reason'] == 'owner_cancelled'
        assert job['merge_pending'] is False and job['token'] == '' and job['next'] == ''


def test_cancel_is_idempotent_and_a_retry_finishes_erasure():
    store = MemoryStore()
    admit(store, ['a'])
    expires = datetime.fromtimestamp(150, timezone.utc)
    store.rows['intakes', JOB]['expires_at'] = expires
    store.rows['content', f'{OWNER}/{CONTENT}']['expires_at'] = expires
    first = cancel(store, FakeEraser(store, fail_archives=1))
    assert first.outcome is Outcome.CANCELLED and first.erasure == 'pending'
    assert 'owner_cancel_erased_at' not in store.rows['intakes', JOB]
    assert 'expires_at' not in store.rows['intakes', JOB]
    assert 'expires_at' not in store.rows['content', f'{OWNER}/{CONTENT}']
    again = FakeEraser(store)
    retry_at = 100 + timedelta(days=46).total_seconds()
    second = cancel(store, again, now=retry_at)
    assert second.outcome is Outcome.CANCELLED and second.erasure == 'complete'
    assert again.archive_calls == [(OWNER, JOB)]
    assert store.rows['intakes', JOB]['owner_cancelled_at'] == 100.0  # original fence time is kept
    assert store.rows['intakes', JOB]['owner_cancel_erased_at'] == retry_at
    receipt_expiry = datetime.fromtimestamp(retry_at, timezone.utc) + timedelta(days=45)
    assert store.rows['intakes', JOB]['expires_at'] == receipt_expiry
    assert store.rows['content', f'{OWNER}/{CONTENT}']['expires_at'] == receipt_expiry
    third = FakeEraser(store)
    assert cancel(store, third, now=retry_at + 1).erasure == 'complete'
    assert third.archive_calls == [] and third.deleted_uris == []


def test_status_after_cancel_returns_custody_to_surviving_siblings():
    store = MemoryStore()
    admit(store, ['a'])
    cancel(store)
    status = owner_cancel.cancelled_status(store.rows['intakes', JOB], JOB)
    assert status['status'] == 'failed'
    assert status['reason_code'] == owner_cancel.REASON_CODE
    assert status['result'] is None and status['poll_after_ms'] == 0


def test_kill_switch_off_refuses_before_any_read(monkeypatch):
    monkeypatch.setenv('SYNC_JOB_OWNER_CANCEL_ENABLED', 'false')
    store = MemoryStore()
    admit(store, ['a'])
    before = deepcopy(store.rows)
    with pytest.raises(owner_cancel.CancelDisabled):
        cancel(store)
    assert store.rows == before


@pytest.mark.parametrize('value,enabled', [(None, True), ('true', True), ('off', False), ('0', False), ('No', False)])
def test_kill_switch_is_on_unless_off(monkeypatch, value, enabled):
    from config import sync_owner_cancel

    if value is None:
        monkeypatch.delenv('SYNC_JOB_OWNER_CANCEL_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SYNC_JOB_OWNER_CANCEL_ENABLED', value)
    assert sync_owner_cancel.enabled() is enabled


class _Snapshot:
    def __init__(self, data, doc_id='a'):
        self._data = data
        self.exists = data is not None
        self.id = doc_id

    def to_dict(self):
        return deepcopy(self._data) if self._data is not None else None


class _Document:
    def __init__(self, rows, table, key):
        self.rows, self.table, self.key = rows, table, key

    def get(self, transaction=None):
        return _Snapshot(self.rows.get((self.table, self.key)), self.key)


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        table = name.split('batch_pipeline_prod_', 1)[1]
        rows = self.rows

        class Collection:
            def document(self, key):
                return _Document(rows, table, key)

        return Collection()


def _fenced_job(**extra):
    return {
        'segment_id': 'a',
        'owner_id': OWNER,
        'owner_key': owner_key(OWNER),
        'priority': 2,
        'state': 'privacy_blocked',
        'owner_cancelled_at': 1.0,
        'audio_uri': 'gs://bucket/audio-a',
        **extra,
    }


def test_production_eraser_erases_objects_then_rows_under_a_refencing_transaction(monkeypatch):
    from database.batch_pipeline_staging import artifact_id
    from utils.batch_pipeline import owner_cancel_erase

    rows = {
        ('jobs', 'a'): _fenced_job(),
        ('artifacts', artifact_id('a', 'gs://bucket/audio-a')): {'owner_id': OWNER, 'uri': 'gs://bucket/audio-a'},
    }
    calls = []
    monkeypatch.setattr(
        owner_cancel_erase,
        'erase_artifact',
        lambda uid, ns, snap, data, delete_uri, fence, client: calls.append(('artifact', uid, ns, data['uri'])),
    )

    def delete_job(client, ns, snapshot, *, retain_ordering, fence):
        calls.append(('job', ns, snapshot.id, retain_ordering))
        fence(None)  # the re-proof passes for a fenced row

    monkeypatch.setattr(owner_cancel_erase, 'delete_job', delete_job)
    deleted = []
    eraser = owner_cancel_erase.FirestoreEraser(
        'batch_pipeline_prod',
        client=_Client(rows),
        delete_uri=lambda uid, uri: deleted.append((uid, uri)),
        delete_archives=lambda uid, raw, paths: calls.append(('archives', uid, raw)) or 0,
    )
    eraser.erase_unit(OWNER, 'a')
    eraser.erase_archives(OWNER, 'bp_upload-1')
    assert deleted == [(OWNER, 'gs://bucket/audio-a')]
    assert calls == [
        ('artifact', OWNER, 'batch_pipeline_prod', 'gs://bucket/audio-a'),
        ('job', 'batch_pipeline_prod', 'a', False),
        ('archives', OWNER, 'upload-1'),
    ]
    eraser.erase_unit(OWNER, 'missing')  # absent rows are already erased


@pytest.mark.parametrize(
    'row', [_fenced_job(owner_id=OTHER), _fenced_job(state='ready'), _fenced_job(owner_cancelled_at=None)]
)
def test_production_eraser_refuses_a_row_the_fence_did_not_write(monkeypatch, row):
    from utils.batch_pipeline import owner_cancel_erase

    monkeypatch.setattr(owner_cancel_erase, 'delete_job', lambda *a, **k: pytest.fail('must not delete'))
    eraser = owner_cancel_erase.FirestoreEraser(
        'batch_pipeline_prod',
        client=_Client({('jobs', 'a'): row}),
        delete_uri=lambda uid, uri: pytest.fail('must not delete objects'),
        delete_archives=lambda uid, raw, paths: 0,
    )
    with pytest.raises(owner_cancel_erase.UnitNotFenced):
        eraser.erase_unit(OWNER, 'a')


def test_production_eraser_fence_aborts_when_the_row_changed_inside_the_transaction(monkeypatch):
    from utils.batch_pipeline import owner_cancel_erase

    rows = {('jobs', 'a'): _fenced_job(audio_uri=None)}

    def delete_job(client, ns, snapshot, *, retain_ordering, fence):
        rows['jobs', 'a'] = _fenced_job(state='ready')  # a concurrent writer reclaimed it
        fence(None)

    monkeypatch.setattr(owner_cancel_erase, 'delete_job', delete_job)
    eraser = owner_cancel_erase.FirestoreEraser(
        'batch_pipeline_prod', client=_Client(rows), delete_uri=lambda *a: None, delete_archives=lambda *a: 0
    )
    with pytest.raises(owner_cancel_erase.UnitNotFenced):
        eraser.erase_unit(OWNER, 'a')


class _Blob:
    def __init__(self, name, metadata, generation=7, missing=False):
        self.name, self.metadata, self.generation, self.missing = name, metadata, generation, missing
        self.deleted = None
        self.metageneration = 3

    def delete(self, *, if_generation_match, if_metageneration_match, timeout):
        assert if_metageneration_match == self.metageneration
        from google.cloud.exceptions import NotFound

        if self.missing:
            raise NotFound('gone')
        self.deleted = if_generation_match


def test_archive_erasure_keeps_originals_linked_to_conversations_and_other_uploads(monkeypatch):
    from utils.other import storage

    blobs = {
        'raw-sync': [
            _Blob('raw-sync/owner-synthetic/a/x.bin', {'sync_job_id': 'upload-1', 'conversation_id': 'unknown'}),
            _Blob('raw-sync/owner-synthetic/a/y.bin', {'sync_job_id': 'upload-1', 'conversation_ids': '["conv-1"]'}),
            _Blob('raw-sync/owner-synthetic/a/z.bin', {'sync_job_id': 'upload-2'}),
            _Blob('raw-sync/owner-synthetic/a/earlier.bin', {'sync_job_id': 'prior-attempt'}),
        ],
        'raw-mobile-batch': [
            _Blob('raw-mobile-batch/owner-synthetic/b/x.bin', {'sync_job_id': 'upload-1'}, generation=9),
            _Blob(
                'raw-mobile-batch/owner-synthetic/b/live.bin',
                {'sync_job_id': 'upload-1', 'conversation_id': 'live-conv'},
            ),
            _Blob('raw-mobile-batch/owner-synthetic/b/bad.bin', {'sync_job_id': 'unrelated', 'conversation_ids': '{'}),
            _Blob('raw-mobile-batch/owner-synthetic/b/gone.bin', {'sync_job_id': 'upload-1'}, missing=True),
        ],
    }
    prefixes = []

    class Bucket:
        def list_blobs(self, *, prefix, versions):
            assert versions is True
            prefixes.append(prefix)
            return [b for b in blobs[prefix.split('/', 1)[0]] if b.deleted is None and not b.missing]

    class Client:
        def bucket(self, name):
            return Bucket()

    monkeypatch.setattr(storage, '_get_storage_client', lambda: Client())
    earlier = 'raw-sync/owner-synthetic/a/earlier.bin'
    assert storage.delete_unlinked_upload_archives(OWNER, 'upload-1', (earlier,)) == 3
    assert prefixes == [f'raw-sync/{OWNER}/', f'raw-mobile-batch/{OWNER}/'] * 2
    assert [b.name for group in blobs.values() for b in group if b.deleted is not None] == [
        'raw-sync/owner-synthetic/a/x.bin',
        earlier,
        'raw-mobile-batch/owner-synthetic/b/x.bin',
    ]
    assert blobs['raw-mobile-batch'][0].deleted == 9
    with pytest.raises(ValueError):
        storage.delete_unlinked_upload_archives(OWNER, '')


@pytest.mark.parametrize('second_pass', ['late_write', 'listing_failed', 'still_present'])
def test_archive_eraser_verifies_after_first_delete_pass(monkeypatch, second_pass):
    from utils.other import storage

    prefix = f'raw-sync/{OWNER}/'
    first = _Blob(prefix + 'first', {'sync_job_id': 'upload-1'})
    late = _Blob(prefix + 'late', {'sync_job_id': 'upload-1'})
    reads = 0

    def list_blobs(*, prefix, versions):
        nonlocal reads
        if not prefix.startswith('raw-sync/'):
            return []
        reads += 1
        if reads == 1:
            return [first]
        if second_pass == 'listing_failed':
            raise RuntimeError('listing unavailable')
        return [late] if late.deleted is None or second_pass == 'still_present' else []

    from types import SimpleNamespace

    bucket = SimpleNamespace(list_blobs=list_blobs)
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
    if second_pass == 'late_write':
        assert storage.delete_unlinked_upload_archives(OWNER, 'upload-1', (first.name,)) == 2
        assert late.deleted == late.generation
    else:
        with pytest.raises(storage.ArchiveReceiptIncomplete):
            storage.delete_unlinked_upload_archives(OWNER, 'upload-1', (first.name,))
    assert first.deleted == first.generation


def test_rejected_upload_erases_only_generations_tagged_by_that_request(monkeypatch):
    from types import SimpleNamespace
    from utils.other import storage

    path = f'raw-sync/{OWNER}/original'
    own = _Blob(path, {'sync_job_id': 'new'}, generation=8)
    reused = _Blob(path, {'sync_job_id': 'earlier'})
    linked = _Blob(path, {'sync_job_id': 'new', 'conversation_id': 'conv'}, generation=9)
    other = _Blob(path + '-other', {'sync_job_id': 'new'})
    bucket = SimpleNamespace(list_blobs=lambda **kwargs: [own, reused, linked, other])
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))

    storage.delete_rejected_upload_archives(OWNER, 'new', [path])

    assert own.deleted == 8
    assert all(blob.deleted is None for blob in (reused, linked, other))


@pytest.mark.parametrize('lane', ['batch', 'legacy'])
@pytest.mark.parametrize('earlier_original_exists', [False, True])
def test_old_receipt_requires_archive_ownership_proof(monkeypatch, lane, earlier_original_exists):
    from tests.unit import test_sync_owner_cancel_legacy as legacy
    from utils.batch_pipeline.owner_cancel_erase import FirestoreEraser
    from utils.other import storage

    if lane == 'batch':
        store = MemoryStore()
        admit(store, ['a'])
        receipt_key = ('intakes', JOB)
        job_id = JOB.removeprefix('bp_')
        eraser = FakeEraser(store)
        cancel_upload = cancel
    else:
        store = legacy.MemoryLegacyStore()
        legacy.held_upload(store)
        receipt_key = ('ledger', OWNER, legacy.CONTENT)
        job_id = legacy.JOB
        eraser = legacy.FakeLegacyEraser(store)
        cancel_upload = legacy.cancel

    assert 'raw_capture_paths' not in store.rows[receipt_key]
    prefix = f'raw-mobile-batch/{OWNER}/'
    earlier = _Blob(prefix + 'same-recording.bin', {'sync_job_id': 'earlier-attempt'})
    known = _Blob(prefix + 'current-attempt.bin', {'sync_job_id': job_id})
    linked = _Blob(prefix + 'conversation.bin', {'sync_job_id': 'unrelated', 'conversation_ids': '["conversation"]'})
    originals = [known, linked, earlier] if earlier_original_exists else [known, linked]

    class Bucket:
        def list_blobs(self, *, prefix, versions):
            assert versions is True
            return [blob for blob in originals if blob.name.startswith(prefix) and blob.deleted is None]

    class Client:
        def bucket(self, name):
            return Bucket()

    monkeypatch.setattr(storage, '_get_storage_client', lambda: Client())
    eraser.erase_archives = FirestoreEraser('batch_pipeline_prod').erase_archives

    first = cancel_upload(store, eraser)
    assert first.outcome is Outcome.CANCELLED
    assert known.deleted == known.generation
    assert linked.deleted is None
    assert earlier.deleted is None
    if earlier_original_exists:
        assert first.erasure == 'pending'
        retry = cancel_upload(store, eraser, now=timedelta(days=46).total_seconds())
        assert retry.erasure == 'pending'
        row = store.rows[receipt_key]
        assert 'expires_at' not in row
        assert 'owner_cancel_erased_at' not in row
        assert earlier.deleted is None
    else:
        assert first.erasure == 'complete'
        assert 'expires_at' in store.rows[receipt_key]


def test_durable_status_answers_a_cancelled_upload_without_redrive():
    from utils.batch_pipeline import intake as batch_intake

    store = MemoryStore()
    admit(store, ['a'])
    cancel(store)
    status = batch_intake.durable_status(store, OWNER, JOB)
    assert status['status'] == 'failed' and status['reason_code'] == owner_cancel.REASON_CODE
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        batch_intake.durable_status(store, OTHER, JOB)
