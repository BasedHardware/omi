"""Hermetic worker contracts; synthetic identities, no cloud clients/credentials."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prometheus_client import generate_latest

from database import record_seal_worker as claims
from utils.batch_pipeline import record_seal_worker as worker
from utils.batch_pipeline import record_seal_repair as repair
from tests.unit.test_record_seal_repair import source, plan, PATH, JOB_PATH, FINISH


@pytest.fixture
def claimed(source):
    client = source[1]
    claim = claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 100)
    assert claim is not None
    return client, claim


def test_claim_expires_and_stale_release_cannot_clear_replacement(claimed):
    client, old = claimed
    assert claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 459.9) is None
    new = claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 460)
    assert new and new['token'] != old['token']
    assert not claims.release(client, 'batch_pipeline_dev', old, clock=lambda: 461)
    assert client.rows[JOB_PATH]['seal_claim']['token'] == new['token']
    assert claims.release(client, 'batch_pipeline_dev', new, clock=lambda: 462)
    assert claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 463) is None
    assert claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 4062)
    assert not client.rows[PATH].get('record_audio_closed')


def test_reclaim_invalidates_older_canonical_plan(source, claimed):
    client, _ = claimed
    approval = plan(source)
    assert claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 461)
    assert repair.apply_seals(source[0], approval, approval['plan_sha256']) == {'state_changed': 1}
    assert not client.rows[PATH].get('record_audio_closed')


def test_concurrent_apply_has_exactly_one_seal(source, monkeypatch):
    approval = plan(source)
    client = source[1]
    original = repair.run_transactional

    def serializable(client, fn, **kwargs):
        # StrictFirestore guards read-before-write. This boundary lock models
        # serializable commit, not SDK retry/contention (staging owns that gate).
        with client.lock:
            return original(client, fn, **kwargs)

    monkeypatch.setattr(repair, 'run_transactional', serializable)
    barrier = Barrier(2)

    def apply():
        barrier.wait(timeout=5)
        return repair.apply_seals(source[0], approval, approval['plan_sha256'])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(), range(2)))
    assert sorted(results, key=str) == sorted([{'sealed': 1}, {'state_changed': 1}], key=str)
    assert sum(path == PATH for tx in client.transactions for path, _ in tx.updates) == 1


def test_concurrent_claim_has_one_owner(source, monkeypatch):
    client = source[1]
    original = claims.run_transactional

    def serializable(client, fn, **kwargs):
        with client.lock:
            return original(client, fn, **kwargs)

    monkeypatch.setattr(claims, 'run_transactional', serializable)
    barrier = Barrier(2)

    def acquire():
        barrier.wait(timeout=5)
        return claims.acquire(client, 'batch_pipeline_dev', 'pending', clock=lambda: 100)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acquire(), range(2)))
    assert sum(result is not None for result in results) == 1


class Process:
    def __init__(self, disposition=None):
        self.returncode = 0 if disposition else None
        self.stdout = io.BytesIO(json.dumps({'disposition': disposition}).encode())
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True

    def wait(self):
        assert self.killed


def slot(source, monkeypatch, process):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'true')
    metrics = worker.Metrics('synthetic-release', 'synthetic-namespace')
    launch = Mock(return_value=process)
    instance = worker.Worker(source[1], 'batch_pipeline_dev', metrics, launch=launch, clock=lambda: 10)
    instance.scan_at = float('inf')
    instance.pending.append('pending')
    instance.tick()
    launch.assert_called_once_with(PATH, 270, 'apply')
    return instance, metrics


def test_termination_reaps_before_release_and_preserves_audio(source, monkeypatch):
    process = Process()
    instance, _ = slot(source, monkeypatch, process)
    release = claims.release

    def after_reap(*a, **kw):
        assert process.killed and process.stdout.closed
        return release(*a, **kw)

    monkeypatch.setattr(claims, 'release', after_reap)
    instance.close()
    assert instance.active is None
    assert not source[1].rows[PATH].get('record_audio_closed')


def test_budget_exhaustion_advances_to_other_rows_and_backs_off(source, monkeypatch):
    process = Process()
    instance, metrics = slot(source, monkeypatch, process)
    next_path = (*PATH[:-1], 'next')
    source[1].rows[next_path] = dict(source[1].rows[PATH])
    source[1].rows[(*JOB_PATH[:-1], 'next')] = {**source[1].rows[JOB_PATH], 'conversation_id': 'next', 'seal_claim': {}}
    instance.pending.extend(['pending', 'next'])
    instance.clock = lambda: 281
    instance.tick()
    assert process.killed
    assert instance.active[2]['job_id'] == 'next'
    assert instance.launch.call_count == 2
    assert instance.launch.call_args.args == (next_path, 270, 'apply')
    assert b'disposition="budget_exhausted"' in generate_latest(metrics.registry)
    instance.close()


@pytest.mark.parametrize('disposition', ['privacy_refused', 'upload_pending', 'proof_refused', 'budget_exhausted'])
def test_refusals_leave_audio_for_sweeper_with_backoff(source, monkeypatch, disposition):
    process = Process(disposition)
    instance, _ = slot(source, monkeypatch, process)
    instance.tick()
    assert not source[1].rows[PATH].get('record_audio_closed')
    assert source[1].rows[JOB_PATH]['seal_claim']['retry_after'] > worker.time.time()
    assert instance.active is None
    assert instance.launch.call_count == 1


def test_kill_switch_idles_without_discovery_or_claims(source, monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'false')
    instance = worker.Worker(source[1], 'batch_pipeline_dev', worker.Metrics('r', 'n'))
    instance.scanner = Mock()
    monkeypatch.setattr(claims, 'acquire', Mock(side_effect=AssertionError('must idle')))
    instance.tick()
    instance.scanner.page.assert_not_called()


def test_switch_off_during_walk_reaps_and_stops_further_claims(source, monkeypatch):
    process = Process()
    instance, _ = slot(source, monkeypatch, process)
    monkeypatch.setenv('RECORD_SEAL_REPAIR_ENABLED', 'false')
    instance.tick()
    assert process.killed and instance.active is None


def test_backlog_sampling_continues_while_child_walks(source, monkeypatch):
    process = Process()
    instance, _ = slot(source, monkeypatch, process)
    instance.scanner = Mock()
    instance.scanner.page.return_value = ([], True)
    instance.scan_at = 0
    instance.tick()
    instance.scanner.page.assert_called_once_with(candidates=False)
    assert instance.active and not process.killed
    instance.close()


@pytest.mark.parametrize(
    'patch', [{'record_audio_closed': True}, {'record_audio_partial': True}, {'status': 'processing'}]
)
def test_claim_rechecks_discovery_hint_before_walking(source, patch):
    source[1].rows[PATH].update(patch)
    assert claims.acquire(source[1], 'batch_pipeline_dev', 'pending') is None
    assert 'seal_claim' not in source[1].rows[JOB_PATH]


def test_private_child_output_cannot_become_a_metric_label():
    process = Process('private-unrecognized-output')
    assert worker.row_result(process) == 'error'


def test_backlog_complete_sample_includes_claimed_and_backoff_but_not_closed_partial(monkeypatch):
    now = worker.time.time()
    jobs = [
        (name, {'owner_id': 'synthetic', 'conversation_id': name, 'seal_claim': claim})
        for name, claim in [
            ('open', {}),
            ('claimed', {'expires_at': now + 360}),
            ('deferred', {'retry_after': now + 3600}),
            ('closed', {}),
            ('partial', {}),
        ]
    ]
    rows = {
        name: {'status': 'completed', 'record_lane_owner': 'batch_live_v1', 'finished_at': FINISH} for name, _ in jobs
    }
    rows['closed']['record_audio_closed'] = True
    rows['partial']['record_audio_partial'] = True
    monkeypatch.setattr(claims, 'pending_page', Mock(side_effect=[(jobs[:2], ('cursor', 'c')), (jobs[2:], None)]))
    monkeypatch.setattr(claims, 'conversation_ref', lambda _, job: SimpleNamespace(path=job['conversation_id']))
    client = Mock()
    client.get_all.side_effect = lambda refs, **_: [
        SimpleNamespace(reference=ref, to_dict=lambda ref=ref: rows[ref.path]) for ref in reversed(refs)
    ]
    metrics = worker.Metrics('r', 'n')
    scanner = worker.Scanner(client, 'batch_pipeline_dev', metrics)
    assert scanner.page() == (['open'], False)
    assert metrics.fresh._value.get() == 0
    assert metrics.backlog._value.get() != metrics.backlog._value.get()  # NaN until complete.
    assert scanner.page() == ([], True)
    assert metrics.backlog._value.get() == 3
    assert metrics.oldest._value.get() >= now - FINISH.timestamp()
    fresh = metrics.fresh._value.get()
    monkeypatch.setattr(claims, 'pending_page', Mock(side_effect=RuntimeError('private error')))
    with pytest.raises(RuntimeError):
        scanner.page()
    assert metrics.fresh._value.get() == fresh
    metrics.outcome('sealed', 1800)
    assert b'omi_record_seal_sealed_total{namespace="n",worker_release="r"} 1.0' in generate_latest(metrics.registry)


def test_pending_query_oldest_first_keyset_survives_removed_cursor():
    # Exercise the production query builder against ordered synthetic snapshots;
    # this tests query operands, not Firestore's service-side index planner.
    calls = []
    later = datetime.fromtimestamp(103, timezone.utc)
    data = [('c', FINISH), ('a', later), ('b', FINISH)]

    class Query:
        def __init__(self):
            self.after, self.size = None, 64

        def where(self, *, filter):
            calls.append(('where', filter.field_path, filter.op_string, filter.value))
            return self

        def order_by(self, field):
            calls.append(('order', field))
            return self

        def select(self, fields):
            assert 'record_snapshot.finished_at' in fields
            return self

        def document(self, name):
            return name

        def start_after(self, value):
            self.after = (value['record_snapshot.finished_at'], value['__name__'])
            return self

        def limit(self, size):
            self.size = size
            return self

        def stream(self, **kwargs):
            assert kwargs == {'timeout': 10, 'retry': None}
            return [
                SimpleNamespace(id=name, to_dict=lambda finish=finish: {'record_snapshot': {'finished_at': finish}})
                for name, finish in sorted(data, key=lambda item: (item[1], item[0]))
                if self.after is None or (finish, name) > self.after
            ][: self.size]

    client = SimpleNamespace(collection=lambda _: Query())
    page, after = claims.pending_page(client, 'batch_pipeline_dev', horizon=later, limit=2)
    assert [name for name, _ in page] == ['b', 'c']
    data.remove(('c', FINISH))
    page, _ = claims.pending_page(client, 'batch_pipeline_dev', horizon=later, after=after)
    assert [name for name, _ in page] == ['a']
    assert calls[:4] == [
        ('where', 'state', '==', 'record_pending'),
        ('where', 'record_snapshot.finished_at', '<=', later),
        ('order', 'record_snapshot.finished_at'),
        ('order', '__name__'),
    ]
