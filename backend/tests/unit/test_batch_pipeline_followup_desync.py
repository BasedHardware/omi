"""Follow-up desync: per-process discovery offset, bounded backoff, kill switch, slots."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.batch_pipeline import projection_followup_backoff_seconds, projection_followup_slots
from database.batch_pipeline_store import PROJECTION_FINISH_STATES, projection_page
from utils.batch_pipeline import projection_followup
from utils.batch_pipeline.projection_followup import BACKOFF_BASE_SECONDS, MAX_FOLLOWUPS, ProjectionFollowups

KNOB = 'BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS'


class ResultQuery:
    """Keyset query fake with both cursor forms the real page uses."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def collection(self, _):
        return self

    def where(self, field, op, values):
        assert (field, op) == ('projection_state', 'in')
        self.states, self.after, self.inclusive = values, None, False
        return self

    def order_by(self, _):
        return self

    def start_after(self, cursor):
        self.after, self.inclusive = (cursor['committed_at'], cursor['__name__']), False
        return self

    def start_at(self, cursor):
        assert set(cursor) == {'committed_at'}
        self.after, self.inclusive = (cursor['committed_at'],), True
        return self

    def document(self, key):
        return key

    def limit(self, size):
        self.size = size
        return self

    def stream(self):
        def keep(entry):
            if self.after is None:
                return True
            return entry[:1] >= self.after if self.inclusive else entry > self.after

        rows = sorted(
            (row['committed_at'], key) for key, row in self.rows.items() if row['projection_state'] in self.states
        )
        page = [entry for entry in rows if keep(entry)][: self.size]
        self.calls.append((self.after, self.size))
        return [SimpleNamespace(id=key, to_dict=lambda key=key: dict(self.rows[key])) for _, key in page]


def runner(rows, monkeypatch, *, fraction=0.0, now=None):
    query = ResultQuery(rows)
    store = Mock()
    store.projection_page.side_effect = lambda **kw: projection_page(query, 'batch_pipeline_dev', **kw)
    projector = Mock()
    projector.store.store = store
    monkeypatch.setattr(projection_followup, 'instance_fraction', lambda: fraction)
    projector.clock = (lambda: now) if now is not None else (lambda: 1e12)
    followups = ProjectionFollowups(projector)
    followups.discovery.states = PROJECTION_FINISH_STATES
    return followups, query


def backlog(count):
    return {f'r{i:03d}': {'projection_state': 'persisted', 'committed_at': 1000.0 + i} for i in range(count)}


def test_offset_starts_mid_backlog_and_one_cycle_still_visits_every_row(monkeypatch):
    rows = backlog(250)
    followups, query = runner(rows, monkeypatch, fraction=0.5, now=1250.0)
    pages = [followups.discovered() for _ in range(4)]
    # Seed: one 1-row head read, then the first page starts at 1000 + 0.5 * 250.
    assert query.calls[0] == (None, 1)
    assert pages[0][0] == 'r125' and pages[0][-1] == 'r224'
    assert pages[1] == [f'r{i:03d}' for i in range(225, 250)]  # end of the log: wrap
    assert pages[2][0] == 'r000'
    assert set().union(*pages) == set(rows)


@pytest.mark.parametrize('fraction', [0.0, 0.37, 0.999999])
def test_every_offset_covers_every_row_within_one_wrap(monkeypatch, fraction):
    rows = backlog(333)
    followups, _ = runner(rows, monkeypatch, fraction=fraction, now=1333.0)
    seen, wrapped = set(), 0
    for _ in range(20):
        page = followups.discovered()
        seen.update(page)
        wrapped += followups.discovery.after is None
        if wrapped >= 2:
            break
    assert seen == set(rows)


def test_seed_runs_once_and_fails_open(monkeypatch):
    rows = backlog(10)
    followups, query = runner(rows, monkeypatch, now=1010.0)
    followups.discovered()
    followups.discovered()
    assert [call for call in query.calls if call[1] == 1] == [(None, 1)]

    broken, _ = runner(rows, monkeypatch, now=1010.0)
    broken.projector.store.store.projection_page.side_effect = [RuntimeError('index'), (['r000'], None)]
    assert broken.discovered() == ['r000']  # head-first, as before
    assert broken.seeded


def test_empty_or_future_head_keeps_head_first(monkeypatch):
    followups, _ = runner({}, monkeypatch, now=1000.0)
    assert followups.discovered() == []
    assert followups.discovery.after is None


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(projection_followup, '_monotonic', clock.monotonic)
    return clock


def test_backoff_is_bounded_doubles_and_clears_on_progress(monkeypatch, clock):
    monkeypatch.setenv(KNOB, '900')
    followups, _ = runner(backlog(1), monkeypatch)
    delays = []
    for _ in range(7):
        followups.note('r000', 'blocked')
        delays.append(followups.backoff['r000'][1])
    assert delays == [60.0, 120.0, 240.0, 480.0, 900.0, 900.0, 900.0]
    assert followups.backed_off('r000')
    clock.now += 899.9
    assert followups.backed_off('r000')
    clock.now += 0.2
    assert not followups.backed_off('r000')
    assert followups.discovered() == ['r000']
    followups.note('r000', 'completed')
    assert 'r000' not in followups.backoff


