"""Malformed-row isolation, aggregate diagnostics and reviewed adapter changes."""

import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
import prometheus_client

from database import record_seal_worker as claims
from utils.batch_pipeline import record_seal_worker as worker
from tests.unit.test_record_seal_repair import source, PATH, JOB_PATH
from tests.unit.test_monitoring_adapter_hpa_contract import ADAPTER
from scripts.diff_prod_adapter import RECORD_SEAL_RULE, expected_config


@pytest.mark.parametrize(
    'identity',
    [{}, {'owner_id': 'bad/path', 'conversation_id': 'record'}, {'owner_id': 42, 'conversation_id': 'record'}],
)
def test_malformed_job_cannot_pin_discovery_or_claim(source, monkeypatch, identity):
    client = source[1]
    valid = client.rows[JOB_PATH]
    monkeypatch.setattr(
        claims,
        'pending_page',
        Mock(side_effect=[([('broken', identity)], ('cursor', 'broken')), ([('pending', valid)], None)]),
    )
    rows = [SimpleNamespace(reference=client.document('/'.join(PATH)), to_dict=lambda: client.rows[PATH])]
    scan_client = SimpleNamespace(collection=client.collection, get_all=lambda *a, **kw: rows)
    metrics = worker.Metrics('r', 'n')
    scanner = worker.Scanner(scan_client, 'batch_pipeline_dev', metrics)
    assert scanner.page() == ([], False)
    assert scanner.after == ('cursor', 'broken')
    assert scanner.page() == (['pending'], True)
    assert metrics.invalid._value.get() == 1
    assert metrics.backlog._value.get() == 1
    client.rows[(*JOB_PATH[:-1], 'broken')] = {'state': 'record_pending', **identity}
    assert claims.acquire(client, 'batch_pipeline_dev', 'broken') is None


@pytest.mark.parametrize('refusal', ['require_runtime', 'server_flags'])
def test_policy_refusal_exits_before_readiness_endpoint(monkeypatch, refusal):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'true')
    start = Mock()
    monkeypatch.setattr(prometheus_client, 'start_http_server', start)
    monkeypatch.setattr(worker.config, 'require_runtime', lambda: None)
    monkeypatch.setattr(worker.config, 'server_flags', lambda: {})
    monkeypatch.setattr(worker.config, refusal, Mock(side_effect=ValueError('private-provider-payload')))
    messages = []

    with pytest.raises(SystemExit) as exited:
        worker.run('r', 'n', pause=Mock(), emit=messages.append)
    assert exited.value.code == 1
    assert messages == [{'event': 'record_seal_worker', 'outcome': 'error', 'stage': 'policy'}]
    start.assert_not_called()


def test_kill_switch_off_serves_metrics_without_policy(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'false')
    server, thread = Mock(), Mock()
    monkeypatch.setattr(prometheus_client, 'start_http_server', Mock(return_value=(server, thread)))
    monkeypatch.setattr(worker.config, 'server_flags', Mock(side_effect=AssertionError('policy read')))

    def stop(_):
        raise SystemExit(0)

    with pytest.raises(SystemExit):
        worker.run('r', 'n', pause=stop)
    server.shutdown.assert_called_once()


def test_startup_client_failure_emits_only_aggregate_and_closes_server(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'true')
    server, thread = Mock(), Mock()
    monkeypatch.setattr(prometheus_client, 'start_http_server', Mock(return_value=(server, thread)))
    monkeypatch.setattr(worker.config, 'require_runtime', lambda: None)
    monkeypatch.setattr(worker.config, 'server_flags', lambda: {})
    import database._client

    monkeypatch.setattr(
        database._client, 'get_data_plane_firestore_client', Mock(side_effect=ValueError('private-provider-payload'))
    )
    messages = []

    def stop(_):
        raise SystemExit(0)

    with pytest.raises(SystemExit):
        worker.run('r', 'n', pause=stop, emit=messages.append)
    assert messages == [{'event': 'record_seal_worker', 'outcome': 'error', 'stage': 'startup'}]
    server.shutdown.assert_called_once()
    server.server_close.assert_called_once()
    thread.join.assert_called_once_with(timeout=5)


@pytest.mark.parametrize('claim', ['invalid', {'expires_at': 'invalid'}, {'retry_after': float('nan')}])
def test_malformed_claim_is_left_for_sweeper_without_pinning_page(claim):
    assert claims.ready(claim, 1000) is False


@pytest.mark.parametrize('change', ['missing', 'query', 'duplicate'])
def test_adapter_accepts_only_exact_seal_backlog_addition(change):
    rules = yaml.safe_load(ADAPTER.read_text())['rules']
    live = {'rules': rules['custom'], 'externalRules': rules['external']}
    altered = copy.deepcopy(live)
    if change == 'missing':
        altered['externalRules'].remove(RECORD_SEAL_RULE)
        assert expected_config(altered) == expected_config(live)
    else:
        altered['externalRules'].append(
            {**RECORD_SEAL_RULE, **({'metricsQuery': 'vector(0)'} if change == 'query' else {})}
        )
        with pytest.raises(ValueError, match='Unexpected live record seal rule'):
            expected_config(altered)
