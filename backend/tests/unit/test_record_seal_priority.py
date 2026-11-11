"""Repair must prefer stored deadlines without losing bounded, encrypted progress."""

from collections import Counter
from datetime import datetime, timezone
import math
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
    # Maintenance phases have their own custody tests; keep priority's query inventory isolated.
    monkeypatch.setattr(cluster, 'promote_record_recoveries', lambda *args, **kwargs: 0)
    monkeypatch.setattr(cluster.record_custody_receipts, 'prune', lambda *args, **kwargs: 0)
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
        ('record_dead_letter_deadline_at', '>', 0),
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
@pytest.mark.parametrize('urgent_index_error', [False, True])
def test_coordinator_orders_urgent_first_deduplicates_and_keeps_existing_budget(monkeypatch, mode, urgent_index_error):
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
        assert max_rows == (1 if urgent else 2)
        if urgent and urgent_index_error:
            raise cluster.FailedPrecondition('private query requires an index: users/private')
        if urgent:
            kwargs['invalid_clock_counts']['invalid_clock_rows'] += 128
        path = 'urgent' if urgent else 'recent-job'
        selected_cursors[path] = {'path': path}
        return [(path, 5000 if urgent else 1000)], False, {'path': path}

    def conversations(client, *, max_scan, max_rows, advance_rows, selected_cursors, **kwargs):
        assert (max_scan, max_rows, advance_rows) == (
            10000 - 256,
            1023 if urgent_index_error else 1022,
            3 if urgent_index_error else 2,
        )
        selected_cursors.update(
            {'urgent': {'path': 'duplicate'}, 'recent-conversation': {'path': 'recent-conversation'}}
        )
        return (
            (
                [('recent-conversation', 500)]
                if urgent_index_error
                else [('urgent', 5000), ('recent-conversation', 500)]
            ),
            False,
            None,
        )

    def coordinate(rows, *, attempted, **kwargs):
        assert rows == ([] if urgent_index_error else [('urgent', 5000)]) + [
            ('recent-job', 1000),
            ('recent-conversation', 500),
        ]
        for path, _ in rows:
            attempted(path)
        return {'invalid_clock_rows': 2}

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
    if urgent_index_error:
        from scripts import record_seal_repair_job as entrypoint
        from utils import record_projection_rebuild

        events, fallbacks = [], []
        monkeypatch.setattr(cluster, 'record_fallback', lambda **kw: fallbacks.append(kw))
        from contextlib import nullcontext

        monkeypatch.setattr(entrypoint, 'repair_probe_server', nullcontext)
        monkeypatch.setattr(entrypoint, 'emit', events.append)
        monkeypatch.setattr(entrypoint.signal, 'signal', lambda *_: None)
        monkeypatch.setattr(entrypoint.sys, 'argv', ['record_seal_repair_job.py'])
        monkeypatch.setattr(record_projection_rebuild, 'run_job', lambda: {'outcome': 'disabled'})
        assert entrypoint.main() == 0
        assert events[0] == {'event': 'record_seal_repair_urgent', 'outcome': 'index_unavailable'}
        assert events[-1]['outcome'] == 'ok'
        assert 'private' not in str(events) + str(fallbacks)
        assert fallbacks[0]['outcome'] == 'degraded'
    else:
        report = cluster.run()
        assert report['outcome'] == 'ok' and report['invalid_clock_rows'] == 130
    for key, path in [((True, True), 'urgent'), ((True, False), 'recent-job'), ((False, False), 'recent-conversation')]:
        assert cursors[key].writes == (
            []
            if mode == 'plan'
            else [None] if urgent_index_error and key[1] else [None if not key[0] else {'path': path}, {'path': path}]
        )


@pytest.mark.parametrize('deadline', [True, None, 'soon', 0, -1, float('nan'), float('inf')])
def test_saturated_malformed_deadlines_never_persist_an_invalid_urgent_frontier(monkeypatch, deadline):
    docs = [pending_job(i, NOW - 5000, record_dead_letter_deadline_at=deadline) for i in range(128)]
    client, budget = OrderedJobsClient([]), SweepBudget(60)
    query = client.collection('batch_pipeline_prod_jobs')
    # Supply a saturated projected page, including types the numeric fake filters
    # out. Exercise the local guard independently of query type filtering.
    monkeypatch.setattr(query, 'stream', lambda **_: docs)
    monkeypatch.setattr(client, 'collection', lambda _: query)
    counts = Counter()
    rows, saturated, cursor = cluster.discover_jobs(client, budget=budget, urgent=True, invalid_clock_counts=counts)
    assert rows == [] and saturated and cursor['path'] == docs[-1].reference.path
    assert counts == {'invalid_clock_rows': 128}
    state = CursorClient()
    frontier = RepairCursor(
        SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: state)),
        b'k' * 32,
        jobs=True,
        urgent=True,
    )
    frontier.write(cursor, budget)
    restored = frontier.read(budget)
    assert restored['path'] == cursor['path']
    value = restored['enqueued_at']
    assert type(value) is type(deadline)
    assert math.isnan(value) if isinstance(deadline, float) and math.isnan(deadline) else value == deadline
    if type(deadline) not in (int, float):
        # This extension belongs only to urgent scalar query positions.
        ordinary = RepairCursor(
            SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: state)), b'k' * 32, jobs=True
        )
        with pytest.raises(ValueError, match='invalid maintenance frontier'):
            ordinary.read(budget)
    # The next run can load the frontier and select a valid deadline.
    docs[:] = [pending_job(129, NOW - 5000, record_dead_letter_deadline_at=NOW + 1)]
    assert cluster.discover_jobs(client, budget=budget, urgent=True, after=frontier.read(budget))[0]


