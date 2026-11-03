"""The staging kit refuses production/default bindings before any client IO."""

import json
import logging
from unittest.mock import MagicMock
import httpx
import pytest

from scripts.staging import syncsplit as kit
from tests.unit.test_sync_backfill_uid_sequencer import db
from tests.unit.test_staging_fence import _clean_env
from utils.staging_fence import StagingFenceError

BASE = 'https://backend-sync-staging-synthetic.run.app'


def env():
    values = _clean_env()
    values.update(
        {
            'SYNC_BACKFILL_WORKER_API_URL': BASE,
            'SYNC_BACKFILL_WORKER_AUDIENCE': BASE,
            'SYNC_BACKFILL_UID_SEQUENCER': 'on',
            'SYNC_LEDGER_FENCE_MODE': 'active',
            'SYNC_BACKFILL_WORKER_PERCENT': '100',
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_TASKS_PROJECT': 'based-hardware-dev',
            'SYNC_TASKS_LOCATION': 'us-central1',
            'SYNC_TASKS_HANDLER_URL': BASE + '/v2/sync-jobs/run',
            'SYNC_TASKS_OIDC_AUDIENCE': BASE + '/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': BASE + '/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE': BASE + '/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': 'staging-sync-backfill',
            'SYNC_TASKS_INVOKER_SA': 'staging-invoker@based-hardware-dev.iam.gserviceaccount.com',
        }
    )
    return values


@pytest.fixture(autouse=True)
def restore_logging():
    level = logging.root.manager.disable
    yield
    logging.disable(level)


def test_known_isolated_contract_is_accepted():
    kit.validate_configuration(env(), BASE)


@pytest.mark.parametrize(
    'key,value',
    [
        ('OMI_DEPLOYMENT', 'prod'),
        ('OMI_ENV_STAGE', 'dev'),
        ('OMI_CUSTOMER_DATA_PROJECT', 'based-hardware'),
        ('FIRESTORE_DATABASE_ID', '(default)'),
        ('SYNC_TASKS_PROJECT', 'based-hardware'),
        ('SYNC_BACKFILL_TASKS_HANDLER_URL', ''),
        ('SYNC_BACKFILL_TASKS_OIDC_AUDIENCE', ''),
        ('SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill-fresh'),
        ('BUCKET_TEMPORAL_SYNC_LOCAL', ''),
        ('REDIS_DB_HOST', ''),
        ('REDIS_DB_PORT', ''),
        ('SYNC_BACKFILL_WORKER_PERCENT', '0'),
        ('SYNC_LEDGER_FENCE_MODE', 'legacy'),
    ],
)
def test_production_or_implicit_binding_is_refused(key, value):
    values = env()
    values[key] = value
    with pytest.raises((kit.ProbeRefused, StagingFenceError)):
        kit.validate_configuration(values, BASE)


@pytest.mark.parametrize(
    'target',
    [
        'https://api.omi.me',
        'https://backend-sync-prod.run.app',
        BASE + '?rig=dev',
        BASE + '/path',
    ],
)
def test_target_must_be_exact_staging_service(target):
    with pytest.raises(kit.ProbeRefused):
        kit.validate_configuration(env(), target)


def test_private_oidc_file_is_required(tmp_path):
    token = tmp_path / 'oidc'
    token.write_text('synthetic-token')
    token.chmod(0o600)
    assert kit.private_token(token) == 'synthetic-token'
    token.chmod(0o644)
    with pytest.raises(kit.ProbeRefused):
        kit.private_token(token)


def test_actual_rpc_client_authenticates_without_emitting_token(tmp_path):
    path = tmp_path / 'oidc'
    path.write_text('synthetic-token')
    path.chmod(0o600)
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        assert json.loads(request.content) == {'stage': 'prod'}
        return httpx.Response(200, json={'lease': None})

    probe = kit.Probe(BASE, path)
    probe.http.close()
    probe.http = httpx.Client(transport=httpx.MockTransport(handle))
    try:
        assert probe.rpc('claim') == {'lease': None}
    finally:
        probe.http.close()
    assert len(requests) == 1


def test_claim_polls_past_an_empty_wrap_and_still_checks_the_job(monkeypatch, tmp_path):
    probe = kit.Probe(BASE, tmp_path / 'unused-token')
    monkeypatch.setattr(kit.time, 'sleep', lambda _: None)
    fixture = {'uid': 'u', 'job_id': 'j', 'epoch': 1}
    try:
        polls = iter([{'lease': None}, {'lease': {'payload': {'job_id': 'j'}, 'token': 't'}}])
        monkeypatch.setattr(probe, 'rpc', lambda operation: next(polls))
        assert probe.claim(fixture)['token'] == 't'

        monkeypatch.setattr(probe, 'rpc', lambda operation: {'lease': {'payload': {'job_id': 'other'}, 'token': 't'}})
        with pytest.raises(kit.ProbeRefused, match='claim mismatch'):
            probe.claim(fixture)
    finally:
        probe.http.close()


def test_plan_never_validates_or_loads_credentials(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['syncsplit', 'plan'])
    monkeypatch.setattr(kit, 'validate_configuration', lambda *args: pytest.fail('credentialed path'))
    assert kit.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['max_seconds'] == 3000
    assert receipt['speech_parity'] == 'NOT_RUN'
    assert receipt['cost'] == 'NOT_MEASURED'


