"""Burst capacity errors retry the pending call, not the owner's shaped session."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from tests.unit.test_dream_cleanup_edits import UID, store  # noqa: F401
from tests.unit.test_dream_harness_runtime import runtime, _plan, _verdict  # noqa: F401
from tests.unit.test_dream_session import call, turn
from utils import dream_agent, dream_capacity, dream_harness_transport as transport


def gateway(monkeypatch, respond):
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'false')
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=transport.DREAM_MODEL))
    monkeypatch.setattr(transport, 'get_llm_gateway_client', lambda: SimpleNamespace(post=respond))
    monkeypatch.setattr(transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))


def reply(result):
    message = (
        {'role': 'assistant', 'content': result.value.model_dump_json()}
        if result.value is not None and hasattr(result.value, 'model_dump_json')
        else result.messages[0]
    )
    return httpx.Response(
        200,
        json={
            'choices': [{'message': message, 'finish_reason': 'stop'}],
            'usage': {
                'prompt_tokens': 10,
                'completion_tokens': 2,
                'prompt_tokens_details': {'cached_tokens': 0},
            },
        },
    )


@pytest.mark.parametrize('failed_lane', [transport.MAIN_LANE, transport.VERIFY_LANE])
def test_real_429_retries_same_history_and_keeps_staged_work_and_budget(runtime, monkeypatch, failed_lane):
    requests, failures = [], []
    main_calls = 0

    async def post(_url, *, json, **kwargs):
        nonlocal main_calls
        requests.append(deepcopy(json))
        assert json['google'] == {'dream_capacity_mode': 'reserved'}
        lane = json['model']
        if lane == transport.MAIN_LANE:
            main_calls += 1
        if not failures and lane == failed_lane and (lane == transport.VERIFY_LANE or main_calls == 2):
            failures.append(len(requests) - 1)
            return httpx.Response(429, json={'error': {'failure_class': 'provider_429_omi_paid'}})
        if lane == transport.VERIFY_LANE:
            return reply(_verdict(json['messages'], True))
        if main_calls == 1:
            return reply(turn([_plan().tool_calls[0]]))
        return reply(turn([call('finish', {'summary': 'Synthetic check complete'})]))

    gateway(monkeypatch, post)
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', wait)
    monkeypatch.setattr(dream_capacity, 'mark_saturated', AsyncMock())
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'complete', report
    assert report['outcomes'][0]['status'] == 'applied'
    assert report['tool_counts']['propose_edit'] == 1
    assert requests[failures[0]] == requests[failures[0] + 1]
    assert report['tokens'] == 48 and report['usage_unknown'] is False
    assert runtime.rows[('dream_users', UID)]['passes'] == 1
    assert runtime.rows[('dream_users', UID)]['lease'] is None
    # Four successful calls charge 10 input + 5*2 output each; rejected attempt refunds its hold.
    minute = sum(v.get('tokens', 0) for k, v in runtime.rows.items() if str(k[1]).startswith('headroom-'))
    assert minute == 80
    wait.assert_awaited_once()
    assert wait.await_args.kwargs == {'mode': 'reserved', 'owner_allowlisted': False}


def test_persistent_429_is_bounded_and_refunds_known_zero_attempts(runtime, monkeypatch):
    post = AsyncMock(return_value=httpx.Response(429, json={'error': {}}))
    gateway(monkeypatch, post)
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', wait)
    monkeypatch.setattr(dream_capacity, 'mark_saturated', AsyncMock())
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'waiting', report
    assert post.await_count == 6 and wait.await_count == 5
    assert report['tokens'] == 0 and report['usage_unknown'] is False
    assert sum(v.get('tokens', 0) for k, v in runtime.rows.items() if str(k[1]).startswith('headroom-')) == 0


def test_capacity_retry_rechecks_kill_switch_before_dispatch(runtime, monkeypatch):
    post = AsyncMock(return_value=httpx.Response(429, json={'error': {}}))
    gateway(monkeypatch, post)

    async def wait(*args, **kwargs):
        monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
        return True

    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', wait)
    monkeypatch.setattr(dream_capacity, 'mark_saturated', AsyncMock())
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'failed' and post.await_count == 1


@pytest.mark.asyncio
async def test_drain_cancels_and_joins_workers_before_summary(monkeypatch):
    stopped = []
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent, 'concurrency', lambda: 1)
    monkeypatch.setattr(dream_agent, 'DRAIN_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=transport.DREAM_MODEL))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: ['synthetic'])

    async def run_pass(_uid):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    monkeypatch.setattr(dream_agent, 'run_pass', run_pass)
    reports = await dream_agent.drain()
    assert reports == [{'status': 'deadline'}] and stopped == [True]


@pytest.mark.parametrize('unknown_attempts', [0, 1])
def test_retry_retains_paid_and_unknown_error_usage(runtime, monkeypatch, unknown_attempts):
    calls = []

    async def post(_url, *, json, **kwargs):
        calls.append(json)
        if len(calls) == 1:
            return httpx.Response(
                429,
                json={
                    'error': {},
                    'dream_usage': {
                        'prompt_tokens': 100,
                        'completion_tokens': 10,
                        'cached_tokens': 0,
                        'unknown_attempts': unknown_attempts,
                    },
                },
            )
        return reply(turn([call('finish', {'summary': 'Synthetic complete'})]))

    gateway(monkeypatch, post)
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', AsyncMock(return_value=True))
    monkeypatch.setattr(dream_capacity, 'mark_saturated', AsyncMock())
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'complete', report
    assert len(calls) == 2 and report['tokens'] == 122
    assert report['accounted_tokens'] > 122 if unknown_attempts else report['accounted_tokens'] == 122
    assert report['usage_unknown'] is bool(unknown_attempts)
    minute = sum(v.get('tokens', 0) for k, v in runtime.rows.items() if str(k[1]).startswith('headroom-'))
    assert minute > 170 if unknown_attempts else minute == 170


def test_insufficient_retry_headroom_does_not_dispatch_again(runtime, monkeypatch):
    post = AsyncMock(return_value=httpx.Response(429, json={'error': {}}))
    gateway(monkeypatch, post)
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', AsyncMock(return_value=False))
    monkeypatch.setattr(dream_capacity, 'mark_saturated', AsyncMock())
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'waiting' and post.await_count == 1


def test_another_workers_cooldown_preserves_this_pass_and_its_proposal(runtime, monkeypatch):
    requests = []

    async def post(_url, *, json, **kwargs):
        requests.append(json)
        return reply(_plan() if json['model'] == transport.MAIN_LANE else _verdict(json['messages'], True))

    gateway(monkeypatch, post)
    # A peer saturates capacity after planning; this pass keeps its staged proposal.
    monkeypatch.setattr(
        dream_capacity,
        'available_model',
        AsyncMock(side_effect=[transport.DREAM_MODEL, None, transport.DREAM_MODEL, transport.DREAM_MODEL]),
    )
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', wait)
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'complete' and report['outcomes'][0]['status'] == 'applied'
    assert len(requests) == 3 and report['tokens'] == 36
    assert runtime.rows[('dream_users', UID)]['passes'] == 1
    wait.assert_awaited_once()


@pytest.mark.parametrize('status', [403, 500])
def test_non_capacity_provider_error_is_not_retried(runtime, monkeypatch, status):
    post = AsyncMock(return_value=httpx.Response(status, json={'error': {}}))
    gateway(monkeypatch, post)
    wait = AsyncMock()
    monkeypatch.setattr(dream_capacity, 'wait_for_capacity', wait)
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'failed' and post.await_count == 1
    wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_retries_waiting_owner_after_short_cooldown(monkeypatch):
    pauses = []
    monkeypatch.setattr(dream_agent, 'enabled', lambda: True)
    monkeypatch.setattr(dream_agent, 'concurrency', lambda: 1)
    monkeypatch.setattr(dream_capacity, 'available_model', AsyncMock(return_value=transport.DREAM_MODEL))
    monkeypatch.setattr(dream_agent.dream_scheduler, 'candidates', lambda **k: ['synthetic'])
    run = AsyncMock(side_effect=[{'status': 'waiting'}, {'status': 'complete'}])
    monkeypatch.setattr(dream_agent, 'run_pass', run)

    async def sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(dream_agent.asyncio, 'sleep', sleep)
    assert await dream_agent.drain() == [{'status': 'waiting'}, {'status': 'complete'}]
    assert pauses == [10]
    assert run.await_args_list[0] == run.await_args_list[1]
