"""Synthetic custody/CAS regressions for held expiry and nightly re-drive."""

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from prometheus_client import CollectorRegistry

from config.batch_pipeline import HELD_DEAD_LETTER_SECONDS, batch_held_dead_letter_enabled, scheduler_control_key
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_projection import held_without_recovery
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore, expire_held_in_transaction
from tests.unit.test_batch_pipeline_quarantine_recovery import setup as setup
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline import held_dead_letter as sweep
from utils.batch_pipeline.intake import _held_status  # pyright: ignore[reportPrivateUsage] -- unit contract seam
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler


def row(client):
    return client.rows['batch_pipeline_prod_jobs', 'bad']


def test_expiry_backfills_full_window_then_cas_expires_without_audio_or_ttl_mutation(setup):
    client, store, _, artifacts, _, _ = setup
    recovery = RecoveryStore(store)
    original = deepcopy(row(client))
    assert recovery.expire_held('bad', 100) == 'stamped'
    assert row(client)['held_deadline_at'] == 100 + HELD_DEAD_LETTER_SECONDS
    assert recovery.expire_held('bad', 100 + HELD_DEAD_LETTER_SECONDS - 1) == 'held'
    assert recovery.expire_held('bad', 100 + HELD_DEAD_LETTER_SECONDS) == 'expired'
    assert recovery.expire_held('bad', 101 + HELD_DEAD_LETTER_SECONDS) == 'held'
    expected = {
        **original,
        'held_deadline_at': 100 + HELD_DEAD_LETTER_SECONDS,
        'state': 'dead',
        'merge_pending': True,
        'dead_letter_reason': 'held_expired',
        'held_expired_at': 100 + HELD_DEAD_LETTER_SECONDS,
    }
    assert row(client) == expected
    artifacts.assert_not_called()
    assert not artifacts.mock_calls
    assert held_without_recovery(row(client))
    assert _held_status([row(client)]) == ('processing', 'batch_unit_held')


@pytest.mark.parametrize('dead', [False, 'legacy', 'rollback_compatible'])
def test_requeue_idempotent_and_usable_with_flag_off_retains_attempt_and_audio_history(setup, monkeypatch, dead):
    client, store, _, _, _, _ = setup
    job = row(client)
    job.update(
        attempt=5,
        recovery_state='failed_held',
        recovery={'token': 'spent', 'settled_at': 10, 'privacy_generation': 0},
        held_deadline_at=20,
    )
    if dead:
        job.update(state='dead', dead_letter_reason='held_expired', held_expired_at=20, merge_pending=dead != 'legacy')
    original = deepcopy(job)
    # Keep the strict document fake off query paths; the emulator covers a cold DRR ring.
    client.rows['batch_pipeline_prod_control', scheduler_control_key(job['owner_key'])] = {'p0_active': True}
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    # Main's retain-attempt contract; class 3 on resets attempt (test_backlog_state_machine.py).
    monkeypatch.setenv('BATCH_HELD_REDRIVE_BUDGET_ENABLED', 'false')
    recovery = RecoveryStore(store)
    assert recovery.requeue_quarantined('bad', 30)
    after = deepcopy(client.rows)
    assert not recovery.requeue_quarantined('bad', 31)
    assert client.rows == after
    for key in ('attempt', 'audio_uri', 'projection_binding', 'privacy_generation', 'recovery', 'held_deadline_at'):
        assert row(client)[key] == original[key]
    assert row(client)['state'] == 'ready' and row(client)['merge_pending'] is True
    assert row(client)['token'] == '' and row(client)['lease_until'] == 0


def test_expired_row_requeues_through_unchanged_legacy_redrive_with_flag_off(setup, monkeypatch):
    client, store, _, artifacts, _, _ = setup
    job = row(client)
    job.update(held_deadline_at=20, attempt=5)
    original = deepcopy(job)
    assert RecoveryStore(store).expire_held('bad', 30) == 'expired'
    assert row(client)['merge_pending'] is True
    client.rows['batch_pipeline_prod_control', scheduler_control_key(job['owner_key'])] = {'p0_active': True}
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    # Main's retain-attempt contract; class 3 on resets attempt (test_backlog_state_machine.py).
    monkeypatch.setenv('BATCH_HELD_REDRIVE_BUDGET_ENABLED', 'false')
    # Only the unchanged, pre-feature path is available after a code rollback.
    queue = Scheduler(store)
    assert queue.redrive_dead('bad', 31)
    after = deepcopy(client.rows)
    assert not queue.redrive_dead('bad', 32)
    assert client.rows == after
    restored = row(client)
    assert restored['state'] == 'ready' and restored['merge_pending'] is True
    assert restored['dead_letter_reason'] == 'held_expired'
    assert restored['held_deadline_at'] == 20 and restored['held_expired_at'] == 30
    for key in ('attempt', 'audio_uri', 'projection_binding', 'privacy_generation'):
        assert restored[key] == original[key]
    assert not artifacts.mock_calls


