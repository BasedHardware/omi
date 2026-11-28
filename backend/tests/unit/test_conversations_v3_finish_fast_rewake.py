"""A Finish whose recording changed under another builder pass is woken again in seconds, not at the next minute."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from database import (
    conversations_v3 as store,
    conversations_v3_finish_markers as markers,
    conversations_v3_leases as leases,
)
from utils.conversations.v3 import Conflict, finish_rewake, service
from utils.conversations.v3.finish_stamp import FINISH_STAMP_FIELD
from tests.unit.test_conversations_v3_review import builder, source  # noqa: F401


def _recent(**updates):
    finished = datetime.now(timezone.utc) - timedelta(seconds=20)
    return source(started_at=finished - timedelta(seconds=10), finished_at=finished, **updates)


class _Queue:
    """Cloud Tasks named-task dedupe: a name it already holds is refused (False)."""

    def __init__(self, events=None):
        self.tasks, self.events = [], events if events is not None else []

    def __call__(self, queue, url, task_id, payload, *, schedule_at=None):
        if any(task[0] == task_id for task in self.tasks):
            return False
        self.tasks.append((task_id, payload, schedule_at))
        self.events.append('rewake')
        return True


def _wakes(monkeypatch, events=None):
    async def blocking(_pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    wakes = []
    monkeypatch.setattr(service, 'enqueue', lambda uid, at=None, **kw: wakes.append((uid, at, kw)))
    queue = _Queue(events)
    monkeypatch.setattr(finish_rewake, 'enqueue_named_task', queue)
    monkeypatch.setattr(finish_rewake, 'task_base', lambda: 'https://sync.example')
    monkeypatch.setattr(finish_rewake, 'run_blocking', blocking)
    return wakes, queue


def _name(uid, rid, ordinal):
    owner, recording = (hashlib.sha256(value.encode()).hexdigest()[:32] for value in (uid, rid))
    return f'conversations-v3-{owner}-finish-rewake-{recording}-{ordinal}'


def _count(reason, outcome='scheduled'):
    return service.metrics.FINISH_REWAKES.labels(reason, outcome)._value.get()


def _raced(monkeypatch, reason='source_changed'):
    def conflict(*a, **kw):
        raise Conflict(reason)

    monkeypatch.setattr(service, '_commit', conflict)


@pytest.mark.asyncio
async def test_a_finish_that_moved_under_the_pass_is_woken_in_seconds(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(
        markers, 'finish_markers', lambda *a, **kw: pytest.fail('the loaded row already names a Finish')
    )
    wakes, queue = _wakes(monkeypatch)
    before, counted = datetime.now(timezone.utc), _count('source_moved')

    assert await service.reconcile('u') == 'committed'

    [(name, payload, at)] = queue.tasks
    assert name == _name('u', 'r', 1) and payload == {'uid': 'u'}
    assert (
        timedelta(0)
        < datetime.fromtimestamp(at, timezone.utc) - before
        <= finish_rewake.FINISH_REWAKE + timedelta(seconds=2)
    )
    # The minute wake stays as the backstop.
    assert any(wake[1] - before >= timedelta(seconds=50) and not wake[2] for wake in wakes)
    assert _count('source_moved') == counted + 1


@pytest.mark.asyncio
async def test_a_finish_written_after_the_load_is_read_from_the_stored_row(builder, monkeypatch):
    # The pass loaded live speech; the Finish request landed during the pass and moved the recording.
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    read = []

    def stored_markers(uid, ids):
        read.append((uid, list(ids)))
        return {'r': {'v3_manual_end_requested': True, 'finished_at': datetime.now(timezone.utc)}}

    monkeypatch.setattr(markers, 'finish_markers', stored_markers)
    _, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert read == [('u', ['r'])]
    assert [task[0] for task in queue.tasks] == [_name('u', 'r', 1)]


@pytest.mark.parametrize(
    'stored',
    [
        {},  # live speech only: no Finish
        {'v3_manual_end': True, 'finished_at': datetime(2026, 11, 16, tzinfo=timezone.utc)},  # an old Finish
        {'v3_manual_end': True, 'deleted': True, 'finished_at': None},
    ],
)
@pytest.mark.asyncio
async def test_live_speech_and_old_finishes_keep_only_the_minute_wake(builder, monkeypatch, stored):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(markers, 'finish_markers', lambda *a, **kw: {'r': stored})
    _, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert queue.tasks == []


@pytest.mark.asyncio
async def test_a_failed_marker_read_never_fails_the_committed_pass(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})

    def unavailable(*a, **kw):
        raise RuntimeError('synthetic read failure')

    monkeypatch.setattr(markers, 'finish_markers', unavailable)
    wakes, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert queue.tasks == [] and wakes


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['source_changed', 'lease_lost'])
async def test_a_raced_pass_with_a_pending_finish_is_woken_in_seconds(builder, monkeypatch, reason):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    _raced(monkeypatch, reason)
    wakes, queue = _wakes(monkeypatch)
    before, counted = datetime.now(timezone.utc), _count('raced')

    assert await service.reconcile('u') == 'raced'

    [(name, _, at)] = queue.tasks
    assert name == _name('u', 'r', 1)
    assert datetime.fromtimestamp(at, timezone.utc) - before <= finish_rewake.FINISH_REWAKE + timedelta(seconds=2)
    # The coalesced minute wake is still the first one scheduled.
    assert wakes[0][2] == {} and wakes[0][1] - before >= timedelta(seconds=50)
    assert _count('raced') == counted + 1


@pytest.mark.asyncio
async def test_a_raced_pass_of_live_speech_keeps_only_the_minute_wake(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    _raced(monkeypatch)
    monkeypatch.setattr(markers, 'finish_markers', lambda *a, **kw: {'r': {}})
    wakes, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'raced'
    assert len(wakes) == 1 and queue.tasks == []


@pytest.mark.asyncio
async def test_a_pass_raced_by_the_finish_write_itself_reads_the_stored_marker(builder, monkeypatch):
    # A live-window Finish writes its cut once; that write is what raced the pass, so the loaded row predates it.
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    _raced(monkeypatch)
    read = []

    def stored_markers(uid, ids):
        read.append((uid, list(ids)))
        return {'r': {'v3_manual_end': True, 'finished_at': datetime.now(timezone.utc)}}

    monkeypatch.setattr(markers, 'finish_markers', stored_markers)
    wakes, queue = _wakes(monkeypatch)
    counted = _count('raced')

    assert await service.reconcile('u') == 'raced'
    assert read == [('u', ['r'])]
    assert [task[0] for task in queue.tasks] == [_name('u', 'r', 1)]
    assert _count('raced') == counted + 1 and len(wakes) == 1


@pytest.mark.asyncio
async def test_a_raced_pass_that_loaded_a_finish_reads_no_markers(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    _raced(monkeypatch)
    monkeypatch.setattr(
        markers, 'finish_markers', lambda *a, **kw: pytest.fail('the loaded row already names a Finish')
    )
    _, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'raced'
    assert [task[0] for task in queue.tasks] == [_name('u', 'r', 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['moved', 'raced'])
async def test_a_failed_rewake_is_counted_as_an_error(builder, monkeypatch, path):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    if path == 'raced':
        _raced(monkeypatch)
    else:
        monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})

    def unavailable(*a, **kw):
        raise RuntimeError('synthetic read failure')

    monkeypatch.setattr(markers, 'finish_markers', unavailable)
    wakes, queue = _wakes(monkeypatch)
    reason = 'raced' if path == 'raced' else 'source_moved'
    errors = _count(reason, 'error')

    assert await service.reconcile('u') == ('raced' if path == 'raced' else 'committed')
    assert queue.tasks == [] and wakes
    assert _count(reason, 'error') == errors + 1


@pytest.mark.asyncio
async def test_kill_switch_keeps_the_minute_wake_and_reads_nothing(builder, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_FAST_REWAKE', 'off')
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(markers, 'finish_markers', lambda *a, **kw: pytest.fail('switched off: no read'))
    wakes, queue = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert queue.tasks == [] and wakes


@pytest.mark.asyncio
async def test_a_perpetually_raced_finish_gets_at_most_the_limit_of_rewakes(builder, monkeypatch):
    # A deterministic guard (retained custody, task links) answers source_changed on every pass.
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    _raced(monkeypatch)
    wakes, queue = _wakes(monkeypatch)
    capped = _count('raced', 'capped')

    for _ in range(6):
        assert await service.reconcile('u') == 'raced'

    assert [task[0] for task in queue.tasks] == [
        _name('u', 'r', ordinal) for ordinal in range(1, finish_rewake.FINISH_REWAKE_LIMIT + 1)
    ]
    assert _count('raced', 'capped') == capped + 6 - finish_rewake.FINISH_REWAKE_LIMIT
    # Every pass still schedules its minute wake: the backstop.
    assert len(wakes) == 6


@pytest.mark.asyncio
async def test_the_task_name_carries_no_clock_across_a_minute_boundary(monkeypatch):
    _, queue = _wakes(monkeypatch)
    # Inside the last 3 s of a minute: now and now + FINISH_REWAKE fall in different minutes.
    late = datetime(2026, 11, 27, 20, 0, 58, 500000, tzinfo=timezone.utc)
    await finish_rewake.wake_soon('u', 'r', 'raced', late)
    await finish_rewake.wake_soon('u', 'r', 'raced', late + timedelta(seconds=2))
    await finish_rewake.wake_soon('u', 'r', 'raced', late + timedelta(seconds=4))

    assert queue.tasks == [
        (_name('u', 'r', 1), {'uid': 'u'}, int(datetime(2026, 11, 27, 20, 1, 2, tzinfo=timezone.utc).timestamp())),
        (_name('u', 'r', 2), {'uid': 'u'}, int(datetime(2026, 11, 27, 20, 1, 4, tzinfo=timezone.utc).timestamp())),
    ]
    # Another Finish of the same owner has its own names.
    await finish_rewake.wake_soon('u', 'r2', 'raced', late)
    assert queue.tasks[-1][0] == _name('u', 'r2', 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['moved', 'raced'])
async def test_the_rewake_is_scheduled_after_the_lease_is_released(builder, monkeypatch, path):
    events = []
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    if path == 'raced':
        _raced(monkeypatch)
    else:
        monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(leases, 'release', lambda *a: events.append('release'))
    _wakes(monkeypatch, events)

    await service.reconcile('u')
    assert events == ['release', 'rewake']


def test_recency_reads_the_finish_stamp_when_one_is_stored():
    now = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)
    old, fresh = now - timedelta(minutes=10), now - timedelta(seconds=20)
    stamped = lambda at, finished: {  # noqa: E731
        'v3_manual_end': True,
        'finished_at': finished,
        FINISH_STAMP_FIELD: {'at': at, 'path': 'tail'},
    }
    # A long recording's finished_at is its last speech; the stamp is when the owner tapped Finish.
    assert finish_rewake.recent_finish(stamped(fresh, old), now)
    assert not finish_rewake.recent_finish(stamped(old, fresh), now)
    assert finish_rewake.recent_finish({'v3_manual_end_requested': True, 'finished_at': fresh}, now)
    assert not finish_rewake.recent_finish({'finished_at': fresh, FINISH_STAMP_FIELD: {'at': fresh}}, now)


@pytest.mark.asyncio
async def test_a_moved_pass_reads_the_newest_moved_recordings_first(monkeypatch):
    now = datetime.now(timezone.utc)
    recordings = {f'r{i}': {'started_at': now - timedelta(minutes=30 - i)} for i in range(12)}
    read = []

    def stored_markers(uid, ids):
        read.append(list(ids))
        return {'r11': {'v3_manual_end': True, 'finished_at': now}}

    monkeypatch.setattr(markers, 'finish_markers', stored_markers)
    _, queue = _wakes(monkeypatch)

    await finish_rewake.after_moved('u', recordings, set(recordings))

    assert read == [[f'r{i}' for i in range(11, -1, -1)]]
    assert [task[0] for task in queue.tasks] == [_name('u', 'r11', 1)]


class _Snapshot:
    def __init__(self, rid, data):
        self.id, self._data, self.exists = rid, data, data is not None

    def to_dict(self):
        return self._data


class _Client:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def collection(self, name):
        return _Path(self, (name,))

    def get_all(self, refs, field_paths=None):
        self.calls.append(([ref.path for ref in refs], field_paths))
        return [_Snapshot(ref.path[-1], self.rows.get(ref.path[-1])) for ref in refs]


class _Path:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def document(self, name):
        return _Path(self.client, self.path + (name,))

    def collection(self, name):
        return _Path(self.client, self.path + (name,))


def test_finish_markers_reads_only_the_marker_fields_of_a_bounded_set():
    client = _Client({f'r{i}': {'v3_manual_end': True} for i in range(10)})
    ids = ['gone', *(f'r{i}' for i in range(9, -1, -1)), 'gone']

    rows = markers.finish_markers('u', ids, firestore_client=client)

    [(paths, fields)] = client.calls
    # The caller's order (likeliest Finishes first) decides which ids fit the bound.
    assert [path[-1] for path in paths] == ['gone', *(f'r{i}' for i in range(9, 2, -1))]
    assert len(paths) == markers.FINISH_MARKER_LIMIT
    assert set(fields) == set(markers.FINISH_MARKER_FIELDS) and 'transcript_segments' not in fields
    assert FINISH_STAMP_FIELD in fields
    assert set(rows) == {f'r{i}' for i in range(9, 2, -1)}
    assert markers.finish_markers('u', set(), firestore_client=client) == {} and len(client.calls) == 1
