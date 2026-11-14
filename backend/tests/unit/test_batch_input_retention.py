"""Held staging inputs: age proxy, retained terminal, approved redrive and warning."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from tests.unit.test_timeliness_metrics_are_scraped import FRESH_NEWEST
from prometheus_client import CollectorRegistry

from config.batch_pipeline import scheduler_control_key
from config.refactor_modes import batch_input_expiring_enabled
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from database.batch_pipeline_artifact_missing import ArtifactMissingStore
from database.batch_pipeline_projection_release import ProjectionReleaseStore
from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from scripts import redrive_staging_inputs as cli
from tests.unit.test_batch_pipeline_quarantine_recovery import setup as setup, row, ledger_row
from tests.unit.test_batch_pipeline_timeliness import _sample, NOW, EPOCH  # pyright: ignore[reportPrivateUsage]
from utils.batch_pipeline.input_retention import STAGING_BUCKET, TERMINAL_SECONDS, WARNING_SECONDS, staged_enqueue
from utils.batch_pipeline.intake import durable_status, get_durable_job_status
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler

URI = f'gs://{STAGING_BUCKET}/synthetic/audio#1'
ENQUEUED = 1_000_000.0
NOW29 = ENQUEUED + TERMINAL_SECONDS
BACKEND = Path(__file__).resolve().parents[2]
BAD_STAGED_CLOCKS = [None, False, True, 0, -1, float('nan'), float('inf'), float('-inf'), '123', {}, []]


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    disabled = logging.root.manager.disable
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.delenv('BATCH_INPUT_EXPIRING_ENABLED', raising=False)
    yield
    logging.disable(disabled)


def seed(setup, leg='gpu'):
    client, store, binding, *_ = setup
    job = row(client)
    job.update(audio_uri=URI, enqueued_at=ENQUEUED, held_deadline_at=NOW29 + 86400)
    if leg == 'assignment':
        job.update(state='committed', recovery_state='held', result={'result_uri': 'gs://synthetic/result'})
        client.rows['batch_pipeline_prod_results', 'bad'] = {
            'segment_id': 'bad',
            'owner_key': job['owner_key'],
            'projection_state': 'quarantine_held',
            'projection': {'state': 'quarantined', 'disposition': 'ambiguous_generation'},
        }
    return client, store, binding


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_exact_day29_terminal_retains_all_bytes_receipts_and_attempts(setup, leg):
    client, store, _ = seed(setup, leg)
    before = deepcopy(client.rows)
    recovery = RecoveryStore(store)
    assert recovery.expire_held('bad', NOW29 - 1) == 'held'
    assert client.rows == before
    assert recovery.expire_held('bad', NOW29) == 'expired'
    job = row(client)
    assert job == {
        **before['batch_pipeline_prod_jobs', 'bad'],
        'state': 'dead',
        'merge_pending': leg == 'gpu',
        'dead_letter_reason': 'input_expiring',
        'input_expiring_at': NOW29,
        'input_expiring_leg': leg,
    }
    assert all(value == client.rows[key] for key, value in before.items() if key[0].endswith(('results', 'artifacts')))
    terminal = deepcopy(client.rows)
    assert recovery.expire_held('bad', NOW29 + 1) == 'held'
    assert client.rows == terminal
    assert not setup[3].mock_calls  # no artifact or provider calls


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_existing_sweep_reaches_both_held_legs_without_nightly_terminal_redrive(setup, monkeypatch, leg):
    from utils.batch_pipeline import held_dead_letter as sweep

    client, store, _ = seed(setup, leg)
    monkeypatch.setattr(sweep, 'input_expiring_candidates', lambda *a, **kw: ([], {}))
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **kw: [('bad', deepcopy(row(client)))])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **kw: [])
    monkeypatch.setattr(sweep, 'held_expired_stock', lambda *a: 0)
    assert sweep.HeldDeadLetter(store).tick(NOW29) == {'expired': 1, 'requeued': 0}
    assert row(client)['dead_letter_reason'] == 'input_expiring'
    assert sweep.HeldDeadLetter(store).tick(NOW29 + 86400) == {'expired': 0, 'requeued': 0}
    assert row(client)['state'] == 'dead'


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_terminal_cannot_arm_completed_artifact_cleanup(setup, monkeypatch, leg):
    from utils.batch_pipeline import retention

    client, store, binding = seed(setup, leg)
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'expired'
    monkeypatch.setattr(retention.queries, 'segment_artifacts', lambda *a: [])
    before = deepcopy(client.rows)
    assert not retention.expire_completed_segment(store, binding.owner_id, 'bad', NOW29 + 1)
    assert client.rows == before
    assert 'expires_at' not in row(client)


@pytest.mark.parametrize('value', ['off', 'false', '0'])
@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_kill_preserves_existing_held_behavior(setup, monkeypatch, value, leg):
    client, store, _ = seed(setup, leg)
    monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', value)
    assert not batch_input_expiring_enabled()
    before = deepcopy(client.rows)
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'held'
    assert client.rows == before


@pytest.mark.parametrize(
    'patch',
    [
        {'state': 'record_pending'},
        {'state': 'ready'},
        {'recovery_state': 'running'},
        {'token': 'active'},
        {'lease_until': NOW29 + 1},
        {'lease_until': float('nan')},
        {'enqueued_at': False},
        {'enqueued_at': float('nan')},
        {'enqueued_at': None},
        {'audio_uri': 'gs://other/audio'},
        {'stt_route': {'stt_route': 'provider'}},
        {'speech_redrive': {'state': 'prepared'}},
    ],
)
def test_terminal_scope_and_active_intent_fences(setup, patch):
    client, store, _ = seed(setup)
    row(client).update(patch)
    before = deepcopy(client.rows)
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'held'
    assert client.rows == before


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
@pytest.mark.parametrize('fence', ['privacy', 'ledger'])
def test_terminal_content_and_privacy_fences(setup, leg, fence):
    client, store, binding = seed(setup, leg)
    error = ProjectionBlocked
    if fence == 'privacy':
        client.rows['batch_pipeline_privacy', privacy_owner_key(binding.owner_id)] = {'generation': 1}
        error = BatchPrivacyBlocked
    else:
        ledger_row(client, binding)['job_id'] = 'other'
    before = deepcopy(client.rows)
    with pytest.raises(error):
        RecoveryStore(store).expire_held('bad', NOW29)
    assert client.rows == before


def test_terminal_failed_status_precedes_partial_and_never_poll_redrives(setup, monkeypatch):
    from utils.batch_pipeline import intake

    client, store, binding = seed(setup)
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'expired'
    client.rows['batch_pipeline_prod_intakes', binding.job_id] = {
        'owner_id': binding.owner_id,
        'content_id': binding.content_id,
        'segment_ids': list(binding.segment_ids),
        'lane': 'backfill',
        'total_files': 2,
    }
    before = deepcopy(client.rows)
    status = durable_status(store, binding.owner_id, binding.job_id)
    assert isinstance(status, dict)
    assert status['status'] == 'failed' and status['reason_code'] == 'batch_artifact_missing'
    assert status['failed_segments'] == 1 and status['poll_after_ms'] == 0
    monkeypatch.setattr(intake, 'FirestoreStore', lambda namespace: store)
    monkeypatch.setattr(intake, 'shadow_from_env', lambda value: value)
    capable = get_durable_job_status(binding.job_id, binding.owner_id, artifact_retry=True)
    legacy = get_durable_job_status(binding.job_id, binding.owner_id)
    assert isinstance(capable, dict) and capable['status'] == 'failed'
    assert isinstance(legacy, dict) and legacy['status'] == 'processing'
    assert client.rows == before
    assert not store.run(lambda tx: Scheduler.redrive_in_transaction(tx, tx.get('jobs', 'bad'), NOW29 + 1))
    # Operator-only requeue uses the existing content/privacy/intent transaction, even with the kill off.
    monkeypatch.setenv('BATCH_INPUT_EXPIRING_ENABLED', 'false')
    client.rows['batch_pipeline_prod_control', scheduler_control_key(row(client)['owner_key'])] = {'p0_active': True}
    assert RecoveryStore(store).requeue_quarantined('bad', NOW29 + 1)
    assert row(client)['state'] == 'ready'


def test_expiring_gpu_reuses_exact_bundle_client_reupload(setup, monkeypatch):
    from database import batch_pipeline_store
    from tests.unit.test_batch_artifact_missing_reupload import staged

    monkeypatch.setattr(batch_pipeline_store, 'service_frontier', lambda *a, **kw: 0.0)
    client, store, binding = seed(setup)
    RecoveryStore(store).expire_held('bad', NOW29)
    repair = ArtifactMissingStore(store)
    assert set(repair.reupload_snapshot(binding.owner_id, binding.content_id)[2]) == {'bad'}
    snapshot = deepcopy(row(client))
    uri = f'gs://{STAGING_BUCKET}/synthetic/replacement#2'
    staged(client, binding, uri)
    good = deepcopy(row(client, 'results', 'good'))
    repair.restore_reupload(binding.owner_id, binding.content_id, {'bad': snapshot}, {'bad': uri}, NOW29 + 1)
    assert row(client)['audio_uri'] == uri and row(client)['state'] == 'ready'
    assert row(client)['audio_staged_at'] == NOW29 + 1
    assert row(client)['enqueued_at'] == ENQUEUED
    row(client).update(state='quarantined', recovery_state='failed_held')
    assert RecoveryStore(store).expire_held('bad', NOW29 + 2) == 'held'
    assert row(client, 'results', 'good') == good


@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_fresh_current_object_does_not_expire_on_old_enqueue(setup, leg):
    client, store, _ = seed(setup, leg)
    row(client)['audio_staged_at'] = NOW29
    assert staged_enqueue(row(client)) == NOW29
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'held'
    assert RecoveryStore(store).expire_held('bad', NOW29 + TERMINAL_SECONDS) == 'expired'


@pytest.mark.parametrize('stamp', BAD_STAGED_CLOCKS)
def test_bad_restage_clock_falls_back_to_earlier_admission(stamp):
    assert staged_enqueue({'audio_uri': URI, 'enqueued_at': ENQUEUED, 'audio_staged_at': stamp}) == ENQUEUED
    assert staged_enqueue({'audio_uri': URI, 'enqueued_at': 0, 'audio_staged_at': stamp}) is None


@pytest.mark.parametrize('stamp', BAD_STAGED_CLOCKS)
@pytest.mark.parametrize('leg', ['gpu', 'assignment'])
def test_bad_restage_clock_expires_by_admission_at_day29(setup, stamp, leg):
    client, store, _ = seed(setup, leg)
    row(client)['audio_staged_at'] = stamp
    assert RecoveryStore(store).expire_held('bad', NOW29 - 1) == 'held'
    assert RecoveryStore(store).expire_held('bad', NOW29) == 'expired'
    assert row(client)['dead_letter_reason'] == 'input_expiring'


@pytest.mark.parametrize('stamp', BAD_STAGED_CLOCKS)
@pytest.mark.parametrize('enqueued', [ENQUEUED, 0, None])
def test_bad_clocks_are_visible_in_the_age_sample_and_exported_count(monkeypatch, stamp, enqueued):
    from utils.batch_pipeline import metrics as metrics_module

    job = {
        'state': 'quarantined',
        'recovery_state': 'held',
        'quarantine_reason': 'worker_failed',
        'audio_uri': URI,
        'enqueued_at': enqueued,
        'audio_staged_at': stamp,
    }
    sample = _sample(jobs=[job], now=NOW29)
    assert sample['held_oldest']['staged_input'] == (ENQUEUED if enqueued else None)
    assert sample['staged_input_clock_invalid'] == 1
    assert sample['truncated']['staged_input'] is (not bool(enqueued))
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    monkeypatch.setattr(metrics_module, 'timeliness_sample', lambda *a, **kw: sample)
    monkeypatch.setattr(metrics_module, 'lever_enabled', lambda name: False)
    monkeypatch.setattr(metrics_module, 'batch_timeliness_alarm_enabled', lambda: True)
    metrics.refresh_timeliness(cast(Any, SimpleNamespace(client=None, namespace='ns')), NOW29)
    assert registry.get_sample_value('omi_batch_staged_input_clock_invalid_total') == 1
    assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': 'staged_input'}) == (
        TERMINAL_SECONDS if enqueued else 0
    )
    assert registry.get_sample_value('omi_batch_timeliness_scan_truncated', {'leg': 'staged_input'}) == (
        0 if enqueued else 1
    )


def test_metric_uses_current_object_and_does_not_mask_older_legacy_input():
    base = {'state': 'quarantined', 'recovery_state': 'held', 'quarantine_reason': 'worker_failed', 'audio_uri': URI}
    assert _sample(jobs=[{**base, 'enqueued_at': 1, 'audio_staged_at': NOW}])['held_oldest']['staged_input'] == NOW
    assert (
        _sample(jobs=[{**base, 'enqueued_at': 1, 'audio_staged_at': NOW}, {**base, 'enqueued_at': 2}])['held_oldest'][
            'staged_input'
        ]
        == 2
    )


def test_terminal_assignment_is_not_automatically_released_but_operator_uses_existing_target_gate(monkeypatch):
    from tests.unit.test_batch_pipeline_projection_release import rows, store_for, OWNER, TARGET

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    seeded = rows()
    key = ('batch_pipeline_prod_jobs', 'held')
    seeded[key].update(state='dead', dead_letter_reason='input_expiring', input_expiring_leg='assignment')
    client, projection = store_for(seeded)
    release = ProjectionReleaseStore(projection)
    before = deepcopy(client.rows)
    assert not release.release('held', NOW29)
    assert client.rows == before
    client.rows['users', OWNER, 'conversations', TARGET]['discarded'] = True
    assert not release.release('held', NOW29, operator=True)
    assert row(client, sid='held')['state'] == 'dead'
    client.rows['users', OWNER, 'conversations', TARGET]['discarded'] = False
    assert release.release('held', NOW29, operator=True)
    assert row(client, sid='held')['state'] == 'committed'
    assert row(client, 'results', 'held')['projection_state'] == 'pending'


def test_enqueue_proxy_export_is_all_epoch_staging_only_and_excludes_record_pending(monkeypatch):
    from utils.batch_pipeline import metrics as metrics_module

    base = {'state': 'quarantined', 'recovery_state': 'held', 'quarantine_reason': 'worker_failed', 'audio_uri': URI}
    sample = _sample(
        jobs=[
            {**base, 'enqueued_at': 1},
            {**base, 'enqueued_at': 2, 'audio_uri': 'gs://other/audio'},
            {**base, 'enqueued_at': 0},
            {**base, 'enqueued_at': 0.5, 'state': 'record_pending'},
            {**base, 'enqueued_at': 3, 'state': 'committed'},
        ]
    )
    assert sample['held_oldest']['staged_input'] == 1 < EPOCH
    registry = CollectorRegistry()
    metrics = QueueMetrics(registry)
    monkeypatch.setattr(metrics_module, 'timeliness_sample', lambda *a, **kw: sample)
    monkeypatch.setattr(metrics_module, 'lever_enabled', lambda name: False)
    monkeypatch.setattr(metrics_module, 'batch_timeliness_alarm_enabled', lambda: True)
    metrics.refresh_timeliness(cast(Any, SimpleNamespace(client=None, namespace='ns')), NOW)
    assert registry.get_sample_value('omi_batch_held_oldest_age_seconds', {'leg': 'staged_input'}) == NOW - 1
    empty = _sample()
    assert empty['held_oldest']['staged_input'] is None


def test_staging_age_scan_fails_sample_instead_of_publishing_false_zero():
    with pytest.raises(RuntimeError, match='staged input age scan incomplete'):
        _sample(
            jobs=[
                {
                    'state': 'quarantined',
                    'recovery_state': 'held',
                    'quarantine_reason': 'worker_failed',
                    'enqueued_at': index + 1,
                    'audio_uri': 'gs://other/audio',
                }
                for index in range(129)
            ]
        )


def test_existing_record_conversation_failure_presentation_at_day29(monkeypatch):
    from utils.conversations import home_step

    monkeypatch.setattr(home_step, 'home_step_projection_enabled', lambda: True)
    assert (
        home_step.classify(
            {
                'status': 'completed',
                'record_lane_owner': 'batch_sync_v1',
                'finished_at': datetime.now(timezone.utc) - timedelta(days=29),
            }
        )
        == 'failed'
    )


def test_digest_requires_exact_approval_before_any_writer_and_binds_whole_snapshot(setup):
    client, store, _ = seed(setup)
    units: list[dict[str, Any]] = [{'id': 'bad', 'leg': 'gpu', 'job': deepcopy(row(client)), 'entry': {}}]
    digest = cli.plan_digest(units, NOW29, 128, None)
    untouched = Mock()
    with pytest.raises(cli.Refused, match='approval_digest_changed'):
        cli.apply_plan(untouched, units, digest, 'wrong', NOW29)
    assert not untouched.mock_calls
    row(client)['attempt'] = 99
    assert cli.apply_plan(store, units, digest, digest, NOW29) == {'refused': 1}
    units[0]['job']['attempt'] = 99
    assert cli.plan_digest(units, NOW29, 128, None) != digest


def test_operator_discovery_is_bounded_oldest_first_and_scopes_21_day_proxy():
    query = Mock()
    for name in ('where', 'order_by', 'limit', 'start_after'):
        getattr(query, name).return_value = query
    query.stream.return_value = []
    client = Mock()
    client.collection.return_value = query
    assert cli.discover(client, NOW29, 128, {'enqueued_at': 1, 'id': 'private'}) == ([], 0, None)
    query.limit.assert_called_once_with(128)
    assert [c.args for c in query.order_by.call_args_list] == [('enqueued_at',), ('__name__',)]
    assert ('enqueued_at', '<=', NOW29 - WARNING_SECONDS) in [c.args for c in query.where.call_args_list]
    with pytest.raises(cli.Refused, match='invalid_page_size'):
        cli.discover(client, NOW29, 129)


@pytest.mark.parametrize('tier', ['ro-prod', 'prod-operator'])
def test_default_dry_run_prints_only_counts_and_digest_without_constructing_writer(monkeypatch, capsys, tier):
    from google.cloud import firestore
    from database import batch_pipeline_store

    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(firestore, 'Client', lambda **kw: Mock())
    units = [{'id': 'private-id', 'leg': 'gpu', 'job': {'audio_uri': URI}, 'entry': {}}]
    monkeypatch.setattr(cli, 'discover', lambda *a: (units, 1, None))
    writer = Mock(side_effect=AssertionError('dry-run constructed a writer'))
    monkeypatch.setattr(batch_pipeline_store, 'FirestoreStore', writer)
    cli.main(['--as-of', '2026-01-01T00:00:00Z'])
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result['firestore_writes'] == 0 and result['selected'] == 1
    assert result['by_leg'] == {'gpu': 1} and len(result['plan_sha256']) == 64
    assert 'private-id' not in output and 'gs://' not in output
    writer.assert_not_called()


def test_warning_rule_threshold_freshness_route_and_pending_period():
    from scripts import alert_backtest as b

    rule = next(
        r
        for r in json.loads((BACKEND / 'charts/monitoring/alert-rules.json').read_text())
        if r['uid'] == 'omi-batch-staged-input-age'
    )
    assert json.loads((BACKEND / 'charts/monitoring/alerts/batch-input-retention.json').read_text()) == [rule]
    assert rule['data'][0]['model']['expr'] == (
        'max(omi_batch_held_oldest_age_seconds{leg="staged_input"} and ignoring(leg) ' f'{FRESH_NEWEST})'
    )
    for age in (WARNING_SECONDS - 1, WARNING_SECONDS, WARNING_SECONDS + 1):
        assert b.evaluate(rule, {'A': {(): [age]}}) == {(): float(age > WARNING_SECONDS)}
    assert b.evaluate(rule, {'A': {}}) == {}
    assert rule['for'] == '10m' and not rule['isPaused']
    assert rule['labels']['severity'] == 'warning' and rule['labels']['audience'] == 'human'
    assert not rule['notification_settings']['mute_time_intervals']
