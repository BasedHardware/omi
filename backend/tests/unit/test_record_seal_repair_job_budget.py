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
