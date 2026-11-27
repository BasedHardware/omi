"""Synthetic exact-scope repair: tail/privacy/failure refusal and digest CAS."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_store import FirestoreStore
from database.record_audio import renew_record_token_lease
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import record_seal_repair as repair
from utils.batch_pipeline import record_producer_proof

PATH = ('users', 'synthetic', 'conversations', 'record')
JOB_PATH = ('batch_pipeline_dev_jobs', 'pending')
FINISH = datetime.fromtimestamp(102, timezone.utc)


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')  # Strict client injected; no network.
    client = StrictFirestore(
        {
            PATH: {
                'record_lane_owner': 'batch_live_v1',
                'status': 'completed',
                'private_cloud_sync_enabled': True,
                'finished_at': FINISH,
                'content': 'untouched',
            },
            JOB_PATH: {
                'owner_id': 'synthetic',
                'conversation_id': 'record',
                'state': 'record_pending',
                'record_content_id': 'content',
                'privacy_generation': 0,
                'record_snapshot': {'finished_at': FINISH},
            },
        }
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    artifacts = SimpleNamespace(authorize=Mock(), key_for_owner=lambda _: b'x' * 32)
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: ['retained'])
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: (u for u in [(100, 2, [{'generation': 1, 'pcm_sha256': 'proof'}])]),
    )

    def allowed(client, tx, uid, **kwargs):
        assert not tx.has_written
        assert kwargs == {'conversation_ids': ('record',), 'expected_generation': 0}

    monkeypatch.setattr(repair, 'assert_batch_write_allowed', allowed)
    return store, client, artifacts


def plan(source):
    store, _, artifacts = source
    return repair.plan_seals(store, ['pending'], object(), artifacts)


def test_dry_run_no_writes_and_apply_only_patches_seal(source, monkeypatch):
    monkeypatch.setattr(repair, 'time', SimpleNamespace(time=lambda: 1000))
    store, client, _ = source
    result = plan(source)
    report = repair.plan_summary(result)
    assert report['dispositions'] == {'eligible': 1}
    assert all(not tx.updates and not tx.sets for tx in client.transactions)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['content'] == 'untouched'
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    seal_tx = next(tx for tx in client.transactions if tx.updates)
    assert seal_tx.updates == [
        (
            PATH,
            {
                'record_audio_closed': True,
                'record_admitted_at': client.rows[PATH]['record_admitted_at'],
                'record_sealed_at': 1000,
            },
        )
    ]
    assert client.rows[('users', 'synthetic', 'pipeline_ledger', 'record')]['stage'] == 'sealed'
    assert not any(value in json.dumps(report) for value in ('synthetic', 'pending', 'record_content_id'))


@pytest.mark.parametrize(
    'change,disposition',
    [
        ({'record_upload_failed': True}, 'upload_failed'),
        ({'record_upload_sessions': {'other-producer': True}}, 'upload_pending'),
        ({'record_lane_owner': 'legacy_final_pass_v1'}, 'not_batch_owned'),
        ({'record_lane_owner': None}, 'not_batch_owned'),
        ({'record_audio_closed': True}, 'already_closed'),
        ({'status': 'processing'}, 'not_completed'),
        ({'private_cloud_sync_enabled': False}, 'privacy_refused'),
        ({'deleted': True}, 'privacy_refused'),
        ({'discarded': True}, 'privacy_refused'),
        ({'finished_at': None}, 'proof_refused'),
        ({'finished_at': datetime.fromtimestamp(103, timezone.utc)}, 'proof_refused'),
    ],
)
def test_refuses_unsafe_conversation_states(source, change, disposition):
    store, client, artifacts = source
    client.rows[PATH].update(change)
    result = plan(source)
    assert result['entries'][0]['disposition'] == disposition
    assert repair.apply_seals(store, result, result['plan_sha256']) == {disposition: 1}
    assert all(not tx.updates for tx in client.transactions)


@pytest.mark.parametrize('units', [[], [(100, 1, [])], [(100, float('nan'), [])]])
def test_missing_short_or_nonfinite_tail_refused(source, monkeypatch, units):
    monkeypatch.setattr(repair, 'retained_record_units', lambda *a, **kw: (u for u in units))
    assert plan(source)['entries'][0]['disposition'] == 'proof_refused'


def test_archive_listing_must_require_archive_and_fail_closed(source, monkeypatch):
    def unavailable(*args, **kwargs):
        assert kwargs['max_count'] == 4096 and kwargs['require_archive'] is True
        assert kwargs['source_metadata'] is True and kwargs['client'] is not None
        raise OSError('synthetic private path')

    monkeypatch.setattr(repair, 'list_audio_chunks', unavailable)
    assert plan(source)['entries'][0]['disposition'] == 'read_error'


def test_snapshot_finish_must_also_be_covered(source):
    source[1].rows[JOB_PATH]['record_snapshot']['finished_at'] = datetime.fromtimestamp(103, timezone.utc)
    assert plan(source)['entries'][0]['disposition'] == 'proof_refused'


def test_nonpending_and_missing_jobs_refused(source):
    source[1].rows[JOB_PATH]['state'] = 'ready'
    assert plan(source)['entries'][0]['disposition'] == 'not_pending'
    source[1].rows.pop(JOB_PATH)
    assert plan(source)['entries'][0]['disposition'] == 'unavailable'


def test_plan_digest_binds_source_generations_and_refuses_stale_approval(source, monkeypatch):
    store, client, _ = source
    old = plan(source)
    monkeypatch.setattr(
        repair,
        'retained_record_units',
        lambda *a, **kw: (u for u in [(100, 2, [{'generation': 2, 'pcm_sha256': 'proof'}])]),
    )
    new = plan(source)
    assert old['plan_sha256'] != new['plan_sha256']
    with pytest.raises(ValueError, match='approval'):
        repair.apply_seals(store, new, old['plan_sha256'])
    new['entries'][0]['job_id'] = 'another'
    with pytest.raises(ValueError, match='approval'):
        repair.apply_seals(store, new, new['plan_sha256'])
    assert all(not tx.updates for tx in client.transactions)


@pytest.mark.parametrize(
    'change',
    [
        {'record_upload_failed': True},
        {'record_upload_sessions': {'p': True}},
        {'finished_at': datetime.fromtimestamp(105, timezone.utc)},
    ],
)
def test_transaction_refuses_state_change_after_proof(source, change):
    store, client, _ = source
    result = plan(source)
    client.rows[PATH].update(change)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'state_changed': 1}
    assert all(not tx.updates for tx in client.transactions)


def test_apply_rechecks_privacy_in_write_transaction(source, monkeypatch):
    store, client, _ = source
    result = plan(source)

    def blocked(*a, **kw):
        raise BatchPrivacyBlocked('privacy_generation_changed')

    monkeypatch.setattr(repair, 'assert_batch_write_allowed', blocked)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'privacy_refused': 1}
    assert all(not tx.updates for tx in client.transactions)


def test_scheduler_retry_wake_does_not_invalidate_approval_or_get_overwritten(source):
    store, client, _ = source
    result = plan(source)
    client.rows[JOB_PATH]['available_at'] = 1000
    refreshed = plan(source)
    assert result['plan_sha256'] == refreshed['plan_sha256']
    assert repair.apply_seals(store, refreshed, result['plan_sha256']) == {'sealed': 1}
    assert client.rows[JOB_PATH]['available_at'] == 1000


@pytest.mark.parametrize('identity', [True, {'pod': 'old', 'process_started_at': 900}])
def test_proven_dead_producer_can_be_cleared_with_tail_proof_and_plan_digest(source, monkeypatch, identity):
    store, client, artifacts = source
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 1000)
    client.rows[PATH]['record_upload_sessions'] = {'token': identity}
    proof = {'namespace': 'prod-omi-backend', 'captured_at': 999, 'pods': {}, 'file_sha256': 'proof'}
    result = repair.plan_seals(
        store, ['pending'], object(), artifacts, producer_proof=proof, producers_stopped=identity is True
    )
    assert result['entries'][0]['disposition'] == 'eligible'
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_upload_sessions'] == {}
    assert client.rows[PATH]['record_audio_closed']


def test_producer_proof_change_or_new_token_requires_fresh_plan(source, monkeypatch):
    store, client, artifacts = source
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 1000)
    client.rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'old', 'process_started_at': 900}}
    proof = {'namespace': 'prod-omi-backend', 'captured_at': 999, 'pods': {}, 'file_sha256': 'first'}
    old = repair.plan_seals(store, ['pending'], object(), artifacts, producer_proof=proof)
    updated = repair.plan_seals(
        store, ['pending'], object(), artifacts, producer_proof={**proof, 'file_sha256': 'second'}
    )
    assert updated['plan_sha256'] != old['plan_sha256']
    with pytest.raises(ValueError):
        repair.apply_seals(store, updated, old['plan_sha256'])
    client.rows[PATH]['record_upload_sessions']['new'] = {'pod': 'new', 'process_started_at': 990}
    assert repair.apply_seals(store, old, old['plan_sha256']) == {'state_changed': 1}


@pytest.mark.parametrize('durable_tail', [False, True])
def test_abandoned_live_pod_still_requires_retained_tail_proof(source, monkeypatch, durable_tail):
    store, client, artifacts = source
    client.rows[PATH]['record_upload_sessions'] = {
        'old': {'pod': 'live', 'process_started_at': 900, 'abandoned_at': 950}
    }
    if not durable_tail:
        monkeypatch.setattr(repair, 'retained_record_units', lambda *a, **kw: iter([(100, 1, [])]))
    result = repair.plan_seals(store, ['pending'], object(), artifacts)
    disposition = 'eligible' if durable_tail else 'proof_refused'
    assert result['entries'][0]['disposition'] == disposition
    assert repair.apply_seals(store, result, result['plan_sha256']) == {
        'sealed' if durable_tail else 'proof_refused': 1
    }
    assert bool(client.rows[PATH].get('record_audio_closed')) == durable_tail
    assert bool(client.rows[PATH]['record_upload_sessions']) != durable_tail


def test_private_exact_id_input_refuses_scans_duplicates_and_unbounded_lists(tmp_path):
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'repair_record_audio_seals.py'
    spec = importlib.util.spec_from_file_location('repair_seals_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    input_file = tmp_path / 'scope.json'
    for value in ({'query': 'all'}, [], ['same', 'same'], ['bad/path'], ['a'] * 129):
        input_file.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            module.read_job_ids(input_file)
    input_file.write_text(json.dumps(['exact']))
    assert module.read_job_ids(input_file) == ['exact']


@pytest.fixture
def cli(monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'repair_record_audio_seals.py'
    spec = importlib.util.spec_from_file_location('repair_seals_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(module.logging, 'disable', Mock())
    for name in (
        'read_job_ids',
        'get_firestore_client',
        'FirestoreStore',
        'create_storage_client',
        'artifacts_for',
        'plan_seals',
        'apply_seals',
    ):
        monkeypatch.setattr(module, name, Mock())
    monkeypatch.setattr(module, 'plan_summary', Mock(return_value={'plan_sha256': 'synthetic-digest'}))
    return module


@pytest.mark.parametrize('tier', ['ro-prod', 'prod-operator'])
def test_cli_dry_run_accepts_read_or_operator_tier_without_applying(cli, monkeypatch, capsys, tier):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.setattr(cli.sys, 'argv', ['repair', '--ids-file', 'synthetic.json'])
    cli.main()
    cli.plan_seals.assert_called_once_with(
        cli.FirestoreStore.return_value,
        cli.read_job_ids.return_value,
        cli.create_storage_client.return_value,
        cli.artifacts_for.return_value,
        producer_proof=None,
        producers_stopped=False,
    )
    cli.apply_seals.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {'apply': False, 'plan_sha256': 'synthetic-digest'}


@pytest.mark.parametrize(
    'tier,extra_args,emulator,error',
    [
        ('ro-prod', ['--apply', '--approve-plan-sha256', 'digest'], False, 'wrong identity'),
        ('prod-operator', ['--apply'], False, 'apply requires a dry-run plan digest'),
        ('ro-dev', [], False, 'wrong identity'),
        ('', [], False, 'wrong identity'),
        ('ro-prod', [], True, 'wrong identity'),
        ('prod-operator', [], True, 'wrong identity'),
        ('prod-operator', ['--apply', '--approve-plan-sha256', 'digest'], True, 'wrong identity'),
    ],
)
def test_cli_refuses_unsafe_operation_before_cloud_access(cli, monkeypatch, capsys, tier, extra_args, emulator, error):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    if emulator:
        monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', 'localhost:8080')
    monkeypatch.setattr(cli.sys, 'argv', ['repair', '--ids-file', 'synthetic.json', *extra_args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert error in capsys.readouterr().err
    for name in (
        'read_job_ids',
        'get_firestore_client',
        'FirestoreStore',
        'create_storage_client',
        'plan_seals',
        'apply_seals',
    ):
        getattr(cli, name).assert_not_called()


@pytest.mark.parametrize('changed', ['metageneration', 'generation'])
def test_listed_source_precondition_failure_never_seals(source, monkeypatch, changed):
    from google.api_core.exceptions import PreconditionFailed
    from utils.batch_pipeline import live, source_audio

    store, client, artifacts = source
    pcm = b'\x01\x00' * 16000
    # Stale 8kHz metadata makes this one-second 16kHz source appear to cover
    # FINISH (102). Enforce both server-side preconditions before any decoding.
    current = {'generation': 7, 'metageneration': 3}
    current[changed] += 1

    def download(**kwargs):
        for version in ('generation', 'metageneration'):
            condition = f'if_{version}_match'
            if condition in kwargs and kwargs[condition] != current[version]:
                raise PreconditionFailed(f'{version} changed')
        return pcm

    blob = SimpleNamespace(reload=Mock(), download_as_bytes=Mock(side_effect=download))
    storage = SimpleNamespace(bucket=lambda _: SimpleNamespace(blob=lambda *a, **kw: blob))
    chunk = {
        'path': 'chunks/synthetic/record/100.batch.bin',
        'bucket': 'synthetic',
        'generation': 7,
        'metageneration': 3,
        'timestamp': 100,
        'size': len(pcm),
        'metadata': {'record_sample_rate': '8000'},
    }
    monkeypatch.setattr(live, 'private_cloud_sync_bucket', 'synthetic')
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: [chunk])
    monkeypatch.setattr(repair, 'retained_record_units', live.retained_record_units)
    decode = Mock(wraps=source_audio.decode_source)
    monkeypatch.setattr(source_audio, 'decode_source', decode)
    result = repair.plan_seals(store, ['pending'], storage, artifacts)
    assert result['entries'][0]['disposition'] == 'read_error'
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'read_error': 1}
    assert not client.rows[PATH].get('record_audio_closed')
    assert all(not tx.updates and not tx.sets for tx in client.transactions)
    blob.download_as_bytes.assert_called_once_with(
        if_generation_match=7, if_metageneration_match=3, timeout=60, retry=None
    )
    blob.reload.assert_not_called()
    decode.assert_not_called()


@pytest.mark.parametrize(
    'mode,disposition', [('off', 'upload_pending'), ('shadow', 'upload_pending'), ('serve', 'eligible')]
)
def test_lease_dead_plan_and_kill_switch_dispositions(source, monkeypatch, mode, disposition):
    store, client, _ = source
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 10000)
    client.rows[PATH]['record_upload_sessions'] = {
        's': {
            'pod': 'live',
            'process_started_at': 100,
            'last_signal_at': 100,
            'lease_expires_at': 3700,
            'signal_source': 'frames',
        }
    }
    result = plan(source)
    assert result['entries'][0]['disposition'] == disposition
    # Killed, the lapsed lease holds the seal and no would-expire diagnostic fires.
    assert result['entries'][0].get('lease_reason') is None
    outcome = repair.apply_seals(store, result, result['plan_sha256'])
    assert outcome == ({'sealed': 1} if mode == 'serve' else {'upload_pending': 1})
    assert bool(client.rows[PATH].get('record_audio_closed')) is (mode == 'serve')


def test_late_append_between_plan_and_apply_refences_and_bumps_revision(source, monkeypatch):

    store, client, _ = source
    client.rows[('users', 'synthetic')] = {'private_cloud_sync_enabled': True}
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 10000)
    client.rows[PATH]['record_upload_sessions'] = {
        's': {
            'pod': 'live',
            'process_started_at': 100,
            'last_signal_at': 100,
            'lease_expires_at': 3700,
            'signal_source': 'frames',
        }
    }
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'eligible'
    from database import record_custody_append

    monkeypatch.setattr(record_custody_append, 'time', SimpleNamespace(time=lambda: 10000))
    assert record_custody_append.begin('synthetic', 'record', 'custody:plan-race', firestore_client=client)
    assert client.rows[PATH].get('record_upload_revision', 0) == 0
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'state_changed': 1}
    assert plan(source)['entries'][0]['disposition'] == 'upload_pending'
    # The durable file append is a throttled heartbeat, still no early bump.
    renew_record_token_lease(
        'synthetic', 'record', source='custody_append', session='custody:plan-race', firestore_client=client
    )
    assert client.rows[PATH].get('record_upload_revision', 0) == 0
    record_custody_append.finish('synthetic', 'record', 'custody:plan-race', accepted=True, firestore_client=client)
    assert client.rows[PATH]['record_upload_revision'] == 1
    assert set(client.rows[PATH]['record_upload_sessions']) == {'s'}
    # The frame token's lease lapsed, so the record is eligible again once the custody uploader ends.
    assert plan(source)['entries'][0]['disposition'] == 'eligible'


def test_lease_kill_switch_after_plan_and_tail_refusal(source, monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 10000)
    source[1].rows[PATH]['record_upload_sessions'] = {
        's': {
            'pod': 'live',
            'process_started_at': 100,
            'last_signal_at': 100,
            'lease_expires_at': 3700,
            'signal_source': 'frames',
        }
    }
    result = plan(source)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
    assert repair.apply_seals(source[0], result, result['plan_sha256']) == {'upload_pending': 1}
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    source[1].rows[PATH]['finished_at'] = datetime.fromtimestamp(150, timezone.utc)
    assert plan(source)['entries'][0]['disposition'] == 'proof_refused'


@pytest.mark.parametrize('available_at', [9900, 200])
def test_moving_retry_wake_cannot_extend_stock_lease_in_plan_or_apply(source, monkeypatch, available_at):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_DEPLOYED_AT', '100')
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 10000)
    source[1].rows[PATH]['record_upload_sessions'] = {'s': {'pod': 'live', 'process_started_at': 100}}
    source[1].rows[JOB_PATH]['available_at'] = available_at
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'eligible'
    source[1].rows[JOB_PATH]['available_at'] = 20000
    assert repair.apply_seals(source[0], result, result['plan_sha256']) == {'sealed': 1}


@pytest.mark.parametrize('age,enabled,wake', [(90, True, 0), (7201, True, 1), (-1, True, 10900), (90, False, 10900)])
def test_fresh_proven_seals_wake_ahead_of_certified_backlog_retries(source, monkeypatch, age, enabled, wake):
    store, client, artifacts = source
    monkeypatch.setattr(repair.time, 'time', lambda: 10000)
    client.rows[JOB_PATH].update(enqueued_at=10000 - age, available_at=10900, record_intake_retry_at=10900)
    approval = repair.plan_seals(store, ['pending'], object(), artifacts, wake_admission=True)
    if not enabled:
        monkeypatch.setenv('RECORD_SEAL_REPAIR_FRESH_ENABLED', 'false')
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[JOB_PATH]['available_at'] == wake
    assert client.rows[JOB_PATH]['state'] == 'record_pending'


@pytest.mark.parametrize('age', [90, 8000])
@pytest.mark.parametrize('claim_between_plan_and_commit', [False, True])
def test_seal_preserves_a_live_claim_including_claims_acquired_after_planning(
    source, monkeypatch, claim_between_plan_and_commit, age
):
    store, client, artifacts = source
    monkeypatch.setattr(repair.time, 'time', lambda: 10000)
    client.rows[JOB_PATH].update(enqueued_at=10000 - age, available_at=10900, record_intake_retry_at=10900)
    if not claim_between_plan_and_commit:
        client.rows[JOB_PATH]['available_at'] = 11000
    approval = repair.plan_seals(store, ['pending'], object(), artifacts, wake_admission=True)
    # Claiming (including by an older binary) changes available_at but does
    # not certify that new value as a retry. This races the planning snapshot.
    client.rows[JOB_PATH]['available_at'] = 11000
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[JOB_PATH]['available_at'] == 11000


def test_plain_deferred_retry_added_after_planning_is_still_woken(source, monkeypatch):
    store, client, artifacts = source
    monkeypatch.setattr(repair.time, 'time', lambda: 10000)
    client.rows[JOB_PATH].update(enqueued_at=9900, available_at=0)
    approval = repair.plan_seals(store, ['pending'], object(), artifacts, wake_admission=True)
    client.rows[JOB_PATH].update(available_at=10900, record_intake_retry_at=10900)
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'sealed': 1}
    assert client.rows[JOB_PATH]['available_at'] == 0
    assert client.rows[JOB_PATH]['record_intake_retry_at'] is None


@pytest.mark.parametrize('age', [90, 8000])
def test_unmarked_future_wake_is_preserved_during_a_rolling_upgrade(source, monkeypatch, age):
    store, client, artifacts = source
    monkeypatch.setattr(repair.time, 'time', lambda: 10000)
    client.rows[JOB_PATH].update(enqueued_at=10000 - age, available_at=10900)
    approval = repair.plan_seals(store, ['pending'], object(), artifacts, wake_admission=True)
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'sealed': 1}
    assert client.rows[JOB_PATH]['available_at'] == 10900


def test_fresh_wake_never_runs_when_seal_privacy_recheck_refuses(source, monkeypatch):
    store, client, artifacts = source
    monkeypatch.setattr(repair.time, 'time', lambda: 10000)
    client.rows[JOB_PATH].update(enqueued_at=9900, available_at=10900)
    approval = repair.plan_seals(store, ['pending'], object(), artifacts, wake_admission=True)

    def revoked(*args, **kwargs):
        raise BatchPrivacyBlocked('account_deleted')

    monkeypatch.setattr(repair, 'assert_batch_write_allowed', revoked)
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'privacy_refused': 1}
    assert not client.rows[PATH].get('record_audio_closed')
    assert client.rows[JOB_PATH]['available_at'] == 10900


def test_repair_admission_is_once_and_ledger_failure_is_fail_open(source, monkeypatch):
    store, client, _ = source
    admissions = Mock()
    monkeypatch.setattr(repair.pipeline_ledger, 'observe_admission', admissions)
    monkeypatch.setattr(repair.pipeline_ledger, 'advance', Mock(side_effect=RuntimeError('ledger unavailable')))
    result = plan(source)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['record_admitted_at'] is not None
    client.rows[PATH]['record_audio_closed'] = False
    result = plan(source)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'sealed': 1}
    assert admissions.call_count == 1


def test_slow_post_commit_ledger_is_bounded_counted_and_still_sealed(source, monkeypatch):
    import signal
    import time

    store, client, _ = source
    counts = {}
    failures = Mock()
    fallback = Mock()
    monkeypatch.setattr(repair.pipeline_ledger, 'record_fallback', fallback)
    monkeypatch.setattr(repair, 'LEDGER_OBSERVATION_SECONDS', 0.02)
    monkeypatch.setattr(repair.pipeline_ledger, '_observe_failure', failures)

    def slow_ledger(*args, **kwargs):
        assert client.rows[PATH]['record_audio_closed']  # The real commit already happened.
        time.sleep(30)  # The real signal deadline must interrupt this IO wait.

    monkeypatch.setattr(repair.pipeline_ledger, 'advance', slow_ledger)
    result = plan(source)
    started = time.monotonic()
    with repair.SweepBudget(270).interrupt_io():
        assert repair.apply_seals(store, result, result['plan_sha256'], observation_counts=counts) == {'sealed': 1}
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 269
    assert time.monotonic() - started < 1
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['record_admitted_at'] is not None
    assert counts == {'ledger_misses': 1}
    assert isinstance(failures.call_args.args[0], TimeoutError)
    fallback.assert_called_once_with(
        component='firestore_read',
        from_mode='record_seal_ledger',
        to_mode='sealed_without_ledger',
        reason='timeout',
        outcome='degraded',
    )


@pytest.mark.parametrize('error,reason', [('timeout', 'timeout'), ('unavailable', 'unavailable')])
def test_source_revision_read_failure_emits_one_fallback_and_preserves_seal(source, monkeypatch, error, reason):
    from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    store, client, _ = source
    original = StrictFirestoreDocument.get
    fallback = Mock()
    monkeypatch.setattr(repair.pipeline_ledger, 'record_fallback', fallback)

    def read(reference, *args, **kwargs):
        if reference.path == PATH and kwargs.get('timeout') == 3:
            raise DeadlineExceeded('synthetic') if error == 'timeout' else ServiceUnavailable('synthetic')
        return original(reference, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', read)
    approval = plan(source)
    counts = {}
    assert repair.apply_seals(store, approval, approval['plan_sha256'], observation_counts=counts) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert counts == {'ledger_misses': 1}
    fallback.assert_called_once_with(
        component='firestore_read',
        from_mode='record_seal_ledger',
        to_mode='sealed_without_ledger',
        reason=reason,
        outcome='degraded',
    )


@pytest.mark.parametrize('prior_stage', ['sealed', 'failed:upload_failed'])
def test_reseal_keeps_original_sealed_deadline_but_recovers_failed_stage(source, monkeypatch, prior_stage):
    from copy import deepcopy

    store, client, _ = source
    client.rows[PATH]['record_admitted_at'] = 50
    ledger_path = ('users', 'synthetic', 'pipeline_ledger', 'record')
    client.rows[ledger_path] = {
        'stage': prior_stage,
        'revision': 2,
        'entered_at': 10,
        'deadline_at': 3610 if prior_stage == 'sealed' else None,
        'terminal': prior_stage != 'sealed',
    }
    before = deepcopy(client.rows[ledger_path])
    monkeypatch.setattr(repair.pipeline_ledger, 'source_revision', lambda _: 3)
    admissions = Mock()
    monkeypatch.setattr(repair.pipeline_ledger, 'observe_admission', admissions)
    approval = plan(source)
    assert repair.apply_seals(store, approval, approval['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    admissions.assert_not_called()
    if prior_stage == 'sealed':
        assert client.rows[ledger_path] == before  # Clock AND deadline/revision remain unchanged.
    else:
        after = client.rows[ledger_path]
        assert after['stage'] == 'sealed' and after['revision'] == 3 and not after['terminal']
        assert after['deadline_at'] == after['entered_at'] + 3600
