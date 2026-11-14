"""Fresh seal scheduling against a saturated chronic backlog, without cloud IO."""

from datetime import datetime, timezone

import pytest
from google.api_core.exceptions import FailedPrecondition

from config import record_seal_repair as config
from config import refactor_modes
from utils.batch_pipeline import record_seal_cluster_repair as cluster
from utils.batch_pipeline.record_seal_budget import SweepBudget, BudgetExhausted
from tests.unit.test_record_seal_cluster_repair import OrderedJobsClient, pending_job, FakeProcess


def test_fresh_query_is_newest_first_and_does_not_wait_thirty_minutes(monkeypatch):
    monkeypatch.setattr(refactor_modes, 'record_seal_repair_age_order', lambda: False)
    now = datetime.now(timezone.utc).timestamp()
    client = OrderedJobsClient(
        [
            pending_job(0, now - 30),
            pending_job(1, now - 90),
            pending_job(2, now - 180),
            pending_job(3, now - 7201),
        ]
    )
    rows, _, _ = cluster.discover_jobs(client, budget=SweepBudget(10), fresh=True)
    assert [path.rsplit('/', 1)[-1] for path, _ in rows] == ['capture-1', 'capture-2']
    query = client.queries[0]
    assert query.order == ['enqueued_at', '__name__']
    assert query.directions == ['DESCENDING', 'DESCENDING']
    assert [f[:2] for f in query.filters] == [('state', '=='), ('enqueued_at', '>='), ('enqueued_at', '<=')]
    assert all('available_at' != f[0] for f in query.filters)


