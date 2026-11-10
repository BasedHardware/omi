"""Owner-hash projection shards, the shard pump and the blocked-head deadline.

Leases and wakes run against fakeredis (real Lua). The pump and serving
wiring use small fakes; chain walks use the owner-chain ``ResultLog`` model.
"""

import asyncio
from collections import Counter
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest
from google.api_core import exceptions as api_exceptions  # noqa: F401 (parity with chain tests)

from config import batch_pipeline as batch_config
from database.batch_pipeline_projection import ProjectionBlocked
from database.batch_pipeline_store import FirestoreStore
from database.jobstore.postgres_store import PostgresStore
from testing.pipeline_sim.postgres_store import PgSimStore
from testing.pipeline_sim.store import CustomerData, SimStore
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain
from utils.batch_pipeline import projection, projection_drain, projection_shard_pump, projection_shards
from utils.batch_pipeline.projection_shard_pump import ShardPump
from utils.batch_pipeline.projection_shards import BACKLOG, FRESH, ProjectionShards, Wake, share, shard_of
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving

ENV = (
    'BATCH_PROJECTION_SHARD_MEMBER',
    'BATCH_PROJECTION_SHARDS_ENABLED',
    'BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED',
    'BATCH_PROJECTION_HEAD_DEADLINE_SECONDS',
    'BATCH_PROJECTION_BACKLOG_RESERVE',
    'BATCH_PIPELINE_MAX_OWNER_DRAINS',
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize('mode', ('off', 'shadow', 'serve'))
@pytest.mark.parametrize(
    'name,read',
    (
        ('BATCH_PROJECTION_SHARDS_ENABLED', batch_config.projection_shards_enabled),
        ('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', batch_config.projection_blocked_head_deadline_enabled),
    ),
)
@pytest.mark.parametrize(
    'raw',
    (
        None,
        '',
        'true',
        '1',
        'on',
        'yes',
        ' TRUE ',
        ' ON ',
        ' YeS ',
        'false',
        '0',
        'off',
        'no',
        'unknown',
        'enabled',
        '2',
    ),
)
def test_opt_in_flag_tokens_match_shared_parser(monkeypatch, mode, name, read, raw):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if raw is not None:
        monkeypatch.setenv(name, raw)
    assert read() is (raw is not None and raw.strip().lower() in {'true', '1', 'on', 'yes'})


@pytest.mark.parametrize(
    'raw,expected', ((None, True), ('true', True), ('false', False), (' FALSE ', False), ('unknown', True))
)
def test_shard_membership_keeps_documented_default_and_false_opt_out(monkeypatch, raw, expected):
    if raw is not None:
        monkeypatch.setenv('BATCH_PROJECTION_SHARD_MEMBER', raw)
    assert batch_config.projection_shard_member() is expected


@pytest.mark.parametrize(
    'name,read,default,low,high',
    (
        ('BATCH_PROJECTION_BACKLOG_RESERVE', batch_config.projection_backlog_reserve, 2, 0, 16),
        ('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', batch_config.projection_head_deadline_seconds, 86400, 3600, 604800),
    ),
)
def test_numeric_shard_flags_match_documented_bounds_and_fallback(monkeypatch, name, read, default, low, high):
    assert read() == default
    for raw, expected in (
        ('', default),
        ('unknown', default),
        (str(low - 1), default),
        (str(high + 1), default),
        (str(low), low),
        (str(high), high),
    ):
        monkeypatch.setenv(name, raw)
        assert read() == expected


@pytest.fixture
def server():
    return fakeredis.FakeServer()


def make(server, *, count=8, member=True, clock=lambda: 1000.0):
    client = fakeredis.FakeRedis(server=server)
    return ProjectionShards('ns', count=count, member=member, client=lambda: client, clock=clock)


def owner_in_shard(shard: int, count: int, prefix='owner') -> str:
    for n in range(10_000):
        owner = f'{prefix}-{n}'
        if shard_of(owner_key(owner), count) == shard:
            return owner
    raise AssertionError('no owner for shard')


class OwnerPageQuery:
    """Ordered result query: field existence, null-first timestamps and document-name ties."""

    def __init__(self, rows):
        self.rows = rows

    def collection(self, name):
        assert name.endswith('_results')
        return self

    def where(self, field, op, states):
        assert (field, op) == ('projection_state', 'in')
        self.states, self.after = states, None
        return self

    def order_by(self, field):
        assert field in ('committed_at', '__name__')
        return self

    def document(self, key):
        return key

    def start_after(self, cursor):
        self.after = (cursor['committed_at'], cursor['__name__'])
        return self

    def start_at(self, cursor):
        self.after = (cursor['committed_at'], '')
        return self

    def limit(self, size):
        self.size = size
        return self

    def stream(self):
        def position(entry):
            return entry[0] is not None, entry[0] or 0.0, entry[1]

        ordered = sorted(
            (
                (row['committed_at'], key)
                for key, row in self.rows.items()
                if row.get('projection_state') in self.states and 'committed_at' in row
            ),
            key=position,
        )
        if self.after is not None:
            ordered = [entry for entry in ordered if position(entry) > position(self.after)]
        return [
            SimpleNamespace(id=key, to_dict=lambda key=key: dict(self.rows[key])) for _, key in ordered[: self.size]
        ]


@pytest.fixture(params=('firestore', 'postgres', 'sim', 'pgsim'))
def owner_page_store(request, monkeypatch):
    def make_store(rows):
        query = OwnerPageQuery(rows)
        if request.param == 'firestore':
            monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
            return FirestoreStore('batch_pipeline_dev', firestore_client=query)
        if request.param == 'sim':
            store = SimStore(CustomerData())
            store.rows.update({('results', key): dict(row) for key, row in rows.items()})
            return store

        class Connection:
            def execute(self, sql, params):
                # A single bounded result query must carry its routing metadata.
                assert sql.startswith('SELECT key, committed_at, doc FROM results WHERE namespace = %s ')
                assert 'projection_state = ANY(%s)' in sql and "doc ? 'committed_at'" in sql
                assert 'ORDER BY committed_at NULLS FIRST, key COLLATE "C" LIMIT %s' in sql
                assert params[0] == 'batch_pipeline_test_owner_page'
                query.where('projection_state', 'in', params[1])
                if len(params) == 5:
                    assert '(committed_at, key COLLATE "C") > (%s, %s)' in sql
                    query.start_after({'committed_at': params[2], '__name__': params[3]})
                elif len(params) == 4:
                    assert 'committed_at IS NULL AND key COLLATE "C" > %s' in sql
                    query.start_after({'committed_at': None, '__name__': params[2]})
                else:
                    assert len(params) == 3
                docs = query.limit(params[-1]).stream()
                return SimpleNamespace(
                    fetchall=lambda: [(doc.id, doc.to_dict()['committed_at'], doc.to_dict()) for doc in docs]
                )

        class Pool:
            @contextmanager
            def connection(self):
                yield Connection()

        if request.param == 'pgsim':
            return PgSimStore(CustomerData(), namespace='batch_pipeline_test_owner_page', pool=Pool())
        return PostgresStore('batch_pipeline_test_owner_page', pool=Pool(), customer_client=None)

    return make_store


def test_owner_pages_keep_raw_page_cursor_when_unroutable_rows_are_skipped(owner_page_store):
    store = owner_page_store(
        {
            'a': {'projection_state': 'pending', 'committed_at': 1, 'owner_id': 'first'},
            'b': {'projection_state': 'pending', 'committed_at': 1, 'owner_id': ''},
            'c': {'projection_state': 'ready', 'committed_at': 1, 'owner_id': 'last', 'capture_at': 0},
            'missing': {'projection_state': 'pending', 'owner_id': 'excluded'},
            'held': {'projection_state': 'quarantine_held', 'committed_at': 2, 'owner_id': 'held'},
        }
    )
    assert store.projection_page_owners(2) == ([('a', 'first', 1.0, None)], (1, 'b'))
    assert store.projection_page_owners(1, after=(1, 'a')) == ([], (1, 'b'))
    assert store.projection_page_owners(2, after=(1, 'b')) == ([('c', 'last', 1.0, 0)], None)
    assert store.projection_page_owners(2, after=(1, 'deleted-cursor')) == ([], None)
    assert store.projection_page_owners(states=('quarantine_held',)) == ([('held', 'held', 2.0, None)], None)


def test_owner_page_limits_and_timestamp_seed_match_firestore(owner_page_store):
    store = owner_page_store(
        {f'r{i:03}': {'projection_state': 'pending', 'committed_at': i // 2, 'owner_id': 'owner'} for i in range(150)}
    )
    page, cursor = store.projection_page_owners(999)
    assert len(page) == 100 and cursor == (49, 'r099')
    assert store.projection_page_owners(0) == ([('r000', 'owner', 0.0, None)], (0, 'r000'))
    assert store.projection_page_owners(1, after=(50, '')) == ([('r100', 'owner', 50.0, None)], (50, 'r100'))


def test_owner_pages_preserve_null_timestamp_cursor_and_wrap(owner_page_store):
    store = owner_page_store(
        {
            'null': {'projection_state': 'pending', 'committed_at': None, 'owner_id': 'owner'},
            'zero': {'projection_state': 'pending', 'committed_at': 0, 'owner_id': 'owner'},
        }
    )
    assert store.projection_page_owners(1) == ([('null', 'owner', 0.0, None)], (None, 'null'))
    assert store.projection_page_owners(1, after=(None, 'null')) == ([('zero', 'owner', 0.0, None)], (0, 'zero'))
    assert store.projection_page_owners(1, after=(0, 'zero')) == ([], None)


@pytest.mark.parametrize(
    'capture,expected', [(0, 0), (1.5, 1.5), (True, None), (False, None), (None, None), ('1', None)]
)
def test_owner_pages_only_return_numeric_capture_hints(owner_page_store, capture, expected):
    store = owner_page_store(
        {
            'a': {
                'projection_state': 'pending',
                'committed_at': 1,
                'owner_id': 'owner',
                'capture_at': capture,
            }
        }
    )
    assert store.projection_page_owners() == ([('a', 'owner', 1.0, expected)], None)


@pytest.mark.parametrize('owner', [None, '', False, 3])
def test_owner_pages_require_nonempty_string_owners(owner_page_store, owner):
    store = owner_page_store({'a': {'projection_state': 'pending', 'committed_at': 1, 'owner_id': owner}})
    assert store.projection_page_owners(1) == ([], (1, 'a'))


@pytest.mark.parametrize('states', [(), ('invalid',), None])
def test_owner_pages_reject_invalid_discovery_states(owner_page_store, states):
    with pytest.raises(ValueError, match='projection discovery states must be drain states'):
        owner_page_store({}).projection_page_owners(states=states)


# --- leases -----------------------------------------------------------------


def test_shard_of_is_stable_and_bounded():
    keys = [owner_key(f'u{n}') for n in range(500)]
    shards = [shard_of(key, 64) for key in keys]
    assert all(0 <= s < 64 for s in shards)
    assert shards == [shard_of(key, 64) for key in keys]
    assert len(set(shards)) > 50  # spreads
    assert share(64, 35) == 2 and share(64, 0) == 64 and share(8, 3) == 3


def test_members_cover_every_shard_exactly_once_and_balance(server):
    members = [make(server, count=16) for _ in range(5)]
    for _ in range(3):
        for member in members:
            assert member.refresh()
    held = [s for member in members for s in member.held]
    assert sorted(held) == list(range(16))
    assert max(len(m.held) for m in members) <= share(16, 5)
    assert all(m.unheld == set() for m in members[-1:])
    assert all(m.active for m in members)


def test_a_released_member_hands_its_shards_to_the_others(server):
    members = [make(server, count=12) for _ in range(3)]
    for _ in range(2):
        for member in members:
            member.refresh()
    gone = members.pop()
    released = set(gone.held)
    assert released
    gone.release()
    assert not gone.active and gone.held == set()
    for _ in range(3):
        for member in members:
            member.refresh()
    held = [s for member in members for s in member.held]
    assert sorted(held) == list(range(12))


def test_a_joining_member_takes_a_share_without_gaps(server):
    first = make(server, count=8)
    first.refresh()
    assert first.held == set(range(8))
    second = make(server, count=8)
    for _ in range(6):
        second.refresh()
        first.refresh()
        assert len(first.held | second.held) + len(first.unheld) >= 8
    assert sorted(first.held | second.held) == list(range(8))
    assert not first.held & second.held
    assert len(second.held) >= 3


def test_non_member_holds_nothing_and_releases_old_leases(server):
    member = make(server, count=4)
    member.refresh()
    observer = make(server, count=4, member=False)
    observer.refresh()
    assert observer.held == set() and observer.unheld == set()
    assert observer.covered(owner_key('anyone'))


def test_redis_failure_fails_open_to_inactive():
    def broken():
        raise ConnectionError('down')

    shards = ProjectionShards('ns', count=4, client=broken)
    assert shards.refresh() is False
    assert not shards.active and shards.held == set() and shards.unheld == set(range(4))
    assert shards.push('o', owner_key('o'), FRESH, 1.0) is False
    assert shards.take(FRESH, 10, shards=[0]) == []


# --- wakes ------------------------------------------------------------------


def test_fresh_wakes_come_newest_first_and_backlog_oldest_first(server):
    shards = make(server, count=1)
    shards.refresh()
    for owner, score in (('a', 10.0), ('b', 30.0), ('c', 20.0)):
        shards.push(owner, owner_key(owner), FRESH, score)
        shards.push(owner, owner_key(owner), BACKLOG, score)
    assert [w.owner_id for w in shards.take(FRESH, 10)] == ['b', 'c', 'a']
    assert [w.owner_id for w in shards.take(BACKLOG, 10)] == ['a', 'c', 'b']
    # Fresh keeps the newest capture, backlog the oldest commit.
    shards.push('a', owner_key('a'), FRESH, 40.0)
    shards.push('a', owner_key('a'), BACKLOG, 50.0)
    assert shards.take(FRESH, 1)[0].owner_id == 'a'
    assert shards.take(BACKLOG, 1)[0].owner_id == 'a'


def test_settle_keeps_a_wake_pushed_after_it_was_taken(server):
    shards = make(server, count=1)
    shards.refresh()
    shards.push('a', owner_key('a'), BACKLOG, 5.0)
    taken = shards.take(BACKLOG, 10)[0]
    shards.push('a', owner_key('a'), BACKLOG, 9.0)  # same score kept (lt), newer push
    assert shards.settle(taken) is False
    assert [w.owner_id for w in shards.take(BACKLOG, 10)] == ['a']
    assert shards.settle(shards.take(BACKLOG, 10)[0]) is True
    assert shards.take(BACKLOG, 10) == []


def test_take_interleaves_held_shards(server):
    shards = make(server, count=2)
    shards.refresh()
    for n in range(3):
        for shard in (0, 1):
            owner = owner_in_shard(shard, 2, prefix=f's{shard}n{n}')
            shards.push(owner, owner_key(owner), BACKLOG, float(n))
    lanes = [w.shard for w in shards.take(BACKLOG, 3)]
    assert lanes[:2] in ([0, 1], [1, 0])
    assert Counter(lanes) == {0: 3, 1: 3}


# --- pump -------------------------------------------------------------------


class FakeDrains:
    def __init__(self, limit=4):
        self.limit = limit
        self.tasks: dict = {}
        self.queue: list = []
        self.delayed: dict = {}
        self.requested: list[str] = []
        self.on_idle = None

    @property
    def free_slots(self):
        return max(0, self.limit - len(self.tasks) - len(self.queue))

    def busy(self, owner):
        return owner in self.tasks or owner in self.queue or owner in self.delayed

    def retry_delay(self, owner):
        return 0.0

    def request(self, owners):
        for owner in owners:
            self.requested.append(owner)
            self.tasks[owner] = True

    def finish(self, owner, stop):
        self.tasks.pop(owner, None)
        self.on_idle(owner, stop)


class FakeProjector:
    def __init__(self, drains):
        self.drains = drains
        self.draining: set[str] = set()
        self.drain_requests: dict = {}
        self.local: list[str] = []

    def ensure_drains(self):
        return self.drains

    @property
    def owes_drains(self):
        return bool(self.drain_requests)

    def start_drains(self):
        self.drains.request(list(self.drain_requests))
        self.drain_requests = {}

    def request_local_drain(self, owner):
        self.local.append(owner)


@pytest.fixture
def blocking_inline(monkeypatch):
    async def inline(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(projection_shard_pump, 'run_blocking', inline)


def pump_for(server, *, limit=4, count=1):
    shards = make(server, count=count)
    drains = FakeDrains(limit)
    pump = ShardPump(FakeProjector(drains), shards)
    return pump, shards, drains


def test_route_keeps_local_drains_when_inactive_or_unheld(server):
    pump, shards, _ = pump_for(server, count=4)
    assert pump.route('o') is True  # never refreshed: inactive
    observer = make(server, count=4, member=False)
    observer.refresh()  # nobody holds anything
    pump.shards = observer
    assert pump.route('o') is True
    holder = make(server, count=4)
    holder.refresh()
    observer.refresh()
    assert pump.route('o') is False  # pushed to the holder's backlog lane
    assert [w.owner_id for w in holder.take(BACKLOG, 10)] == ['o']


def test_tick_takes_fresh_first_and_keeps_a_backlog_reserve(server, blocking_inline, monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_BACKLOG_RESERVE', '1')
    pump, shards, drains = pump_for(server, limit=3)
    for owner, score in (('f1', 3.0), ('f2', 2.0), ('f3', 1.0)):
        shards.push(owner, owner_key(owner), FRESH, score)
    shards.push('b1', owner_key('b1'), BACKLOG, 1.0)
    assert asyncio.run(pump.tick()) == 3
    assert drains.requested == ['f1', 'f2', 'b1']


def test_reserve_returns_to_fresh_when_no_backlog_waits(server, blocking_inline, monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_BACKLOG_RESERVE', '2')
    pump, shards, drains = pump_for(server, limit=3)
    for owner, score in (('f1', 3.0), ('f2', 2.0), ('f3', 1.0)):
        shards.push(owner, owner_key(owner), FRESH, score)
    assert asyncio.run(pump.tick()) == 3
    assert drains.requested == ['f1', 'f2', 'f3']


def test_end_settles_the_wake_and_a_stuck_owner_cools_down(server, blocking_inline):
    pump, shards, drains = pump_for(server, limit=2)
    now = [100.0]
    pump.monotonic = lambda: now[0]
    shards.clock = lambda: 1000.0 + now[0] - 100.0
    shards.push('done', owner_key('done'), FRESH, 2.0)
    shards.push('stuck', owner_key('stuck'), FRESH, 1.0)
    asyncio.run(pump.tick())
    drains.finish('done', 'end')
    drains.finish('stuck', 'blocked_other')
    asyncio.run(pump.tick())
    assert shards.take(FRESH, 10) == []
    # The stuck wake waits in backlog at its retry time, not at the lane head.
    assert shards.take(BACKLOG, 10) == []
    assert shards._client().zscore(shards._lane_key(BACKLOG, 0), 'stuck') > 1000.0
    assert drains.requested == ['done', 'stuck']  # stuck is cooling, not retaken
    now[0] += projection_shard_pump.STUCK_RETRY_SECONDS * 1.3
    asyncio.run(pump.tick())
    assert drains.requested == ['done', 'stuck', 'stuck']


def test_stuck_owners_cannot_fill_the_take_page(server, blocking_inline, monkeypatch):
    monkeypatch.setattr(projection_shard_pump, 'MAX_TAKE', 4)
    pump, shards, drains = pump_for(server, limit=2)
    stuck = [f'stuck-{n}' for n in range(6)]
    for n, owner in enumerate(stuck):
        shards.push(owner, owner_key(owner), BACKLOG, float(n))
    shards.push('due', owner_key('due'), BACKLOG, 500.0)
    for _ in range(3):
        asyncio.run(pump.tick())
        for owner in list(drains.tasks):
            drains.finish(owner, 'blocked_other')
    asyncio.run(pump.tick())
    assert 'due' in drains.requested
    assert drains.requested.count('due') == 1


@pytest.mark.parametrize('stop', sorted(projection_shard_pump.CLAIM_STOPS))
def test_claim_stops_defer_wakes_past_later_due_owners(server, blocking_inline, monkeypatch, stop):
    monkeypatch.setattr(projection_shard_pump, 'MAX_TAKE', 1)
    monkeypatch.setattr(projection_shard_pump.random, 'uniform', lambda a, b: 1.0)
    pump, shards, drains = pump_for(server, limit=1)
    now = [1000.0]
    shards.clock = pump.monotonic = lambda: now[0]
    shards.push('a', owner_key('a'), FRESH, 5.0)
    assert asyncio.run(pump.tick()) == 1
    drains.finish('a', stop)
    for n in range(3):
        shards.push(f'later-{n}', owner_key(f'later-{n}'), BACKLOG, 100.0 + n)
    for n in range(3):
        assert asyncio.run(pump.tick()) == 1
        assert drains.requested[-1] == f'later-{n}'
        drains.finish(f'later-{n}', 'end')
    assert shards._client().zscore(shards._lane_key(BACKLOG, 0), 'a') == (
        now[0] + projection_shard_pump.CLAIM_RETRY_SECONDS
    )
    now[0] += projection_shard_pump.CLAIM_RETRY_SECONDS
    assert asyncio.run(pump.tick()) == 1
    assert drains.requested == ['a', 'later-0', 'later-1', 'later-2', 'a']


def test_defer_keeps_a_wake_that_was_pushed_since_the_take(server):
    shards = make(server, count=1)
    assert shards.refresh()
    shards.push('a', owner_key('a'), FRESH, 5.0)
    (wake,) = shards.take(FRESH, 10)
    shards.push('a', owner_key('a'), FRESH, 6.0)
    assert shards.defer(wake, 9999.0) is False
    assert [w.score for w in shards.take(FRESH, 10)] == [6.0]
    (wake,) = shards.take(FRESH, 10)
    assert shards.defer(wake, 9999.0) is True
    assert shards.take(FRESH, 10) == []
    assert shards.take(BACKLOG, 10) == []
    shards.clock = lambda: 9999.0
    assert [(w.owner_id, w.score) for w in shards.take(BACKLOG, 10)] == [('a', 9999.0)]


def test_a_wake_pushed_during_the_drain_survives_the_settle(server, blocking_inline):
    pump, shards, drains = pump_for(server, limit=1)
    shards.push('a', owner_key('a'), FRESH, 1.0)
    asyncio.run(pump.tick())
    shards.push('a', owner_key('a'), FRESH, 1.0)  # another commit while draining
    drains.finish('a', 'end')
    asyncio.run(pump.tick())
    assert drains.requested == ['a', 'a']


def test_owner_in_both_lanes_drains_once_and_settles_both(server, blocking_inline):
    pump, shards, drains = pump_for(server, limit=4)
    shards.push('a', owner_key('a'), FRESH, 1.0)
    shards.push('a', owner_key('a'), BACKLOG, 1.0)
    asyncio.run(pump.tick())
    assert drains.requested == ['a']
    drains.finish('a', 'end')
    asyncio.run(pump.tick())
    assert shards.take(FRESH, 10) == [] and shards.take(BACKLOG, 10) == []


@pytest.mark.parametrize('reserve', [0, 1])
def test_stuck_owner_in_both_lanes_moves_behind_due_backlog(server, blocking_inline, monkeypatch, reserve):
    monkeypatch.setenv('BATCH_PROJECTION_BACKLOG_RESERVE', str(reserve))
    monkeypatch.setattr(projection_shard_pump, 'MAX_TAKE', 1)
    pump, shards, drains = pump_for(server, limit=1)
    shards.push('stuck', owner_key('stuck'), FRESH, 990.0)
    shards.push('stuck', owner_key('stuck'), BACKLOG, 1.0)
    shards.push('due', owner_key('due'), BACKLOG, 500.0)
    asyncio.run(pump.tick())
    assert {wake.lane for wake in pump.inflight['stuck']} == {FRESH, BACKLOG}
    drains.finish('stuck', 'blocked_other')
    asyncio.run(pump.tick())
    assert shards.take(FRESH, 10) == []
    backlog = shards.take(BACKLOG, 10)
    assert [wake.owner_id for wake in backlog] == ['due']
    assert shards._client().zscore(shards._lane_key(BACKLOG, 0), 'stuck') > 1000.0
    assert drains.requested == ['stuck', 'due']


@pytest.mark.parametrize('lane', [FRESH, BACKLOG])
def test_dual_lane_defer_preserves_a_push_during_the_drain(server, blocking_inline, lane):
    pump, shards, drains = pump_for(server, limit=1)
    shards.push('a', owner_key('a'), FRESH, 990.0)
    shards.push('a', owner_key('a'), BACKLOG, 1.0)
    asyncio.run(pump.tick())
    shards.push('a', owner_key('a'), lane, 995.0)
    drains.finish('a', 'blocked_other')
    asyncio.run(pump.tick())
    # New work retains its lane position even though the old turn stopped short.
    assert [(w.owner_id, w.score) for w in shards.take(lane, 10)] == [('a', 995.0 if lane == FRESH else 1.0)]


@pytest.mark.parametrize('source', ['direct', 'committed'])
def test_future_capture_wakes_use_backlog(server, source):
    pump, shards, _ = pump_for(server)
    shards.refresh()
    if source == 'direct':
        assert pump.wake('future', 1000.0 + 3600, 999.0)
    else:
        pump.committed('future', [{'capture_at': 1000.0 + 3600, 'committed_at': 999.0}])
    assert shards.take(FRESH, 10) == []
    (wake,) = shards.take(BACKLOG, 10)
    assert wake.owner_id == 'future' and wake.score == 999.0


def test_commit_wakes_pick_the_lane_from_capture_age(server, monkeypatch):
    monkeypatch.setattr(projection_shard_pump, 'FRESH_CAPTURE_SECONDS', 3600.0)
    pump, shards, _ = pump_for(server)
    shards.refresh()
    pump.committed('new', [{'capture_at': 1000.0 - 60, 'committed_at': 1000.0}])
    pump.committed('old', [{'capture_at': 1000.0 - 7200, 'committed_at': 999.0}])
    assert [w.owner_id for w in shards.take(FRESH, 10)] == ['new']
    assert [w.owner_id for w in shards.take(BACKLOG, 10)] == ['old']


def test_backstop_routes_owners_once_and_falls_back_locally_for_unheld(server):
    holder = make(server, count=2)
    holder.refresh()
    holder.release()  # nobody holds shard leases now
    member = make(server, count=2)
    member.refresh()
    lone = owner_in_shard(0, 2, prefix='lone')
    rows = [('s1', lone, 1.0, None), ('s2', lone, 2.0, None), ('s3', 'x', 3.0, None)]

    class Store:
        def projection_page_owners(self, *, limit, after, states):
            assert states == ('pending',)
            if after is not None:
                return [], None  # the tail: nothing committed lately
            return rows, None

    real = projection.Projector(Mock(), Mock())
    real.store = Mock()
    real.store.store = Store()
    pump = ShardPump(real, member)
    counts = pump.backstop()
    assert counts == {'pages': 1, 'rows': 3, 'owners': 2, 'wrapped': 1, 'tail_rows': 0, 'tail_owners': 0}
    assert sorted(w.owner_id for w in member.take(BACKLOG, 10)) == sorted({lone, 'x'})
    # Unheld shards drain where they were found.
    observer = make(server, count=2, member=False)
    member.release()
    observer.refresh()
    real.drain_requests.clear()
    ShardPump(real, observer).backstop()
    assert set(real.drain_requests) == {lone, 'x'}


def test_tail_discovery_wakes_gpu_commits_fresh_and_follows_the_newest_row(server):
    member = make(server, count=1)
    member.refresh()
    calls = []
    pages = {
        (940.0, ''): ([('s1', 'gpu-fresh', 995.0, 990.0), ('s2', 'gpu-old', 996.0, 1000.0 - 7 * 3600)], None),
        (986.0, ''): ([], None),
    }

    class Store:
        def projection_page_owners(self, *, limit, after, states):
            calls.append(after)
            if after is None:
                return [], None  # the whole-log backstop
            return pages[after]

    real = projection.Projector(Mock(), Mock(), clock=lambda: 1000.0)
    real.store = Mock()
    real.store.store = Store()
    pump = ShardPump(real, member)
    counts = pump.backstop()
    assert counts['tail_rows'] == 2 and counts['tail_owners'] == 2
    assert [w.owner_id for w in member.take(FRESH, 10)] == ['gpu-fresh']
    assert [(w.owner_id, w.score) for w in member.take(BACKLOG, 10)] == [('gpu-old', 996.0)]
    # Caught up: the next pass starts just before the newest row seen.
    assert real.tail_after == (996.0 - projection_shard_pump.TAIL_SLACK_SECONDS, '')
    pump.backstop()
    assert calls == [(940.0, ''), None, (986.0, ''), None]


@pytest.mark.parametrize('first_capture', [None, 1000.0 - 7 * 3600, 980.0, 995.0])
@pytest.mark.parametrize('split_pages', [False, True])
def test_tail_discovery_uses_the_owners_freshest_capture(server, first_capture, split_pages):
    shards = make(server, count=1)
    shards.refresh()
    rows = [('old', 'gpu', 995.0, first_capture), ('fresh', 'gpu', 996.0, 990.0)]
    pages = iter([(rows[:1], (995.0, 'old')), (rows[1:], None)] if split_pages else [(rows, None)])
    store = Mock()
    store.store.projection_page_owners.side_effect = lambda **kwargs: next(pages)
    real = projection.Projector(store, Mock(), clock=lambda: 1000.0)
    real.store = store
    pump = ShardPump(real, shards)
    routed = []

    def route(owner, committed, capture):
        routed.append((owner, committed, capture))
        assert pump.wake(owner, capture, committed)

    counts = real.discover_tail(route, pages=2, overlap_seconds=60.0, slack_seconds=10.0)
    expected_capture = max(first_capture or 990.0, 990.0)
    assert routed == [('gpu', 995.0, expected_capture)]
    assert counts == {'pages': 2 if split_pages else 1, 'rows': 2, 'owners': 1}
    assert [(w.owner_id, w.score) for w in shards.take(FRESH, 10)] == [('gpu', expected_capture)]
    assert shards.take(BACKLOG, 10) == []
    assert real.tail_after == (986.0, '')


def test_a_failed_take_turns_the_process_back_to_the_sweep(server):
    shards = make(server, count=2)
    assert shards.refresh() and shards.active
    shards._client = lambda: (_ for _ in ()).throw(ConnectionError('down'))
    assert shards.take(FRESH, 10) == []
    assert not shards.active


def test_kill_switches_disengage_the_pump(server, monkeypatch):
    pump, shards, _ = pump_for(server)
    shards.refresh()
    assert pump.engaged
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    assert not pump.engaged
    assert pump.route('o') is True


def test_a_settle_never_resets_the_push_sequence(server):
    shards = make(server, count=1)
    shards.refresh()
    shards.push('a', owner_key('a'), FRESH, 1.0)
    (first,) = shards.take(FRESH, 10)
    (stale,) = shards.take(FRESH, 10)  # a second take of the same push
    assert shards.settle(first)
    shards.push('a', owner_key('a'), FRESH, 2.0)  # new work after the settle
    assert not shards.settle(stale)
    assert [w.owner_id for w in shards.take(FRESH, 10)] == ['a']


def test_commits_on_an_unheld_shard_drain_locally(server):
    pump, shards, _ = pump_for(server, count=2)
    shards.refresh()
    shards.held = {0}
    shards.unheld = {1}
    lone = owner_in_shard(1, 2, prefix='lone')
    pump.committed(lone, [{'capture_at': 990.0, 'committed_at': 999.0}])
    assert pump.projector.local == [lone]


# --- serving wiring -----------------------------------------------------------


class Pump:
    def __init__(self, active):
        self.engaged = active
        self.backstops = 0
        self.commits = []

    def backstop(self):
        self.backstops += 1

    def committed(self, owner, entries):
        self.commits.append((owner, len(entries)))


def serving_with(pump, *, leads):
    service = Serving(Mock(), projector=Mock(), shard_pump=pump)
    service._leads = lambda periodic: leads
    service._maintain = lambda **kw: None
    service.merge = Mock(held_owners=set())
    return service


def test_sharded_reconcile_skips_the_sweep_and_only_the_leader_backstops():
    pump = Pump(active=True)
    follower = serving_with(pump, leads=False)
    follower.reconcile(periodic=True)
    follower.projector.sweep.assert_not_called()
    assert pump.backstops == 0 and follower.projector.has_async_followups is True
    leader = serving_with(pump, leads=True)
    leader.reconcile(periodic=True)
    leader.projector.sweep.assert_not_called()
    leader.projector.sweep_finish_only.assert_called_once()
    assert pump.backstops == 1


def test_inactive_shards_keep_the_legacy_sweep():
    service = serving_with(Pump(active=False), leads=False)
    service.reconcile(periodic=True)
    service.projector.sweep.assert_called_once()
    service = serving_with(None, leads=True)
    service.reconcile(periodic=True)
    service.projector.sweep.assert_called_once()


def test_drain_owner_pushes_one_wake_for_its_commits():
    pump = Pump(active=True)
    service = serving_with(pump, leads=False)
    entries = iter([{'capture_at': 1.0}, {'capture_at': 2.0}, None])
    service.merge.commit_next = lambda owner, now, release=None: next(entries)
    service.drain_owner('owner-1')
    assert pump.commits == [('owner-1', 2)]
    service.merge.commit_next = lambda owner, now, release=None: None
    service.drain_owner('owner-2')
    assert pump.commits == [('owner-1', 2)]


# --- blocked-head deadline ----------------------------------------------------


def blocked_session(log, ids, message, *, refusals):
    real = log.session
    attempts = {'n': 0}

    def session(sid, *args, **kwargs):
        if sid == ids[0]:
            attempts['n'] += 1
            if attempts['n'] <= refusals:
                raise ProjectionBlocked(message)
        return real(sid, *args, **kwargs)

    log.session = session


def walker(log):
    projector = projection.Projector(log, Mock(), clock=lambda: 1000.0)
    projector.store = log
    return projector


def test_blocked_head_waits_forever_with_the_switch_off():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    blocked_session(log, ids, 'validated VAD speech accounting required', refusals=10**6)
    projector = walker(log)
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'pending'
    assert 'projection_blocked_since' not in log.results[ids[0]]


def test_eligible_blocked_head_is_held_after_the_deadline(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', '3600')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    # Refusals: the first pass, the in-bound second pass, the past-bound assignment.
    blocked_session(log, ids, 'validated VAD speech accounting required', refusals=3)
    projector = walker(log)
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'pending'
    assert log.results[ids[0]]['projection_blocked_since'] == 1000.0
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'pending'
    assert log.results[ids[0]]['projection_block_type'] == projection.blocked_head_type(
        ProjectionBlocked('validated VAD speech accounting required')
    )
    log.results[ids[0]]['projection_blocked_since'] = 1000.0 - 3601
    projector.project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'quarantine_held'
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]


def test_a_stamp_from_another_failure_restarts_the_blocked_clock(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', '3600')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    blocked_session(log, ids, 'recovery result requires recovery handoff', refusals=10**6)
    # A transient error stamped this head long ago; the refusal is new.
    log.results[ids[0]].update(projection_blocked_since=0.0, projection_block_type='TimeoutError')
    projector = walker(log)
    projector.project_owner(BURST)
    row = log.results[ids[0]]
    assert row['projection_state'] == 'pending'
    assert row['projection_blocked_since'] == 1000.0
    assert row['projection_block_type'] == projection.blocked_head_type(
        ProjectionBlocked('recovery result requires recovery handoff')
    )


@pytest.mark.parametrize('message_a', sorted(projection.BLOCKED_HEAD_DEADLINE_MESSAGES))
@pytest.mark.parametrize('change', ['message', 'reason'])
def test_changed_message_refusal_gets_a_fresh_deadline(monkeypatch, message_a, change):
    monkeypatch.setenv('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', '3600')
    message_b = (
        next(message for message in sorted(projection.BLOCKED_HEAD_DEADLINE_MESSAGES) if message != message_a)
        if change == 'message'
        else message_a
    )
    log = ResultLog()
    ids = chain(log, BURST, 'a', 1)
    real_session = log.session
    refusal = [message_a]
    reason = ['invalid_recording_clock' if change == 'reason' else None]

    def session(sid, *args, **kwargs):
        if refusal[0] is not None:
            error = ProjectionBlocked(refusal[0])
            if reason[0] is not None:
                error.block_reason = reason[0]
            raise error
        return real_session(sid, *args, **kwargs)

    log.session = session
    projector = walker(log)
    now = [1000.0]
    projector.clock = lambda: now[0]
    projector.project_owner(BURST)
    row = log.results[ids[0]]
    first_type = row['projection_block_type']
    assert row['projection_blocked_since'] == 1000.0
    hold = Mock(return_value=True)
    monkeypatch.setattr(projector, '_hold_failing_head', hold)
    # A's expired episode must not hold a newly observed B refusal.
    now[0] = 4601.0
    refusal[0] = message_b
    if change == 'reason':
        reason[0] = 'invalid_recording_identity'
    projector.project_owner(BURST)
    assert row['projection_state'] == 'pending'
    assert row['projection_blocked_since'] == 4601.0
    assert row['projection_block_type'] != first_type
    hold.assert_not_called()
    projector.project_owner(BURST)
    assert row['projection_blocked_since'] == 4601.0


def test_a_walk_past_a_held_head_reports_the_chain_end(monkeypatch):
    monkeypatch.setenv('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', 'true')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    blocked_session(
        log, ids, 'validated VAD speech accounting required', refusals=1
    )  # The test session refuses; the real refusal is in assignment.
    log.results[ids[0]].update(
        projection_blocked_since=1000.0 - 86401,
        projection_block_type=projection.blocked_head_type(
            ProjectionBlocked('validated VAD speech accounting required')
        ),
    )
    from contextlib import contextmanager

    @contextmanager
    def claim(namespace, key):
        yield True

    monkeypatch.setattr(projection, 'projection_claim', claim)
    walk = walker(log).drain_step(BURST, 60.0)
    assert log.results[ids[0]]['projection_state'] == 'quarantine_held'
    assert walk.advanced == ids and walk.stop == 'end'


@pytest.mark.parametrize(
    'message',
    [
        'projection assignment claim busy',
        'shadow publication forbidden',
        'authenticated intake manifest loader required',
    ],
)
def test_ineligible_blocked_heads_never_take_the_deadline(monkeypatch, message):
    monkeypatch.setenv('BATCH_PROJECTION_BLOCKED_HEAD_DEADLINE_ENABLED', 'true')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 1)
    blocked_session(log, ids, message, refusals=10**6)
    log.results[ids[0]].update(projection_blocked_since=0.0, projection_block_type='ProjectionBlocked:other')
    walker(log).project_owner(BURST)
    assert log.results[ids[0]]['projection_state'] == 'pending'


def test_eligibility_uses_closed_reasons_and_exact_messages():
    from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending

    reasoned = ProjectionBlocked('anything')
    reasoned.block_reason = 'invalid_recording_clock'
    assert projection.blocked_head_deadline_eligible(reasoned)
    assert projection.blocked_head_deadline_eligible(ProjectionBlocked('terminal empty recovery evidence required'))
    assert not projection.blocked_head_deadline_eligible(ProjectionBlocked('projection assignment claim busy'))
    assert not projection.blocked_head_deadline_eligible(
        ProjectionPredecessorPending('validated VAD speech accounting required')
    )


def test_head_deadline_is_configurable_and_bounded(monkeypatch):
    entry = {'projection_blocked_since': 0.0}
    assert not projection.head_retry_bound_exceeded(entry, 24 * 3600.0)
    assert projection.head_retry_bound_exceeded(entry, 24 * 3600.0 + 1)
    monkeypatch.setenv('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', '7200')
    assert projection.head_retry_bound_exceeded(entry, 7201)
    monkeypatch.setenv('BATCH_PROJECTION_HEAD_DEADLINE_SECONDS', '60')  # below the floor: default
    assert not projection.head_retry_bound_exceeded(entry, 7201)
    assert not projection.head_retry_bound_exceeded({'projection_blocked_since': True}, 10**9)


def test_a_drain_task_that_raised_never_reports_the_chain_end(monkeypatch):
    from utils.batch_pipeline import projection_drain

    def boom(namespace, key):
        raise RuntimeError('admission failed')

    monkeypatch.setattr(projection_drain, 'projection_claim_held', boom)
    projector = Mock()
    projector.draining = set()
    drains = projection_drain.OwnerDrains(projector)
    seen = []
    drains.on_idle = lambda owner, stop: seen.append((owner, stop))

    async def go():
        drains.request(['a'])
        await asyncio.gather(*drains.tasks.values(), return_exceptions=True)
        await asyncio.sleep(0)

    asyncio.run(go())
    assert seen == [('a', 'error')]


def test_a_kill_switched_member_hands_its_shards_to_engaged_members(server, blocking_inline, monkeypatch):
    pumps = []
    for _ in range(2):
        shards = make(server, count=4)
        pumps.append(ShardPump(FakeProjector(FakeDrains(4)), shards))
    for _ in range(3):
        for pump in pumps:
            pump.shards.refresh()
    assert pumps[0].shards.held and pumps[1].shards.held
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    asyncio.run(pumps[0].tick())
    assert pumps[0].shards.held == set() and not pumps[0].shards.active
    # The engaged member sees one member left and takes every shard.
    pumps[1].shards.refresh()
    assert pumps[1].shards.held == set(range(4)) and pumps[1].shards.unheld == set()
    asyncio.run(pumps[0].tick())  # still switched off: no lease pass, no shards
    assert pumps[0].shards.held == set()
    monkeypatch.delenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED')
    asyncio.run(pumps[0].tick())
    assert pumps[0].shards.active  # switched back on: rejoins on the next lease pass


def test_future_capture_does_not_hide_a_valid_fresh_commit(server):
    pump, shards, _ = pump_for(server)
    shards.refresh()
    pump.committed(
        'mixed',
        [
            {'capture_at': 4600.0, 'committed_at': 999.0},
            {'capture_at': 990.0, 'committed_at': 998.0},
        ],
    )
    (wake,) = shards.take(FRESH, 10)
    assert wake.owner_id == 'mixed' and wake.score == 990.0
    assert shards.take(BACKLOG, 10) == []


@pytest.mark.parametrize('lane', [FRESH, BACKLOG])
def test_take_returns_only_due_wakes_without_hiding_them_behind_future_scores(server, lane):
    now = [1000.0]
    shards = make(server, count=1, clock=lambda: now[0])
    shards.refresh()
    shards.push('due', owner_key('due'), lane, 1000.0)
    shards.push('future', owner_key('future'), lane, 1050.0)
    client = shards._client()
    lane_key, seq_key = shards._lane_key(lane, 0), shards._seq_key(lane, 0)
    before = client.zrange(lane_key, 0, -1, withscores=True), client.hgetall(seq_key)
    assert [(w.owner_id, w.score) for w in shards.take(lane, 1)] == [('due', 1000.0)]
    now[0] = 1049.99
    assert [w.owner_id for w in shards.take(lane, 10)] == ['due']
    assert (client.zrange(lane_key, 0, -1, withscores=True), client.hgetall(seq_key)) == before
    now[0] = 1050.0
    assert [w.owner_id for w in shards.take(lane, 10)] == (['future', 'due'] if lane == FRESH else ['due', 'future'])


@pytest.mark.parametrize('stop', ['blocked_other', 'yielded'])
def test_new_holder_honors_persisted_retry_without_reserving_backlog_slots(server, blocking_inline, monkeypatch, stop):
    monkeypatch.setenv('BATCH_PROJECTION_BACKLOG_RESERVE', '2')
    monkeypatch.setattr(projection_shard_pump.random, 'uniform', lambda a, b: 1.0)
    now = [1000.0]
    old, shards, old_drains = pump_for(server, limit=4)
    shards.clock = lambda: now[0]
    shards.push('retry', owner_key('retry'), FRESH, 990.0)
    assert asyncio.run(old.tick()) == 1
    old_drains.finish('retry', stop)
    assert asyncio.run(old.tick()) == 0  # Flush the deferred wake to Redis.
    client = shards._client()
    lane_key, seq_key = shards._lane_key(BACKLOG, 0), shards._seq_key(BACKLOG, 0)
    stored = client.zscore(lane_key, 'retry'), client.hget(seq_key, 'retry')
    retry_at = stored[0]
    assert retry_at > now[0]
    shards.release()
    replacement = make(server, count=1, clock=lambda: now[0])
    replacement.refresh()
    drains = FakeDrains(4)
    pump = ShardPump(FakeProjector(drains), replacement)
    assert pump.cooldown == {}  # New process has none of the old holder's state.
    for index in range(4):
        replacement.push(f'fresh{index}', owner_key(f'fresh{index}'), FRESH, 999.0 - index)
    assert asyncio.run(pump.tick()) == 4
    assert drains.requested == [f'fresh{i}' for i in range(4)]  # No premature backlog reserve.
    assert (client.zscore(lane_key, 'retry'), client.hget(seq_key, 'retry')) == stored
    for owner in list(drains.tasks):
        drains.finish(owner, 'end')
    now[0] = retry_at - 0.01
    assert asyncio.run(pump.tick()) == 0
    assert pump.cooldown == {}
    now[0] = retry_at
    assert asyncio.run(pump.tick()) == 1
    assert drains.requested[-1] == 'retry'


def test_pick_excludes_future_scores_before_calculating_backlog_reserve(server):
    pump, _, drains = pump_for(server, limit=3)
    fresh = [Wake('future-fresh', FRESH, 0, 1100.0)] + [Wake(f'fresh{i}', FRESH, 0, 999.0 - i) for i in range(3)]
    backlog = [Wake('future-backlog', BACKLOG, 0, 1100.0)]
    assert list(pump.pick(fresh, backlog, 3, drains)) == [f'fresh{i}' for i in range(3)]


@pytest.mark.parametrize('lanes', [(FRESH,), (BACKLOG,), (FRESH, BACKLOG)])
@pytest.mark.parametrize('stop', ['blocked_other', 'yielded'])
def test_discovery_replays_preserve_taken_retry_across_restart(server, blocking_inline, monkeypatch, lanes, stop):
    monkeypatch.setattr(projection_shard_pump.random, 'uniform', lambda a, b: 1.0)
    now = [1000.0]
    pump, shards, drains = pump_for(server, limit=1)
    shards.clock = pump.monotonic = lambda: now[0]
    for lane in lanes:
        shards.push('retry', owner_key('retry'), lane, 990.0 if lane == FRESH else 1.0)
    assert asyncio.run(pump.tick()) == 1

    def discover(pump):
        # Run both real discovery passes over the same pending row, as the leader does.
        real = projection.Projector(Mock(), Mock(), clock=lambda: now[0])
        real.store = SimpleNamespace(
            store=SimpleNamespace(projection_page_owners=lambda **kwargs: ([('row', 'retry', 995.0, 990.0)], None))
        )
        pump.projector.discover_tail = real.discover_tail
        pump.projector.discover_owners = real.discover_owners
        counts = pump.backstop()
        assert counts['tail_owners'] == counts['owners'] == 1

    def stored():
        return [
            (
                shards._client().zscore(shards._lane_key(lane, 0), 'retry'),
                shards._client().hget(shards._seq_key(lane, 0), 'retry'),
            )
            for lane in (FRESH, BACKLOG)
        ]

    before = stored()
    discover(pump)  # Replay while the turn is still active.
    assert stored() == before
    drains.finish('retry', stop)
    discover(pump)  # Replay between the idle callback and Redis deferral.
    assert asyncio.run(pump.tick()) == 0
    retry_at = now[0] + (1.0 if stop == 'yielded' else 120.0)
    assert shards._client().zscore(shards._lane_key(FRESH, 0), 'retry') is None
    assert shards._client().zscore(shards._lane_key(BACKLOG, 0), 'retry') == retry_at
    deferred = stored()

    shards.release()
    replacement = make(server, count=1, clock=lambda: now[0])
    replacement.refresh()
    next_drains = FakeDrains(1)
    next_pump = ShardPump(FakeProjector(next_drains), replacement, monotonic=lambda: now[0])
    assert next_pump.cooldown == {}
    discover(next_pump)  # Must neither pull backlog earlier nor recreate a fresh wake.
    assert stored() == deferred
    replacement.push('due-backlog', owner_key('due-backlog'), BACKLOG, 500.0)
    assert asyncio.run(next_pump.tick()) == 1
    assert next_drains.requested == ['due-backlog']
    next_drains.finish('due-backlog', 'end')
    now[0] = retry_at - 0.01
    discover(next_pump)
    assert asyncio.run(next_pump.tick()) == 0
    assert stored() == deferred
    now[0] = retry_at
    assert asyncio.run(next_pump.tick()) == 1
    assert next_drains.requested == ['due-backlog', 'retry']


@pytest.mark.parametrize('wake', (False, True))
def test_overflow_preserves_passive_hold_and_uses_local_shard_intent(monkeypatch, wake):
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 0)
    projector = Mock()
    drains = projection_drain.OwnerDrains(projector)
    assert not drains.defer('owner', delay=30.0, wake=wake)
    projector.request_drain.assert_not_called()
    if wake:
        projector.request_local_drain.assert_called_once_with('owner')
    else:
        projector.request_local_drain.assert_not_called()
    assert not drains.delayed


@pytest.mark.asyncio
async def test_passive_live_target_hold_returns_and_persists_the_shard_wake(server, blocking_inline, monkeypatch):
    monkeypatch.setattr(projection_drain, '_recurring_sweep', 'serving')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_PROJECTION_SWEEP', 'on')
    monkeypatch.setenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', 'on')
    now = [1000.0]
    pump, shards, _ = pump_for(server)
    shards.clock = lambda: now[0]
    pump.monotonic = lambda: now[0]
    shards.push('held', owner_key('held'), BACKLOG, 10.0)
    assert await pump.tick() == 1
    drains = projection_drain.OwnerDrains(pump.projector)
    pump.projector.drains = drains
    pump.attach()
    holds = []
    real_defer = drains.defer

    def hold(owner, *, delay, wake):
        holds.append((owner, delay, wake))
        return real_defer(owner, delay=delay, wake=wake)

    monkeypatch.setattr(drains, 'defer', hold)
    task = Mock()
    task.cancelled.return_value = False
    task.exception.return_value = None
    task.result.return_value = False
    drains.stops['held'] = 'head_awaiting_live_target'
    drains.finished('held', task)
    assert holds == [('held', 30, False)]
    assert 'held' in drains.delayed
    assert 'held' not in pump.inflight
    assert len(pump.deferring) == 1
    retry_at = pump.deferring[0][1]
    assert retry_at > now[0]
    assert await pump.tick() == 0
    assert shards._client().zscore(shards._lane_key(BACKLOG, 0), 'held') == retry_at
    replacement_drains = FakeDrains()
    replacement = ShardPump(FakeProjector(replacement_drains), shards, monotonic=lambda: now[0])
    now[0] = retry_at - 0.001
    assert await replacement.tick() == 0
    now[0] = retry_at
    assert await replacement.tick() == 1
    assert replacement_drains.requested == ['held']
    drains.close()
