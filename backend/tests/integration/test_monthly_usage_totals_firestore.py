"""Loopback-only proof of snapshot seeding, atomic counters, retry and resets."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
from types import SimpleNamespace
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import Aborted
from google.cloud import firestore
import pytest

from database import monthly_usage_totals as totals, user_usage

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)


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
    return client, uid, client.collection('users').document(uid)


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
    from scripts.admin.reset_transcription_usage import ResetPlan, apply_reset

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
    from database.batch_pipeline_projection import ProjectionStore
    from database.hourly_usage_updates import prepare_hourly_usage_updates
    from database.sync_ledger import BATCH_PARTIAL_STATUS

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
