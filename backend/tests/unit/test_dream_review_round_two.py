"""Search truncation, distributed turn headroom and cold kill-switch regressions."""

import importlib.util
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.dream_agent import Caps
from database import dream_store, dream_turns
from models.agent_tools import Read, Search
from tests.support.dream_firestore import DreamFirestore
from utils.agent_capabilities import search
from utils.agent_capabilities.limits import SessionLimits
from utils.agent_capabilities.session import Session, serialized_bytes
from utils.llm.shaped_agent import Turn

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def search_source(monkeypatch, rows):
    monkeypatch.setattr(search.dream_history, 'history_page', lambda *a, **kw: list(rows))

    async def read(self, ref):
        return rows[ref.partition('/')[2]]

    monkeypatch.setattr(search.OwnerSearch, 'read', read)
    return search.OwnerSearch('synthetic-search-owner')


@pytest.mark.asyncio
async def test_search_keeps_fitting_hits_and_budget_after_oversized_hit(monkeypatch):
    small = {'content': 'Synthetic small fact.'}
    source = search_source(monkeypatch, {'small': small, 'oversized': {'content': 'x' * 2000}})
    session = Session('synthetic-search-owner', source, SessionLimits(read_bytes=400), {}, authority='user')
    result = await session.search(Search(collections=['memory_items', 'people']))
    assert result['results'] == [{'ref': 'memory_items/small', 'snippet': small['content']}]
    assert result['truncated'] is True and result['complete'] is False
    assert result['counts']['hydrated'] == 2
    assert result['counts']['read_bytes'] == serialized_bytes(small)
    assert session.read_bytes == 2 + max(serialized_bytes(result['results']), serialized_bytes(small))
    assert session.known == {'memory_items/small'}
    # The omitted hit did not exhaust the budget or hide the useful ref.
    loaded = await session.read(Read(refs=['memory_items/small']))
    assert loaded['records']['memory_items/small'] == small
    assert session.read_bytes <= session.limits.read_bytes


@pytest.mark.asyncio
async def test_search_empty_truncation_does_not_charge_dropped_hit_or_control_envelope(monkeypatch):
    source = search_source(monkeypatch, {'oversized': {'content': 'x' * 2000}})
    session = Session('synthetic-search-owner', source, SessionLimits(read_bytes=32), {}, authority='user')
    before = session.read_bytes
    result = await session.search(Search(collections=['memory_items']))
    assert result['results'] == [] and result['truncated'] is True
    assert result['complete'] is False and result['counts'].get('read_bytes', 0) == 0
    assert session.read_bytes == before and not session.known


@pytest.mark.asyncio
async def test_search_exact_data_budget_returns_hit_without_envelope_rejection(monkeypatch):
    row = {'content': 'x' * 300}
    source = search_source(monkeypatch, {'small': row})
    session = Session(
        'synthetic-search-owner', source, SessionLimits(read_bytes=2 + serialized_bytes(row)), {}, authority='user'
    )
    result = await session.search(Search(collections=['memory_items']))
    assert result['results'][0]['ref'] == 'memory_items/small'
    assert result['complete'] is True and result['truncated'] is False
    assert session.read_bytes == session.limits.read_bytes


@pytest.mark.asyncio
async def test_injected_search_provider_also_truncates_to_fitting_hits():
    class Source:
        async def search(self, request):
            return {
                'results': [
                    {'ref': 'people/small', 'snippet': 'Synthetic'},
                    {'ref': 'people/large', 'snippet': 'x' * 2000},
                ],
                'counts': {},
                'complete': True,
            }

    session = Session('synthetic-search-owner', Source(), SessionLimits(read_bytes=100), {}, authority='user')
    result = await session.search(Search(collections=['people']))
    assert [row['ref'] for row in result['results']] == ['people/small']
    assert result['truncated'] is True and result['complete'] is False
    assert session.known == {'people/small'} and session.read_bytes < 100


