"""Loopback-only proof of snapshot seeding, atomic counters, retry and resets."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import Aborted
from google.cloud import firestore
import pytest

from database import legal_holds, monthly_usage_totals as totals, user_usage
from database.batch_pipeline_projection import ProjectionStore
from database.hourly_usage_updates import prepare_hourly_usage_updates
from database.sync_ledger import BATCH_PARTIAL_STATUS
from scripts.admin.reset_transcription_usage import ResetPlan, apply_reset

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)


WRITERS = ['ordinary', 'once', 'absolute', 'admin', 'migration']


def run_writer(client, uid, writer, monkeypatch):
    if writer == 'ordinary':
        return user_usage.update_hourly_usage(uid, NOW, {'speech_seconds': 5}, firestore_client=client)
    if writer == 'once':
        return user_usage.update_hourly_usage_once(uid, NOW, {'speech_seconds': 5}, 'erasure', firestore_client=client)
    if writer == 'absolute':
        return user_usage.batch_update_hourly_usage(uid, {NOW: {'speech_seconds': 5}})
    if writer == 'admin':
        return apply_reset(client, uid, ResetPlan((NOW.strftime('%Y-%m-%d-%H'),), 9))
    import firebase_admin
    from firebase_admin import firestore as admin_firestore

    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.setattr(firebase_admin, 'initialize_app', lambda *a, **k: None)
    monkeypatch.setattr(admin_firestore, 'client', lambda: client)
    spec = importlib.util.spec_from_file_location(
        'monthly_usage_migration', Path(__file__).resolve().parents[2] / 'migrations/002_populate_historical_usage.py'
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.delete_hourly_usage_for_user(uid)


@pytest.mark.parametrize('writer', WRITERS)
@pytest.mark.parametrize('state', ['pending', 'completed', 'missing_root', 'destructive_gate'])
def test_writer_cannot_publish_after_erasure_inventory(lane, monkeypatch, writer, state):
    client, uid, user = lane
    source = user.collection('hourly_usage').document(NOW.strftime('%Y-%m-%d-%H'))
    source.set({'speech_seconds': 11, 'transcription_seconds': 9})
    before = source.get().to_dict()
    assert 'monthly_usage_totals' not in [c.id for c in user.collections()]
    if state in {'pending', 'completed'}:
        client.collection('account_deletions').document(uid).set({'wipe_status': state})
    elif state == 'missing_root':
        user.delete()
    else:
        legal_holds.acquire_destructive_operation(
            uid, kind='explicit_memory_deletion', token=uuid4().hex, firestore_client=client
        )
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        run_writer(client, uid, writer, monkeypatch)
    assert source.get().to_dict() == before
    assert not totals.month_ref(user, NOW).get().exists
    assert not user.collection('sync_content_ledger').document('erasure').get().exists


@pytest.mark.parametrize('writer', WRITERS)
@pytest.mark.parametrize('abort', [False, True])
def test_writer_rollback_or_retry_keeps_source_total_and_receipt_atomic(lane, monkeypatch, writer, abort):
    client, uid, user = lane
    source = user.collection('hourly_usage').document(NOW.strftime('%Y-%m-%d-%H'))
    source.set({'speech_seconds': 11, 'transcription_seconds': 9})
    transaction = client.transaction()
    original = transaction._commit
    attempts = []

    def commit():
        attempts.append(1)
        if len(attempts) == 1:
            if abort:
                transaction._rollback()
                raise Aborted('synthetic first-attempt abort')
            raise RuntimeError('synthetic commit failure')
        return original()

    monkeypatch.setattr(transaction, '_commit', commit)
    monkeypatch.setattr(client, 'transaction', lambda: transaction)
    if not abort:
        with pytest.raises(RuntimeError, match='synthetic commit failure'):
            run_writer(client, uid, writer, monkeypatch)
        assert source.get().to_dict() == {'speech_seconds': 11, 'transcription_seconds': 9}
        assert not totals.month_ref(user, NOW).get().exists
        assert not user.collection('sync_content_ledger').document('erasure').get().exists
        return
    run_writer(client, uid, writer, monkeypatch)
    assert len(attempts) == 2
    total = totals.month_ref(user, NOW).get().to_dict()
    if writer in {'ordinary', 'once'}:
        assert source.get().to_dict()['speech_seconds'] == 16
        assert total['totals']['speech_seconds'] == 5
    else:
        assert total['ready'] is False
        if writer == 'migration':
            assert not source.get().exists
        else:
            assert source.get().to_dict()['speech_seconds'] == (5 if writer == 'absolute' else 11)
            assert source.get().to_dict()['transcription_seconds'] == (0 if writer == 'admin' else 9)
    if writer == 'once':
        assert user.collection('sync_content_ledger').document('erasure').get().to_dict()['usage_committed_at']
        assert not run_writer(client, uid, writer, monkeypatch)
        assert source.get().to_dict()['speech_seconds'] == 16


@pytest.mark.parametrize('writer', WRITERS)
@pytest.mark.parametrize('authority', ['marker', 'root'])
def test_writer_publication_cannot_escape_racing_wipe_inventory(lane, monkeypatch, writer, authority):
    client, uid, user = lane
    user.collection('hourly_usage').document(NOW.strftime('%Y-%m-%d-%H')).set({'transcription_seconds': 9})
    fenced, release = threading.Event(), threading.Event()
    original = totals.publication_fence

    @contextmanager
    def pause(*args, **kwargs):
        with original(*args, **kwargs):
            fenced.set()
            assert release.wait(20), 'writer release timed out'
            yield

    monkeypatch.setattr(totals, 'publication_fence', pause)

    def erase():
        if authority == 'marker':
            client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})
        else:
            user.delete()
        for collection in list(user.collections()):
            for snapshot in collection.stream():
                snapshot.reference.delete()
        user.delete()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(run_writer, client, uid, writer, monkeypatch)
        try:
            assert fenced.wait(20), 'writer fence timed out'
            erasing = pool.submit(erase)
            threading.Event().wait(0.25)
        finally:
            release.set()
        try:
            writing.result(timeout=30)
        except legal_holds.DestructiveOperationInProgress:
            pass  # A retry may observe the erasure and reject the entire commit.
        erasing.result(timeout=30)
    assert not totals.month_ref(user, NOW).get().exists
    assert not list(user.collection('hourly_usage').stream())
    assert not list(user.collection('sync_content_ledger').stream())


@pytest.mark.parametrize('writer', ['absolute', 'admin', 'migration'])
def test_chunked_correction_rechecks_authority_after_partial_completion(lane, monkeypatch, writer):
    client, uid, user = lane
    stamps = [NOW.replace(day=1, hour=0) + timedelta(hours=i) for i in range(201)]
    batch = client.batch()
    for stamp in stamps:
        batch.set(user.collection('hourly_usage').document(stamp.strftime('%Y-%m-%d-%H')), {'transcription_seconds': 9})
    batch.commit()
    original = totals.commit_fenced
    committed = []

    def commit(*args, **kwargs):
        original(*args, **kwargs)
        committed.append(1)
        client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})

    monkeypatch.setattr(totals, 'commit_fenced', commit)
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        if writer == 'absolute':
            user_usage.batch_update_hourly_usage(uid, {stamp: {'transcription_seconds': 2} for stamp in stamps})
        elif writer == 'admin':
            apply_reset(client, uid, ResetPlan(tuple(stamp.strftime('%Y-%m-%d-%H') for stamp in stamps), 1809))
        else:
            run_writer(client, uid, writer, monkeypatch)
    assert committed == [1]
    assert totals.month_ref(user, NOW).get().to_dict()['ready'] is False
    rows = list(user.collection('hourly_usage').stream())
    if writer == 'migration':
        assert len(rows) == 1 and rows[0].to_dict()['transcription_seconds'] == 9
    else:
        values = [row.to_dict()['transcription_seconds'] for row in rows]
        assert values.count(9) == 1
        assert values.count(2 if writer == 'absolute' else 0) == 200


@pytest.fixture
def lane(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback Firestore emulator required; no cloud fallback')
    client = firestore.Client(project='demo-fs-p3', credentials=AnonymousCredentials())
    uid = 'synthetic-' + uuid4().hex
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    monkeypatch.setattr(user_usage, 'db', client)
    monkeypatch.setattr(user_usage, 'resolve_usage_plan_id', lambda *a, **k: 'free')
    user = client.collection('users').document(uid)
    user.set({'synthetic': True})
    return client, uid, user


def source_stats(user, date, start=None):
    counts = dict.fromkeys(totals.FIELDS, 0)
    for snap in user.collection('hourly_usage').stream():
        data = snap.to_dict()
        if (data['year'], data['month']) != (date.year, date.month):
            continue
        if start and data.get('id', '') < start.strftime('%Y-%m-%d-00'):
            continue
        for key in counts:
            counts[key] += data.get(key, 0)
    return counts


def test_bootstrap_late_updates_current_hour_and_month_rollover(lane):
    client, uid, user = lane
    for offset in (0, 1, 15, 30):
        stamp = NOW.replace(day=1) + timedelta(days=offset)
        user_usage.update_hourly_usage(uid, stamp, {'transcription_seconds': offset + 2}, firestore_client=client)
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)
    for stamp in (NOW, NOW.replace(day=1), NOW.replace(month=9), NOW.replace(month=11)):
        assert user_usage.update_hourly_usage_once(
            uid, stamp, {'transcription_seconds': 5}, stamp.isoformat(), firestore_client=client
        )
        assert not user_usage.update_hourly_usage_once(
            uid, stamp, {'transcription_seconds': 5}, stamp.isoformat(), firestore_client=client
        )
        assert totals.read_monthly_totals(uid, stamp, firestore_client=client) == source_stats(user, stamp)
    for start in (NOW.replace(month=9), NOW.replace(day=1), NOW.replace(hour=23), NOW.replace(month=11)):
        assert totals.read_monthly_totals(uid, NOW, start_date=start, firestore_client=client) == source_stats(
            user, NOW, start
        )


def test_concurrent_duplicate_receipt_and_cold_seeding(lane):
    client, uid, user = lane
    # No total exists. Contend seeding with both distinct and duplicate charges.
    barrier = threading.Barrier(4)

    def run(i):
        barrier.wait(timeout=20)
        if i == 0:
            return totals.read_monthly_totals(uid, NOW, firestore_client=client)
        return user_usage.update_hourly_usage_once(
            uid, NOW, {'transcription_seconds': 10}, 'duplicate' if i <= 2 else 'distinct', firestore_client=client
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(4)))
    assert sum(result is True for result in results) == 2
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)
    assert source_stats(user, NOW)['transcription_seconds'] == 20


def test_absolute_overwrite_and_admin_reset_invalidate_atomically(lane):
    client, uid, user = lane
    user_usage.update_hourly_usage(
        uid, NOW, {'transcription_seconds': 20, 'words_transcribed': 10}, firestore_client=client
    )
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client)['transcription_seconds'] == 20
    user_usage.batch_update_hourly_usage(uid, {NOW: {'transcription_seconds': 3}})
    assert totals.month_ref(user, NOW).get().to_dict()['ready'] is False
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)
    apply_reset(client, uid, ResetPlan((NOW.strftime('%Y-%m-%d-%H'),), 3))
    assert totals.month_ref(user, NOW).get().to_dict()['ready'] is False
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client)['words_transcribed'] == 10


def test_aborted_transaction_retries_source_receipt_and_total_together(lane, monkeypatch):
    client, uid, user = lane
    transaction = client.transaction()
    original = transaction._commit
    attempts = []

    def commit():
        attempts.append(1)
        if len(attempts) == 1:
            # A real server abort releases locks. Release this synthetic
            # attempt too before asking the SDK to begin its retry.
            transaction._rollback()
            raise Aborted('synthetic retry before commit')
        return original()

    monkeypatch.setattr(transaction, '_commit', commit)
    monkeypatch.setattr(client, 'transaction', lambda: transaction)
    assert user_usage.update_hourly_usage_once(uid, NOW, {'speech_seconds': 8}, 'retry', firestore_client=client)
    assert len(attempts) == 2
    assert source_stats(user, NOW)['speech_seconds'] == 8
    assert totals.month_ref(user, NOW).get().to_dict()['totals']['speech_seconds'] == 8


def test_partial_projection_charges_only_delta_then_completion_replay_is_noop(lane):
    client, uid, user = lane
    store = ProjectionStore(SimpleNamespace(client=client))
    ledger_ref = user.collection('sync_content_ledger').document('partial')
    ledger_ref.set({'status': 'pending'})
    binding = SimpleNamespace(owner_id=uid)

    def charge(seconds, previously, status):
        @firestore.transactional
        def commit(transaction):
            ledger = ledger_ref.get(transaction=transaction).to_dict()
            accounting = {
                'charged': previously,
                'hour': NOW.strftime('%Y-%m-%d-%H'),
                'updates': prepare_hourly_usage_updates(NOW, {'speech_seconds': seconds - previously}, 'free'),
            }
            store._commit_usage(transaction, ledger_ref, ledger, binding, accounting, seconds, NOW.timestamp())
            transaction.update(ledger_ref, {'status': status})

        commit(client.transaction())

    charge(2, 0, BATCH_PARTIAL_STATUS)
    charge(5, 2, 'completed')
    charge(5, 0, 'completed')  # Existing completion receipt skips all usage writes.
    assert source_stats(user, NOW)['speech_seconds'] == 5
    assert totals.month_ref(user, NOW).get().to_dict()['totals']['speech_seconds'] == 5
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)


def test_epoch_rebuild_recovers_old_writer_rollback(lane, monkeypatch):
    client, uid, user = lane
    user_usage.update_hourly_usage(uid, NOW, {'transcription_seconds': 20}, firestore_client=client)
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client)['transcription_seconds'] == 20
    # Simulate a legacy writer while the reader kill switch is off.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    user.collection('hourly_usage').document(NOW.strftime('%Y-%m-%d-%H')).set(
        {'transcription_seconds': firestore.Increment(7)}, merge=True
    )
    monkeypatch.setenv('FSR_USAGE_MONTH_TOTAL_EPOCH', 'v2')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"usage_month_total":100}')
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) == source_stats(user, NOW)
    assert totals.month_ref(user, NOW).get().to_dict()['epoch'] == 'v2'


def test_legacy_missing_or_mismatched_ids_keep_original_queries(lane):
    client, uid, user = lane
    user.collection('hourly_usage').document('legacy').set({'year': 2026, 'month': 10, 'transcription_seconds': 7})
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) is None
    assert user_usage.get_monthly_usage_stats(uid, NOW)['transcription_seconds'] == 7
    assert user_usage.get_monthly_usage_stats_since(uid, NOW, NOW)['transcription_seconds'] == 0
    user.collection('hourly_usage').document('legacy').set({'id': '2099-01-01-00'}, merge=True)
    assert user_usage.get_monthly_usage_stats_since(uid, NOW, NOW)['transcription_seconds'] == 7


def test_invalid_source_payload_cannot_partially_commit_total(lane):
    client, uid, user = lane
    with pytest.raises((TypeError, ValueError)):
        batch = client.batch()
        totals.queue_increment(batch, user, NOW, {'speech_seconds': firestore.Increment(5)})
        batch.set(user.collection('hourly_usage').document('bad'), {'unsupported': object()})
        batch.commit()
    assert not totals.month_ref(user, NOW).get().exists


@pytest.mark.parametrize('status', ['pending', 'completed'])
def test_cold_seed_respects_account_deletion_without_changing_legacy_read(lane, status):
    client, uid, user = lane
    user.collection('hourly_usage').document('2026-10-23-15').set(
        {'id': '2026-10-23-15', 'year': 2026, 'month': 10, 'transcription_seconds': 9}
    )
    client.collection('account_deletions').document(uid).set({'wipe_status': status})
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) is None
    assert not totals.month_ref(user, NOW).get().exists
    assert user_usage.get_monthly_usage_stats(uid, NOW)['transcription_seconds'] == 9


def test_cold_seed_does_not_recreate_data_beneath_a_missing_user(lane):
    client, uid, user = lane
    user.delete()
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client) is None
    assert not totals.month_ref(user, NOW).get().exists
    assert user_usage.get_monthly_usage_stats(uid, NOW)['transcription_seconds'] == 0


def test_cold_seed_respects_existing_destructive_gate_then_recovers(lane):
    client, uid, user = lane
    user.collection('hourly_usage').document('2026-10-23-15').set(
        {'id': '2026-10-23-15', 'year': 2026, 'month': 10, 'transcription_seconds': 9}
    )
    token = uuid4().hex
    legal_holds.acquire_destructive_operation(
        uid, kind='explicit_memory_deletion', token=token, firestore_client=client
    )
    try:
        assert totals.read_monthly_totals(uid, NOW, firestore_client=client) is None
        assert not totals.month_ref(user, NOW).get().exists
        assert user_usage.get_monthly_usage_stats(uid, NOW)['transcription_seconds'] == 9
    finally:
        legal_holds.finish_destructive_operation(
            uid, kind='explicit_memory_deletion', token=token, outcome='completed', firestore_client=client
        )
    assert totals.read_monthly_totals(uid, NOW, firestore_client=client)['transcription_seconds'] == 9


def test_deletion_inventory_cannot_miss_a_racing_cold_seed(lane, monkeypatch):
    client, uid, user = lane
    # A pre-contract hour exists, but no monthly document does yet.
    user.collection('hourly_usage').document('2026-10-23-15').set(
        {'id': '2026-10-23-15', 'year': 2026, 'month': 10, 'transcription_seconds': 9}
    )
    scanned, release, marked = threading.Event(), threading.Event(), threading.Event()
    original = totals._month_rows

    def pause_after_scan(*args):
        yield from original(*args)
        scanned.set()
        assert release.wait(20), 'seeder release timed out'

    monkeypatch.setattr(totals, '_month_rows', pause_after_scan)

    def erase():
        client.collection('account_deletions').document(uid).set({'wipe_status': 'pending'})
        inventory = list(user.collections())
        marked.set()
        for collection in inventory:
            for snapshot in collection.stream():
                snapshot.reference.delete()
        user.delete()

    with ThreadPoolExecutor(max_workers=2) as pool:
        seed = pool.submit(totals.read_monthly_totals, uid, NOW, firestore_client=client)
        assert scanned.wait(20), 'seeder scan timed out'
        erased = pool.submit(erase)
        try:
            marked.wait(0.25)
        finally:
            release.set()
        assert seed.result(timeout=20)['transcription_seconds'] == 9
        erased.result(timeout=20)
    assert not totals.month_ref(user, NOW).get().exists, 'derived usage survived the wipe inventory'
