"""Sweep deadlines, aggregate progress and plain-read production adapter."""

from copy import deepcopy
import importlib.util
import json
import logging
from pathlib import Path
import signal
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from config import record_seal_sweeper as config
from tests.unit.test_record_seal_repair import source, PATH, JOB_PATH
from tests.unit.test_record_seal_sweeper import proof
from tests.unit.test_record_seal_sweeper_deploy import render
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument
from utils.batch_pipeline import record_seal_repair as repair
from utils.batch_pipeline import record_seal_sweeper as sweeper
from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget


def eligible(source):
    source[1].rows[PATH]['record_upload_sessions'] = {'private-token': {'pod': 'old', 'process_started_at': 900}}


def run(source, proof, **kwargs):
    return sweeper.sweep(source[0], object(), source[2], inventory=proof, discover=lambda *_: ['pending'], **kwargs)


@pytest.mark.parametrize('phase', ['inventory', 'discovery', 'classification', 'plan'])
def test_expiry_in_each_read_phase_never_applies(source, proof, monkeypatch, phase):
    eligible(source)
    clock = [0.0]
    budget = SweepBudget(150, clock=lambda: clock[0])
    events = []

    def progress(event):
        events.append(event)
        if event['phase'] == phase:
            clock[0] = 150

    apply = Mock()
    monkeypatch.setattr(repair, 'apply_seals', apply)
    result = run(source, proof, budget=budget, progress=progress)
    assert result['outcome'] == 'budget_exhausted'
    assert events[-1]['elapsed_ms'] == 150000
    assert result['discovered'] == int(phase != 'inventory')
    assert result['classified'] == int(phase in {'classification', 'plan'})
    apply.assert_not_called()
    assert not any(tx.updates for tx in source[1].transactions)


def test_deadline_inside_tail_iterator_is_not_a_proof_refusal(source, proof, monkeypatch):
    eligible(source)
    closed = Mock()

    def stalled(*_, **kwargs):
        try:
            signal.raise_signal(signal.SIGALRM)
            yield None
        finally:
            closed()

    monkeypatch.setattr(repair, 'retained_record_units', stalled)
    result = run(source, proof, interrupt_io=True)
    assert result['outcome'] == 'budget_exhausted'
    assert result['candidates'] == result['classified'] == 1
    closed.assert_called_once()
    assert not any(tx.updates for tx in source[1].transactions)


def test_real_timer_interrupts_blocking_io_and_restores_handler():
    previous = signal.getsignal(signal.SIGALRM)
    budget = SweepBudget(0.01)
    with pytest.raises(BudgetExhausted):
        with budget.interrupt_io():
            time.sleep(1)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_budget_between_seals_preserves_completed_counts_and_skips_rest(source, proof, monkeypatch):
    eligible(source)
    source[1].rows[('batch_pipeline_dev_jobs', 'second')] = deepcopy(source[1].rows[JOB_PATH])
    source[1].rows[('users', 'synthetic', 'conversations', 'second')] = deepcopy(source[1].rows[PATH])
    source[1].rows[('batch_pipeline_dev_jobs', 'second')]['conversation_id'] = 'second'
    monkeypatch.setattr(repair, 'assert_batch_write_allowed', lambda *a, **kw: None)
    clock = [0.0]
    original = repair.run_transactional

    def first_commit(*a, **kw):
        result = original(*a, **kw)
        clock[0] = 150
        return result

    monkeypatch.setattr(repair, 'run_transactional', first_commit)
    report = sweeper.sweep(
        source[0],
        object(),
        source[2],
        inventory=proof,
        discover=lambda *_: ['pending', 'second'],
        budget=SweepBudget(150, clock=lambda: clock[0]),
    )
    assert report['outcome'] == 'budget_exhausted'
    assert report['dispositions'] == {'sealed': 1}
    assert source[1].rows[PATH]['record_audio_closed'] is True
    assert not source[1].rows[('users', 'synthetic', 'conversations', 'second')].get('record_audio_closed')


def test_expiry_in_privacy_read_prevents_transaction_patch(source, proof, monkeypatch):
    eligible(source)
    clock = [0.0]
    monkeypatch.setattr(repair, 'assert_batch_write_allowed', lambda *a, **kw: clock.__setitem__(0, 150))
    result = run(source, proof, budget=SweepBudget(150, clock=lambda: clock[0]))
    assert result['outcome'] == 'budget_exhausted'
    assert not any(tx.updates for tx in source[1].transactions)