@pytest.mark.parametrize(
    'patch',
    [
        {'state': 'ready'},
        {'state': 'privacy_blocked'},
        {'quarantine_reason': 'privacy'},
        {'state': 'dead', 'dead_letter_reason': 'other'},
        {'stt_route': {'stt_route': 'provider'}},
        {'recovery_state': 'running'},
        {'recovery_state': 'prepared'},
        {'token': 'live'},
        {'lease_until': 31},
        {'result': {'result_uri': 'gs://synthetic/result'}},
        {'merge_pending': True},
        {'recovery': {'token': 'active', 'privacy_generation': 0}},
        {'speech_redrive': {'state': 'running'}},
        {'silence_disposition': {'state': 'prepared'}},
        {'terminal_disposition': {'state': 'prepared'}},
    ],
)
def test_expiry_and_requeue_fence_matrix_is_read_only(setup, patch):
    client, store, _, _, _, _ = setup
    row(client).update(held_deadline_at=20, **patch)
    before = deepcopy(client.rows)
    recovery = RecoveryStore(store)
    assert recovery.expire_held('bad', 30) == 'held'
    assert not recovery.requeue_quarantined('bad', 30)
    assert client.rows == before


@pytest.mark.parametrize('patch', [{'token': 'live'}, {'lease_until': 31}, {'result': {'result_uri': 'synthetic'}}])
def test_pending_dead_letter_still_requires_dormant_requeue_fences(setup, patch):
    client, store, _, _, _, _ = setup
    row(client).update(state='dead', dead_letter_reason='held_expired', merge_pending=True, **patch)
    before = deepcopy(client.rows)
    assert not RecoveryStore(store).requeue_quarantined('bad', 30)
    assert client.rows == before


def test_result_receipt_fences_expiry_and_requeue_even_if_job_result_missing(setup):
    client, store, _, _, _, _ = setup
    row(client)['held_deadline_at'] = 20
    client.rows['batch_pipeline_prod_results', 'bad'] = {'result': {'result_uri': 'gs://synthetic/result'}}
    before = deepcopy(client.rows)
    recovery = RecoveryStore(store)
    assert recovery.expire_held('bad', 30) == 'held'
    assert not recovery.requeue_quarantined('bad', 30)
    assert client.rows == before


@pytest.mark.parametrize('fence', ['privacy', 'ledger'])
def test_content_and_privacy_fences_remain_authoritative(setup, fence):
    client, store, binding, _, _, _ = setup
    row(client)['held_deadline_at'] = 20
    if fence == 'privacy':
        client.rows['batch_pipeline_privacy', privacy_owner_key(binding.owner_id)] = {'generation': 1}
        error = BatchPrivacyBlocked
    else:
        client.rows['users', binding.owner_id, 'sync_content_ledger', binding.content_id]['job_id'] = 'other'
        error = ProjectionBlocked
    before = deepcopy(client.rows)
    recovery = RecoveryStore(store)
    with pytest.raises(error):
        recovery.expire_held('bad', 30)
    with pytest.raises(error):
        recovery.requeue_quarantined('bad', 30)
    assert client.rows == before


@pytest.mark.parametrize('bad', [False, 'old', float('nan'), float('inf')])
def test_bad_deadline_never_expires(setup, bad):
    client, store, _, _, _, _ = setup
    row(client)['held_deadline_at'] = bad
    assert RecoveryStore(store).expire_held('bad', 30) == 'held'


