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
    assert first == {'scanned': 1, 'admitted': 1, 'near_expiry_admitted': 0, 'errors': 0, 'expired_seen': 0}
    assert repair.tick(now=221, client=client) == {
        'scanned': 0,
        'admitted': 0,
        'near_expiry_admitted': 0,
        'errors': 0,
        'expired_seen': 0,
    }
    assert len(tasks) == 1


@pytest.mark.parametrize('retry_transaction', [0, 1], ids=['claim', 'finish'])
def test_tick_transaction_retry_does_not_recount_or_republish_expired_rows(debt_store, monkeypatch, retry_transaction):
    from unittest.mock import Mock
    from google.api_core.exceptions import Aborted
    from google.cloud.firestore_v1.transaction import Transaction
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    pending = now - 100
    ref.update({'summary_first_pending_at': pending, 'summary_due_at': now - 1})
    expired_ref = ref.parent.document('created-old')
    expired_row = {
        **row,
        'summary_first_pending_at': pending,
        'summary_due_at': now - 1,
        'created_at': now - max_age_seconds() - 1,
    }
    expired_ref.set(expired_row)
    commit = Transaction._commit
    cursor_transactions = []
    commit_attempts = []

    def abort_once(transaction):
        # Exercise the SDK's actual transactional retry loop against the
        # emulator, rejecting one cursor commit before it reaches storage.
        if any(write.update.name.endswith('/' + repair.CURSOR) for write in transaction._write_pbs):
            if transaction not in cursor_transactions:
                cursor_transactions.append(transaction)
                commit_attempts.append(0)
            index = cursor_transactions.index(transaction)
            commit_attempts[index] += 1
            if index == retry_transaction and commit_attempts[index] == 1:
                # A server abort releases read locks. A client-only exception
                # would leave the emulator transaction open across the retry.
                transaction._rollback()
                raise Aborted('synthetic cursor contention')
        return commit(transaction)

    monkeypatch.setattr(Transaction, '_commit', abort_once)
    counter = Mock(wraps=delivery.REPAIR)
    monkeypatch.setattr(delivery, 'REPAIR', counter)
    query = Mock(wraps=repair.due_conversations)
    monkeypatch.setattr(repair, 'due_conversations', query)
    gauge = Mock(wraps=delivery.EXPIRED_SEEN)
    monkeypatch.setattr(delivery, 'EXPIRED_SEEN', gauge)
    try:
        assert repair.tick(now=now, client=client) == {
            'scanned': 2,
            'admitted': 1,
            'errors': 0,
            'expired_seen': 1,
            'near_expiry_admitted': 0,
        }
        assert commit_attempts == ([2, 1] if retry_transaction == 0 else [1, 2])
        assert query.call_count == 2
        assert counter.labels.call_count == 5
        gauge.set.assert_called_once_with(1)
        assert gauge._mock_wraps._value.get() == 1
        assert len(tasks) == 1
        assert expired_ref.get().to_dict() == expired_row
        assert not client.collection(reprocess.COLLECTION).document(reprocess.key(uid, expired_ref.id)).get().exists
    finally:
        expired_ref.delete()


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
    from database.summary_processing import record_empty_failure, EmptyFailureOutcome

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
    assert record_empty_failure(client, reprocess.COLLECTION, key, 'worker', token) is EmptyFailureOutcome.BLOCKED
    assert ref.get().to_dict() == before
    assert outbox.get().to_dict()['summary_seen']
    reprocess.mark(uid, 'c', 'en', now=300)
    assert outbox.get().to_dict()['due_at'] == 900  # Later revisions retain ordinary coalescing.


