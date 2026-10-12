"""Synthetic fair rotation, concurrent admission and reserved-capacity contracts."""

import asyncio
import pytest
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
    assert dream_scheduler.priority(free_old, NOW) > dream_scheduler.priority(paid, NOW, weight=2)
    paid['last_pass_at'] = NOW - timedelta(hours=2.5)
    assert dream_scheduler.priority(paid, NOW, weight=2) > dream_scheduler.priority(free_old, NOW)


def test_rotation_reaches_owners_beyond_top_100_and_wraps(monkeypatch):
    db = DreamFirestore()
    db.get_all = lambda refs, **kwargs: [SimpleNamespace(id=ref.id, to_dict=lambda: {}) for ref in refs]
    rows = [SimpleNamespace(id=f'owner-{i:03}', to_dict=lambda: {'usage_weight': 1}) for i in range(205)]

    def page(*, after=None, limit=100, **kwargs):
        start = next((i + 1 for i, row in enumerate(rows) if row.id == after), 0)
        return rows[start : start + limit]

    monkeypatch.setattr(dream_scheduler, 'candidate_page', page)
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    seen = []
    for _ in range(3):
        page = dream_scheduler.candidates(now=NOW, firestore_client=db)
        seen.extend(page)
        dream_scheduler.advance(page, set(page), firestore_client=db)
    assert seen == [row.id for row in rows]
    assert dream_scheduler.candidates(now=NOW, firestore_client=db)[0] == rows[0].id
    assert len(db.transactions) == 3


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


@pytest.mark.parametrize('reason', ['dream_run_in_progress', 'dream_manual_limit', 'dream_budget_unavailable'])
def test_deterministic_admission_rejection_releases_reserved_slot(monkeypatch, reason):
    slot = ('fixture-slot', 'token')
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=slot))
    released = AsyncMock()
    monkeypatch.setattr(dream_capacity, 'release', released)
    monkeypatch.setattr(
        dream_agent.dream_store, 'acquire', Mock(side_effect=dream_agent.dream_store.AdmissionDenied(reason))
    )
    with pytest.raises(dream_agent.dream_store.AdmissionDenied, match=reason):
        asyncio.run(dream_agent.run_pass('synthetic', trigger='manual'))
    released.assert_awaited_once_with(slot)


def test_scheduling_reads_current_subscription_for_idle_and_changed_owners(monkeypatch):
    from config.plan_catalog import PAID_PLAN_IDS

    db = DreamFirestore()
    rows = [
        SimpleNamespace(id=uid, to_dict=lambda: {'last_pass_at': NOW - timedelta(hours=2), 'usage_weight': 1})
        for uid in ['free', 'paid']
    ]
    plans = {'free': '', 'paid': next(iter(PAID_PLAN_IDS))}

    def get_all(refs, *, timeout, field_paths):
        assert timeout == 3
        assert field_paths == ['subscription.plan', 'plan']
        return [
            SimpleNamespace(id=ref.id, to_dict=lambda uid=ref.id: {'subscription': {'plan': plans[uid]}})
            for ref in refs
        ]

    db.get_all = get_all
    monkeypatch.setattr(dream_scheduler, 'candidate_page', lambda **k: rows)
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    assert dream_scheduler.candidates(now=NOW, firestore_client=db) == ['paid', 'free']
    plans.update(free=next(iter(PAID_PLAN_IDS)), paid='')
    assert dream_scheduler.candidates(now=NOW, firestore_client=db) == ['free', 'paid']


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


def test_capacity_wait_keeps_untried_prefix_and_worker_fault_does_not_cancel_sibling(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_CONCURRENCY', '2')
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value='synthetic'))
    page = dream_scheduler.CandidatePage(['paid', 'free', 'later'], ordered=['free', 'later', 'paid'], after=None)
    monkeypatch.setattr(dream_scheduler, 'candidates', lambda **k: page)
    receipts = []
    real_advance = dream_scheduler.advance
    monkeypatch.setattr(dream_scheduler, 'advance', lambda page, tried: receipts.append(set(tried)))

    async def run(uid):
        if uid == 'paid':
            await asyncio.sleep(0)
            raise RuntimeError('synthetic owner fault')
        return {'status': 'waiting'}

    monkeypatch.setattr(dream_agent, 'run_pass', run)
    result = asyncio.run(dream_agent.drain())
    assert sorted(r['status'] for r in result) == ['failed', 'waiting']
    assert receipts == [{'paid'}]
    db = DreamFirestore()
    monkeypatch.setattr(dream_scheduler.firestore, 'transactional', lambda fn: fn)
    real_advance(page, {'paid'}, firestore_client=db)
    assert ('dream_scheduler', 'rotation') not in db.rows
    real_advance(page, {'paid', 'free'}, firestore_client=db)
    assert db.rows[('dream_scheduler', 'rotation')]['after'] == 'free'


def test_ordinary_acquire_failure_releases_slot(monkeypatch):
    slot = ('synthetic-slot', 'token')
    monkeypatch.setattr(dream_capacity, 'claim', AsyncMock(return_value=slot))
    release = AsyncMock()
    monkeypatch.setattr(dream_capacity, 'release', release)
    monkeypatch.setattr(dream_agent.dream_store, 'acquire', Mock(side_effect=RuntimeError('synthetic outage')))
    with pytest.raises(RuntimeError):
        asyncio.run(dream_agent.run_pass('synthetic'))
    release.assert_awaited_once_with(slot)


def test_runtime_backend_gateway_reservation_keys_match(monkeypatch):
    import os
    import yaml
    from pathlib import Path
    from unittest.mock import patch

    manifest = yaml.safe_load((Path(__file__).resolve().parents[3] / 'backend/deploy/runtime_env.yaml').read_text())
    for stage, env in manifest['environments'].items():
        hosts = [env['cloud_run']['services'][name]['env'] for name in ('backend', 'backend-sync')]
        chart = yaml.safe_load(
            (
                Path(__file__).resolve().parents[3]
                / ('backend/charts/llm-gateway/' + stage + '_omi_llm_gateway_values.yaml')
            ).read_text()
        )
        gateway = {row['name']: {'value': row['value']} for row in chart['env'] if 'value' in row}
        gateway.update(env['llm_gateway']['env'])
        keys = []
        for values in (*hosts, gateway):
            config = {
                key: str(row['value']).replace('{compute_project}', env['compute_project'])
                for key, row in values.items()
                if 'value' in row
            }
            assert (
                config.get('OMI_VERTEX_RESERVATION_PROJECT', config['GOOGLE_CLOUD_PROJECT']) == env['compute_project']
            )
            with patch.dict(os.environ, config, clear=True):
                keys.append(ReservationState.key())
        assert len(set(keys)) == 1, stage