def test_flag_off_preserves_legacy_quarantine_and_sweep_is_zero_io(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert not batch_held_dead_letter_enabled()
    store = cast(Any, MemoryStore())
    queue = Scheduler(store)
    queue.enqueue(item('bad'), 0)
    lease = queue.pull(0)[0]
    assert queue.fail('bad', lease.token, 1)
    assert 'held_deadline_at' not in store.rows['jobs', 'bad']
    before = deepcopy(store.rows)
    assert store.run(lambda tx: expire_held_in_transaction(tx, tx.get('jobs', 'bad'), 10**9)) == 'disabled'
    assert store.rows == before
    untouched = Mock()
    assert sweep.HeldDeadLetter(untouched).tick(10**9) == {'expired': 0, 'requeued': 0}
    assert not untouched.mock_calls


def model_store(monkeypatch, n=35):
    monkeypatch.setattr(sweep, 'input_expiring_candidates', lambda *a, **kw: ([], {}))
    store = cast(Any, MemoryStore())
    store.client, store.namespace = None, 'synthetic'
    queue = Scheduler(store)
    for i in range(n):
        sid = f'held-{i:03d}'
        queue.enqueue(replace(item(sid), capture_at=i), 0)
        lease = queue.pull(0)[0]
        queue.fail(sid, lease.token, 1, quarantine=True)
        store.rows['jobs', sid]['held_deadline_at'] = 2

    def page(state, after_id, limit):
        return [
            (sid, deepcopy(job))
            for (table, sid), job in sorted(store.rows.items())
            if table == 'jobs' and job['state'] == state and (after_id is None or sid > after_id)
        ][:limit]

    monkeypatch.setattr(
        sweep, 'held_candidates', lambda c, ns, limit, after_id=None: page('quarantined', after_id, limit)
    )
    monkeypatch.setattr(
        sweep, 'dead_held_candidates', lambda c, ns, limit, after_id=None: page('dead', after_id, limit)
    )
    # Model synthetic authorized content; strict Firestore tests above exercise the real fence.
    monkeypatch.setattr(RecoveryStore, 'checked', lambda self, tx, sid: (tx.get('jobs', sid), None))
    monkeypatch.setattr(sweep, 'held_expired_stock', lambda c, ns: len(page('dead', None, n)))
    return store


def test_nightly_bounded_cursor_survives_restart_and_double_delivery(monkeypatch):
    store = model_store(monkeypatch)
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    runner = sweep.HeldDeadLetter(store, metrics=metrics)
    assert runner.tick(86400) == {'expired': 32, 'requeued': 0}
    assert registry.get_sample_value('omi_batch_held_expired_total') == 32
    before = deepcopy(store.rows)
    assert runner.tick(86400) == {'expired': 0, 'requeued': 0}
    assert store.rows == before
    # A fresh process continues the durable held cursor, then waits for midnight.
    runner = sweep.HeldDeadLetter(store, metrics=metrics)
    assert runner.tick(86700) == {'expired': 3, 'requeued': 0}
    assert runner.tick(172800) == {'expired': 0, 'requeued': 32}
    assert registry.get_sample_value('omi_batch_held_expired_units') == 3
    assert sweep.HeldDeadLetter(store).tick(173100) == {'expired': 0, 'requeued': 3}
    assert not any(job['state'] == 'dead' for (table, _), job in store.rows.items() if table == 'jobs')
    assert registry.get_sample_value('omi_batch_held_expired_total') == 35


def test_crash_before_checkpoint_replays_without_duplicate_expiry(monkeypatch):
    store = model_store(monkeypatch, 1)
    runner = sweep.HeldDeadLetter(store)
    run = store.run
    crashed = False

    def crash(fn):
        nonlocal crashed
        if fn.__name__ == 'checkpoint' and not crashed:
            crashed = True
            raise RuntimeError('synthetic crash after row commit')
        return run(fn)

    monkeypatch.setattr(store, 'run', crash)
    with pytest.raises(RuntimeError, match='synthetic crash'):
        runner.tick(86400)
    assert sweep.HeldDeadLetter(store).tick(86400) == {'expired': 0, 'requeued': 0}
    assert sweep.HeldDeadLetter(store).tick(172800) == {'expired': 0, 'requeued': 1}


def test_private_requeue_rpc_is_stage_bound_authenticated_and_idempotent(setup, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import batch_pipeline as router
    from types import SimpleNamespace

    client, store, _, _, _, _ = setup
    job = row(client)
    client.rows['batch_pipeline_prod_control', scheduler_control_key(job['owner_key'])] = {'p0_active': True}
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    monkeypatch.setattr(router, 'serving_for_stage', lambda stage: SimpleNamespace(store=store))
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_worker] = lambda: None
    path = '/v2/batch-pipeline/requeue-quarantined'
    with TestClient(app) as api:
        assert api.post(path, json={'stage': 'dev', 'segment_id': 'bad'}).status_code == 409
        assert api.post(path, json={'stage': 'prod', 'segment_id': 'bad'}).json() == {'accepted': True}
        assert api.post(path, json={'stage': 'prod', 'segment_id': 'bad'}).json() == {'accepted': False}
    app.dependency_overrides.clear()
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_AUDIENCE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', raising=False)
    with TestClient(app) as api:
        assert api.post(path, json={'stage': 'prod', 'segment_id': 'bad'}).status_code == 403


def test_failed_recovery_writers_stamp_new_full_window_and_off_restores_exact_payload(setup, monkeypatch):
    client, store, binding, _, _, _ = setup
    recovery = RecoveryStore(store)
    prepared = recovery.prepare('bad', binding.owner_id, 100)
    token = prepared['recovery']['token']
    before = deepcopy(client.rows)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    assert recovery.hold_invalid_manifest('bad', token, 200, audio_uri=row(client)['audio_uri'])
    legacy = deepcopy(row(client))
    assert 'held_deadline_at' not in legacy
    client.rows = deepcopy(before)
    monkeypatch.delenv('BATCH_HELD_DEAD_LETTER_ENABLED')
    assert recovery.hold_invalid_manifest('bad', token, 200, audio_uri=row(client)['audio_uri'])
    assert row(client) == {**legacy, 'held_deadline_at': 200 + HELD_DEAD_LETTER_SECONDS}
    # An actual failed paid recovery settlement uses the same fresh window.
    client.rows = deepcopy(before)
    assert recovery.start('bad', token, 201)
    assert recovery.settle('bad', token, 202, failure={'stage': 'provider', 'reason': 'operation_failed'})
    assert row(client)['held_deadline_at'] == 202 + HELD_DEAD_LETTER_SECONDS


def test_nightly_rechecks_dead_age_inside_transaction_instead_of_trusting_scan_snapshot(setup):
    client, store, _, _, _, _ = setup
    recovery = RecoveryStore(store)
    row(client).update(state='dead', dead_letter_reason='held_expired', held_expired_at=31)
    before = deepcopy(client.rows)
    assert not recovery.requeue_quarantined('bad', 32, dead_before=30)
    assert client.rows == before
    row(client).update(state='quarantined', held_expired_at=29)
    assert not recovery.requeue_quarantined('bad', 32, dead_before=30)


@pytest.mark.parametrize('lease', [None, False, 'expired', float('nan'), float('inf')])
def test_unknown_lease_metadata_is_not_evidence_of_expiry(setup, lease):
    client, store, _, _, _, _ = setup
    row(client).update(lease_until=lease, held_deadline_at=20)
    recovery = RecoveryStore(store)
    assert recovery.expire_held('bad', 30) == 'held'
    assert not recovery.requeue_quarantined('bad', 30)
    assert row(client)['state'] == 'quarantined'


def test_one_unreadable_row_does_not_pin_expiry_or_nightly_pages(monkeypatch, caplog):
    store = model_store(monkeypatch, 2)
    original = RecoveryStore.checked

    def unreadable(self, tx, sid):
        if sid == 'held-000':
            raise RuntimeError('synthetic row read failure')
        return original(self, tx, sid)

    monkeypatch.setattr(RecoveryStore, 'checked', unreadable)
    runner = sweep.HeldDeadLetter(store)
    assert runner.tick(86400) == {'expired': 1, 'requeued': 0}
    assert store.rows['jobs', 'held-000']['state'] == 'quarantined'
    # A corrupt old dead row is also skipped without blocking the next key.
    store.rows['jobs', 'held-000'].update(state='dead', dead_letter_reason='held_expired', held_expired_at=86400)
    assert runner.tick(172800) == {'expired': 0, 'requeued': 1}
    assert store.rows['jobs', 'held-001']['state'] == 'ready'
    assert 'action=expire outcome=retry exception_type=RuntimeError' in caplog.text
    assert 'action=requeue outcome=retry exception_type=RuntimeError' in caplog.text