def test_empty_failure_from_replaced_owner_or_token_does_not_record_or_block(debt_store):
    from database.summary_processing import record_empty_failure, EmptyFailureOutcome

    client, uid, tasks, ref, row = debt_store
    reprocess.mark(uid, 'c', 'en', now=100)
    key = reprocess.key(uid, 'c')
    outbox = client.collection(reprocess.COLLECTION).document(key)
    token = outbox.get().to_dict()['task_token']
    outbox.update({'owner': 'replacement'})
    before = outbox.get().to_dict()
    assert record_empty_failure(client, reprocess.COLLECTION, key, 'old-worker', token) is EmptyFailureOutcome.STALE
    assert (
        record_empty_failure(client, reprocess.COLLECTION, key, 'replacement', 'old-token') is EmptyFailureOutcome.STALE
    )
    assert outbox.get().to_dict() == before and ref.get().to_dict() == row
    outbox.update({'summary_empty_failures': 2})
    before = outbox.get().to_dict()
    ref.update({'summary_processing_owner': 'new-conversation-owner'})
    assert (
        record_empty_failure(client, reprocess.COLLECTION, key, 'replacement', token)
        is EmptyFailureOutcome.OWNER_MISMATCH
    )
    assert outbox.get().to_dict() == {**before, 'summary_empty_outcome': 'owner_mismatch'}
    assert ref.get().to_dict()['summary_due_at'] == row['summary_due_at']


@pytest.mark.parametrize('cursor_kind', ['legacy', 'expired', 'none'])
def test_window_reaches_fresh_debt_behind_expired_history_in_one_tick(debt_store, monkeypatch, cursor_kind):
    """Real query ordering/filtering, not a fake pre-filtered page."""
    from unittest.mock import Mock
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    expired = {**row, 'summary_first_pending_at': cutoff - 1000, 'summary_due_at': cutoff - 880}
    refs = [ref.parent.document(f'expired-{i:04}') for i in range(1200)]
    # Fresh pending but historical creation still fails the second arm of the
    # age gate. It must be counted without touching conversation/outbox state.
    created_old = ref.parent.document('created-old')
    created_old_row = {**row, 'summary_first_pending_at': cutoff, 'summary_due_at': now - 5, 'created_at': cutoff - 1}
    fresh = {**row, 'summary_first_pending_at': cutoff, 'summary_due_at': cutoff - 1}
    ref.set(fresh)  # Deliberately no due >= pending assumption.
    created_old.set(created_old_row)
    redrive = Mock(return_value=True)
    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        for start in range(0, len(refs), 400):
            batch = client.batch()
            for added in refs[start : start + 400]:
                batch.set(added, expired)
            batch.commit()
        if cursor_kind != 'none':
            cursor = {'due': expired['summary_due_at'], 'path': refs[599].path}
            if cursor_kind == 'expired':
                cursor['pending'] = expired['summary_first_pending_at']
            client.document(repair.CURSOR).set(cursor)
        assert repair.tick(now=now, client=client) == {
            'scanned': 2,
            'admitted': 1,
            'errors': 0,
            'expired_seen': 1,
            'near_expiry_admitted': 1,
        }
        redrive.assert_called_once_with(client, uid, 'c', now=now)
        assert delivery.DEBT._value.get() == 1
        assert delivery.EXPIRED_SEEN._value.get() == 1
        assert delivery.SAMPLED_AT._value.get() == now
        assert created_old.get().to_dict() == created_old_row
        assert ref.get().to_dict() == fresh
        assert all(snapshot.to_dict() == expired for snapshot in client.get_all(refs))
        assert not list(client.collection(reprocess.COLLECTION).where('uid', '==', uid).stream())
        assert not tasks
    finally:
        for start in range(0, len(refs), 400):
            batch = client.batch()
            for added in refs[start : start + 400]:
                batch.delete(added)
            batch.commit()
        created_old.delete()


@pytest.mark.parametrize('hours', [1, 72, 0])
def test_window_preserves_every_non_expired_row_and_disabled_gate(debt_store, monkeypatch, hours):
    from utils.enrichment.age_gate import expired, max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', str(hours))
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    pending_times = [cutoff - 1, cutoff, cutoff + 1, now - 1]
    refs = [ref.parent.document(f'boundary-{i}') for i in range(len(pending_times))]
    candidates = [
        {**row, 'summary_first_pending_at': pending, 'summary_due_at': now - 10000} for pending in pending_times
    ]
    ref.update({'summary_due_at': None})
    try:
        for added, candidate in zip(refs, candidates):
            added.set(candidate)
        page = [
            s
            for phase in ('near_expiry', 'newest')
            for s in repair.due_conversations(now=now, phase=phase, firestore_client=client)
        ]
        paths = {snapshot.reference.path for snapshot in page}
        expected = {
            added.path
            for added, candidate in zip(refs, candidates)
            if not expired({'first_pending_at': candidate['summary_first_pending_at']}, now=now)
        }
        assert paths == expected
    finally:
        for added in refs:
            added.delete()