@pytest.mark.parametrize('deadline', [0, -1])
@pytest.mark.parametrize('force_malformed_page', [False, True])
def test_persistent_malformed_prefix_cannot_pin_valid_urgent_jobs(monkeypatch, deadline, force_malformed_page):
    bad = sorted(
        [pending_job(i, NOW - 5000, record_dead_letter_deadline_at=deadline) for i in range(128)],
        key=lambda doc: doc.reference.path,
    )
    good = pending_job(129, NOW - 5000, record_dead_letter_deadline_at=NOW + 1)
    client, budget = OrderedJobsClient(bad + [good]), SweepBudget(60)
    if force_malformed_page:
        # Also exercise cursor progress independently of the query floor, as
        # with the adversarial projected page in the saturated-page regression.
        collection = client.collection

        def unfiltered_collection(name):
            query = collection(name)

            def stream(**_):
                docs = client.documents
                if query.after:
                    point = (query.after['record_dead_letter_deadline_at'], query.after['__name__'].path)
                    docs = [
                        doc
                        for doc in docs
                        if (doc.to_dict()['record_dead_letter_deadline_at'], doc.reference.path) > point
                    ]
                return docs[: query.cap]

            query.stream = stream
            return query

        monkeypatch.setattr(client, 'collection', unfiltered_collection)
    state = CursorClient()
    frontier = RepairCursor(
        SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: state)),
        b'k' * 32,
        jobs=True,
        urgent=True,
    )
    counts, found = Counter(), []
    for _ in range(2 if force_malformed_page else 1):
        selected = {}
        rows, saturated, cursor = cluster.discover_jobs(
            client,
            budget=budget,
            urgent=True,
            after=frontier.read(budget),
            selected_cursors=selected,
            invalid_clock_counts=counts,
        )
        if not rows:
            assert saturated and selected == {} and cursor['path'] == bad[-1].reference.path
        found.extend(path for path, _ in rows)
        frontier.write(cursor, budget)
    assert found == ['users/synthetic/conversations/capture-129']
    assert len(client.documents) == 129  # The malformed prefix was never removed.
    assert counts['invalid_clock_rows'] == (128 if force_malformed_page else 0)
    assert all(('record_dead_letter_deadline_at', '>', 0) in query.filters for query in client.queries)


def test_conversation_newest_first_encrypted_resume_frozen_horizon_and_wrap(monkeypatch):
    # Discovery validates datetime instances as well as consulting now().
    monkeypatch.setattr(cluster, 'datetime', datetime)
    now = datetime.now(timezone.utc).timestamp()

    class OrderedConversationsClient(CursorClient):
        def collection_group(self, name):
            assert name == 'conversations'
            client = self

            class Query:
                def __init__(self):
                    self.orders, self.after, self.horizon, self.cap = [], None, None, 128

                def where(self, *, filter):
                    if filter.field_path == 'finished_at':
                        self.horizon = filter.value
                    return self

                def order_by(self, field, direction=None):
                    self.orders.append((field, direction))
                    return self

                def select(self, _):
                    return self

                def limit(self, cap):
                    self.cap = cap
                    return self

                def start_after(self, cursor):
                    self.after = (cursor['finished_at'], cursor['__name__'].path)
                    return self

                def stream(self, **_):
                    assert self.orders == [('finished_at', 'DESCENDING'), ('__name__', 'DESCENDING')]
                    key = lambda doc: (doc.to_dict()['finished_at'], doc.reference.path)
                    docs = sorted(client.documents, key=key, reverse=self.orders[0][1] == 'DESCENDING')
                    return [
                        d for d in docs if key(d)[0] <= self.horizon and (self.after is None or key(d) < self.after)
                    ][: self.cap]

            return Query()

    def conversation(name, finished):
        return SimpleNamespace(
            reference=SimpleNamespace(path=f'users/synthetic/conversations/{name}'),
            to_dict=lambda: {'finished_at': datetime.fromtimestamp(finished, timezone.utc)},
        )

    docs = [conversation('old', now - 7000), conversation('a', now - 5000), conversation('z', now - 5000)]
    client, budget = OrderedConversationsClient(docs), SweepBudget(60)
    frontier = RepairCursor(client, b'k' * 32)
    observed = []
    for index in range(3):
        rows, saturated, cursor = cluster.discover(
            client, budget=budget, after=frontier.read(budget), max_rows=1, advance_rows=1
        )
        assert saturated and len(rows) == 1
        observed.append(rows[0][0].rsplit('/', 1)[-1])
        frontier.write(cursor, budget)
        if index == 0:
            # A later arrival cannot move the frozen upper boundary or strand the tail.
            client.documents.append(conversation('new-arrival', datetime.now(timezone.utc).timestamp()))
    assert observed == ['z', 'a', 'old']
    assert cluster.discover(client, budget=budget, after=frontier.read(budget)) == ([], False, None)
    frontier.write(None, budget)
    rows, _, _ = cluster.discover(client, budget=budget, after=frontier.read(budget), max_rows=1)
    assert rows[0][0].endswith('/new-arrival')


