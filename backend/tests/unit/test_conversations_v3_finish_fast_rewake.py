"""A Finish whose recording changed under another builder pass is woken again in seconds, not at the next minute."""

from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store, conversations_v3_finish_markers as markers
from utils.conversations.v3 import Conflict, finish_rewake, service
from tests.unit.test_conversations_v3_review import builder, source  # noqa: F401


def _recent(**updates):
    finished = datetime.now(timezone.utc) - timedelta(seconds=20)
    return source(started_at=finished - timedelta(seconds=10), finished_at=finished, **updates)


def _wakes(monkeypatch):
    async def blocking(_pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    wakes = []
    record = lambda uid, at=None, **kw: wakes.append((uid, at, kw))  # noqa: E731
    monkeypatch.setattr(service, 'enqueue', record)
    monkeypatch.setattr(finish_rewake, 'enqueue', record)
    monkeypatch.setattr(finish_rewake, 'run_blocking', blocking)
    return wakes


def _fast(wakes):
    return [wake for wake in wakes if str(wake[2].get('wake_key', '')).startswith('finish-rewake-')]


def _count(reason):
    return service.metrics.FINISH_REWAKES.labels(reason)._value.get()


@pytest.mark.asyncio
async def test_a_finish_that_moved_under_the_pass_is_woken_in_seconds(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(
        markers, 'finish_markers', lambda *a, **kw: pytest.fail('the loaded row already names a Finish')
    )
    wakes = _wakes(monkeypatch)
    before, counted = datetime.now(timezone.utc), _count('source_moved')

    assert await service.reconcile('u') == 'committed'

    fast = _fast(wakes)
    assert len(fast) == 1 and fast[0][0] == 'u'
    assert timedelta(0) < fast[0][1] - before <= finish_rewake.FINISH_REWAKE + timedelta(seconds=2)
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
        read.append((uid, set(ids)))
        return {'r': {'v3_manual_end_requested': True, 'finished_at': datetime.now(timezone.utc)}}

    monkeypatch.setattr(markers, 'finish_markers', stored_markers)
    wakes = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert read == [('u', {'r'})]
    assert len(_fast(wakes)) == 1


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
    wakes = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert _fast(wakes) == []


@pytest.mark.asyncio
async def test_a_failed_marker_read_never_fails_the_committed_pass(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})

    def unavailable(*a, **kw):
        raise RuntimeError('synthetic read failure')

    monkeypatch.setattr(markers, 'finish_markers', unavailable)
    wakes = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert _fast(wakes) == [] and wakes


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['source_changed', 'lease_lost'])
async def test_a_raced_pass_with_a_pending_finish_is_woken_in_seconds(builder, monkeypatch, reason):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent(v3_manual_end=True)}, {}, []))

    def conflict(*a, **kw):
        raise Conflict(reason)

    monkeypatch.setattr(service, '_commit', conflict)
    wakes = _wakes(monkeypatch)
    before, counted = datetime.now(timezone.utc), _count('raced')

    assert await service.reconcile('u') == 'raced'

    fast = _fast(wakes)
    assert len(fast) == 1 and fast[0][1] - before <= finish_rewake.FINISH_REWAKE + timedelta(seconds=2)
    # The coalesced minute wake is still the first one scheduled.
    assert wakes[0][2] == {} and wakes[0][1] - before >= timedelta(seconds=50)
    assert _count('raced') == counted + 1


@pytest.mark.asyncio
async def test_a_raced_pass_of_live_speech_keeps_only_the_minute_wake(builder, monkeypatch):
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))

    def conflict(*a, **kw):
        raise Conflict('source_changed')

    monkeypatch.setattr(service, '_commit', conflict)
    wakes = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'raced'
    assert len(wakes) == 1 and _fast(wakes) == []


@pytest.mark.asyncio
async def test_kill_switch_keeps_the_minute_wake_and_reads_nothing(builder, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_FAST_REWAKE', 'off')
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': _recent()}, {}, []))
    monkeypatch.setattr(service, '_commit', lambda *a, **kw: {'r'})
    monkeypatch.setattr(markers, 'finish_markers', lambda *a, **kw: pytest.fail('switched off: no read'))
    wakes = _wakes(monkeypatch)

    assert await service.reconcile('u') == 'committed'
    assert _fast(wakes) == [] and wakes


@pytest.mark.asyncio
async def test_wakes_in_one_slot_share_a_task_name(monkeypatch):
    wakes = _wakes(monkeypatch)
    at = datetime(2026, 11, 27, 20, 0, 0, tzinfo=timezone.utc)
    for offset in (1, 9, 10):
        await finish_rewake.wake_soon('u', 'raced', at + timedelta(seconds=offset))
    keys = [wake[2]['wake_key'] for wake in wakes]
    # Cloud Tasks deduplicates a repeated name, so one slot schedules one follow-up.
    assert keys[0] == keys[1] != keys[2]
    assert [wake[1] - (at + timedelta(seconds=o)) for wake, o in zip(wakes, (1, 9, 10))] == [
        finish_rewake.FINISH_REWAKE
    ] * 3


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
    ids = {f'r{i}' for i in range(10)} | {'gone'}

    rows = markers.finish_markers('u', ids, firestore_client=client)

    [(paths, fields)] = client.calls
    assert len(paths) == markers.FINISH_MARKER_LIMIT
    assert set(fields) == set(markers.FINISH_MARKER_FIELDS) and 'transcript_segments' not in fields
    assert set(rows) <= {path[-1] for path in paths} and 'gone' not in rows
    assert markers.finish_markers('u', set(), firestore_client=client) == {} and len(client.calls) == 1