def test_phase_logs_are_content_free_and_keep_one_final_summary(source, proof, monkeypatch, capsys):
    eligible(source)
    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_sweep.py'
    spec = importlib.util.spec_from_file_location('sweep_budget_cli', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(sweeper, 'run', lambda **kw: run(source, proof, **kw))
    assert cli.main() == 0
    captured = capsys.readouterr()
    payloads = [json.loads(json.loads(line)['message']) for line in captured.out.splitlines()]
    assert [p['phase'] for p in payloads[:-1]] == ['inventory', 'discovery', 'classification', 'plan', 'apply']
    assert payloads[-1]['event'] == 'record_seal_sweep'
    assert all(
        set(p) == {'event', 'phase', 'elapsed_ms', 'discovered', 'classified', 'candidates'} for p in payloads[:-1]
    )
    assert captured.err == ''
    assert not any(
        s in captured.out for s in ['synthetic', 'private-token', 'pending', 'users/', '"old"', 'record_content_id']
    )


def test_emitting_aggregate_never_enables_concurrent_dependency_diagnostics(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[2] / 'scripts/record_seal_sweep.py'
    spec = importlib.util.spec_from_file_location('sweep_logging_window', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    logger = logging.getLogger('record-seal-sweeper')
    original = logger.handle

    def concurrent(record):
        logging.getLogger('synthetic-sdk').error('private-owner/private-job user@example.invalid')
        original(record)

    monkeypatch.setattr(logger, 'handle', concurrent)
    cli.emit_progress({'event': 'record_seal_sweep_phase', 'phase': 'inventory', 'elapsed_ms': 0})
    assert logging.root.manager.disable == logging.CRITICAL
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1 and captured.err == ''
    assert 'private-owner' not in captured.out and 'example.invalid' not in captured.out


def test_plain_reads_use_no_transactions_and_bound_each_rpc():
    ref = Mock()
    ref.get.return_value.to_dict.return_value = {'state': 'record_pending'}
    client = Mock()
    client.collection.return_value.document.return_value = ref
    ref.collection.return_value.document.return_value = ref
    read = sweeper.SweepReadStore(SimpleNamespace(client=client, namespace='batch_pipeline_prod'), SweepBudget(150))
    assert read.run(lambda tx: tx.get('jobs', 'private-job')) == {'state': 'record_pending'}
    read.run(lambda tx: tx.get('conversations', 'private-owner/private-conversation'))
    assert ref.get.call_count == 2
    assert all(c.kwargs == {'timeout': 10.0, 'retry': None} for c in ref.get.call_args_list)
    client.transaction.assert_not_called()


def test_runtime_composition_uses_plain_reads_and_keeps_the_seal_transaction(source, proof, monkeypatch):
    # Artifact authorization is the shared mocked fixture; measure the two
    # classification/planning passes and the unchanged seal transaction here.
    eligible(source)
    original = StrictFirestoreDocument.get
    plain_reads = []

    def read(ref, *args, **kwargs):
        if 'retry' in kwargs:
            assert kwargs.pop('retry') is None
            assert 0 < kwargs.pop('timeout') <= 10
            plain_reads.append(ref.path)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', read)
    monkeypatch.setattr(sweeper, 'create_storage_client', lambda: object())
    monkeypatch.setattr(sweeper, 'artifacts_for', lambda _: source[2])
    discover = Mock(return_value=['pending'])
    monkeypatch.setattr(sweeper, 'discover_pending', discover)
    result = run(source, proof, runtime_reads=True)
    assert result['outcome'] == 'ok' and result['dispositions'] == {'sealed': 1}
    assert plain_reads == [JOB_PATH, PATH, JOB_PATH, PATH]
    assert len(source[1].transactions) == 1
    assert source[1].transactions[0].updates == [(PATH, {'record_audio_closed': True, 'record_upload_sessions': {}})]
    assert discover.call_args.kwargs['limit'] == sweeper.DISCOVERY_LIMIT
    assert isinstance(discover.call_args.kwargs['budget'], SweepBudget)


def test_phase_timings_identify_serial_tail_cost(source, proof, monkeypatch):
    eligible(source)
    clock = [0.0]
    original = source[0].run

    def read(body):
        clock[0] += 1
        return original(body)

    def tail(*_, **kwargs):
        clock[0] += 20
        yield (100, 2, [{'generation': 1, 'pcm_sha256': 'proof'}])

    monkeypatch.setattr(source[0], 'run', read)
    monkeypatch.setattr(repair, 'retained_record_units', tail)
    events = []
    assert (
        run(source, proof, mode='plan', budget=SweepBudget(150, clock=lambda: clock[0]), progress=events.append)[
            'outcome'
        ]
        == 'ok'
    )
    elapsed = {e['phase']: e['elapsed_ms'] for e in events}
    assert elapsed['classification'] == 2000
    # One final-chunk precheck plus the unchanged full retained proof.
    assert elapsed['plan'] - elapsed['classification'] == 42000


@pytest.mark.parametrize('value', ['nan', 'inf', '0', '181', 'private-invalid'])
def test_invalid_budget_refused(value, monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_BUDGET_SECONDS', value)
    with pytest.raises(ValueError):
        config.budget_seconds()


def test_runtime_defaults_and_hard_limits(monkeypatch):
    assert config.budget_seconds() == 150
    assert config.limits() == (32, 4)
    monkeypatch.setenv('RECORD_SEAL_SWEEPER_SEAL_LIMIT', '65')
    with pytest.raises(ValueError):
        config.limits()


def test_rendered_job_budget_keeps_deadline_and_concurrency_guards():
    rendered = render()
    assert rendered.returncode == 0
    cron = next(
        doc
        for doc in yaml.safe_load_all(rendered.stdout)
        if doc and doc['kind'] == 'CronJob' and doc['metadata']['name'] == 'record-seal-sweeper'
    )
    spec = cron['spec']['jobTemplate']['spec']
    env = {item['name']: item.get('value') for item in spec['template']['spec']['containers'][0]['env']}
    assert float(env['RECORD_SEAL_SWEEPER_BUDGET_SECONDS']) == 150 < spec['activeDeadlineSeconds'] == 240 < 300
    assert env['RECORD_SEAL_SWEEPER_DISCOVERY_LIMIT'] == '32'
    assert env['RECORD_SEAL_SWEEPER_SEAL_LIMIT'] == '4'
    assert spec['backoffLimit'] == 0 and cron['spec']['concurrencyPolicy'] == 'Forbid'
