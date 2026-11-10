"""Repair must prefer stored deadlines without losing bounded, encrypted progress."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import record_seal_repair as config
from tests.unit.test_record_seal_cluster_repair import CursorClient, OrderedJobsClient, pending_job
from utils.batch_pipeline import record_seal_cluster_repair as cluster
from utils.batch_pipeline.record_seal_budget import SweepBudget
from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

NOW = 1_800_000_000


@pytest.fixture(autouse=True)
def priority_clock(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'on')
    monkeypatch.setattr(cluster, 'datetime', SimpleNamespace(now=lambda _: datetime.fromtimestamp(NOW, timezone.utc)))


def test_urgent_query_uses_stored_deadline_and_includes_final_day_boundary():
    docs = [
        pending_job(0, NOW - 5000),  # No deadline: age alone never invents urgency.
        pending_job(1, NOW - 6000, record_dead_letter_deadline_at=NOW + 86401),
        pending_job(2, NOW - 7000, record_dead_letter_deadline_at=NOW + 86400),
        pending_job(3, NOW - 8000, record_dead_letter_deadline_at=NOW - 1),
        pending_job(4, NOW - 9000, record_dead_letter_deadline_at=NOW + 1),
    ]
    client = OrderedJobsClient(docs)
    rows, saturated, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), urgent=True)
    assert [path.rsplit('-', 1)[-1] for path, _ in rows] == ['3', '4', '2']
    assert not saturated and cursor is None
    query = client.queries[0]
    assert query.filters == [
        ('state', '==', 'record_pending'),
        ('record_dead_letter_deadline_at', '<=', NOW + 86400),
    ]
    assert query.order == ['record_dead_letter_deadline_at', '__name__']
    assert query.directions == ['ASCENDING', 'ASCENDING']


def test_urgent_ties_resume_exactly_and_frontiers_are_independent():
    docs = [pending_job(i, NOW - 5000, record_dead_letter_deadline_at=NOW + 0.1234567) for i in range(3)]
    client, budget, states = OrderedJobsClient(docs), SweepBudget(60), {}
    state_client = SimpleNamespace(
        collection=lambda _: SimpleNamespace(document=lambda name: states.setdefault(name, CursorClient()))
    )
    urgent = RepairCursor(state_client, b'k' * 32, jobs=True, urgent=True)
    ordinary = RepairCursor(state_client, b'k' * 32, jobs=True)
    conversations = RepairCursor(state_client, b'k' * 32)
    seen, after = [], None
    for _ in docs:
        selected = {}
        rows, saturated, after = cluster.discover_jobs(
            client, budget=budget, urgent=True, after=after, max_rows=1, selected_cursors=selected
        )
        assert saturated and after == selected[rows[0][0]]
        urgent.write(after, budget)
        after = urgent.read(budget)
        assert after['enqueued_at'] == NOW + 0.1234567  # Exact query clock, no datetime round trip.
        seen.extend(path for path, _ in rows)
    assert len(set(seen)) == 3
    assert cluster.discover_jobs(client, budget=budget, urgent=True, after=after) == ([], False, None)
    assert ordinary.read(budget) is None and conversations.read(budget) is None
    assert b'synthetic' not in urgent.ref.state['cursor']
    assert len(states) == 3


@pytest.mark.parametrize('deadline', [0, -1, True, None, 'soon', float('nan'), float('inf')])
def test_malformed_deadlines_never_create_urgent_work(deadline):
    client = OrderedJobsClient([pending_job(0, NOW - 5000, record_dead_letter_deadline_at=deadline)])
    assert cluster.discover_jobs(client, budget=SweepBudget(60), urgent=True)[0] == []


def test_priority_kill_switch_skips_urgent_query(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'off')
    assert cluster.discover_jobs(Mock(), budget=SweepBudget(60), urgent=True) == ([], False, None)


def test_urgent_missing_index_fails_without_silently_dropping_deadline_priority():
    client = OrderedJobsClient([], cluster.FailedPrecondition('query requires an index'))
    with pytest.raises(cluster.FailedPrecondition):
        cluster.discover_jobs(client, budget=SweepBudget(60), urgent=True)


@pytest.mark.parametrize('mode', ['plan', 'apply'])
def test_coordinator_orders_urgent_first_deduplicates_and_keeps_existing_budget(monkeypatch, mode):
    from database import _client
    from utils.batch_pipeline import record_seal_repair_cursor, record_seal_sweeper

    cursors = {}

    class Frontier:
        def __init__(self, client, secret, *, jobs=False, urgent=False):
            self.writes = []
            cursors[(jobs, urgent)] = self

        def read(self, budget):
            return None

        def write(self, value, budget):
            self.writes.append(value)

    def jobs(client, *, urgent=False, selected_cursors, max_rows, **kwargs):
        assert max_rows == (2 if urgent else 1)
        path = 'urgent' if urgent else 'recent-job'
        selected_cursors[path] = {'path': path}
        return [(path, 5000 if urgent else 1000)], False, {'path': path}

    def conversations(client, *, max_scan, max_rows, advance_rows, selected_cursors, **kwargs):
        assert (max_scan, max_rows, advance_rows) == (10000 - 256, 1022, 2)
        selected_cursors.update(
            {'urgent': {'path': 'duplicate'}, 'recent-conversation': {'path': 'recent-conversation'}}
        )
        return [('urgent', 5000), ('recent-conversation', 500)], False, None

    def coordinate(rows, *, attempted, **kwargs):
        assert rows == [('urgent', 5000), ('recent-job', 1000), ('recent-conversation', 500)]
        for path, _ in rows:
            attempted(path)
        return {}

    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: {})
    monkeypatch.setattr(config, 'cursor_secret', lambda: b'k' * 32)
    monkeypatch.setattr(config, 'settings', lambda: (4, 270, 1500, mode))
    monkeypatch.setattr(config, 'jobs_enabled', lambda: True)
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: object())
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: None)
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)
    monkeypatch.setattr(record_seal_repair_cursor, 'RepairCursor', Frontier)
    monkeypatch.setattr(cluster, 'discover_jobs', jobs)
    monkeypatch.setattr(cluster, 'discover', conversations)
    monkeypatch.setattr(cluster, 'coordinate', coordinate)
    assert cluster.run()['outcome'] == 'ok'
    for key, path in [((True, True), 'urgent'), ((True, False), 'recent-job'), ((False, False), 'recent-conversation')]:
        assert cursors[key].writes == (
            [] if mode == 'plan' else [None if not key[0] else {'path': path}, {'path': path}]
        )
