"""Synthetic operator backfill: no dry-run writes, atomic seal+job and privacy CAS."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import (
    live,
    record_producer_proof,
    record_seal_nojob as backfill,
    record_seal_repair as repair,
)

PATH = ('users', 'synthetic', 'conversations', 'capture')
SCOPE = ['/'.join(PATH)]
JOB_PATH = ('batch_pipeline_dev_jobs', live.record_identity('synthetic', 'capture')[1])
SERVER = {
    'K_SERVICE': 'synthetic-serving-role',
    'BATCH_PIPELINE_PERCENT': '5',
    'BATCH_LIVE_STT_RETIRE_PERCENT': '0',
}


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 1000)
    client = StrictFirestore(
        {
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
            PATH: {
                'record_lane_owner': 'batch_live_v1',
                'status': 'completed',
                'private_cloud_sync_enabled': True,
                'finished_at': datetime.fromtimestamp(102, timezone.utc),
                'source': 'omi',
                'language': 'en',
                'content': 'untouched',
            },
        }
    )
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    artifacts = SimpleNamespace(authorize=Mock(), key_for_owner=lambda _: b'x' * 32)
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: ['retained'])
    monkeypatch.setattr(repair, 'retained_record_units', lambda *a: (u for u in [(100, 2, [{'generation': 1}])]))
    return store, client, artifacts


def plan(source, proof=None):
    store, _, artifacts = source
    return backfill.plan_backfill(store, SCOPE, object(), artifacts, server_flags=SERVER, producer_proof=proof)


def apply(source, result):
    return backfill.apply_backfill(source[0], result, result['plan_sha256'])


def no_writes(client):
    return all(not tx.updates and not tx.sets for tx in client.transactions)


def test_dry_run_counts_only_and_atomic_idempotent_apply(source):
    _, client, _ = source
    result = plan(source)
    report = backfill.summary(result)
    assert report['dispositions'] == {'eligible': 1}
    assert no_writes(client)
    assert all(value not in json.dumps(report) for value in ('synthetic', 'capture', JOB_PATH[1]))
    assert apply(source, result) == {'sealed_registered': 1}
    transaction = client.transactions[-1]
    assert transaction.sets[0][0] == JOB_PATH
    assert transaction.updates == [(PATH, {'record_upload_sessions': {}, 'record_audio_closed': True})]
    assert client.rows[PATH]['content'] == 'untouched'
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    assert client.rows[JOB_PATH]['record_snapshot']['finished_at'] == client.rows[PATH]['finished_at']
    assert apply(source, result) == {'already_registered': 1}
    assert plan(source)['entries'][0]['disposition'] == 'already_registered'
    assert len([tx for tx in client.transactions if tx.sets]) == 1


def test_active_refused_row_cannot_churn_approval_or_gain_write_authority(source):
    store, client, artifacts = source
    active = ('users', 'synthetic', 'conversations', 'active')
    client.rows[active] = {**client.rows[PATH], 'status': 'processing', 'record_upload_revision': 1}
    paths = [*SCOPE, '/'.join(active)]
    previous = backfill.plan_backfill(store, paths, object(), artifacts, server_flags=SERVER)
    client.rows[active]['record_upload_revision'] = 2
    refreshed = backfill.plan_backfill(store, paths, object(), artifacts, server_flags=SERVER)
    assert refreshed['plan_sha256'] == previous['plan_sha256']
    assert apply(source, refreshed) == {'not_completed': 1, 'sealed_registered': 1}
    assert 'record_audio_closed' not in client.rows[active]
    assert client.transactions[-1].updates[0][0] == PATH


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'record_upload_failed': True}, 'upload_failed'),
        ({'uses_custom_stt': True}, 'privacy_refused'),
        ({'data_protection_level': 'e2ee'}, 'privacy_refused'),
        ({'deleted': True}, 'privacy_refused'),
        ({'discarded': True}, 'privacy_refused'),
        ({'private_cloud_sync_enabled': False}, 'privacy_refused'),
        ({'record_lane_owner': 'batch_sync_v1'}, 'not_batch_owned'),
        ({'record_audio_closed': True}, 'already_closed'),
        ({'status': 'processing'}, 'not_completed'),
        ({'finished_at': None}, 'proof_refused'),
        ({'record_upload_sessions': {'legacy': True}}, 'upload_pending'),
    ],
)
def test_unsafe_rows_never_touched(source, change, reason):
    source[1].rows[PATH].update(change)
    result = plan(source)
    assert result['entries'][0]['disposition'] == reason
    assert apply(source, result) == {reason: 1}
    assert no_writes(source[1])


def test_live_pod_token_never_cleared_and_dead_pod_requires_fresh_proof(source):
    source[1].rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'producer', 'process_started_at': 900}}
    proof = {'namespace': 'prod-omi-backend', 'captured_at': 999, 'pods': {'producer': 900}, 'file_sha256': 'proof'}
    assert plan(source, proof)['entries'][0]['disposition'] == 'upload_pending'
    assert plan(source)['entries'][0]['disposition'] == 'upload_pending'
    dead = {**proof, 'pods': {}}
    result = plan(source, dead)
    assert result['entries'][0]['disposition'] == 'eligible'
    assert apply(source, result) == {'sealed_registered': 1}
    assert source[1].rows[PATH]['record_upload_sessions'] == {}


def test_token_capacity_limit_refuses_even_proven_dead_map(source):
    source[1].rows[PATH]['record_upload_sessions'] = {
        str(index): {'pod': 'producer', 'process_started_at': 900} for index in range(129)
    }
    result = plan(source, {'namespace': 'prod-omi-backend', 'captured_at': 999, 'pods': {}})
    assert apply(source, result) == {'upload_pending': 1}
    assert no_writes(source[1])


def test_inventory_expiring_after_plan_refuses_apply(source, monkeypatch):
    source[1].rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'producer', 'process_started_at': 900}}
    result = plan(source, {'namespace': 'prod-omi-backend', 'captured_at': 999, 'pods': {}})
    monkeypatch.setattr(record_producer_proof.time, 'time', lambda: 1300)
    assert apply(source, result) == {'upload_pending': 1}
    assert no_writes(source[1])


def test_even_an_empty_existing_job_is_never_overwritten(source):
    source[1].rows[JOB_PATH] = {}
    result = plan(source)
    assert result['entries'][0]['disposition'] == 'already_registered'
    assert apply(source, result) == {'already_registered': 1}
    assert no_writes(source[1])


@pytest.mark.parametrize(
    'change',
    [
        {'record_upload_failed': True},
        {'record_upload_revision': 2},
        {'record_upload_sessions': {'new': True}},
        {'uses_custom_stt': True},
        {'language': 'es'},
    ],
)
def test_stale_row_digest_and_transaction_race_are_refused(source, change):
    previous = plan(source)
    source[1].rows[PATH].update(change)
    fresh = plan(source)
    with pytest.raises(ValueError, match='approval'):
        backfill.apply_backfill(source[0], fresh, previous['plan_sha256'])
    assert apply(source, previous) == {'state_changed': 1}
    assert no_writes(source[1])


def test_tail_generation_changes_digest_and_short_tail_refused(source, monkeypatch):
    previous = plan(source)
    monkeypatch.setattr(repair, 'retained_record_units', lambda *a: (u for u in [(100, 2, [{'generation': 2}])]))
    fresh = plan(source)
    with pytest.raises(ValueError, match='approval'):
        backfill.apply_backfill(source[0], fresh, previous['plan_sha256'])
    monkeypatch.setattr(repair, 'retained_record_units', lambda *a: (u for u in [(100, 1, [])]))
    assert plan(source)['entries'][0]['disposition'] == 'proof_refused'
    assert no_writes(source[1])


@pytest.mark.parametrize(
    'change',
    [
        (('users', 'synthetic'), {'private_cloud_sync_enabled': False}),
        (('users', 'synthetic'), {'data_protection_level': 'e2ee'}),
        (('account_deletions', 'synthetic'), {'wipe_status': 'pending'}),
    ],
)
def test_account_privacy_change_before_apply_prevents_both_writes(source, change):
    result = plan(source)
    path, fields = change
    source[1].rows.setdefault(path, {}).update(fields)
    assert apply(source, result) == {'privacy_refused': 1}
    assert no_writes(source[1])


def test_discovery_bound_and_cursor_contract():
    client, query = Mock(), Mock()
    client.collection_group.return_value = query
    for method in ('where', 'order_by', 'select', 'limit', 'start_after'):
        getattr(query, method).return_value = query
    query.stream.return_value = [SimpleNamespace(reference=SimpleNamespace(path=SCOPE[0]))]
    assert backfill.discover(client, limit=128, after=SCOPE[0]) == (SCOPE, SCOPE[0])
    query.limit.assert_called_once_with(128)
    query.order_by.assert_called_once_with('__name__')
    query.select.assert_called_once_with(())
    query.start_after.assert_called_once_with({'__name__': client.document.return_value})
    query.stream.return_value = []
    assert backfill.discover(client, limit=128, after=SCOPE[0]) == ([], None)
    for limit in (0, 129, True):
        with pytest.raises(ValueError):
            backfill.discover(client, limit=limit)
    with pytest.raises(ValueError):
        backfill.discover(client, after='unscoped/path')


def cli():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'backfill_record_seal_nojob.py'
    spec = importlib.util.spec_from_file_location('backfill_seal_cli', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    'tier,apply_mode,allowed',
    [
        ('ro-prod', False, True),
        ('prod-operator', False, True),
        ('ro-prod', True, False),
        ('prod-operator', True, True),
        ('ro-dev', False, False),
    ],
)
def test_cli_tiers_before_any_client_access(monkeypatch, tier, apply_mode, allowed):
    monkeypatch.setenv('GCP_AGENT_TIER', tier)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    reached = Mock(side_effect=RuntimeError('stop before network'))
    module = cli()
    monkeypatch.setattr(module, 'get_firestore_client', reached)
    monkeypatch.setattr(module, 'read_server_flags', lambda _: SERVER)
    args = ['--next-file', '/unused', '--server-flags-file', '/flags'] + (
        ['--apply', '--approve-plan-sha256', 'digest'] if apply_mode else []
    )
    with pytest.raises(RuntimeError if allowed else SystemExit):
        module.main(args)
    assert reached.called is allowed


def test_cli_dry_run_outputs_only_counts_and_digest(source, monkeypatch, capsys):
    module = cli()
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(module, 'get_firestore_client', lambda: source[1])

    def store(*args, **kwargs):
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
        return source[0]

    monkeypatch.setattr(module, 'FirestoreStore', store)
    monkeypatch.setattr(module, 'discover', lambda *a, **kw: (SCOPE, SCOPE[0]))
    monkeypatch.setattr(module, 'artifacts_for', lambda _: source[2])
    monkeypatch.setattr(module, 'create_storage_client', object)
    cursor = Mock()
    monkeypatch.setattr(module, 'write_cursor', cursor)
    monkeypatch.setattr(module, 'read_server_flags', lambda _: SERVER)
    module.main(['--next-file', '/private/cursor', '--server-flags-file', '/flags'])
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report['dispositions'] == {'eligible': 1}
    assert set(report) == {'operation', 'plan_sha256', 'count', 'dispositions', 'apply'}
    assert all(value not in output.out + output.err for value in ('synthetic', 'capture', '/private', JOB_PATH[1]))
    cursor.assert_called_once_with('/private/cursor', SCOPE[0])
    assert no_writes(source[1])


def test_cli_invalid_arguments_do_not_echo_sensitive_values(capsys):
    with pytest.raises(SystemExit):
        cli().main(['--limit', 'synthetic-private-path'])
    output = capsys.readouterr()
    assert json.loads(output.out)['outcome'] == 'invalid_arguments'
    assert 'synthetic-private-path' not in output.out + output.err


def test_operator_registration_cannot_pin_laptop_policy(source, monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'operator-laptop')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    result = plan(source)
    assert result['entries'][0]['job']['policy']['source_role'] == SERVER['K_SERVICE']
    assert result['entries'][0]['job']['policy']['batch_percent'] == 5
    assert apply(source, result) == {'sealed_registered': 1}
    assert source[1].rows[JOB_PATH]['policy']['source_role'] == SERVER['K_SERVICE']
    with pytest.raises(ValueError):
        backfill.plan_backfill(source[0], SCOPE, object(), source[2], server_flags=None)


def test_server_flag_file_filters_unrelated_values_and_requires_role(tmp_path):
    module = cli()
    path = tmp_path / 'flags.json'
    path.write_text(json.dumps({**SERVER, 'SECRET': 'synthetic-secret'}))
    assert module.read_server_flags(path) == SERVER
    for value in ([], {}, {'K_SERVICE': True}, {'K_SERVICE': 'role', 'BATCH_PIPELINE_PERCENT': 5}):
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            module.read_server_flags(path)


@pytest.mark.parametrize(
    'flags',
    [
        {'K_SERVICE': 'role'},
        {'K_SERVICE': 'role', 'BATCH_PIPELINE_PERCENT': '5'},
        {**SERVER, 'BATCH_PIPELINE_PERCENT': 'NaN'},
        {**SERVER, 'BATCH_PIPELINE_PERCENT': '-1'},
        {**SERVER, 'BATCH_PIPELINE_PERCENT': '101'},
        {**SERVER, 'BATCH_PIPELINE_PERCENT': 'invalid'},
        {**SERVER, 'BATCH_LIVE_STT_RETIRE_PERCENT': '6'},
    ],
)
def test_incomplete_or_invalid_serving_ramps_refuse_before_planning(source, flags, tmp_path):
    module = cli()
    path = tmp_path / 'flags.json'
    path.write_text(json.dumps(flags))
    with pytest.raises(ValueError):
        module.read_server_flags(path)
    with pytest.raises(ValueError):
        backfill.plan_backfill(source[0], SCOPE, object(), source[2], server_flags=flags)
    assert no_writes(source[1])


def test_private_cursor_permissions_and_rejects_public_directory(tmp_path, monkeypatch):
    module = cli()
    # Redirect only the configured scratch root for the isolated fixture.
    real_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        return tmp_path if str(path) == '/Volumes/Ephemeral/scratch' else real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', resolve)
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'cursor.json'
    module.write_cursor(path, SCOPE[0])
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == {'after': SCOPE[0]}
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        module.write_cursor(path, SCOPE[0])