@pytest.mark.parametrize('outcome', ['blocked', 'retry', 'timeout', 'incomplete'])
def test_failed_outcomes_back_off_one_base_step(monkeypatch, clock, outcome):
    followups, _ = runner(backlog(2), monkeypatch)
    followups.note('r000', outcome)
    assert followups.discovered() == ['r001']
    clock.now += BACKOFF_BASE_SECONDS
    assert followups.discovered() == ['r000', 'r001']


def test_claimed_elsewhere_waits_one_step_without_escalating(monkeypatch, clock):
    followups, _ = runner(backlog(1), monkeypatch)
    for _ in range(5):
        followups.note('r000', 'claim_busy')
    assert followups.backoff['r000'][1] == BACKOFF_BASE_SECONDS


def test_backoff_memory_is_bounded(monkeypatch, clock):
    monkeypatch.setattr(projection_followup, 'MAX_BACKOFF_ROWS', 3)
    followups, _ = runner(backlog(1), monkeypatch)
    for i in range(10):
        followups.note(f's{i}', 'blocked')
    assert len(followups.backoff) <= 3


def test_kill_switch_restores_head_first_and_immediate_retry(monkeypatch, clock):
    monkeypatch.setenv(KNOB, '0')
    followups, query = runner(backlog(5), monkeypatch, now=1005.0)
    assert followups.discovered()[0] == 'r000'
    assert query.calls == [(None, 100)]  # no seed read
    followups.note('r000', 'blocked')
    assert followups.backoff == {}
    assert followups.discovered()[0] == 'r000'


@pytest.mark.asyncio
async def test_targeted_wake_bypasses_this_process_backoff(monkeypatch, clock):
    followups, _ = runner(backlog(1), monkeypatch)
    followups.note('r000', 'blocked')
    followups.run = AsyncMock(return_value=None)
    await followups.schedule(['r000'], discover=False)
    await asyncio.gather(*list(followups.tasks.values()))
    followups.run.assert_awaited_once_with('r000')


@pytest.mark.asyncio
async def test_run_records_the_outcome_and_timeout(monkeypatch, clock):
    followups, _ = runner(backlog(1), monkeypatch)
    followups._run = AsyncMock(return_value='claim_busy')
    await followups.run('r000')
    assert followups.backoff['r000'][1] == BACKOFF_BASE_SECONDS

    async def stuck(_):
        await asyncio.Event().wait()

    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 0.01)
    followups._run = stuck
    await followups.run('r001')
    assert 'r001' in followups.backoff


@pytest.mark.asyncio
async def test_claim_not_acquired_is_reported_as_claim_busy(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def busy(namespace, key):
        yield False

    monkeypatch.setattr(projection_followup, 'projection_claim', busy)
    followups, _ = runner(backlog(1), monkeypatch)
    followups.projector.store.store.namespace = 'batch_pipeline_dev'
    assert await followups._run('r000') == 'claim_busy'


@pytest.mark.parametrize(
    ('raw', 'expected'), [(None, MAX_FOLLOWUPS), ('8', 8), ('16', 16), ('0', 4), ('17', 4), ('x', 4), (' ', 4)]
)
def test_slots_are_env_tunable_and_malformed_keeps_default(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_SLOTS', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_SLOTS', raw)
    assert projection_followup_slots(4) == expected


@pytest.mark.asyncio
async def test_slots_bound_concurrent_followups(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_SLOTS', '2')
    followups, _ = runner(backlog(1), monkeypatch)
    release = asyncio.Event()

    async def wait(_):
        await release.wait()

    followups.run = AsyncMock(side_effect=wait)
    followups.pending.extend(['a', 'b', 'c'])
    followups.launch()
    assert sorted(followups.tasks) == ['a', 'b']
    release.set()
    while followups.tasks:
        await asyncio.gather(*list(followups.tasks.values()))


@pytest.mark.parametrize(
    ('raw', 'expected'), [(None, 900.0), ('0', 0.0), ('120', 120.0), ('3600', 3600.0), ('-1', 900.0), ('nan', 900.0)]
)
def test_backoff_knob_parsing(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(KNOB, raising=False)
    else:
        monkeypatch.setenv(KNOB, raw)
    assert projection_followup_backoff_seconds() == expected


def test_seed_past_the_newest_row_wraps_to_the_head_in_the_same_pass(monkeypatch):
    rows = backlog(10)
    followups, _ = runner(rows, monkeypatch, fraction=0.5, now=1e12)  # projector clock ahead of commit stamps
    assert followups.discovered() == [f'r{i:03d}' for i in range(10)]


def test_seed_never_moves_a_cursor_discovery_already_holds(monkeypatch):
    rows = backlog(10)
    followups, query = runner(rows, monkeypatch, fraction=0.5, now=1010.0)
    followups.discovery.after = (1007.0, 'r007')
    assert followups.discovered() == ['r008', 'r009']
    assert [call for call in query.calls if call[1] == 1] == []
