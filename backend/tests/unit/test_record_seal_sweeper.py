"""Hermetic sweeper: real repair transactions, fake pod inventory and bounded IO."""

from datetime import datetime, timezone
import builtins
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from tests.unit.test_record_seal_repair import source, PATH, JOB_PATH  # shared strict Firestore fixture
from tests.unit.test_record_producer_proof import inventory, pod
from utils.batch_pipeline import record_seal_repair as repair
from utils.batch_pipeline import record_seal_sweeper as sweeper
from utils.batch_pipeline import record_producer_proof as proof_module


@pytest.fixture
def proof(monkeypatch):
    monkeypatch.setattr(sweeper.time, 'time', lambda: 1000)

    def build(items=()):
        return proof_module.parse_pusher_pod_proof(
            json.dumps(inventory(list(items))).encode(), datetime.fromtimestamp(999, timezone.utc).isoformat()
        )

    return build


def run(source, proof):
    store, _, artifacts = source
    return sweeper.sweep(store, object(), artifacts, inventory=lambda: proof, discover=lambda *_: ['pending'])


@pytest.mark.parametrize(
    'pods,sealed',
    [
        ([], True),
        ([pod('old', 950)], True),
        ([pod('old', 800)], False),
        ([pod('old', 902)], False),
        ([pod('old', 950, extra_start=800)], False),
    ],
)
def test_live_pod_or_mixed_sidecar_token_is_never_cleared(source, proof, pods, sealed):
    client = source[1]
    tokens = {'token': {'pod': 'old', 'process_started_at': 900}}
    client.rows[PATH]['record_upload_sessions'] = tokens
    report = run(source, proof(pods))
    assert report['outcome'] == 'ok'
    assert client.rows[PATH]['record_upload_sessions'] == ({} if sealed else tokens)
    assert bool(client.rows[PATH].get('record_audio_closed')) == sealed
    if not sealed:
        assert report['dispositions'] == {'upload_pending': 1}
        assert not any(tx.updates for tx in client.transactions)


def test_stale_inventory_refuses_before_any_discovery_or_writes(source, proof):
    snapshot = proof()
    snapshot['captured_at'] = 699
    report = run(source, snapshot)
    assert report['outcome'] == 'error'
    assert not source[1].transactions


def test_api_error_refuses_without_discovery(source):
    discover = Mock()
    report = sweeper.sweep(
        *[source[0], object(), source[2]], inventory=Mock(side_effect=OSError('private')), discover=discover
    )
    assert report['outcome'] == 'error'
    discover.assert_not_called()
    assert not source[1].transactions


def test_inventory_expiring_during_tail_reads_refuses_apply(source, proof, monkeypatch):
    source[1].rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'old', 'process_started_at': 900}}
    original = repair.plan_seals

    def delayed(*args, **kwargs):
        plan = original(*args, **kwargs)
        monkeypatch.setattr(sweeper.time, 'time', lambda: 1400)
        return plan

    monkeypatch.setattr(repair, 'plan_seals', delayed)
    report = run(source, proof())
    assert report['outcome'] == 'error'
    assert not any(tx.updates for tx in source[1].transactions)


@pytest.mark.parametrize(
    'tokens,failed,disposition',
    [
        ({'bare': True}, False, 'bare_token'),
        ({}, False, 'no_tokens'),
        ({'token': {'pod': 'old', 'process_started_at': 900}}, True, 'upload_failed'),
    ],
)
def test_skips_bare_tokenless_and_upload_failed_rows(source, proof, tokens, failed, disposition):
    source[1].rows[PATH].update(record_upload_sessions=tokens, record_upload_failed=failed)
    report = run(source, proof())
    assert report['dispositions'] == {disposition: 1}
    assert report['bare_token_skips'] == int(disposition == 'bare_token')
    assert source[1].rows[PATH]['record_upload_sessions'] == tokens
    assert source[1].rows[PATH]['record_upload_failed'] == failed
    assert not any(tx.updates for tx in source[1].transactions)


def test_plan_read_error_aborts_all_seals(source, proof, monkeypatch):
    source[1].rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'old', 'process_started_at': 900}}
    monkeypatch.setattr(repair, 'list_audio_chunks', Mock(side_effect=OSError('sensitive/object')))
    assert run(source, proof())['outcome'] == 'read_error'
    assert not any(tx.updates for tx in source[1].transactions)


