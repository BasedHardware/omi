"""Synthetic fair rotation, concurrent admission and reserved-capacity contracts."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from config.vertex_reservations import State, RESERVATIONS
from database import dream_scheduler
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_capacity, dream_transport
from utils.llm.vertex_reservation_state import ReservationState
from utils.llm.vertex_pt_routing import PT_MODEL_CURRENT

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)


def test_age_weight_and_paid_ties():
    free_old = {'usage_weight': 1, 'last_pass_at': NOW - timedelta(hours=5)}
    paid = {'usage_weight': 2, 'last_pass_at': NOW - timedelta(hours=2)}
    assert dream_scheduler.priority(free_old, NOW) > dream_scheduler.priority(paid, NOW)
    paid['last_pass_at'] = NOW - timedelta(hours=2.5)
    assert dream_scheduler.priority(paid, NOW) > dream_scheduler.priority(free_old, NOW)


def test_rotation_reaches_owners_beyond_top_100_and_wraps(monkeypatch):
    db = DreamFirestore()
    rows = [SimpleNamespace(id=f'owner-{i:03}', to_dict=lambda: {'usage_weight': 1}) for i in range(205)]

    def page(*, after=None, limit=100, **kwargs):
        start = next((i + 1 for i, row in enumerate(rows) if row.id == after), 0)
        return rows[start : start + limit]

    monkeypatch.setattr(dream_scheduler, 'candidate_page', page)
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    seen = []
    for _ in range(3):
        seen.extend(dream_scheduler.candidates(now=NOW, firestore_client=db))
    assert seen == [row.id for row in rows]
    assert dream_scheduler.candidates(now=NOW, firestore_client=db)[0] == rows[0].id
    assert len(db.transactions) == 4


def test_saturation_signal_and_shared_slots_fail_closed(monkeypatch):
    async def exercise():
        state = ReservationState()
        client = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(return_value=True), eval=AsyncMock())
        monkeypatch.setattr(state, 'client', lambda: client)
        states = {model: State.INACTIVE for model in RESERVATIONS}
        states[PT_MODEL_CURRENT] = State.ACTIVE
        monkeypatch.setattr(state, 'refresh', AsyncMock(return_value=states))
        monkeypatch.setattr(dream_capacity, 'reservation_state', state)
        slot = await dream_capacity.claim(2)
        assert slot and client.set.call_args.kwargs == {'nx': True, 'ex': 240}
        await dream_capacity.release(slot)
        assert client.eval.call_args.args[-1] == slot[1]
        await state.record(PT_MODEL_CURRENT, 'dedicated', 429, None)
        assert client.set.call_args.args[0].endswith(':saturated:' + PT_MODEL_CURRENT)
        assert client.set.call_args.kwargs == {'ex': 120}
        client.get.return_value = '1'
        assert await dream_capacity.claim(2) is None
        client.get.return_value = None
        client.set.return_value = False
        assert await dream_capacity.claim(2) is None
        states[PT_MODEL_CURRENT] = State.UNKNOWN
        assert await dream_capacity.available_model() is None
        monkeypatch.setattr(state, 'client', lambda: None)
        assert await dream_capacity.claim(2) is None

    asyncio.run(exercise())


def test_waiting_does_not_acquire_budget(monkeypatch):
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=None))
    acquire = Mock(side_effect=AssertionError('capacity wait acquired budget'))
    monkeypatch.setattr(dream_agent.dream_store, 'acquire', acquire)
    assert asyncio.run(dream_agent.run_pass('synthetic')) == {'status': 'waiting', 'reason': 'reserved_capacity'}
    acquire.assert_not_called()


def test_bounded_parallel_drain(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_CONCURRENCY', '2')
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value='synthetic'))
    monkeypatch.setattr(dream_scheduler, 'candidates', lambda **kwargs: list(range(6)))
    active = peak = 0

    async def run(uid):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return {'status': 'complete', 'uid': uid}

    monkeypatch.setattr(dream_agent, 'run_pass', run)
    results = asyncio.run(dream_agent.drain())
    assert peak == 2 and len(results) == 6


def test_dream_capacity_has_no_provider_or_lkg_fallback():
    from llm_gateway.gateway.config_loader import load_gateway_config
    from llm_gateway.gateway.schemas import FailureClass
    from llm_gateway.gateway.resolver import is_lkg_eligible
    from llm_gateway.gateway.reserved_fallback import can_try_next_provider

    config = load_gateway_config(prod_mode=True)
    route = next(route for route in config.route_artifacts.values() if route.lane_id == dream_transport.MAIN_LANE)
    assert route.primary.provider == 'gemini'
    assert route.provider_options['reserved_capacity_only'] is True
    for failure in (FailureClass.RESERVED_CAPACITY_UNAVAILABLE, FailureClass.PROVIDER_429_OMI_PAID):
        assert not can_try_next_provider(route, route.primary, failure)
        assert not is_lkg_eligible(route, failure)
