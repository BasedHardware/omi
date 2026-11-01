"""Real transactions for completed-minimum repair and durable lease/generation fences."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from services import summary_debt_repair as repair
from utils.conversations import summary_delivery as delivery
from utils.sync import reprocess
from tests.integration.test_sync_reprocess_emulator import store, loopback_only_network  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def debt_store(store, monkeypatch):
    client, uid, tasks = store
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.setenv('SUMMARY_DEBT_REPAIR_ENABLED', 'true')
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'standard'})
    ref = user.collection('conversations').document('c')
    row = {
        'status': 'completed',
        'discarded': False,
        'summary_first_pending_at': 100,
        'summary_due_at': 220,
        'summary_title_provenance': 'server_minimum',
        'summary_output_present': False,
        'summary_lane': 'batch',
        'sync_content_revision': 3,
        'data_protection_level': 'standard',
    }
    ref.set(row)
    yield client, uid, tasks, ref, row
    ref.delete()
    user.delete()
    client.document(repair.CURSOR).delete()


def test_worker_death_after_minimum_projection_before_mark_is_repaired(debt_store):
    client, uid, tasks, ref, row = debt_store
    assert not repair.redrive(client, uid, 'c', now=219)
    assert repair.redrive(client, uid, 'c', now=220)
    obligation = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'c')).get().to_dict()
    assert obligation['first_pending_at'] == 100 and obligation['due_at'] == 220
    assert obligation['summary_expected_revision'] == 3 and obligation['summary_lane'] == 'batch'
    assert ref.get().to_dict() == row  # Repair never manufactures a new conversation generation.


def test_lost_enqueue_ack_and_expired_lease_preserve_deadline(debt_store, monkeypatch):
    client, uid, tasks, ref, row = debt_store
    enqueue = reprocess._enqueue
    monkeypatch.setattr(reprocess, '_enqueue', lambda _: (_ for _ in ()).throw(RuntimeError('lost ack')))
    with pytest.raises(RuntimeError):
        repair.redrive(client, uid, 'c', now=220)
    outbox = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, 'c'))
    first = outbox.get().to_dict()
    monkeypatch.setattr(reprocess, '_enqueue', enqueue)
    outbox.update({'lease_until': 300})
    assert not repair.redrive(client, uid, 'c', now=299)
    assert repair.redrive(client, uid, 'c', now=300)
    recovered = outbox.get().to_dict()
    assert recovered['first_pending_at'] == first['first_pending_at'] == 100
    assert recovered['due_at'] == first['due_at'] == 220
    assert recovered['task_token'] == first['task_token']
    assert recovered['wake_generation'] > first['wake_generation']
    # The earliest queued wake remains eligible instead of being sent to the tail.
    output = SimpleNamespace(discarded=False, structured={'overview': 'Synthetic summary'})
    assert reprocess.run(outbox.id, first['task_token'], lambda *_: output, now=300) == 'processed'


@pytest.mark.parametrize(
    'field,value',
    [
        ('user_title', 'manual'),
        ('discarded', True),
        ('deleted', True),
        ('deferred', True),
        ('is_locked', True),
        ('processing_state', 'local_pending'),
        ('finalization_job_id', 'existing'),
        ('data_protection_level', 'e2ee'),
    ],
)
def test_repair_refuses_protected_rows(debt_store, field, value):
    client, uid, tasks, ref, row = debt_store
    ref.update({field: value})
    assert not repair.redrive(client, uid, 'c', now=220)
    assert not tasks


def test_byok_exhaustion_stays_blocked_without_platform_fallback(debt_store):
    client, uid, tasks, ref, row = debt_store
    client.collection('users').document(uid).update({'byok': {'active': True}})
    assert not repair.redrive(client, uid, 'c', now=220)
    assert not tasks
    assert ref.get().to_dict()['summary_blocked_reason'] == 'blocked_byok'
    # Restoring account funding resumes the same obligation, no new generation.
    client.collection('users').document(uid).update({'byok': {'active': False}})
    assert repair.redrive(client, uid, 'c', now=221)


def test_privacy_and_account_deletion_block_repair(debt_store):
    client, uid, tasks, ref, row = debt_store
    marker = client.collection('account_deletions').document(uid)
    marker.set({'wipe_status': 'pending'})
    try:
        assert not repair.redrive(client, uid, 'c', now=220)
        assert not tasks
    finally:
        marker.delete()


def test_completed_receipt_preserves_coalescing_and_lost_ack_is_stale(debt_store):
    client, uid, tasks, ref, row = debt_store
    repair.redrive(client, uid, 'c', now=220)
    key, token = reprocess.key(uid, 'c'), tasks[-1]['task_token']

    def process(*_):
        assert delivery.REPAIR_CONTEXT.get()['summary_expected_revision'] == 3
        return SimpleNamespace(discarded=False, structured={'overview': 'Synthetic summary'})

    assert reprocess.run(key, token, process, now=220) == 'processed'
    assert reprocess.run(key, token, process, now=221) == 'stale'
    reprocess.mark(uid, 'c', 'en', now=222)
    assert tasks[-1]['due_at'] == 822


def test_null_settled_due_is_excluded_from_numeric_sweep(debt_store):
    client, uid, tasks, ref, row = debt_store
    reprocess.mark(uid, 'c', 'en', now=100)
    key, token = reprocess.key(uid, 'c'), tasks[-1]['task_token']
    reprocess.run(key, token, lambda *_: SimpleNamespace(discarded=False, structured={'overview': 'Summary'}), now=220)
    matches = list(client.collection(reprocess.COLLECTION).where('due_at', '<=', 300).stream())
    assert key not in {s.id for s in matches}


def test_repair_tick_global_lease_and_bounded_cursor(debt_store):
    client, uid, tasks, ref, row = debt_store
    first = repair.tick(now=220, client=client)
    assert first == {'scanned': 1, 'admitted': 1, 'errors': 0}
    assert repair.tick(now=221, client=client) == {'scanned': 0, 'admitted': 0, 'errors': 0}
    assert len(tasks) == 1


def test_short_lease_replaced_owner_cannot_durably_write(debt_store, monkeypatch):
    import time
    from database import conversations as conversations_db
    from database.summary_processing import claim_from_snapshot

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda _: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *_: None)
    receipts = []
    monkeypatch.setattr(delivery, 'emit', lambda receipt: receipts.append(receipt))
    first = {'owner': 'first', 'lease_until': time.time() + 120}
    token = delivery.PROCESS_CONTEXT.set(first)
    try:
        snapshot = ref.get()
        assert claim_from_snapshot(client, uid, 'c', {**snapshot.to_dict(), 'updated_at': snapshot.update_time})
        second = {'owner': 'second', 'lease_until': time.time() + 120}
        delivery.PROCESS_CONTEXT.set(second)
        snapshot = ref.get()
        assert claim_from_snapshot(client, uid, 'c', {**snapshot.to_dict(), 'updated_at': snapshot.update_time})
        output = {
            'id': 'c',
            'status': 'completed',
            'sync_content_revision': 3,
            'data_protection_level': 'standard',
            'structured': {'title': 'Synthetic title', 'overview': 'Synthetic summary'},
        }
        delivery.PROCESS_CONTEXT.set(first)
        assert not conversations_db.persist_processing_result_with_lifecycle(uid, deepcopy(output))
        assert not receipts
        delivery.PROCESS_CONTEXT.set(second)
        assert conversations_db.persist_processing_result_with_lifecycle(uid, deepcopy(output))
        assert len(receipts) == 1 and receipts[0]['present']
        delivery.PROCESS_CONTEXT.set(first)
        assert not conversations_db.persist_processing_result_with_lifecycle(uid, deepcopy(output))
        assert len(receipts) == 1
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_cursor_rotates_past_blocked_rows_and_caps_attempts(debt_store, monkeypatch):
    client, uid, tasks, ref, row = debt_store
    user = client.collection('users').document(uid)
    refs = [user.collection('conversations').document(name) for name in ('a', 'b', 'd')]
    for added in refs:
        added.set({**row, 'user_title': 'manual'})
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 2)
    try:
        assert repair.tick(now=220, client=client)['scanned'] == 2
        assert repair.tick(now=340, client=client)['scanned'] == 2
        # A full page preserves cursor; empty next page resets the cycle.
        assert repair.tick(now=460, client=client)['scanned'] == 0
        assert len(tasks) == 1
    finally:
        for added in refs:
            added.delete()


def test_repair_preserves_stored_conversation_language(debt_store):
    client, uid, tasks, ref, row = debt_store
    ref.update({'language': 'vi'})
    assert repair.redrive(client, uid, 'c', now=220)
    assert tasks[-1]['language'] == 'vi'


def test_empty_output_budget_atomically_removes_terminal_debt_and_preserves_content(debt_store, monkeypatch):
    import time
    from database.summary_processing import claim_from_snapshot

    client, uid, tasks, ref, row = debt_store
    ref.update({'structured': {'title': 'Synthetic minimum', 'overview': ''}})
    reprocess.mark(uid, 'c', 'en', now=time.time() - 120)
    key, token = reprocess.key(uid, 'c'), tasks[-1]['task_token']
    outbox = client.collection(reprocess.COLLECTION).document(key)

    def empty_process(*_):
        snapshot = ref.get()
        assert claim_from_snapshot(client, uid, 'c', {**snapshot.to_dict(), 'updated_at': snapshot.update_time})
        raise delivery.SummaryOutputUnavailable('Synthetic empty kept output')

    for attempt in range(3):
        now = time.time() + attempt * 121
        if attempt < 2:
            with pytest.raises(delivery.SummaryOutputUnavailable):
                reprocess.run(key, token, empty_process, now=now)
        else:
            assert reprocess.run(key, token, empty_process, now=now) == 'blocked'
    blocked = ref.get().to_dict()
    assert blocked['summary_blocked_reason'] == 'empty_output_exhausted'
    assert blocked['summary_due_at'] is None and blocked['summary_empty_failures'] == 3
    assert blocked['structured'] == {'title': 'Synthetic minimum', 'overview': ''}
    assert outbox.get().to_dict()['due_at'] is None
    assert not repair.redrive(client, uid, 'c', now=time.time() + 1000)
    assert not [s for s in repair.due_conversations(now=time.time() + 1000, firestore_client=client) if s.id == 'c']


def test_empty_failure_never_clears_a_previously_committed_good_overview(debt_store):
    from database.summary_processing import record_empty_failure

    client, uid, tasks, ref, row = debt_store
    reprocess.mark(uid, 'c', 'en', now=100)
    key = reprocess.key(uid, 'c')
    outbox = client.collection(reprocess.COLLECTION).document(key)
    token = outbox.get().to_dict()['task_token']
    outbox.update({'owner': 'worker', 'summary_empty_failures': 2})
    ref.update(
        {
            'summary_processing_owner': 'previous-successful-worker',
            'structured': {'title': 'Synthetic title', 'overview': 'Previously committed good overview'},
            'summary_output_present': True,
            'summary_completed_at': 150,
            'summary_due_at': None,
        }
    )
    before = ref.get().to_dict()
    assert record_empty_failure(client, reprocess.COLLECTION, key, 'worker', token)
    assert ref.get().to_dict() == before
    assert outbox.get().to_dict()['summary_seen']
    reprocess.mark(uid, 'c', 'en', now=300)
    assert outbox.get().to_dict()['due_at'] == 900  # Later revisions retain ordinary coalescing.


def test_empty_failure_from_replaced_owner_or_token_does_not_record_or_block(debt_store):
    from database.summary_processing import record_empty_failure

    client, uid, tasks, ref, row = debt_store
    reprocess.mark(uid, 'c', 'en', now=100)
    key = reprocess.key(uid, 'c')
    outbox = client.collection(reprocess.COLLECTION).document(key)
    token = outbox.get().to_dict()['task_token']
    outbox.update({'owner': 'replacement'})
    before = outbox.get().to_dict()
    assert not record_empty_failure(client, reprocess.COLLECTION, key, 'old-worker', token)
    assert not record_empty_failure(client, reprocess.COLLECTION, key, 'replacement', 'old-token')
    assert outbox.get().to_dict() == before and ref.get().to_dict() == row
    outbox.update({'summary_empty_failures': 2})
    before = outbox.get().to_dict()
    ref.update({'summary_processing_owner': 'new-conversation-owner'})
    assert not record_empty_failure(client, reprocess.COLLECTION, key, 'replacement', token)
    assert outbox.get().to_dict() == before
    assert ref.get().to_dict()['summary_due_at'] == row['summary_due_at']
