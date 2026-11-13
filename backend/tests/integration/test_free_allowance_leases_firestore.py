"""Loopback-only contention and real billing proofs for shadow allowance leases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
from types import SimpleNamespace
from uuid import uuid4

from google.api_core.exceptions import Aborted
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import free_allowance_leases as ledger, monthly_usage_totals as totals, user_usage
from database.legal_holds import DestructiveOperationInProgress
from utils import analytics
from utils.stt.allowance_session import Operation
from utils.stt.allowance_batch import observe_billed_batch
from utils.stt import allowance_batch

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
pytestmark = pytest.mark.integration


@pytest.fixture
def lane(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-free-allowance', credentials=AnonymousCredentials())
    uid = 'synthetic-' + uuid4().hex
    user = client.collection('users').document(uid)
    user.set({'synthetic': True})
    totals.month_ref(user, NOW).set(
        {'schema_version': 1, 'epoch': 'v1', 'ready': True, 'totals': {'transcription_seconds': 90}, 'days': {}}
    )
    monkeypatch.setattr(ledger, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(totals, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(user_usage, 'db', client)
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'free')
    yield client, uid, user
    client.close()


def reserve(lane, operation, seconds=6, **kwargs):
    client, uid, _ = lane
    return ledger.reserve(uid, operation, seconds, 100, now=NOW, firestore_client=client, **kwargs)


@pytest.fixture
def finish_batch_observations(monkeypatch):
    """Await real DB workers separately from the observer's serving deadline."""
    executor = allowance_batch.free_allowance_executor
    pending = []

    def submit(*args, **kwargs):
        future = executor.submit(*args, **kwargs)
        pending.append(future)
        return future

    def finish():
        for future in pending:
            future.result(timeout=30)

    monkeypatch.setattr(allowance_batch, 'free_allowance_executor', SimpleNamespace(submit=submit))
    yield finish
    finish()


def test_two_replicas_race_for_the_last_allowance(lane):
    barrier = threading.Barrier(2)

    def contender(operation):
        barrier.wait(timeout=5)
        try:
            return reserve(lane, operation)
        except (Aborted, ValueError) as error:
            if not isinstance(error, Aborted) and not isinstance(error.__cause__, Aborted):
                raise
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(contender, ['first', 'second']))
    assert sum(result is not None and result.lease is not None for result in results) <= 1
    if not any(result is not None and result.lease is not None for result in results):
        assert reserve(lane, 'after-contention').lease is not None
    assert reserve(lane, 'another').reason == 'allowance_exhausted'
    client, uid, _ = lane
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 96


def test_replica_retry_of_same_operation_never_duplicates_a_hold(lane):
    barrier = threading.Barrier(2)

    def contender(_):
        barrier.wait(timeout=5)
        try:
            return reserve(lane, 'same-operation')
        except (Aborted, ValueError) as error:
            if not isinstance(error, Aborted) and not isinstance(error.__cause__, Aborted):
                raise
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(contender, range(2)))
    recovered = reserve(lane, 'same-operation')
    assert recovered.lease is not None
    assert all(result.lease.key == recovered.lease.key for result in results if result is not None)
    assert reserve(lane, 'same-operation').lease.key == recovered.lease.key
    assert ledger.chargeable_seconds(lane[1], NOW, firestore_client=lane[0]) == 96


def test_firestore_aborted_commit_retries_with_no_extra_spend(lane, monkeypatch):
    client, uid, _ = lane
    transaction = client.transaction(max_attempts=3)
    original = transaction._commit
    attempts = []

    def commit():
        attempts.append(True)
        if len(attempts) == 1:
            transaction._rollback()
            raise Aborted('synthetic first commit abort')
        return original()

    monkeypatch.setattr(transaction, '_commit', commit)
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction)
    assert reserve(lane, 'retry').lease is not None
    assert len(attempts) == 2
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 96