def test_window_cursor_paginates_equal_timestamps_and_resets_on_mode_changes(debt_store, monkeypatch):
    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    refs = [ref.parent.document(name) for name in ('a', 'b')]
    for added in refs:
        added.set(row)
    try:
        first = repair.due_conversations(now=220, limit=1, firestore_client=client)[0]
        cursor = {'phase': 'newest', 'window': 72 * 3600, 'due': 220, 'pending': 100, 'path': first.reference.path}
        second = repair.due_conversations(now=220, limit=1, after=cursor, firestore_client=client)[0]
        assert second.reference.path != first.reference.path
        monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
        # The old ordering cannot be reused after disabling the gate.
        assert (
            repair.due_conversations(now=220, limit=1, after=cursor, firestore_client=client)[0].reference
            == first.reference
        )
        legacy = {'due': 220, 'path': first.reference.path}
        assert (
            repair.due_conversations(now=220, limit=1, after=legacy, firestore_client=client)[0].reference
            == second.reference
        )
        monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
        assert (
            repair.due_conversations(now=220, limit=1, after=legacy, firestore_client=client)[0].reference
            == first.reference
        )
    finally:
        for added in refs:
            added.delete()


@pytest.mark.parametrize('cursor_kind', ['legacy', 'old_disabled_phase'])
@pytest.mark.parametrize('pending_kind', ['missing', 'null'])
def test_disabled_gate_repairs_missing_pending_and_persists_legacy_cursor(
    debt_store, monkeypatch, cursor_kind, pending_kind
):
    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '0')
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 1)
    missing = ref.parent.document('missing-pending')
    candidate = {**row, 'summary_due_at': 219}
    if pending_kind == 'missing':
        del candidate['summary_first_pending_at']
    else:
        candidate['summary_first_pending_at'] = None
    missing.set(candidate)
    cursor = {'due': 218, 'path': ref.path}
    if cursor_kind == 'old_disabled_phase':
        cursor = {'version': 2, 'phases': {'newest': {**cursor, 'phase': 'newest', 'window': 0, 'pending': 100}}}
    client.document(repair.CURSOR).set(cursor)
    try:
        counts = repair.tick(now=220, client=client)
        assert counts == {'scanned': 1, 'admitted': 1, 'near_expiry_admitted': 0, 'errors': 0, 'expired_seen': 0}
        obligation = client.collection(reprocess.COLLECTION).document(reprocess.key(uid, missing.id)).get().to_dict()
        assert obligation['first_pending_at'] == obligation['summary_deadline_at'] == obligation['due_at'] == 219
        assert missing.get().to_dict() == candidate
        progress = client.document(repair.CURSOR).get().to_dict()
        assert progress['path'] == missing.path and progress['due'] == 219 and progress['pending'] is None
        assert progress['phases'] == {}
        counts = repair.tick(now=340, client=client)
        assert counts['scanned'] == counts['admitted'] == 1 and counts['errors'] == 0
        assert client.document(repair.CURSOR).get().to_dict()['path'] == ref.path
    finally:
        missing.delete()


@pytest.mark.parametrize('due', [0, -10])
def test_gated_nonpositive_due_cursor_advances_from_a_to_b(debt_store, monkeypatch, due):
    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    ref.update({'summary_due_at': None})
    refs = [ref.parent.document(name) for name in ('a', 'b')]
    pending = now - 1
    try:
        for added in refs:
            added.set({**row, 'summary_first_pending_at': pending, 'summary_due_at': due})
        first = repair.due_conversations(now=now, limit=1, firestore_client=client)[0]
        assert first.reference == refs[0]
        after = {'phase': 'newest', 'window': 72 * 3600, 'pending': pending, 'due': due, 'path': first.reference.path}
        second = repair.due_conversations(now=now, limit=1, after=after, firestore_client=client)[0]
        assert second.reference == refs[1]
    finally:
        for added in refs:
            added.delete()