def test_row_read_error_aborts_before_plan(source, proof, monkeypatch):
    monkeypatch.setattr(source[0], 'run', Mock(side_effect=OSError('sensitive')))
    assert run(source, proof())['outcome'] == 'error'
    assert not source[1].transactions


def test_discovery_and_seal_caps_are_hard(proof, monkeypatch):
    job = {'state': 'record_pending', 'owner_id': 'synthetic', 'conversation_id': 'record'}
    row = {'record_upload_sessions': {'token': {'pod': 'old', 'process_started_at': 900}}}
    tx = SimpleNamespace(get=lambda table, _: job if table == 'jobs' else row)
    store = SimpleNamespace(run=lambda body: body(tx), client=object(), namespace='batch_pipeline_prod')
    plan = Mock(return_value={'entries': [], 'plan_sha256': 'digest'})
    apply = Mock(return_value={'sealed': 64})
    monkeypatch.setattr(repair, 'plan_seals', plan)
    monkeypatch.setattr(repair, 'apply_seals', apply)
    report = sweeper.sweep(
        store, object(), object(), inventory=proof, discover=lambda *_: [f'job-{n}' for n in range(128)]
    )
    assert report['discovered'] == report['backlog'] == 128
    assert report['discovery_saturated'] is True
    assert report['dispositions'] == {'seal_cap': 64, 'sealed': 64}
    assert len(plan.call_args.args[1]) == 64
    assert plan.call_args.kwargs['producer_proof']['resource_version'] == '1'
    report = sweeper.sweep(
        store, object(), object(), inventory=proof, discover=lambda *_: [f'job-{n}' for n in range(129)]
    )
    assert report['outcome'] == 'error'
    assert plan.call_count == apply.call_count == 1


def test_discovery_query_is_bounded_and_uses_existing_index():
    query = Mock()
    query.where.return_value = query.order_by.return_value = query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id='pending')]
    store = SimpleNamespace(
        client=SimpleNamespace(collection=Mock(return_value=query)), namespace='batch_pipeline_prod'
    )
    assert sweeper.discover_pending(store.client, store.namespace) == ['pending']
    store.client.collection.assert_called_once_with('batch_pipeline_prod_jobs')
    query.limit.assert_called_once_with(128)
    query.order_by.assert_called_once_with('available_at')
    assert query.where.call_args.kwargs['filter'].value == 'record_pending'


@pytest.mark.parametrize(
    'change', [{'metadata': {'resourceVersion': '1', 'continue': 'next'}}, {'metadata': {}}, {'items': None}]
)
def test_partial_or_malformed_inventory_refuses(proof, change):
    raw = {**inventory([]), **change}
    with pytest.raises(ValueError):
        proof_module.parse_pusher_pod_proof(
            json.dumps(raw).encode(), datetime.fromtimestamp(999, timezone.utc).isoformat()
        )


def test_tls_api_read_is_scoped_and_does_not_persist_inventory(proof, monkeypatch, tmp_path):
    (tmp_path / 'token').write_text('synthetic-token')
    (tmp_path / 'namespace').write_text('prod-omi-backend')
    monkeypatch.setattr(sweeper, 'SERVICE_ACCOUNT_PATH', tmp_path)
    monkeypatch.setattr(sweeper, 'datetime', SimpleNamespace(now=lambda _: datetime.fromtimestamp(999, timezone.utc)))
    context = Mock()
    monkeypatch.setattr(sweeper.ssl, 'create_default_context', Mock(return_value=context))
    response = Mock()
    response.read.return_value = json.dumps(inventory([])).encode()
    opener = Mock(return_value=SimpleNamespace(__enter__=lambda _: response, __exit__=lambda *args: False))
    # MagicMock owns context-manager special methods on its type.
    opener.return_value = MagicMock()
    opener.return_value.__enter__.return_value = response
    monkeypatch.setattr(sweeper, 'urlopen', opener)
    assert sweeper.read_pusher_pod_proof()['pods'] == {}
    request = opener.call_args.args[0]
    assert request.full_url == 'https://kubernetes.default.svc' + sweeper.POD_LIST_PATH
    assert opener.call_args.kwargs == {'context': context, 'timeout': 15}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['namespace', 'token']