@pytest.fixture
def turn_store(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setattr(dream_turns.firestore, 'transactional', lambda fn: fn)
    return DreamFirestore()


def lease_for(database, index, caps):
    uid = 'synthetic-shard-owner-' + str(index)
    database.rows[('users', uid)] = {}
    lease = dream_store.acquire(uid, caps, now=NOW, firestore_client=database)
    assert lease is not None
    lease['run_id'] = 'synthetic-shard-run-' + str(index)
    database.rows[('dream_users', uid)]['lease']['run_id'] = lease['run_id']
    return uid, lease['run_id']


def minute_total(database, now=NOW):
    minute = now.strftime('%Y-%m-%dT%H:%M')
    return sum(
        row['tokens']
        for path, row in database.rows.items()
        if path[0] == 'dream_scheduler' and path[1].startswith('headroom-') and row['minute'] == minute
    )


def test_turn_reserve_and_settle_distribute_headroom_without_a_shared_document(turn_store):
    caps = Caps(tokens_per_minute=2000003)
    assert sum(dream_turns.headroom_quota(caps.tokens_per_minute, shard) for shard in range(64)) == 2000003
    owners, paths = [], set()
    for index in range(8):
        uid, run = lease_for(turn_store, index, caps)
        dream_turns.reserve(uid, run, 10000, caps, now=NOW, firestore_client=turn_store)
        held = turn_store.rows[('dream_users', uid)]['lease']['minute_hold']['shards']
        owners.append((uid, run, held))
        paths.update(held)
    assert len(paths) > 1 and minute_total(turn_store) == 80000
    assert ('dream_scheduler', 'headroom') not in turn_store.reads
    for uid, run, held in owners:
        before = len(turn_store.reads)
        dream_turns.settle(uid, run, Turn(tokens=4000), firestore_client=turn_store)
        capacity_reads = {path for path in turn_store.reads[before:] if path[0] == 'dream_scheduler'}
        assert capacity_reads == {('dream_scheduler', 'headroom-' + shard) for shard in held}
        assert turn_store.rows[('dream_users', uid)]['lease']['minute_hold'] is None
    assert minute_total(turn_store) == 32000
    assert ('dream_scheduler', 'headroom') not in turn_store.rows


def test_large_turn_spans_shards_and_aggregate_cap_and_refunds_are_exact(turn_store):
    caps = Caps(tokens_per_minute=1003)
    first, second, third = [lease_for(turn_store, index, caps) for index in range(3)]
    dream_turns.reserve(*first, 700, caps, now=NOW, firestore_client=turn_store)
    assert len(turn_store.rows[('dream_users', first[0])]['lease']['minute_hold']['shards']) > 1
    before = deepcopy(turn_store.rows)
    with pytest.raises(ValueError, match='dream_minute_headroom'):
        dream_turns.reserve(*second, 304, caps, now=NOW, firestore_client=turn_store)
    assert turn_store.rows == before  # Failed multi-shard claims are atomic.
    dream_turns.reserve(*second, 303, caps, now=NOW, firestore_client=turn_store)
    assert minute_total(turn_store) == 1003
    with pytest.raises(ValueError, match='dream_minute_headroom'):
        dream_turns.reserve(*third, 1, caps, now=NOW, firestore_client=turn_store)
    dream_turns.settle(*first, Turn(tokens=200), firestore_client=turn_store)
    assert minute_total(turn_store) == 503
    dream_turns.reserve(*third, 500, caps, now=NOW, firestore_client=turn_store)
    assert minute_total(turn_store) == 1003


def test_late_settlement_does_not_refund_shards_reset_for_a_new_minute(turn_store):
    caps = Caps(tokens_per_minute=1003)
    first, second = [lease_for(turn_store, index, caps) for index in range(2)]
    dream_turns.reserve(*first, 1003, caps, now=NOW, firestore_client=turn_store)
    later = NOW + timedelta(minutes=1)
    dream_turns.reserve(*second, 1003, caps, now=later, firestore_client=turn_store)
    dream_turns.settle(*first, Turn(tokens=20), firestore_client=turn_store)
    assert minute_total(turn_store, later) == 1003


def test_accounted_usage_above_hold_is_retained_on_shards(turn_store):
    caps = Caps(tokens_per_minute=1003)
    owner = lease_for(turn_store, 0, caps)
    dream_turns.reserve(*owner, 100, caps, now=NOW, firestore_client=turn_store)
    dream_turns.settle(*owner, Turn(tokens=20, accounted_tokens=200), firestore_client=turn_store)
    assert minute_total(turn_store) == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('first_state', [False, True, None])
async def test_cold_dynamic_switch_denies_while_first_read_is_pending_or_unavailable(monkeypatch, first_state):
    # Load actual startup defaults without the suite's warm-cache fixture and
    # without replacing the production module in sys.modules.
    path = Path(__file__).resolve().parents[2] / 'config' / 'dream_control.py'
    spec = importlib.util.spec_from_file_location('_synthetic_cold_control', path)
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    from utils import executors

    pending = []
    monkeypatch.setattr(executors, 'submit_with_context', lambda pool, fn: pending.append(fn))

    def load():
        if first_state is None:
            raise RuntimeError('Synthetic unavailable control store')
        return first_state

    monkeypatch.setattr(control, 'load_flag', load)
    assert control.allowed() is False
    assert control.allowed() is False and len(pending) == 1
    pending.pop()()
    assert control.allowed() is (first_state is True)
