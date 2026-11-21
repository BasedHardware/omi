"""Cron phase deadlines must not turn a truncated prepass into a failed shard."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
import signal
import sys

import pytest

from scripts import record_seal_repair_job as job
from utils import record_projection_rebuild as projection
from utils.batch_pipeline import record_seal_cluster_repair as cluster
from utils.batch_pipeline.record_seal_budget import BudgetExhausted


@pytest.fixture
def cron(monkeypatch):
    events = []
    monkeypatch.setattr(job, 'emit', lambda event: events.append(dict(event)))
    monkeypatch.setattr(job, 'configure_logging', lambda *a, **kw: None)
    monkeypatch.setattr(job, 'terminal_probe_totals', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(job, 'repair_probe_server', nullcontext)
    monkeypatch.setattr(cluster, 'silent_dependencies', nullcontext)
    monkeypatch.setattr(job, 'process_deadline', lambda *a: job.time.monotonic() + 120)
    monkeypatch.setattr(job, 'partition_arguments', lambda _: (0, 5))
    monkeypatch.setattr(sys, 'argv', ['record_seal_repair_job.py'])
    from prometheus_client import Counter
    from utils.observability import firestore_probe_export as export

    counter = Counter('omi_record_seal_repair_run_outcomes_total', 'test', ('outcome', 'phase'), registry=None)
    monkeypatch.setattr(export, 'REPAIR_RUN_OUTCOMES', counter)
    previous = signal.getsignal(signal.SIGTERM)
    yield events
    signal.signal(signal.SIGTERM, previous)


def test_local_projection_budget_escape_continues_seal_and_reports_truncation(cron, monkeypatch):
    seal = Mock(return_value={'event': 'record_seal_repair', 'outcome': 'ok', 'dispositions': {'sealed': 1}})

    def run(*, before, **kwargs):
        before()
        return seal()

    monkeypatch.setattr(cluster, 'run', run)
    monkeypatch.setattr(projection, 'run_job', Mock(side_effect=BudgetExhausted()))
    assert job.main() == 0
    seal.assert_called_once_with()
    assert cron[-1]['dispositions'] == {'sealed': 1}
    assert cron[-1]['projection_prepass_budget_exhausted'] == 1
    assert cron[-1]['projection_prepass']['outcome'] == 'budget_exhausted'


def test_all_five_partitions_seal_when_only_explicit_prepass_shard_exhausts(cron, monkeypatch):
    assert job.PROJECTION_PREPASS_SHARD == 0
    from database import _client
    from utils.batch_pipeline import record_seal_run_lease, record_seal_sweeper

    lease = Mock(acquire=Mock(return_value=True))
    monkeypatch.setattr(cluster.config, 'enabled', lambda: True)
    monkeypatch.setattr(cluster.config, 'settings', lambda: (8, 270, 1500, 'apply'))
    monkeypatch.setattr(cluster.config, 'require_runtime', lambda: None)
    monkeypatch.setattr(cluster.config, 'server_flags', lambda: {})
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: object())
    proof = Mock()
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: proof)
    custody_check = Mock()
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', custody_check)
    monkeypatch.setattr(record_seal_run_lease, 'RepairRunLease', lambda *a: lease)
    prepass = Mock(side_effect=BudgetExhausted())
    monkeypatch.setattr(projection, 'run_job', prepass)
    partition = [f'synthetic-{i}' for i in range(250)]
    sealed = []

    def seal_partition(*, shard, shards, **kwargs):
        owned = [cid for cid in partition if cluster.owns_record('synthetic', cid, shard=shard, shards=shards)]
        assert owned
        sealed.extend(owned)
        return {'event': 'record_seal_repair', 'outcome': 'ok', 'shard': shard, 'dispositions': {'sealed': len(owned)}}

    monkeypatch.setattr(cluster, '_run', seal_partition)
    for shard in range(5):
        monkeypatch.setattr(job, 'partition_arguments', lambda _, index=shard: (index, 5))
        assert job.main() == 0
    assert sorted(sealed) == sorted(partition) and len(set(sealed)) == 250
    prepass.assert_called_once()
    assert custody_check.call_count == lease.acquire.call_count == lease.release.call_count == 5
    summaries = [e for e in cron if e.get('event') == 'record_seal_repair']
    assert len(summaries) == 5
    assert summaries[0]['projection_prepass_budget_exhausted'] == 1
    assert all('projection_prepass' not in summary for summary in summaries[1:])
    assert [(s['run_outcome'], s['run_phase']) for s in summaries] == [
        ('incomplete', 'prepass'),
        *[('complete', 'overall')] * 4,
    ]
    from utils.observability import firestore_probe_export as export

    assert export.REPAIR_RUN_OUTCOMES.labels('incomplete', 'prepass')._value.get() == 1
    assert export.REPAIR_RUN_OUTCOMES.labels('complete', 'overall')._value.get() == 4


def test_real_prepass_exception_still_surfaces_as_error_and_seal_continues(cron, monkeypatch):
    monkeypatch.setattr(projection, 'run_job', Mock(side_effect=ValueError('private data must stay hidden')))
    monkeypatch.setattr(
        cluster, 'run', lambda *, before, **kw: (before(), {'event': 'record_seal_repair', 'outcome': 'ok'})[1]
    )
    assert job.main() == 0
    assert cron[0]['event'] == 'record_projection_rebuild' and cron[0]['outcome'] == 'error'
    assert cron[0]['exception_type'] == 'ValueError'
    assert 'private data' not in str(cron)
    assert cron[-1]['projection_prepass_budget_exhausted'] == 0


@pytest.mark.parametrize('exception,exit_code', [(BudgetExhausted(), 0), (SystemExit(1), 1), (RuntimeError(), 1)])
def test_overall_budget_stops_cleanly_but_shutdown_and_real_errors_fail(cron, monkeypatch, exception, exit_code):
    monkeypatch.setattr(cluster, 'run', Mock(side_effect=exception))
    assert job.main() == exit_code
    assert cron[-1]['outcome'] == ('budget_exhausted' if exit_code == 0 else 'error')
    if exit_code == 0:
        assert cron[-1]['work_incomplete'] is True
        assert 'dispositions' not in cron[-1]


def test_expired_outer_budget_is_not_swallowed_as_local_prepass(cron, monkeypatch):
    from utils.batch_pipeline import record_seal_budget

    checks = Mock(side_effect=[None, BudgetExhausted()])
    monkeypatch.setattr(record_seal_budget.SweepBudget, 'check', checks)
    monkeypatch.setattr(projection, 'run_job', Mock(side_effect=BudgetExhausted()))
    seal = Mock()

    def run(*, before, **kw):
        before()
        seal()

    monkeypatch.setattr(cluster, 'run', run)
    assert job.main() == 0
    seal.assert_not_called()
    assert cron[-1]['outcome'] == 'budget_exhausted'
    assert cron[-1]['work_incomplete'] is True


def test_partial_projection_counts_include_only_finished_markers(monkeypatch):
    from config import record_seal_repair as config
    from utils.batch_pipeline import record_seal_budget

    monkeypatch.setattr(config, 'enabled', lambda: True)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'apply'))
    monkeypatch.setattr(projection, 'durable_debt_enabled', lambda: True)
    now = [0]
    budget = record_seal_budget.SweepBudget(60, clock=lambda: now[0])
    monkeypatch.setattr(record_seal_budget, 'SweepBudget', lambda seconds: budget)
    docs = []
    for cid in ['a', 'b', 'c']:
        ref = Mock(update=Mock(return_value=SimpleNamespace(update_time='attempt')))
        docs.append(
            SimpleNamespace(
                id=projection.jobs.marker_id('u', cid),
                reference=ref,
                update_time='old',
                to_dict=lambda cid=cid: {'owner_id': 'u', 'conversation_id': cid, 'kind': projection.jobs.KIND},
            )
        )
    client = Mock()
    client.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = docs
    monkeypatch.setattr(projection, 'get_firestore_client', lambda: client)

    def rebuild(uid, cid):
        if cid == 'b':
            now[0] = 60
            raise BudgetExhausted()
        return True

    monkeypatch.setattr(projection, 'rebuild', rebuild)
    report = projection.run_job(seconds=60)
    assert report['outcome'] == 'budget_exhausted'
    assert report['dispositions'] == {'rebuilt': 1}
    assert report['attempted'] == 2 and report['interrupted'] == report['unattempted'] == 1
    docs[0].reference.delete.assert_called_once()
    docs[1].reference.delete.assert_not_called()
    docs[2].reference.update.assert_not_called()


def test_disabled_prepass_preserves_existing_disabled_exit_report(cron, monkeypatch):
    monkeypatch.setattr(
        projection, 'run_job', lambda **kwargs: {'event': 'record_projection_rebuild', 'outcome': 'disabled'}
    )
    monkeypatch.setattr(
        cluster, 'run', lambda *, before, **kw: (before(), {'event': 'record_seal_repair', 'outcome': 'disabled'})[1]
    )
    assert job.main() == 0
    assert len(cron) == 1 and cron[0]['outcome'] == 'disabled'
    assert cron[0]['run_outcome'] == 'complete' and cron[0]['run_phase'] == 'overall'


@pytest.mark.parametrize('phase', ['setup', 'prepass', 'discovery', 'rows', 'checkpoint', 'overall'])
def test_budget_terminal_phase_is_counted_once_and_matches_summary(cron, monkeypatch, phase):
    from utils.observability import firestore_probe_export as export

    def run(*, phase_progress, **kwargs):
        phase_progress(phase)
        raise BudgetExhausted()

    monkeypatch.setattr(cluster, 'run', run)
    assert job.main() == 0
    assert len(cron) == 1
    summary = cron[0]
    assert summary['repair_run_summary'] == 1
    assert (summary['run_outcome'], summary['run_phase'], summary['shard'], summary['shards']) == (
        'incomplete',
        phase,
        0,
        5,
    )
    assert summary['exit_code'] == 0 and 'dispositions' not in summary
    assert export.REPAIR_RUN_OUTCOMES.labels('incomplete', phase)._value.get() == 1


@pytest.mark.parametrize(
    'report,phase',
    [
        ({'cursor_checkpoint_outcome': 'budget_exhausted', 'work_incomplete': True}, 'checkpoint'),
        ({'dispositions': {'sealed': 1, 'budget_exhausted': 2}}, 'rows'),
        ({'dispositions': {'sealed': 1, 'deferred': 2}}, 'rows'),
        ({'outcome': 'overlap_refused'}, 'setup'),
    ],
)
def test_returned_incomplete_work_uses_primary_phase(cron, monkeypatch, report, phase):
    monkeypatch.setattr(cluster, 'run', lambda **kwargs: {'event': 'record_seal_repair', **report})
    assert job.main() == 0
    assert cron[-1]['run_outcome'] == 'incomplete' and cron[-1]['run_phase'] == phase


def test_outcome_is_served_by_repair_registry_with_only_bounded_labels(cron):
    import json
    from pathlib import Path
    from prometheus_client import CollectorRegistry, generate_latest
    from utils.observability import firestore_probe_export as export

    for outcome, phase in [('complete', 'overall'), ('incomplete', 'prepass')]:
        export.record_repair_run_outcome(outcome, phase)
    registry = CollectorRegistry()
    export.register_probe_collectors(registry, repair_age=True)
    rendered = generate_latest(registry).decode()
    assert 'omi_record_seal_repair_run_outcomes_total{outcome="incomplete",phase="prepass"} 1.0' in rendered
    samples = [s for f in export.REPAIR_RUN_OUTCOMES.collect() for s in f.samples if s.name.endswith('_total')]
    assert all(set(s.labels) == {'outcome', 'phase'} for s in samples)
    for labels in [('unknown', 'overall'), ('incomplete', 'uid-or-shard')]:
        with pytest.raises(ValueError):
            export.record_repair_run_outcome(*labels)
    inventory = json.loads(
        (Path(__file__).resolve().parents[2] / 'charts/monitoring/metric-inventory.prod.json').read_text()
    )
    assert 'omi_record_seal_repair_run_outcomes_total' in inventory['declared_metrics']


@pytest.mark.parametrize('exception,exit_code', [(BudgetExhausted(), 0), (RuntimeError(), 1)])
def test_row_child_escape_does_not_count_a_coordinator_run(cron, monkeypatch, exception, exit_code):
    import io
    from utils.observability import firestore_probe_export as export

    monkeypatch.setattr(sys, 'argv', ['record_seal_repair_job.py', '--row'])
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'{}')))
    monkeypatch.setattr(cluster, 'row_main', Mock(side_effect=exception))
    assert job.main() == exit_code
    assert not any(row.get('repair_run_summary') for row in cron)
    assert not [s for f in export.REPAIR_RUN_OUTCOMES.collect() for s in f.samples]


def test_repair_outcome_labels_use_reason_enum_members(cron, monkeypatch):
    from utils.observability import firestore_probe_export as export
    from utils.observability.reasons import ReasonFamily, RecordSealRepairRunOutcome, RecordSealRepairRunStage

    label = Mock(wraps=export.reason_label)
    monkeypatch.setattr(export, 'reason_label', label)
    export.record_repair_run_outcome('incomplete', 'prepass')
    assert label.call_args_list[0].args == (
        ReasonFamily.RECORD_SEAL_REPAIR,
        RecordSealRepairRunOutcome.INCOMPLETE,
        RecordSealRepairRunOutcome,
    )
    assert label.call_args_list[1].args == (
        ReasonFamily.RECORD_SEAL_REPAIR,
        RecordSealRepairRunStage.PREPASS,
        RecordSealRepairRunStage,
    )
    assert export.REPAIR_RUN_PHASES == {'prepass', 'setup', 'discovery', 'rows', 'checkpoint', 'overall'}
    assert export.REPAIR_RUN_OUTCOME_VALUES == {'complete', 'incomplete'}
    for outcome, phase in [('unknown', 'overall'), ('complete', 'unknown')]:
        with pytest.raises(ValueError):
            export.record_repair_run_outcome(outcome, phase)
    assert label.call_count == 2