def test_runtime_kill_switch_precedes_cloud_io(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_ENABLED', 'false')
    reader = Mock()
    monkeypatch.setattr(sweeper, 'read_pusher_pod_proof', reader)
    assert sweeper.run() == {'event': 'record_seal_sweep', 'outcome': 'disabled'}
    reader.assert_not_called()


def test_plan_mode_runs_full_proof_without_writes(source, proof, monkeypatch):
    source[1].rows[PATH]['record_upload_sessions'] = {'token': {'pod': 'old', 'process_started_at': 900}}
    apply = Mock()
    monkeypatch.setattr(repair, 'apply_seals', apply)
    report = sweeper.sweep(
        source[0], object(), source[2], inventory=proof, discover=lambda *_: ['pending'], mode='plan'
    )
    assert report['outcome'] == 'ok' and report['mode'] == 'plan'
    assert report['dispositions'] == {'eligible': 1}
    apply.assert_not_called()
    assert not any(tx.updates for tx in source[1].transactions)


def test_oldest_age_threshold_is_exact(source, proof, monkeypatch):
    source[1].rows[PATH]['finished_at'] = datetime.fromtimestamp(1000 - 14400, timezone.utc)
    assert run(source, proof())['oldest_unsealed_over_four_hours'] is False
    source[1].rows[PATH]['finished_at'] = datetime.fromtimestamp(1000 - 14401, timezone.utc)
    assert run(source, proof())['oldest_unsealed_over_four_hours'] is True


@pytest.mark.parametrize('emulator,stage', [(True, 'prod'), (False, 'dev'), (False, '')])
def test_runtime_refuses_outside_approved_stage(monkeypatch, emulator, stage):
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_ENABLED', 'true')
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    if emulator:
        monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', 'localhost:8080')
    reader = Mock()
    monkeypatch.setattr(sweeper, 'read_pusher_pod_proof', reader)
    with pytest.raises(ValueError):
        sweeper.run()
    reader.assert_not_called()


def test_invalid_mode_refuses_before_inventory(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_ENABLED', 'true')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_MODE', 'other')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    reader = Mock()
    monkeypatch.setattr(sweeper, 'read_pusher_pod_proof', reader)
    with pytest.raises(ValueError, match='invalid sweep mode'):
        sweeper.run()
    reader.assert_not_called()


def test_one_nested_structured_log_and_no_error_payload(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_sweep.py'
    spec = importlib.util.spec_from_file_location('sweeper_cli', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(
        sweeper,
        'run',
        Mock(side_effect=OSError('AbC0123456789abcdefghijkLMNOP user@example.invalid object/private/job')),
    )
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    assert cli.main() == 1
    out = capsys.readouterr()
    assert out.err == ''
    lines = out.out.splitlines()
    assert len(lines) == 1
    outer = json.loads(lines[0])
    assert outer['severity'] == 'ERROR'
    assert outer['logger'] == 'record-seal-sweeper'
    assert json.loads(outer['message']) == {'event': 'record_seal_sweep', 'outcome': 'error'}
    assert 'example.invalid' not in out.out and 'object/private' not in out.out and 'AbC012' not in out.out


def test_cli_import_failure_emits_only_generic_summary(monkeypatch, capsys):
    original_import = builtins.__import__

    def fail_import(name, *args, **kwargs):
        if name == 'utils.batch_pipeline':
            raise ImportError('private/object user@example.invalid AbC0123456789abcdefghijkLMNOP')
        return original_import(name, *args, **kwargs)

    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_sweep.py'
    spec = importlib.util.spec_from_file_location('sweeper_import_failure', path)
    cli = importlib.util.module_from_spec(spec)
    monkeypatch.setenv('OMI_LOG_FORMAT', 'json')
    with monkeypatch.context() as patcher:
        patcher.setattr(builtins, '__import__', fail_import)
        spec.loader.exec_module(cli)
    assert cli.main() == 1
    out = capsys.readouterr()
    assert out.err == '' and len(out.out.splitlines()) == 1
    assert json.loads(json.loads(out.out)['message']) == {'event': 'record_seal_sweep', 'outcome': 'error'}
    assert 'example.invalid' not in out.out and 'private/object' not in out.out and 'AbC012' not in out.out