def test_newest_phase_orders_pending_desc_then_due_and_name(debt_store, monkeypatch):
    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    refs = [ref.parent.document(name) for name in ('a', 'b', 'd', 'e')]
    ref.update({'summary_due_at': None})
    try:
        for added, pending, due in zip(refs, (now - 10, now - 10, now - 10, now - 100), (3, 2, 2, 1)):
            added.set({**row, 'summary_first_pending_at': pending, 'summary_due_at': now - 10 + due})
        page = repair.due_conversations(now=now, firestore_client=client)
        assert [s.id for s in page] == ['b', 'd', 'a', 'e']
        first = page[0]
        cursor = {
            'phase': 'newest',
            'window': 72 * 3600,
            'pending': first.to_dict()['summary_first_pending_at'],
            'due': first.to_dict()['summary_due_at'],
            'path': first.reference.path,
        }
        assert [s.id for s in repair.due_conversations(now=now, after=cursor, firestore_client=client)] == [
            'd',
            'a',
            'e',
        ]
    finally:
        for added in refs:
            added.delete()


@pytest.mark.parametrize('legacy', [True, False])
def test_near_expiry_is_not_starved_by_large_newer_pile_and_retains_unattempted_tail(debt_store, monkeypatch, legacy):
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 10)
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    urgent = [ref.parent.document(f'urgent-{i:02}') for i in range(12)]
    newer = [ref.parent.document(f'newer-{i:03}') for i in range(150)]
    ref.update({'summary_due_at': None})
    admitted = []

    def redrive(client, owner, conversation_id, *, now):
        admitted.append(conversation_id)
        # Synthetic settlement keeps the second tick focused on remaining debt.
        ref.parent.document(conversation_id).update({'summary_due_at': None})
        return True

    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        batch = client.batch()
        for i, added in enumerate(urgent):
            batch.set(added, {**row, 'summary_first_pending_at': cutoff + 300 + i, 'summary_due_at': now - 1})
        for i, added in enumerate(newer):
            batch.set(added, {**row, 'summary_first_pending_at': now - 100 - i, 'summary_due_at': now - 1})
        batch.commit()
        stale = {'pending': now - 200, 'due': now - 1, 'path': newer[100].path}
        cursor = (
            stale
            if legacy
            else {'version': 2, 'phases': {'newest': {**stale, 'phase': 'newest', 'window': max_age_seconds()}}}
        )
        client.document(repair.CURSOR).set(cursor)
        first = repair.tick(now=now, client=client)
        assert first['near_expiry_admitted'] == first['admitted'] == 8
        assert delivery.NEAR_EXPIRY_ADMITTED._value.get() == 8
        assert first['scanned'] == 12  # No newest query after urgent exhausts admissions.
        assert admitted == [s.id for s in urgent[:8]]
        progress = client.document(repair.CURSOR).get().to_dict()
        assert progress['version'] == 2 and progress['path'] is None
        assert progress['phases']['near_expiry']['path'] == urgent[7].path
        if not legacy:
            assert progress['phases']['newest'] == cursor['phases']['newest']
        second = repair.tick(now=now + repair.REPAIR_INTERVAL_SECONDS, client=client)
        assert second['near_expiry_admitted'] == 4 and second['admitted'] == 8
        assert delivery.NEAR_EXPIRY_ADMITTED._value.get() == 4
        assert second['scanned'] <= repair.REPAIR_SCAN_LIMIT
        assert admitted[:12] == [s.id for s in urgent]
        if legacy:
            assert admitted[12:] == [s.id for s in newer[:4]]
    finally:
        batch = client.batch()
        for added in urgent + newer:
            batch.delete(added)
        batch.commit()


def test_expiry_band_boundary_goes_first_and_remaining_budget_goes_newest(debt_store, monkeypatch):
    from config.summary_guarantee import REPAIR_NEAR_EXPIRY_SECONDS
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 10)
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    pending = [cutoff, cutoff + REPAIR_NEAR_EXPIRY_SECONDS, cutoff + REPAIR_NEAR_EXPIRY_SECONDS + 1, now - 1]
    refs = [ref.parent.document(f'band-{i}') for i in range(4)]
    ref.update({'summary_due_at': None})
    admitted = []
    monkeypatch.setattr(repair, 'redrive', lambda _, uid, cid, **kwargs: admitted.append(cid) or True)
    try:
        for added, at in zip(refs, pending):
            added.set({**row, 'summary_first_pending_at': at, 'summary_due_at': now - 1})
        counts = repair.tick(now=now, client=client)
        assert admitted == ['band-0', 'band-1', 'band-3', 'band-2']
        assert counts['near_expiry_admitted'] == 2
        assert counts['admitted'] == counts['scanned'] == 4
    finally:
        for added in refs:
            added.delete()


