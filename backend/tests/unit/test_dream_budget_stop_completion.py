"""Expected budget stops finish cleanly; invalid usage remains a failure."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_dream_harness_runtime import _plan, _verdict, runtime, store, UID
from utils import dream_agent
from utils.dream_harness_transport import MAIN_LANE, VERIFY_LANE, PreTokenFailure
from utils.llm.shaped_agent import Turn


@pytest.mark.parametrize('stop_code', ['dream_input_token_budget', 'dream_daily_budget'])
def test_budget_exhaustion_without_staged_work_completes_without_verification(runtime, monkeypatch, stop_code):
    verifier = AsyncMock(side_effect=AssertionError('Empty budget stop must not verify'))
    monkeypatch.setattr(dream_agent.dream_verify, 'verify', verifier)

    async def model(uid, lane, mount, messages):
        assert lane == MAIN_LANE
        raise ValueError(stop_code)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete'
    assert report['stop_reason'] == stop_code
    assert report['verifier_calls'] == 0
    verifier.assert_not_awaited()


@pytest.mark.parametrize('stop_code', ['dream_input_token_budget', 'dream_daily_budget'])
def test_budget_exhaustion_with_staged_work_still_runs_verification(runtime, stop_code):
    main_calls = 0
    verifier_lanes = []

    async def model(uid, lane, mount, messages):
        nonlocal main_calls
        if lane == MAIN_LANE:
            main_calls += 1
            if main_calls == 1:
                proposal = _plan().tool_calls[0]
                return Turn(
                    tokens=10,
                    prompt_tokens=10,
                    completion_tokens=0,
                    cached_tokens=0,
                    tool_calls=(proposal,),
                    messages=({'role': 'assistant', 'content': None, 'tool_calls': [proposal]},),
                )
            raise ValueError(stop_code)
        verifier_lanes.append(lane)
        return _verdict(messages, True)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert report['stop_reason'] == stop_code
    assert report['verifier_calls'] == 2
    assert verifier_lanes == [VERIFY_LANE, VERIFY_LANE]
    assert report['outcomes'][0]['status'] == 'dry_run'


def test_non_budget_value_error_with_staged_work_still_fails(runtime, monkeypatch):
    verifier = AsyncMock(side_effect=AssertionError('Invalid usage must not verify staged work'))
    monkeypatch.setattr(dream_agent.dream_verify, 'verify', verifier)
    main_calls = 0

    async def model(uid, lane, mount, messages):
        nonlocal main_calls
        assert lane == MAIN_LANE
        main_calls += 1
        if main_calls == 1:
            proposal = _plan().tool_calls[0]
            return Turn(
                tokens=10,
                prompt_tokens=10,
                completion_tokens=0,
                cached_tokens=0,
                tool_calls=(proposal,),
                messages=({'role': 'assistant', 'content': None, 'tool_calls': [proposal]},),
            )
        raise ValueError('dream_invalid_usage')

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'failed'
    assert report['error_code'] == 'dream_invalid_usage'
    verifier.assert_not_awaited()


@pytest.mark.parametrize(
    'failure',
    [
        PreTokenFailure('dream_gateway_rejected'),
        RuntimeError('dream_gateway_failure'),
        ValueError('dream_response_truncated'),
        ValueError('dream_invalid_tool_calls'),
    ],
    ids=['rejected', 'failure', 'truncated', 'invalid_tool_calls'],
)
def test_late_provider_failure_still_verifies_staged_work(runtime, failure):
    main_calls = 0
    verifier_lanes = []

    async def model(uid, lane, mount, messages):
        nonlocal main_calls
        if lane == MAIN_LANE:
            main_calls += 1
            if main_calls == 1:
                proposal = _plan().tool_calls[0]
                return Turn(
                    tokens=10,
                    prompt_tokens=10,
                    completion_tokens=0,
                    cached_tokens=0,
                    tool_calls=(proposal,),
                    messages=({'role': 'assistant', 'content': None, 'tool_calls': [proposal]},),
                )
            raise failure
        verifier_lanes.append(lane)
        return _verdict(messages, True)

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    assert report['stop_reason'] == str(failure)
    assert verifier_lanes == [VERIFY_LANE, VERIFY_LANE]


def test_provider_failure_without_staged_work_still_fails(runtime):
    async def model(uid, lane, mount, messages):
        raise PreTokenFailure('dream_gateway_rejected')

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'failed'


def test_status_log_carries_bounded_error_code_and_stop_reason(caplog):
    from utils.dream_metrics import record_pass

    caplog.set_level('INFO', logger='utils.dream_metrics')
    record_pass(
        {
            'status': 'failed',
            'error_type': 'ValueError',
            'error_code': 'dream_response_truncated',
            'stop_reason': 'free text from somewhere',
            'price_weighted_tokens': 1234,
            'cost_usd': 0.5,
        }
    )
    line = caplog.records[-1].getMessage()
    assert 'error_type=ValueError error_code=dream_response_truncated stop_reason=other' in line
    assert 'weighted_tokens=1234 cost_usd=0.5000' in line
