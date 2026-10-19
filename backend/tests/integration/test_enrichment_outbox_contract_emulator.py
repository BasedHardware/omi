"""Enrichment outbox contracts that every future backing store must keep.

Plan C (backend target architecture, workstream C) moves the sync enrichment
outbox (``utils/sync/reprocess.py``) into a neutral ``utils/enrichment``
package and onto a dedicated queue. These tests pin the behaviour the move must
preserve, against today's code and a real Firestore emulator:

1. first-summary dispatch: the wake is scheduled no later than
   ``first_pending_at`` + 120s, regardless of the trailing settle window;
2. coalescing: repeated marks fold into one obligation and one wake;
3. stale-token refusal: a delivery whose token was rotated never runs work;
4. lease expiry: a crashed worker's lease blocks redelivery until it expires,
   then the sweep re-wakes the obligation under a new token;
5. custody transfer: a merged donor's debt moves to the canonical conversation
   without extending its deadline, and the donor's token goes stale;
6. privacy fence: a deleted conversation or blocked owner discards the row
   without running work; invalid redirect topology keeps the debt.

Only the Cloud Tasks client leaf is replaced (captured in memory). Run under a
loopback Firestore emulator, for example::

    cd backend && firebase emulators:exec --only firestore --project demo-omi-isolated-tests \\
        'python -m pytest -m integration tests/integration/test_enrichment_outbox_contract_emulator.py'

No cloud credentials, accounts or production documents are used.
"""

from __future__ import annotations

import math
import uuid
from unittest.mock import Mock

import pytest

from tests.integration.test_sync_reprocess_emulator import loopback_only_network, store  # noqa: F401
from utils.sync import reprocess

pytestmark = pytest.mark.integration

REAL_ENQUEUE = reprocess._enqueue  # type: ignore[reportPrivateUsage]
HANDLER = 'https://fresh.invalid/v2/sync-jobs/run'
SUMMARY = {'structured': {'overview': 'Synthetic summary committed through the normal callback'}}


@pytest.fixture
def outbox(store, monkeypatch):  # noqa: F811
    """Real outbox IO and real ``_enqueue``; Cloud Tasks calls are captured."""
    client, uid, _ = store
    from utils import cloud_tasks

    for name in (
        'DEMAND_PROCESSING_ENABLED',
        'REPEAT_WORK_REVISION_ENABLED',
        'FIRST_SUMMARY_DEADLINE_SECONDS',
        'FIRST_SUMMARY_DEADLINE_ENABLED',
        'FIRST_SUMMARY_DEADLINE_PERCENT',
        'FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED',
    ):
        monkeypatch.delenv(name, raising=False)
    tasks: list[dict] = []

    def enqueue_named_task(queue, url, task_id, payload, *, audience=None, invoker_sa=None, schedule_at=None):
        tasks.append(
            {
                'queue': queue,
                'url': url,
                'name': task_id,
                'payload': dict(payload),
                'audience': audience,
                'schedule_at': schedule_at,
            }
        )

    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue_named_task)
    monkeypatch.setattr(reprocess, '_enqueue', REAL_ENQUEUE)
    # The sweep probes Cloud Tasks for an existing first-summary wake; model an
    # exhausted/missing task so the repair path is exercised.
    monkeypatch.setattr(reprocess, '_wake_exists', lambda _row: False)
    yield client, uid, tasks


