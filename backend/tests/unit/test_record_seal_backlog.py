"""Work-conserving capacity, newest-first refill and crash-safe maintenance cursors."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition

from config import record_seal_repair as config
from database import _client
from utils.batch_pipeline import (
    record_seal_cluster_repair as cluster,
    record_seal_backlog as backlog,
    record_seal_sweeper,
)
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor
from tests.unit.test_record_seal_cluster_repair import OrderedJobsClient, pending_job, FakeProcess, CursorClient
from tests.unit.test_record_seal_nojob import SERVER


def test_empty_fresh_reservation_lends_every_slot_but_bounds_loans():
    now, launched = [0.0], []

    def launch(path, seconds, mode):
        launched.append((now[0], path, seconds))
        return FakeProcess(now, float('inf'))

    cluster.coordinate(
        [(f'old-{i}', 100000) for i in range(20)],
        workers=8,
        row_seconds=270,
        run_seconds=110,
        mode='apply',
        fresh=lambda _: [('fresh', 60)] if now[0] >= 15 else [],
        fresh_workers=4,
        launch=launch,
        clock=lambda: now[0],
        pause=lambda t: now.__setitem__(0, now[0] + t),
    )
    assert [path for _, path, _ in launched[:8]] == [f'old-{i}' for i in range(8)]
    assert [seconds for _, _, seconds in launched[:8]] == [110, 110, 110, 110, 90, 90, 90, 90]
    at = next(at for at, path, _ in launched if path == 'fresh')
    assert 90 <= at < 90.2  # fresh takes the first returned loan, before another backlog row


def test_newest_backlog_is_refilled_past_1024_without_repeating_rows():
    stamp = datetime.now(timezone.utc).timestamp()
    client = OrderedJobsClient([pending_job(i, stamp - 8000 - i) for i in range(1800)])
    frontier = SimpleNamespace(read=lambda _: None, write=Mock())
    lane = backlog.BacklogLane(client, frontier, mode='apply')
    now, launched, children = [0.0], [], []

    def launch(path, seconds, mode):
        launched.append(path)
        child = FakeProcess(now, now[0] + 1, 'sealed', 0)
        children.append(child)
        return child

    report = cluster.coordinate(
        [],
        workers=8,
        row_seconds=270,
        run_seconds=300,
        mode='apply',
        fresh=lambda _: [],
        fresh_workers=4,
        backlog=lane,
        launch=launch,
        clock=lambda: now[0],
        pause=lambda t: now.__setitem__(0, now[0] + t),
    )
    assert launched == [f'users/synthetic/conversations/capture-{i}' for i in range(1800)]
    assert report['dispositions'] == {'sealed': 1800}
    assert all(c.reaped and c.stdout.closed for c in children)
    assert len(client.queries) == 15  # one pass, even after exhausting all work
    assert frontier.write.call_count == 15 and frontier.write.call_args.args[0] is None
    assert all(q.directions == ['DESCENDING', 'DESCENDING'] for q in client.queries)


def test_prefetch_does_not_checkpoint_past_deferred_rows_and_preview_never_writes():
    stamp = datetime.now(timezone.utc).timestamp()
    client = OrderedJobsClient([pending_job(i, stamp - 8000 - i) for i in range(300)])
    for mode in ('apply', 'plan'):
        frontier = SimpleNamespace(read=lambda _: None, write=Mock())
        lane = backlog.BacklogLane(client, frontier, mode=mode)
        first = lane(set())
        assert len(first) == 128 and not frontier.write.called  # merely selected, not attempted
        lane({p for p, _ in first})  # called only after the entire first page has been launched
        assert frontier.write.call_count == (1 if mode == 'apply' else 0)
        if mode == 'apply':
            cursor = frontier.write.call_args.args[0]
            assert cursor['enqueued_at'] == stamp - 8000 - 127


@pytest.mark.parametrize('mode', ['apply', 'plan'])
def test_next_run_resumes_after_last_backlog_attempt_at_deadline(monkeypatch, mode):
    stamp = datetime.now(timezone.utc).timestamp()
    jobs = OrderedJobsClient([pending_job(i, stamp - 8000 - i) for i in range(10)])
    refs = {}

    def collection(name):
        if name == 'batch_pipeline_prod_maintenance':
            return SimpleNamespace(document=lambda key: refs.setdefault(key, CursorClient()))
        return jobs.collection(name)

    client = CursorClient()
    client.collection = collection
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: None)
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)
    monkeypatch.setattr(config, 'enabled', lambda: True)
    monkeypatch.setattr(config, 'jobs_enabled', lambda: True)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: SERVER)
    monkeypatch.setattr(config, 'cursor_secret', lambda: b'x' * 32)
    monkeypatch.setattr(config, 'settings', lambda: (1, 20, 1, mode))
    monkeypatch.setattr(cluster, 'promote_record_recoveries', lambda *args, **kwargs: 0)
    monkeypatch.setattr(cluster.record_custody_receipts, 'prune', lambda *args, **kwargs: 0)
    monkeypatch.setattr(cluster.refactor_modes, 'record_seal_repair_age_order', lambda: False)
    discover_jobs = cluster.discover_jobs
    monkeypatch.setattr(
        cluster,
        'discover_jobs',
        lambda *args, **kwargs: discover_jobs(*args, **kwargs) if kwargs.get('newest') else ([], False, None),
    )

    launched = []
    coordinate = cluster.coordinate

    def run_to_deadline(rows, **kwargs):
        now = [0.0]

        def launch(path, seconds, mode):
            launched.append(path)
            return FakeProcess(now, float('inf'))

        return coordinate(
            rows,
            **kwargs,
            launch=launch,
            clock=lambda: now[0],
            pause=lambda seconds: now.__setitem__(0, now[0] + seconds),
        )

    monkeypatch.setattr(cluster, 'coordinate', run_to_deadline)
    assert cluster.run()['dispositions'] == {'budget_exhausted': 1, 'deferred': 9}
    first_query = jobs.queries[-1]
    assert first_query.after is None
    report = cluster.run()
    second_query = jobs.queries[-1]
    assert report['dispositions']['budget_exhausted'] == 1
    if mode == 'apply':
        assert report['dispositions']['deferred'] == 8
        assert second_query.after['enqueued_at'] == stamp - 8000
        assert second_query.filters == first_query.filters  # Same frozen horizon.
        assert launched == [f'users/synthetic/conversations/capture-{i}' for i in (0, 1)]
    else:
        assert report['dispositions']['deferred'] == 9
        assert all(doc.writes == 0 for doc in refs.values())
        assert second_query.after is None
        assert launched[0] == launched[1]


def test_backlog_fails_closed_on_missing_index_instead_of_hash_order():
    with pytest.raises(FailedPrecondition):
        cluster.discover_jobs(
            OrderedJobsClient([], error=FailedPrecondition('requires an index')), budget=SweepBudget(10), newest=True
        )


def test_new_backlog_cursor_is_separate_and_encrypted():
    refs = {}

    def document(name):
        if name not in refs:
            refs[name] = CursorClient()
            refs[name].path = f'batch_pipeline_prod_maintenance/{name}'
        return refs[name]

    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=document))
    cursor = RepairCursor(client, b'x' * 32, jobs=True, backlog=True)
    old = RepairCursor(client, b'x' * 32, jobs=True)
    assert cursor.ref.path != old.ref.path
    value = {'path': 'batch_pipeline_prod_jobs/synthetic', 'enqueued_at': 1, 'horizon': datetime.now(timezone.utc)}
    cursor.write(value, SweepBudget(10))
    assert cursor.read(SweepBudget(10)) == value
    assert old.read(SweepBudget(10)) is None