def test_tick_repair_counter_matches_returned_counts_and_ignores_unclaimed_ticks(debt_store, monkeypatch):
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    refs = [ref.parent.document(name) for name in ('urgent-ok', 'urgent-error', 'newest-ok', 'created-old')]
    ref.update({'summary_due_at': None})
    keys = {
        'scanned': 'scanned',
        'admitted': 'admitted',
        'error': 'errors',
        'expired_seen': 'expired_seen',
        'near_expiry_admitted': 'near_expiry_admitted',
    }
    before = {outcome: delivery.REPAIR.labels(outcome=outcome)._value.get() for outcome in keys}

    def redrive(_, owner, conversation_id, *, now):
        if conversation_id == 'urgent-error':
            raise RuntimeError('synthetic admission failure')
        return True

    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        for added, pending in zip(refs, (cutoff + 100, cutoff + 101, now - 1, now - 2)):
            candidate = {**row, 'summary_first_pending_at': pending, 'summary_due_at': now - 1}
            if added.id == 'created-old':
                candidate['created_at'] = cutoff - 1
            added.set(candidate)
        counts = repair.tick(now=now, client=client)
        assert counts == {'scanned': 4, 'admitted': 2, 'near_expiry_admitted': 1, 'errors': 1, 'expired_seen': 1}
        after = {outcome: delivery.REPAIR.labels(outcome=outcome)._value.get() for outcome in keys}
        assert {outcome: after[outcome] - before[outcome] for outcome in keys} == {
            outcome: counts[key] for outcome, key in keys.items()
        }
        assert {sample.labels['outcome'] for sample in next(iter(delivery.REPAIR.collect())).samples} == set(keys)
        assert not any(repair.tick(now=now + 1, client=client).values())
        assert {outcome: delivery.REPAIR.labels(outcome=outcome)._value.get() for outcome in keys} == after
    finally:
        for added in refs:
            added.delete()


def test_owner_fairness_is_shared_across_phases_and_skipped_rows_return_next_tick(debt_store, monkeypatch):
    from collections import Counter
    from utils.enrichment.age_gate import max_age_seconds

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 3)
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    now = 1_800_000_000.0
    cutoff = now - max_age_seconds()
    other = client.collection('users').document(uid + '-other').collection('conversations')
    urgent = [ref.parent.document(f'urgent-{i}') for i in range(4)]
    newest = [ref.parent.document(f'newest-{i}') for i in range(4)]
    other_urgent = [other.document(f'urgent-{i}') for i in range(2)]
    other_newest = [other.document(f'newest-{i}') for i in range(2)]
    ref.update({'summary_due_at': None})
    admitted = []

    def redrive(client, owner, conversation_id, *, now):
        admitted.append((owner, conversation_id))
        client.collection('users').document(owner).collection('conversations').document(conversation_id).update(
            {'summary_due_at': None}
        )
        return True

    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        for refs, pending in (
            (urgent, [cutoff + 400 + i for i in range(4)]),
            (other_urgent, [cutoff + 420 + i for i in range(2)]),
            (newest, [now - 10 - i for i in range(4)]),
            (other_newest, [now - 30 - i for i in range(2)]),
        ):
            for added, at in zip(refs, pending):
                added.set({**row, 'summary_first_pending_at': at, 'summary_due_at': now - 1})
        for tick, expected, urgent_count in ((0, 6, 5), (1, 4, 1), (2, 2, 0)):
            start = len(admitted)
            counts = repair.tick(now=now + tick * repair.REPAIR_INTERVAL_SECONDS, client=client)
            assert counts['admitted'] == expected
            assert counts['near_expiry_admitted'] == urgent_count
            assert counts['scanned'] <= repair.REPAIR_SCAN_LIMIT
            assert max(Counter(owner for owner, _ in admitted[start:]).values()) <= 3
            if tick == 0:
                # One owner's fourth urgent row is retried next tick, while
                # the other owner still receives urgent and newest capacity.
                assert (uid, urgent[3].id) not in admitted
                assert (uid + '-other', other_newest[0].id) in admitted
            if tick == 1:
                assert (uid, urgent[3].id) in admitted[start:]
        assert len(admitted) == len(set(admitted)) == 12
    finally:
        for added in urgent + newest + other_urgent + other_newest:
            added.delete()