@pytest.fixture
def first_summary(monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')


def owned(tasks, uid, conversation_id):
    key = reprocess.key(uid, conversation_id)
    return [task for task in tasks if task['payload']['key'] == key]


def row(client, uid, conversation_id):
    return client.collection(reprocess.COLLECTION).document(reprocess.key(uid, conversation_id)).get().to_dict()


# 1. First-summary dispatch within 120s ------------------------------------------------


@pytest.mark.parametrize('configured_deadline', [None, '600'])
def test_first_summary_wake_is_scheduled_within_120s_of_acceptance(
    outbox, first_summary, monkeypatch, configured_deadline
):
    client, uid, tasks = outbox
    if configured_deadline:
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', configured_deadline)  # Clamped to 120.
    accepted = 1_000.0
    reprocess.mark(uid, 'c', 'en', now=accepted)

    stored = row(client, uid, 'c')
    assert stored['first_pending_at'] == accepted
    assert stored['summary_deadline_at'] <= accepted + 120
    assert stored['due_at'] <= accepted + 120  # Not the 600s settle window.
    (task,) = owned(tasks, uid, 'c')
    assert task['schedule_at'] <= math.ceil(accepted + 120)
    assert task['queue'] == 'sync-jobs' and task['url'] == HANDLER and task['audience'] == HANDLER
    assert task['name'] == f"sr-{reprocess.key(uid, 'c')}-{stored['task_token']}"
    assert task['payload'] == {
        'kind': 'sync_reprocess',
        'key': reprocess.key(uid, 'c'),
        'task_token': stored['task_token'],
    }

    process = Mock(return_value=SUMMARY)
    assert reprocess.run(task['payload']['key'], stored['task_token'], process, now=accepted + 120) == 'processed'
    process.assert_called_once_with(uid, 'c', 'en')
    receipt = row(client, uid, 'c')
    assert receipt['summary_seen'] and receipt['dormant'] and receipt['uid'] is None


def test_appends_never_extend_the_first_summary_deadline(outbox, first_summary):
    client, uid, tasks = outbox
    reprocess.mark(uid, 'c', 'en', now=1_000)
    reprocess.mark(uid, 'c', 'en', now=1_090)
    stored = row(client, uid, 'c')
    assert stored['first_pending_at'] == 1_000 and stored['summary_deadline_at'] == 1_120
    assert stored['due_at'] == 1_120
    assert [task['schedule_at'] for task in owned(tasks, uid, 'c')] == [1_120]


def test_without_first_summary_policy_the_trailing_settle_window_applies(outbox):
    client, uid, tasks = outbox
    reprocess.mark(uid, 'c', 'en', now=1_000)
    stored = row(client, uid, 'c')
    assert 'summary_deadline_at' not in stored and stored['due_at'] == 1_600
    assert [task['schedule_at'] for task in owned(tasks, uid, 'c')] == [1_600]


# 2. Coalescing -----------------------------------------------------------------------


def test_repeated_marks_coalesce_into_one_obligation_and_one_wake(outbox):
    client, uid, tasks = outbox
    for offset in range(5):
        reprocess.mark(uid, 'c', 'en', now=1_000 + offset)
    stored = row(client, uid, 'c')
    assert stored['version'] == 5
    assert stored['due_at'] == 1_604  # Trailing edge of the latest update.
    assert len(owned(tasks, uid, 'c')) == 1
    assert owned(tasks, uid, 'c')[0]['payload']['task_token'] == stored['task_token']
    docs = list(client.collection(reprocess.COLLECTION).where('uid', '==', uid).stream())
    assert [doc.id for doc in docs] == [reprocess.key(uid, 'c')]

    process = Mock()
    assert reprocess.run(stored['document_id'], stored['task_token'], process, now=1_604) == 'processed'
    process.assert_called_once_with(uid, 'c', 'en')
    assert row(client, uid, 'c') is None


def test_obligations_are_keyed_per_owner_and_conversation(outbox):
    client, uid, tasks = outbox
    reprocess.mark(uid, 'a', 'en', now=0)
    reprocess.mark(uid, 'b', 'en', now=0)
    assert reprocess.key(uid, 'a') != reprocess.key(uid, 'b')
    assert len(owned(tasks, uid, 'a')) == len(owned(tasks, uid, 'b')) == 1


# 3. Stale-token refusal --------------------------------------------------------------


def test_stale_or_unknown_tokens_never_run_work(outbox):
    client, uid, tasks = outbox
    reprocess.mark(uid, 'c', 'en', now=0)
    key = reprocess.key(uid, 'c')
    original = row(client, uid, 'c')['task_token']
    process = Mock(side_effect=AssertionError('stale delivery must not run'))

    assert reprocess.run(key, uuid.uuid4().hex, process, now=600) == 'stale'
    assert reprocess.run(reprocess.key(uid, 'missing'), original, process, now=600) == 'stale'

    # An early delivery defers and rotates the token; the old token is fenced.
    assert reprocess.run(key, original, process, now=10) == 'deferred'
    rotated = row(client, uid, 'c')['task_token']
    assert rotated != original and owned(tasks, uid, 'c')[-1]['payload']['task_token'] == rotated
    assert reprocess.run(key, original, process, now=600) == 'stale'

    work = Mock()
    assert reprocess.run(key, rotated, work, now=600) == 'processed'
    work.assert_called_once()
    assert reprocess.run(key, rotated, process, now=601) == 'stale'  # Replay after completion.


def test_batch_task_adapter_rejects_malformed_bindings_before_any_io(outbox):
    from utils.batch_pipeline import enrichment

    with pytest.raises(ValueError):
        enrichment.run_enrichment('not-a-key', uuid.uuid4().hex, process=Mock())
    with pytest.raises(ValueError):
        enrichment.run_enrichment('0' * 64, 'not-a-token', process=Mock())


# 4. Lease expiry repaired by the sweep ------------------------------------------------


@pytest.mark.parametrize(
    ('summary_policy', 'lease_seconds'),
    [(False, reprocess.LEASE_SECONDS), (True, reprocess.FIRST_SUMMARY_LEASE_SECONDS)],
)
def test_crashed_worker_lease_blocks_until_expiry_then_sweep_rewakes(
    outbox, monkeypatch, summary_policy, lease_seconds
):
    client, uid, tasks = outbox
    if summary_policy:
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
        monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    reprocess.mark(uid, 'c', 'en', now=0)
    key = reprocess.key(uid, 'c')
    claimed_at = row(client, uid, 'c')['due_at']
    token = row(client, uid, 'c')['task_token']

    with pytest.raises(RuntimeError):
        reprocess.run(key, token, Mock(side_effect=RuntimeError('worker dies')), now=claimed_at)
    leased = row(client, uid, 'c')
    assert leased['lease_until'] == claimed_at + lease_seconds and leased['owner']

    # Redelivery of the same task while leased is refused without running work.
    assert reprocess.run(key, token, Mock(side_effect=AssertionError()), now=claimed_at + 1) == 'busy'
    wakes = len(owned(tasks, uid, 'c'))
    assert reprocess.sweep(now=claimed_at + lease_seconds - 1)['error'] == 0
    assert len(owned(tasks, uid, 'c')) == wakes  # Active lease: no repair.

    expired = claimed_at + lease_seconds
    assert reprocess.sweep(now=expired)['error'] == 0
    repaired = row(client, uid, 'c')
    assert len(owned(tasks, uid, 'c')) == wakes + 1
    assert repaired['task_token'] != token
    assert owned(tasks, uid, 'c')[-1]['payload']['task_token'] == repaired['task_token']

    assert reprocess.run(key, token, Mock(side_effect=AssertionError()), now=expired + 1) == 'stale'
    process = Mock(return_value=SUMMARY)
    assert reprocess.run(key, repaired['task_token'], process, now=expired + 1) == 'processed'
    process.assert_called_once_with(uid, 'c', 'en')


def test_sweep_repairs_a_lost_enqueue_between_mark_and_dispatch(outbox, monkeypatch):
    client, uid, tasks = outbox
    from utils import cloud_tasks

    capture = cloud_tasks.enqueue_named_task
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', Mock(side_effect=RuntimeError('lost enqueue ack')))
    with pytest.raises(RuntimeError):
        reprocess.mark(uid, 'c', 'en', now=0)  # The caller sees the failure; the obligation stays durable.
    assert row(client, uid, 'c') is not None and not owned(tasks, uid, 'c')
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', capture)
    assert reprocess.sweep(now=600)['error'] == 0
    (task,) = owned(tasks, uid, 'c')
    assert reprocess.run(task['payload']['key'], task['payload']['task_token'], Mock(), now=600) == 'processed'


# 5. Custody transfer on redirect ------------------------------------------------------


def test_redirect_transfers_custody_without_extending_the_deadline(outbox, first_summary):
    client, uid, tasks = outbox
    user = client.collection('users').document(uid)
    user.collection('conversations').document('canonical').set(
        {'id': 'canonical', 'owner_uid': uid, 'status': 'completed'}
    )
    user.collection('conversations').document('donor').set(
        {'id': 'donor', 'owner_uid': uid, 'deleted': True, 'sync_merged_into': 'canonical'}
    )
    reprocess.mark(uid, 'donor', 'en', now=0)
    reprocess.mark(uid, 'canonical', 'en', now=60)
    donor_key, donor_token = reprocess.key(uid, 'donor'), row(client, uid, 'donor')['task_token']

    def redirect(*_):
        reprocess.summary_delivery.PROCESS_CONTEXT.get()['redirect_to'] = 'canonical'

    assert reprocess.run(donor_key, donor_token, redirect, now=120) == 'redirected'
    assert row(client, uid, 'donor') is None
    canonical = row(client, uid, 'canonical')
    assert canonical['first_pending_at'] == 0  # Earliest acceptance wins.
    assert canonical['summary_deadline_at'] == canonical['due_at'] == 120
    assert canonical['version'] == 2 and not canonical.get('summary_seen')
    assert owned(tasks, uid, 'canonical')[-1]['payload']['task_token'] == canonical['task_token']

    assert reprocess.run(donor_key, donor_token, Mock(side_effect=AssertionError()), now=121) == 'stale'
    process = Mock(return_value=SUMMARY)
    assert reprocess.run(canonical['document_id'], canonical['task_token'], process, now=121) == 'processed'
    process.assert_called_once_with(uid, 'canonical', 'en')
    assert row(client, uid, 'canonical')['summary_seen']


# 6. Privacy fence ---------------------------------------------------------------------


def _blocked_by_user_deletion(client, uid):
    client.collection('users').document(uid).collection('deleted_conversations').document('c').set({'deleted': True})


def _blocked_by_privacy_generation(client, uid):
    from database.batch_pipeline_privacy import advance_privacy_generation

    advance_privacy_generation(client, uid, blocked=True)


def _blocked_by_account_deletion(client, uid):
    client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})