def test_terminal_zero_releases_expired_hold_without_fabricating_an_overage(lane):
    client, uid, user = lane
    first = reserve(lane, 'failed-request').lease
    assert first is not None
    result = ledger.reserve(uid, 'failed-request', 6, 100, now=NOW + timedelta(seconds=31))
    assert result.reason == 'lease_expired'
    assert ledger.settle_billed([first], 0, now=NOW)
    receipt = user.collection('free_allowance_receipts').document(f'{first.month}_{first.key}').get().to_dict()
    assert receipt['decision'] == 'unobserved' and receipt['billed_seconds'] == 0
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 90
    assert reserve(lane, 'failed-request').reason == 'already_settled'
    assert reserve(lane, 'next-request', 10).lease is not None


def test_actual_billing_units_release_their_hold_and_no_other(lane):
    client, uid, user = lane
    first = reserve(lane, 'first', 4).lease
    other = reserve(lane, 'other', 4).lease
    assert first is not None and other is not None
    scope = Operation(uid, 'one_shot', operation='first', seconds=4)
    scope.reference = first
    analytics.record_usage(uid, transcription_seconds=3, allowance_operation=scope)
    # Billing used 3, not the 4-second input estimate; other work is still held.
    assert totals.month_ref(user, NOW).get().to_dict()['totals']['transcription_seconds'] == 93
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 97
    assert reserve(lane, 'first').reason == 'already_settled'


def test_lost_settlement_reply_can_be_replayed_without_double_ptt_charge(lane, monkeypatch):
    client, uid, user = lane
    lease = reserve(lane, 'ptt').lease
    assert lease is not None
    assert ledger.settle_daily_ptt(lease, 3.125, now=NOW, firestore_client=client)
    assert not ledger.settle_daily_ptt(lease, 3.125, now=NOW, firestore_client=client)
    assert totals.month_ref(user, NOW).get().to_dict()['totals']['transcription_seconds'] == 90
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 93.125


def test_pending_wipe_or_missing_root_refuses_publication(lane):
    client, uid, user = lane
    client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})
    with pytest.raises(DestructiveOperationInProgress):
        reserve(lane, 'during-wipe')
    assert not user.collection('free_allowance_months').document('2026-11').get().exists
    client.collection('account_deletions').document(uid).delete()
    user.delete()
    with pytest.raises(DestructiveOperationInProgress):
        reserve(lane, 'missing-root')
    assert not user.collection('free_allowance_months').document('2026-11').get().exists


def test_rollover_keeps_old_holds_until_billing_and_releases_all_operation_periods(lane):
    client, uid, user = lane
    boundary = NOW.replace(day=30, hour=23, minute=59, second=50)
    old = ledger.reserve(uid, 'spanning', 6, 100, now=boundary, firestore_client=client).lease
    assert old is not None
    next_month = boundary + timedelta(seconds=11)
    totals.month_ref(user, next_month).set(
        {'schema_version': 1, 'epoch': 'v1', 'ready': True, 'totals': {'transcription_seconds': 0}, 'days': {}}
    )
    new = ledger.reserve(uid, 'spanning', 6, 100, now=next_month, firestore_client=client).lease
    assert new is not None
    # Successful daily PTT settlement uses the current billing month, not the input's capture month.
    assert ledger.settle_daily_ptt(new, 3.125, now=next_month, firestore_client=client)
    assert ledger.chargeable_seconds(uid, boundary, firestore_client=client) == 90
    assert ledger.chargeable_seconds(uid, next_month, firestore_client=client) == 3.125


def test_new_month_baseline_is_proved_from_sources_not_an_empty_usage_fallback(lane):
    client, uid, user = lane
    totals.month_ref(user, NOW).delete()
    user.collection('hourly_usage').document('2026-11-12-12').set(
        {'id': '2026-11-12-12', 'year': 2026, 'month': 11, 'transcription_seconds': 90}
    )
    totals.establish_verified_month(uid, NOW, firestore_client=client)
    assert totals.read_verified_transcription_seconds(uid, NOW, firestore_client=client) == 90
    assert reserve(lane, 'after-proof').lease is not None