@pytest.mark.parametrize('mode', ['refusals', 'owner_fairness'])
def test_scan_budget_walks_refusals_in_bounded_chunks(debt_store, monkeypatch, mode):
    client, uid, tasks, ref, row = debt_store
    now = 1_800_000_000.0
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 1200)
    ref.update({'summary_due_at': None})
    other = client.collection('users').document(uid + '-chunk-other').collection('conversations')
    refs = [
        (other if mode == 'owner_fairness' and i == 600 else ref.parent).document(f'chunk-{i:04}') for i in range(1201)
    ]
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    calls = []
    query = repair.due_conversations

    def tracked(**kwargs):
        calls.append((kwargs['phase'], kwargs['limit']))
        return query(**kwargs)

    admitted = []
    monkeypatch.setattr(repair, 'due_conversations', tracked)
    monkeypatch.setattr(repair, 'redrive', lambda _, owner, cid, **kwargs: admitted.append(cid) or True)
    try:
        for start in range(0, len(refs), 500):
            batch = client.batch()
            for i in range(start, min(start + 500, len(refs))):
                batch.set(
                    refs[i],
                    {
                        **row,
                        'summary_first_pending_at': now - i - 1,
                        'summary_due_at': now - 1,
                        'summary_output_present': (i != 1000 if mode == 'refusals' else i > 600),
                    },
                )
            batch.commit()
        counts = repair.tick(now=now, client=client)
        assert counts['scanned'] == 1200
        assert counts['admitted'] == (1 if mode == 'refusals' else 4)
        assert admitted == ([refs[1000].id] if mode == 'refusals' else [s.id for s in refs[:3]] + [refs[600].id])
        assert [limit for phase, limit in calls if phase == 'newest'] == [500, 500, 200]
        assert all(limit <= 500 for _, limit in calls)
        progress = client.document(repair.CURSOR).get().to_dict()['phases']['newest']
        retained = 1199
        assert progress['path'] == refs[retained].path
        assert (
            query(now=now, phase='newest', after=progress, limit=1, firestore_client=client)[0].reference
            == refs[retained + 1]
        )
    finally:
        for start in range(0, len(refs), 500):
            batch = client.batch()
            for added in refs[start : start + 500]:
                batch.delete(added)
            batch.commit()


@pytest.mark.parametrize('stop', ['admission', 'time', 'fence_time'])
def test_scan_stops_before_next_chunk_and_preserves_fetched_tail(debt_store, monkeypatch, stop):
    client, uid, tasks, ref, row = debt_store
    now = 1_800_000_000.0
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 1200)
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 10)
    clock = [0.0]
    monkeypatch.setattr(repair, '_scan_clock', lambda: clock[0])

    def deletion_gate(_):
        if stop == 'fence_time':
            clock[0] = repair.REPAIR_SCAN_TIME_BUDGET_SECONDS
        return False

    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', deletion_gate)
    ref.update({'summary_due_at': None})
    refs = [ref.parent.document(f'stop-{i:04}') for i in range(501)]
    calls, admitted = [], []
    query = repair.due_conversations

    def tracked(**kwargs):
        calls.append((kwargs['phase'], kwargs['limit']))
        return query(**kwargs)

    def redrive(_, owner, cid, **kwargs):
        admitted.append(cid)
        if stop == 'time':
            clock[0] = repair.REPAIR_SCAN_TIME_BUDGET_SECONDS
        return True

    monkeypatch.setattr(repair, 'due_conversations', tracked)
    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        for start in range(0, len(refs), 500):
            batch = client.batch()
            for i in range(start, min(start + 500, len(refs))):
                batch.set(
                    refs[i],
                    {
                        **row,
                        'summary_first_pending_at': now - i - 1,
                        'summary_due_at': now - 1,
                        'summary_output_present': i >= 9,
                    },
                )
            batch.commit()
        counts = repair.tick(now=now, client=client)
        expected = {'admission': 8, 'time': 1, 'fence_time': 0}[stop]
        assert counts['scanned'] == 500 and counts['admitted'] == expected
        assert admitted == [s.id for s in refs[:expected]]
        assert [limit for phase, limit in calls if phase == 'newest'] == [500]
        progress = client.document(repair.CURSOR).get().to_dict()['phases'].get('newest')
        if expected:
            assert progress['path'] == refs[expected - 1].path
        else:
            assert progress is None
        assert (
            query(now=now, phase='newest', after=progress, limit=1, firestore_client=client)[0].reference
            == refs[expected]
        )
    finally:
        for start in range(0, len(refs), 500):
            batch = client.batch()
            for added in refs[start : start + 500]:
                batch.delete(added)
            batch.commit()