def test_new_arrivals_jump_a_frozen_tail_and_already_attempted_rows(monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    client = OrderedJobsClient([pending_job(i, now - 120 - i) for i in range(300)])
    lane = cluster.FreshLane(client)
    first = lane(set())
    assert len(first) == 256
    seen = {path for path, _ in first}
    client.documents.append(pending_job(999, now - 90))
    second = lane(seen)
    assert second[0][0].endswith('/capture-999')
    assert not seen.intersection(path for path, _ in second)
    assert any(path.endswith('/capture-299') for path, _ in second)
    assert len(client.queries) == 4  # bounded to head + one tail page per poll


def test_fresh_lane_fails_closed_instead_of_hash_fallback():
    client = OrderedJobsClient([], error=FailedPrecondition('requires an index'))
    with pytest.raises(FailedPrecondition):
        cluster.discover_jobs(client, budget=SweepBudget(10), fresh=True)
    assert len(client.queries) == 1


def schedule(fresh, *, backlog=20, seconds=31, fresh_slots=3):
    now, launched, children, events, checkpoints = [0.0], [], [], [], []

    def launch(path, budget, mode):
        launched.append((now[0], path, budget))
        process = FakeProcess(now, float('inf') if path.startswith('old') else now[0] + 1, 'upload_pending', 0)
        children.append(process)
        return process

    def pause(amount):
        now[0] += amount

    report = cluster.coordinate(
        [(f'old-{i}', 100000) for i in range(backlog)],
        workers=4,
        row_seconds=20,
        run_seconds=seconds,
        mode='apply',
        fresh=fresh,
        fresh_workers=fresh_slots,
        launch=launch,
        clock=lambda: now[0],
        pause=pause,
        progress=events.append,
        attempted=checkpoints.append,
    )
    assert all(p.reaped and p.stdout.closed for p in children)
    return launched, events, checkpoints, report


def test_reserved_budget_new_arrivals_and_refusals_cannot_starve_either_lane():
    polls = [0]

    def fresh(seen):
        polls[0] += 1
        return [(f'new-{polls[0]}-{i}', i + 60) for i in range(5)]

    launched, events, checkpoints, report = schedule(fresh)
    assert [path for _, path, _ in launched[:4]] == ['new-1-0', 'new-1-1', 'new-1-2', 'old-0']
    assert next(at for at, path, _ in launched if path == 'new-2-0') < 16.1
    assert sum(path.startswith('old') for _, path, _ in launched) == 2
    assert all(path.startswith('old') for path in checkpoints)
    assert {e['lane'] for e in events if e['event'] == 'record_seal_repair_row'} == {'fresh', 'backlog'}
    assert report['dispositions']['upload_pending'] >= 10


def test_fresh_continues_with_an_empty_backlog_and_deduplicates():
    launched, _, _, _ = schedule(lambda seen: [('fresh', 60)] if 'fresh' not in seen else [], backlog=0)
    assert [path for _, path, _ in launched] == ['fresh']


@pytest.mark.parametrize('error', [RuntimeError('private test payload'), BudgetExhausted()])
def test_discovery_failure_keeps_backlog_and_hard_deadline(error):
    def fresh(_):
        raise error

    launched, events, _, report = schedule(fresh, seconds=2)
    assert [path for _, path, _ in launched] == ['old-0']
    assert report['dispositions']['budget_exhausted'] == 1
    assert events[0] == {'event': 'record_seal_repair_fresh', 'outcome': 'error'}
    assert 'private' not in str(events)


def test_kill_switch_and_single_slot_budget(monkeypatch):
    monkeypatch.delenv('RECORD_SEAL_REPAIR_FRESH_ENABLED', raising=False)
    assert config.fresh_enabled()
    monkeypatch.setenv('RECORD_SEAL_REPAIR_FRESH_ENABLED', 'false')
    assert not config.fresh_enabled()
    with pytest.raises(ValueError):
        schedule(lambda _: [], fresh_slots=4)


def test_recent_refusal_retries_after_two_minutes_without_a_new_cron_run():
    launched, _, _, _ = schedule(lambda seen: [] if 'fresh' in seen else [('fresh', 60)], backlog=0, seconds=130)
    attempts = [at for at, path, _ in launched if path == 'fresh']
    assert len(attempts) == 2 and 120 <= attempts[1] - attempts[0] < 121


def test_fresh_children_have_a_shorter_deadline_than_backlog():
    now, launches = [0.0], []

    def launch(path, seconds, mode):
        launches.append((path, seconds))
        return FakeProcess(now, float('inf'))

    cluster.coordinate(
        [('old', 100000)],
        workers=2,
        row_seconds=270,
        run_seconds=100,
        mode='apply',
        fresh=lambda seen: [('fresh', 60)],
        fresh_workers=1,
        launch=launch,
        clock=lambda: now[0],
        pause=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    assert launches == [('fresh', 90), ('old', 100)]


def test_initial_frontier_reserves_only_slots_the_legacy_sweep_can_start(monkeypatch):
    from database import _client
    from utils.batch_pipeline import record_seal_sweeper
    from tests.unit.test_record_seal_cluster_repair import CursorClient

    client, observed = CursorClient(), {}
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(config, 'require_runtime', lambda: None)
    monkeypatch.setattr(config, 'server_flags', lambda: {})
    monkeypatch.setattr(config, 'settings', lambda: (8, 270, 1500, 'plan'))
    monkeypatch.setattr(config, 'jobs_enabled', lambda: True)
    monkeypatch.setattr(config, 'fresh_enabled', lambda: True)
    monkeypatch.setattr(record_seal_sweeper, 'read_pusher_pod_proof', lambda: {})
    monkeypatch.setattr(record_seal_sweeper, 'require_fresh_proof', lambda _: None)

    def jobs(*args, **kwargs):
        observed['job_rows'] = kwargs['max_rows']
        return [], False, None

    def conversations(*args, **kwargs):
        observed['advance_rows'] = kwargs['advance_rows']
        return [], False, None

    def coordinate(*args, **kwargs):
        observed['fresh_slots'] = kwargs['fresh_workers']
        return {'rows': 0, 'dispositions': {}}

    monkeypatch.setattr(cluster, 'discover_jobs', jobs)
    monkeypatch.setattr(cluster, 'discover', conversations)
    monkeypatch.setattr(cluster, 'coordinate', coordinate)
    assert cluster.run()['outcome'] == 'ok'
    assert observed == {'job_rows': 1, 'advance_rows': 2, 'fresh_slots': 6}
    assert client.writes == 0  # preview remains read-only