def test_failed_baseline_scan_never_publishes_zero(lane, monkeypatch):
    client, uid, user = lane
    totals.month_ref(user, NOW).delete()

    def unreadable(*args, **kwargs):
        raise TimeoutError('synthetic unreadable hourly source')

    monkeypatch.setattr(totals, '_month_rows', unreadable)
    with pytest.raises(TimeoutError):
        totals.establish_verified_month(uid, NOW, firestore_client=client)
    assert not totals.month_ref(user, NOW).get().exists


def test_genuine_zero_requires_a_successful_source_query(lane):
    client, uid, user = lane
    totals.month_ref(user, NOW).delete()
    totals.establish_verified_month(uid, NOW, firestore_client=client)
    assert totals.read_verified_transcription_seconds(uid, NOW, firestore_client=client) == 0


def test_batch_writer_and_late_registered_chunk_preserve_exact_partial_billing(
    lane, monkeypatch, finish_batch_observations
):
    from types import SimpleNamespace
    from database.batch_pipeline_projection import ProjectionStore
    from database.sync_ledger import sync_content_ledger_ref
    from database.hourly_usage_updates import prepare_hourly_usage_updates

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client, uid, user = lane
    content = 'batch-content'
    source = sync_content_ledger_ref(client, uid, content)
    source.set({'status': 'processing'})
    reserve(lane, 'batch-unit:64')
    projection = ProjectionStore(SimpleNamespace(client=client))

    def write(seconds, charged, now):
        updates = prepare_hourly_usage_updates(NOW, {'transcription_seconds': int(seconds) - int(charged)}, 'free')

        @firestore.transactional
        def commit(tx):
            with totals.publication_fence(user, tx, firestore_client=client):
                prior = source.get(transaction=tx).to_dict()
                projection._commit_usage(
                    tx,
                    source,
                    prior,
                    SimpleNamespace(owner_id=uid),
                    {'charged': charged, 'updates': updates, 'hour': NOW.strftime('%Y-%m-%d-%H')},
                    seconds,
                    now,
                )
                tx.update(source, {'status': 'partial'})

        commit(client.transaction())

    write(3.8, 0, NOW.timestamp())
    # The entire partial observer is missed; the next completion must repair it.
    write(7.9, 3.8, NOW.timestamp() + 10)
    assert totals.month_ref(user, NOW).get().to_dict()['totals']['transcription_seconds'] == 97
    assert source.get().to_dict()['allowance_billed_seconds'] == 7
    ids = [str(i) for i in range(65)]
    observe_billed_batch(client, uid, content, NOW, ids, NOW.timestamp() + 10)
    observe_billed_batch(client, uid, content, NOW, ids, NOW.timestamp() + 20)
    finish_batch_observations()
    receipts = [row.to_dict() for row in user.collection('free_allowance_receipts').stream()]
    assert sum(row['billed_seconds'] for row in receipts) == 7
    assert ledger.chargeable_seconds(uid, NOW, firestore_client=client) == 97


def test_concurrent_batch_replays_share_one_cumulative_receipt(lane, monkeypatch, finish_batch_observations):
    from database.sync_ledger import sync_content_ledger_ref

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client, uid, user = lane
    sync_content_ledger_ref(client, uid, 'batch-content').set(
        {
            'usage_committed_at': NOW,
            'allowance_billing_started_at': NOW,
            'allowance_billed_seconds': 7,
        }
    )
    reserve(lane, 'batch-unit:0', 2)
    reserve(lane, 'batch-unit:64', 2)
    ids = [str(i) for i in range(65)]

    def replay(_):
        observe_billed_batch(client, uid, 'batch-content', NOW, ids, NOW.timestamp())

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(replay, range(2)))
    replay(None)  # Repair any conservative bounded-contention failure.
    finish_batch_observations()
    receipts = [row.to_dict() for row in user.collection('free_allowance_receipts').stream()]
    assert sum(row['billed_seconds'] for row in receipts) == 7
    assert not user.collection('free_allowance_months').document('2026-11').get().to_dict()['holds']