def test_production_run_refuses_before_probe_construction(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['syncsplit', 'run', '--target', BASE])
    monkeypatch.setenv('OMI_DEPLOYMENT', 'prod')
    monkeypatch.setattr(kit, 'Probe', lambda *args: pytest.fail('network client constructed'))
    assert kit.main() == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['result'] == 'FAIL'
    assert receipt['exception_type'] == 'ProbeRefused'


def test_waiter_has_deadline_and_stops_on_first_failure(monkeypatch):
    monkeypatch.setattr(kit.time, 'monotonic', lambda: 10)
    with pytest.raises(kit.ProbeRefused, match='deadline'):
        kit.wait_until(lambda: False, 60, deadline=9)
    calls = []

    def failed():
        calls.append(True)
        raise kit.ProbeRefused('first failure')

    with pytest.raises(kit.ProbeRefused, match='first failure'):
        kit.wait_until(failed, 60, deadline=100)
    assert len(calls) == 1


@pytest.mark.parametrize('mode', ['run', 'fleet_case'])
@pytest.mark.parametrize('occupied', [False, True])
def test_probe_checks_generator_contents_before_starting(monkeypatch, tmp_path, mode, occupied):
    from database import sync_backfill_sequencer as registry, sync_jobs

    def candidates():
        if occupied:
            yield {'uid': 'synthetic'}
        else:
            yield from ()

    monkeypatch.setattr(registry, 'worker_candidates', candidates)
    fixture = {'job_id': 'job'}
    seed = MagicMock(return_value=fixture)
    enqueue = MagicMock()
    monkeypatch.setattr(kit, 'seed', seed)
    monkeypatch.setattr(kit, 'enqueue_fixture', enqueue)
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _: {'execution_drive': 'pull'})
    probe = kit.Probe(BASE, tmp_path / 'unused-token')
    probe.rpc_cases = MagicMock()
    probe.no_worker_case = MagicMock()
    probe.death_case = MagicMock()
    probe.terminal_fallback = lambda _: True
    try:
        if occupied:
            with pytest.raises(kit.ProbeRefused, match='pre-existing'):
                getattr(probe, mode)()
            seed.assert_not_called()
            probe.rpc_cases.assert_not_called()
        else:
            receipt = getattr(probe, mode)()
            assert receipt['result'] == 'PASS'
            if mode == 'run':
                probe.rpc_cases.assert_called_once()
                probe.no_worker_case.assert_called_once()
                probe.death_case.assert_called_once()
            else:
                seed.assert_called_once()
                enqueue.assert_called_once_with(fixture)
        if mode == 'run':
            assert probe.http.is_closed
    finally:
        probe.http.close()


def test_rpc_cases_exercise_real_seed_and_owner_fences(db, monkeypatch, tmp_path):
    from database import sync_backfill_sequencer as registry
    from utils.sync import legacy_dark, worker_control

    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    monkeypatch.setenv('SYNC_BACKFILL_WORKER_PERCENT', '100')
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'active')
    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'false')
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: legacy_dark.LegacySyncMode.ON)
    operations = []

    def rpc(operation, body=None):
        operations.append(operation)
        if operation == 'claim':
            return {'lease': worker_control.claim()}
        return {'accepted': getattr(worker_control, operation)(**body)}

    probe = kit.Probe(BASE, tmp_path / 'unused-token')
    probe.rpc = rpc
    try:
        probe.rpc_cases()
        assert probe.passed == ['claim', 'heartbeat', 'duplicate-claim', 'complete', 'fail']
        assert set(operations) == {'claim', 'heartbeat', 'complete', 'fail'}
        owners = [row for path, row in db.docs.items() if path[0] == registry.COLLECTION]
        assert len(owners) == 2
        assert all('active_job_id' not in owner for owner in owners)
    finally:
        probe.http.close()


@pytest.mark.parametrize('drive', [None, 'pull'])
def test_fleet_requires_installed_execution_marker(monkeypatch, tmp_path, drive):
    from database import sync_backfill_sequencer as registry, sync_jobs

    monkeypatch.setattr(registry, 'worker_candidates', lambda: iter(()))
    monkeypatch.setattr(kit, 'seed', lambda: {'job_id': 'job'})
    monkeypatch.setattr(kit, 'enqueue_fixture', lambda _: None)
    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda _: {'execution_drive': drive})
    probe = kit.Probe(BASE, tmp_path / 'unused-token')
    probe.terminal_fallback = lambda _: True
    try:
        if drive == 'pull':
            assert probe.fleet_case()['fleet_execution'] == 'PASS'
        else:
            with pytest.raises(kit.ProbeRefused, match='installed worker'):
                probe.fleet_case()
    finally:
        probe.http.close()


@pytest.mark.parametrize('mode', ['run', 'fleet'])
def test_main_reaches_documented_mode_and_closes_client(monkeypatch, tmp_path, capsys, mode):
    path = tmp_path / 'token'
    path.write_text('synthetic-token')
    path.chmod(0o600)
    monkeypatch.setattr('sys.argv', ['syncsplit', mode, '--target', BASE, '--token-file', str(path)])
    monkeypatch.setattr(kit, 'validate_configuration', lambda *args: None)
    probe = MagicMock()
    probe.run.return_value = probe.fleet_case.return_value = {'result': 'PASS'}
    monkeypatch.setattr(kit, 'Probe', lambda *args: probe)
    assert kit.main() == 0
    assert json.loads(capsys.readouterr().out) == {'result': 'PASS'}
    (probe.run if mode == 'run' else probe.fleet_case).assert_called_once()
    if mode == 'fleet':
        probe.http.close.assert_called_once()
