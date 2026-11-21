"""Synthetic transactional meter and small multi-owner simulator regression."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted, ServiceUnavailable

from testing.pipeline_sim.store import CustomerData, SimStore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction
from utils.batch_pipeline import backlog_release as gate
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.scheduler import owner_key

NOW = 100_000.0
METER = 'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED'
RELEASE = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'


@pytest.fixture(autouse=True)
def switches(monkeypatch):
    for name in (METER, RELEASE):
        monkeypatch.delenv(name, raising=False)


def put(store, table, key, row):
    store.run(lambda tx: tx.put(table, key, row))


def ready(store, name, *, owner='synthetic', fresh=False, capture=1000):
    row = dict(
        segment_id=name,
        owner_id=owner,
        owner_key=owner_key(owner),
        capture_at=capture,
        duration_seconds=10,
        protocol_version=1,
        merge_pending=True,
        state='result_ready',
        ready_at=NOW,
        fresh_capture=fresh,
        stt_route={'stt_route': 'provider'},
        result={},
    )
    put(store, 'jobs', name, row)


def opened(store, now=NOW):
    row = dict(state='open', rate_per_hour=2, reach_seconds=0, window=int(now // 3600), tokens_used=0, updated_at=now)
    put(store, 'backlog_release', 'gate', row)


def merge(store, now=NOW, owner='synthetic', depth=0):
    return OrderedMerge(store, catch_up_depth=depth).commit_next(owner, now)


def tokens(store):
    return store.run(lambda tx: tx.get('backlog_release', 'gate'))['tokens_used']


def test_rate_fresh_is_free_and_rollover(monkeypatch):
    store = MemoryStore()
    for name in ('a', 'b', 'c'):
        ready(store, name)
    opened(store)
    for name in ('a', 'b'):
        assert merge(store)['segment_id'] == name
        assert store.rows['results', name]['backlog_release'] is True
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None and tokens(store) == 2
    refused.labels.assert_called_with('rate')
    ready(store, 'f', fresh=True)
    get = MemoryTransaction.get

    def no_gate(tx, table, key):
        assert table != 'backlog_release'
        return get(tx, table, key)

    with monkeypatch.context() as patch:
        patch.setattr(MemoryTransaction, 'get', no_gate)
        assert 'backlog_release' not in merge(store)
    assert tokens(store) == 2
    rollover = (int(NOW // 3600) + 1) * 3600.0
    row = store.rows['backlog_release', 'gate']
    put(store, 'backlog_release', 'gate', {**row, 'updated_at': rollover})
    assert merge(store, rollover)['segment_id'] == 'c' and tokens(store) == 1


@pytest.mark.parametrize(
    'fields,reason',
    [
        (None, 'missing'),
        ({'updated_at': NOW - 181}, 'stale'),
        ({'updated_at': NOW - 180}, 'stale'),
        ({'state': 'closed'}, 'closed'),
        ({'rate_per_hour': 0}, 'rate'),
        ({'reach_seconds': 100}, 'reach'),
        ({'rate_per_hour': '2'}, 'closed'),
        ({'rate_per_hour': True}, 'closed'),
        ({'tokens_used': -1}, 'closed'),
        ({'window': -1}, 'closed'),
        ({'reach_seconds': -1}, 'closed'),
        ({'state': 'OPEN'}, 'closed'),
        ({'updated_at': str(NOW)}, 'closed'),
        ({'updated_at': float('nan')}, 'closed'),
        ({'updated_at': -1.0, 'window': 0}, 'closed'),
        ({'note': 'unknown field'}, 'closed'),
    ],
)
def test_refusals_and_deploy_safety(fields, reason, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    if fields is not None:
        opened(store)
        store.rows['backlog_release', 'gate'].update(fields)
    before = deepcopy(store.rows)
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None and store.rows == before
    refused.labels.assert_called_with(reason)
    assert not any(table == 'merge_holds' for table, _ in store.rows)


@pytest.mark.parametrize('missing', gate.FIELDS)
def test_incomplete_gate_cannot_reset_the_budget(missing, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    opened(store)
    store.rows['backlog_release', 'gate']['tokens_used'] = 2  # The hour is spent.
    del store.rows['backlog_release', 'gate'][missing]
    before = deepcopy(store.rows)
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None and store.rows == before
    refused.labels.assert_called_with('closed')


def test_only_the_heartbeat_rolls_the_budget_hour(monkeypatch):
    """A committer whose clock crosses the hour early, or late, cannot reset the count."""
    store = MemoryStore()
    for name in ('a', 'b', 'c'):
        ready(store, name)
    opened(store)
    later = (int(NOW // 3600) + 1) * 3600.0
    row = store.rows['backlog_release', 'gate']
    put(store, 'backlog_release', 'gate', {**row, 'tokens_used': 2, 'updated_at': later - 1})
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store, later - 1) is None and merge(store, later + 5) is None  # A fast clock opens nothing.
    refused.labels.assert_called_with('rate')
    put(store, 'backlog_release', 'gate', {**store.rows['backlog_release', 'gate'], 'updated_at': later})
    assert merge(store, later - 1) is None  # A clock behind the heartbeat is refused.
    refused.labels.assert_called_with('stale')
    assert merge(store, later)['segment_id'] == 'a' and merge(store, later + 5)['segment_id'] == 'b'
    row = store.rows['backlog_release', 'gate']
    assert (row['window'], row['tokens_used'], row['updated_at']) == (int(later // 3600), 2, later)
    assert merge(store, later + 5) is None
    refused.labels.assert_called_with('rate')


def test_gate_age_is_judged_when_it_is_read_not_when_the_drain_began(monkeypatch):
    """A heartbeat 179 s old at drain start is stale once two seconds pass before the gate read, on every attempt."""
    store = MemoryStore()
    ready(store, 'a')
    opened(store, NOW - 179)
    ticks = iter([0.0] + [2.0] * 50)
    clock = Mock(monotonic=lambda: next(ticks), time=lambda: NOW)
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    worker = OrderedMerge(store, catch_up_depth=0)
    with monkeypatch.context() as patch:
        patch.setattr('utils.batch_pipeline.merge.time', clock)
        assert worker.commit_next('synthetic', NOW) is None
    refused.labels.assert_called_with('stale')
    assert merge(store)['segment_id'] == 'a'  # With no delay the same gate is still young enough.


@pytest.mark.parametrize('reason', ['stale', 'reach'])
@pytest.mark.parametrize('retry', [False, True])
def test_gate_read_latency_counts_toward_expiry_on_every_attempt(reason, retry, monkeypatch):
    customer = CustomerData()
    customer.add_user('synthetic')
    store = SimStore(customer)
    ready(store, 'a', capture=NOW - 109)  # Capture ended 99 s ago.
    opened(store, NOW - 179 if reason == 'stale' else NOW)
    if reason == 'reach':
        row = store.rows['backlog_release', 'gate']
        put(store, 'backlog_release', 'gate', {**row, 'reach_seconds': 100})
    before = deepcopy(store.rows)
    elapsed, reads = [0.0], []
    run = store.run
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)

    def delayed_run(body):
        def attempt(tx):
            get = tx.get

            def delayed_get(table, key):
                row = get(table, key)
                if table == 'backlog_release':
                    reads.append(True)
                    elapsed[0] += 0 if retry and len(reads) == 1 else 5
                return row

            tx.get = delayed_get
            result = body(tx)
            if retry and len(reads) == 1:
                assert result is not None  # First attempt was eligible, but its writes must abort.
                raise Aborted('retry after an eligible gate read')
            return result

        try:
            return run(attempt)
        except Aborted:
            return run(attempt)

    clock = Mock(monotonic=lambda: elapsed[0], time=lambda: NOW)
    with monkeypatch.context() as patch:
        patch.setattr('utils.batch_pipeline.merge.time', clock)
        patch.setattr(store, 'run', delayed_run)
        assert merge(store) is None
    refused.labels.assert_called_with(reason)
    assert len(reads) == (2 if retry else 1)
    assert store.rows == before  # No token, heartbeat, result, job or owner mutation.
    ready(store, 'fresh', fresh=True, capture=NOW)
    monkeypatch.setattr(gate, 'read', Mock(side_effect=AssertionError('fresh must not touch gate')))
    assert merge(store)['segment_id'] == 'fresh'


def test_window_ahead_of_the_heartbeat_is_closed(monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    opened(store)
    store.rows['backlog_release', 'gate']['window'] += 1
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None
    refused.labels.assert_called_with('closed')


@pytest.mark.parametrize('reach', [0, 100])
@pytest.mark.parametrize('fields', [{'duration_seconds': None}, {'duration_seconds': -1}, {'duration_seconds': '10'}])
def test_job_without_valid_times_is_refused(fields, reach, monkeypatch):
    store = MemoryStore()
    ready(store, 'a')
    for name, value in fields.items():
        if value is None:
            del store.rows['jobs', 'a'][name]
        else:
            store.rows['jobs', 'a'][name] = value
    opened(store)
    store.rows['backlog_release', 'gate']['reach_seconds'] = reach
    before = deepcopy(store.rows)
    refused = Mock()
    monkeypatch.setattr(gate, 'REFUSED', refused)
    assert merge(store) is None and store.rows == before
    refused.labels.assert_called_with('job')


@pytest.mark.parametrize('reach', [0, 100])
@pytest.mark.parametrize('capture', [None, 'x', True, float('inf')])
def test_job_without_a_capture_time_gets_no_token(capture, reach):
    # The ordered queries cannot return a row with no capture time; the gate still refuses one.
    row = dict(state='open', rate_per_hour=2, reach_seconds=reach, window=0, tokens_used=0, updated_at=NOW)
    assert (
        gate.read(
            Mock(get=Mock(return_value=row)), {'capture_at': NOW - 20, 'duration_seconds': 10}, lambda: NOW, 'test'
        )[1]
        is None
    )
    job = {'duration_seconds': 10} if capture is None else {'capture_at': capture, 'duration_seconds': 10}
    assert gate.read(Mock(get=Mock(return_value=row)), job, lambda: NOW, 'test') == (None, 'job')


@pytest.mark.parametrize('release,expected', [('false', False), ('true', True), (None, True)])
def test_override_and_reach(release, expected, monkeypatch):
    store = MemoryStore()
    ready(store, 'a', capture=NOW - 109)  # Capture ended 99 s ago: inside the reach.
    opened(store)
    store.rows['backlog_release', 'gate']['reach_seconds'] = 100
    if release is not None:
        monkeypatch.setenv(RELEASE, release)
    assert bool(merge(store)) is expected


@pytest.mark.parametrize('ended_ago,reason', [(100, None), (100.5, 'reach')])
def test_reach_boundary_is_inclusive(ended_ago, reason):
    row = dict(state='open', rate_per_hour=2, reach_seconds=100, window=0, tokens_used=0, updated_at=NOW)
    job = {'capture_at': NOW - ended_ago - 10, 'duration_seconds': 10}
    assert gate.read(Mock(get=Mock(return_value=row)), job, lambda: NOW, 'test')[1] == reason


def test_uncommittable_fresh_waits_while_backlog_uses_tokens(monkeypatch):
    store = MemoryStore()
    for name in ('a', 'f0', 'f1'):
        ready(store, name, fresh=name != 'a', capture=1000 if name == 'a' else 90000)
    store.rows['jobs', 'f0']['state'] = 'leased'
    opened(store)
    ordered = OrderedMerge(store, catch_up_depth=0, head_wait_seconds=60)
    assert ordered.commit_next('synthetic', NOW)['segment_id'] == 'a' and tokens(store) == 1
    monkeypatch.setattr(gate, 'read', Mock(side_effect=AssertionError('fresh must not touch gate')))
    assert ordered.commit_next('synthetic', NOW + 60)['segment_id'] == 'f1'


def test_depth_still_holds_without_a_marker():
    store = MemoryStore()
    ready(store, 'a')
    ready(store, 'b')
    opened(store)
    assert merge(store, depth=1)
    assert merge(store, depth=1) is None and tokens(store) == 1
    assert not any(table == 'merge_holds' for table, _ in store.rows)


@pytest.mark.parametrize('error_type', [ServiceUnavailable, Aborted])
def test_read_error_fallback_and_fresh(error_type, monkeypatch, caplog):
    store = MemoryStore()
    ready(store, 'a')
    get = MemoryTransaction.get

    def fail(tx, table, key):
        if table == 'backlog_release':
            raise error_type('synthetic failure')
        return get(tx, table, key)

    monkeypatch.setattr(MemoryTransaction, 'get', fail)
    fallback = Mock()
    monkeypatch.setattr(gate, 'record_fallback', fallback)
    if error_type is Aborted:
        with pytest.raises(Aborted):
            merge(store)
        fallback.assert_not_called()
    else:
        assert merge(store) is None
        fallback.assert_called_once()
        assert (
            'outcome=backlog_gate_unavailable source=ordered_merge exception_type=ServiceUnavailable count=1'
            in caplog.text
        )
    ready(store, 'f', fresh=True)
    assert merge(store)['segment_id'] == 'f'


@pytest.mark.parametrize('retry', [False, True])
def test_atomic_abort_and_retry(retry, monkeypatch):
    customer = CustomerData()
    customer.add_user('synthetic')
    store = SimStore(customer)
    ready(store, 'a')
    opened(store)
    run, injected = store.run, []

    def wrapped(body):
        def abort_once(tx):
            result = body(tx)
            if result and not injected:
                injected.append(True)
                raise Aborted('after computing token and buffering writes')
            return result

        try:
            return run(abort_once)
        except Aborted:
            assert tokens_original() == 0
            if not retry:
                raise
            return run(abort_once)

    tokens_original = lambda: run(lambda tx: tx.get('backlog_release', 'gate'))['tokens_used']
    monkeypatch.setattr(store, 'run', wrapped)
    if retry:
        assert merge(store)['backlog_release'] is True and tokens_original() == 1
    else:
        with pytest.raises(Aborted):
            merge(store)
        assert tokens_original() == 0 and ('results', 'a') not in store.rows


@pytest.mark.parametrize('metered', [True, False])
def test_simulated_flood_preserves_fresh_priority_and_hourly_cap(metered, monkeypatch):
    monkeypatch.setenv(METER, str(metered).lower())
    monkeypatch.setenv(RELEASE, 'true')
    customer = CustomerData()
    owners = [f'synthetic-{i}' for i in range(6)]
    for owner in owners:
        customer.add_user(owner)
    store = SimStore(customer)
    for owner in owners:
        for n in range(8):
            ready(store, f'{owner}-old-{n}', owner=owner, capture=n)
    for hour in range(2):
        now = NOW + 3600 * hour
        opened(store, now)
        released = 0
        for turn in range(2):
            for owner in owners:
                fresh = f'{owner}-fresh-{hour}-{turn}'
                ready(store, fresh, owner=owner, fresh=True, capture=now)
                first = merge(store, now, owner, depth=1)
                if not metered and first['segment_id'] != fresh:
                    released += 1
                    first = merge(store, now, owner, depth=1)
                assert first['segment_id'] == fresh and 'backlog_release' not in first
                key = owner_key(owner)
                state = store.run(lambda tx: tx.get('owners', key))
                put(store, 'owners', key, {**state, 'projection_watermark': fresh})
                backlog = merge(store, now, owner, depth=1)
                released += bool(backlog)
                state = store.run(lambda tx: tx.get('owners', key))
                put(
                    store, 'owners', key, {**state, 'projection_watermark': backlog['segment_id'] if backlog else fresh}
                )
        assert released == (2 if metered else 24)
        assert tokens(store) == (2 if metered else 0)
