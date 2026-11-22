"""Work-conserving capacity, newest-first refill and crash-safe maintenance cursors."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition

from config import record_seal_repair as config
from utils.batch_pipeline import record_seal_cluster_repair as cluster, record_seal_backlog as backlog
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor
from tests.unit.test_record_seal_cluster_repair import OrderedJobsClient, pending_job, FakeProcess, CursorClient


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
