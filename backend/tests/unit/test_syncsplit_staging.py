"""The staging kit refuses production/default bindings before any client IO."""

import json
import logging
import httpx
import pytest

from scripts.staging import syncsplit as kit
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