@pytest.mark.parametrize('hours', [72, 0])
def test_owner_deferral_continuation_discovers_other_owner_and_retries_all_debt_after_wrap(
    debt_store, monkeypatch, hours
):
    """A failing urgent share must not pin discovery behind multiple scan budgets."""
    from collections import Counter
    from math import ceil

    client, uid, tasks, ref, row = debt_store
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', str(hours))
    monkeypatch.setattr(repair, 'REPAIR_SCAN_LIMIT', 8)
    monkeypatch.setattr(repair, 'REPAIR_PER_OWNER_TICK_LIMIT', 3)
    monkeypatch.setattr(repair, 'REPAIR_ADMISSION_LIMIT', 8)
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    now = 1_800_000_000.0
    urgent = [ref.parent.document(f'urgent-{i}') for i in range(3 if hours else 0)]
    newest = [ref.parent.document(f'newest-{i:03}') for i in range(17)]
    other = client.collection('users').document(uid + '-other').collection('conversations').document('other')
    ref.update({'summary_due_at': None})
    attempts, admitted = [], []
    failing = True

    def redrive(client, owner, cid, **kwargs):
        attempts.append((owner, cid))
        if failing and owner == uid:
            raise RuntimeError('synthetic persistent admission failure')
        admitted.append((owner, cid))
        client.collection('users').document(owner).collection('conversations').document(cid).update(
            {'summary_due_at': None}
        )
        return True

    monkeypatch.setattr(repair, 'redrive', redrive)
    try:
        batch = client.batch()
        for i, added in enumerate(urgent):
            batch.set(added, {**row, 'summary_first_pending_at': now - hours * 3600 + 480 + i})
        for i, added in enumerate(newest):
            batch.set(added, {**row, 'summary_first_pending_at': now - i - 1})
        batch.set(other, {**row, 'summary_first_pending_at': now - 1000})
        batch.commit()
        bound = ceil((len(newest) + 1) / (8 - len(urgent)))
        for tick in range(bound):
            start = len(attempts)
            counts = repair.tick(now=now + tick * repair.REPAIR_INTERVAL_SECONDS, client=client)
            assert counts['scanned'] <= 8 and len(attempts) - start <= 8
            assert max(Counter(owner for owner, _ in attempts[start:]).values()) <= 3
            if tick == 0:
                progress = client.document(repair.CURSOR).get().to_dict()
                cursor = progress['phases']['newest'] if hours else progress
                assert cursor['path'] == newest[8 - len(urgent) - 1].path
        assert admitted == [(uid + '-other', 'other')]
        assert all(snapshot.to_dict()['summary_due_at'] == row['summary_due_at'] for snapshot in client.get_all(newest))
        # Quota deferral changes no debt row. Once urgent failures are removed,
        # wrapping the continuation must eventually admit every deferred row.
        for added in urgent:
            added.update({'summary_due_at': None})
        failing = False
        for tick in range(bound, bound + ceil(len(newest) / 3) + 2):
            repair.tick(now=now + tick * repair.REPAIR_INTERVAL_SECONDS, client=client)
            if len(admitted) == len(newest) + 1:
                break
        assert len(admitted) == len(set(admitted)) == len(newest) + 1
        assert set(admitted) == {(uid, added.id) for added in newest} | {(uid + '-other', 'other')}
        assert all(snapshot.to_dict()['summary_due_at'] is None for snapshot in client.get_all(newest + [other]))
    finally:
        batch = client.batch()
        for added in urgent + newest + [other]:
            batch.delete(added)
        batch.commit()