@pytest.mark.parametrize(
    'block', [_blocked_by_user_deletion, _blocked_by_privacy_generation, _blocked_by_account_deletion]
)
def test_privacy_blocked_row_is_discarded_without_running_work(outbox, block):
    from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key
    from utils.batch_pipeline import enrichment

    client, uid, _ = outbox
    client.collection('users').document(uid).collection('conversations').document('c').set({'id': 'c'})
    reprocess.mark(uid, 'c', 'en', now=0)
    key, token = reprocess.key(uid, 'c'), row(client, uid, 'c')['task_token']
    try:
        block(client, uid)
        process = Mock(side_effect=AssertionError('blocked work must not run'))
        assert enrichment.run_enrichment(key, token, now=600, process=process) == 'superseded'
        process.assert_not_called()
        assert row(client, uid, 'c') is None
        # A late redelivery cannot recreate or run the discarded obligation.
        assert enrichment.run_enrichment(key, token, now=601, process=process) == 'stale'
    finally:
        user = client.collection('users').document(uid)
        user.collection('deleted_conversations').document('c').delete()
        user.collection('conversations').document('c').delete()
        client.collection('account_deletions').document(uid).delete()
        client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid)).delete()


def test_invalid_redirect_topology_keeps_the_debt(outbox):
    from utils.batch_pipeline import enrichment

    client, uid, _ = outbox
    conversation = client.collection('users').document(uid).collection('conversations').document('cycle')
    conversation.set({'id': 'cycle', 'deleted': True, 'sync_merged_into': 'cycle'})
    try:
        reprocess.mark(uid, 'cycle', 'en', now=0)
        assert enrichment.discard_blocked(reprocess.key(uid, 'cycle')) is False
        assert row(client, uid, 'cycle') is not None
    finally:
        conversation.delete()
