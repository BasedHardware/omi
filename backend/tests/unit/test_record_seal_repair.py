"""Synthetic exact-scope repair: tail/privacy/failure refusal and digest CAS."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_store import FirestoreStore
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
        repair, 'retained_record_units', lambda *a: (u for u in [(100, 2, [{'generation': 1, 'pcm_sha256': 'proof'}])])
    )

    def allowed(client, tx, uid, **kwargs):
        assert not tx.has_written
        assert kwargs == {'conversation_ids': ('record',), 'expected_generation': 0}

    monkeypatch.setattr(repair, 'assert_batch_write_allowed', allowed)
    return store, client, artifacts


def plan(source):
    store, _, artifacts = source
    return repair.plan_seals(store, ['pending'], object(), artifacts)


def test_dry_run_no_writes_and_apply_only_patches_seal(source):
    store, client, _ = source
    result = plan(source)
    report = repair.plan_summary(result)
    assert report['dispositions'] == {'eligible': 1}
    assert all(not tx.updates and not tx.sets for tx in client.transactions)
    assert repair.apply_seals(store, result, result['plan_sha256']) == {'sealed': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['content'] == 'untouched'
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    assert client.transactions[-1].updates == [(PATH, {'record_audio_closed': True})]
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
    monkeypatch.setattr(repair, 'retained_record_units', lambda *a: (u for u in units))
    assert plan(source)['entries'][0]['disposition'] == 'proof_refused'


def test_archive_listing_must_require_archive_and_fail_closed(source, monkeypatch):
    def unavailable(*args, **kwargs):
        assert kwargs == {'max_count': 4096, 'require_archive': True}
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
        repair, 'retained_record_units', lambda *a: (u for u in [(100, 2, [{'generation': 2, 'pcm_sha256': 'proof'}])])
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