@pytest.mark.parametrize('ordinary_count', [0, 1, 8, 32])
@pytest.mark.parametrize('workers', [2, 4, 16])
def test_ordinary_reserve_survives_sustained_urgent_backlog_and_returns_unused_capacity(
    monkeypatch, ordinary_count, workers
):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper

    class Client(OrderedJobsClient):
        def __init__(self, documents):
            super().__init__(documents)
            self.states = {}

        def collection(self, name):
            if name == 'batch_pipeline_prod_maintenance':
                return SimpleNamespace(document=lambda key: self.states.setdefault(key, CursorClient()))
            return super().collection(name)

    ordinary = [pending_job(i, NOW - 10000 - i) for i in range(ordinary_count)]
    urgent = [pending_job(100 + i, NOW - 5000 - i, record_dead_letter_deadline_at=NOW + i) for i in range(64)]
    client = Client(ordinary + urgent)
    allocation = max(1, workers // 2)
    reserve = max(1, allocation // 4)
    expected_ordinary = min(reserve, ordinary_count)
    normal = RepairCursor(client, b'k' * 32, jobs=True)
    # An exhausted ordinary pass can be empty while urgent has independent work.
    normal.write(
        {
            'path': 'batch_pipeline_prod_jobs/head',
            'enqueued_at': NOW - 9999 if ordinary_count else 0,
            'horizon': datetime.fromtimestamp(NOW, timezone.utc),
        },
        SweepBudget(60),
    )
    calls = []

    def conversations(client, *, advance_rows, **kwargs):
        assert advance_rows == workers - allocation
        assert kwargs['max_scan'] <= cluster.MAX_SCAN - 128
        return [], False, None

    def coordinate(rows, *, attempted, **kwargs):
        calls.append([path for path, _ in rows])
        if ordinary_count:
            # Check the checkpoint BEFORE attempts can overwrite it. Candidates
            # fetched beyond the ordinary reserve must remain for the next run.
            checkpoint = normal.read(SweepBudget(60))
            if ordinary_count == 1 and allocation > 1:
                assert checkpoint is None  # Entire ordinary pass was selected.
            else:
                assert checkpoint['enqueued_at'] == NOW - 10000 - (len(calls) * reserve - 1)
        for path, _ in rows:
            attempted(path)
        return {}

    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: {})
    monkeypatch.setattr(config, 'cursor_secret', lambda: b'k' * 32)
    monkeypatch.setattr(config, 'settings', lambda: (workers, 270, 1500, 'apply'))
    monkeypatch.setattr(config, 'jobs_enabled', lambda: True)
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: None)
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)
    monkeypatch.setattr(cluster, 'discover', conversations)
    monkeypatch.setattr(cluster, 'coordinate', coordinate)
    for iteration in range(3 if ordinary_count >= 8 else 1):
        assert cluster.run()['outcome'] == 'ok'
        paths = calls[-1]
        assert len(paths) == allocation and len(set(paths)) == allocation
        urgent_count = allocation - expected_ordinary
        assert paths[:urgent_count] == [
            f'users/synthetic/conversations/capture-{100 + i}'
            for i in range(iteration * urgent_count, (iteration + 1) * urgent_count)
        ]
        assert paths[urgent_count:] == [
            f'users/synthetic/conversations/capture-{i}'
            for i in range(iteration * reserve, iteration * reserve + expected_ordinary)
        ]
        # Every run performs ordinary discovery, despite >= allocation urgent jobs.
        assert sum(query.order[0] == 'enqueued_at' for query in client.queries) == iteration + 1
