"""A full shared minute pauses a pass; it never discards the work already done."""

import asyncio

from database import dream_turns
from tests.unit.test_dream_harness_runtime import runtime, scripted, store, UID
from utils import dream_agent


def test_minute_headroom_pauses_then_continues_the_pass(runtime, monkeypatch):
    real_reserve = dream_turns.reserve
    refusals = []
    sleeps = []

    def reserve(*args, **kwargs):
        if not refusals:
            refusals.append(args[2])
            raise ValueError('dream_minute_headroom')
        return real_reserve(*args, **kwargs)

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(dream_turns, 'reserve', reserve)
    monkeypatch.setattr(dream_agent.asyncio, 'sleep', no_sleep)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['status'] == 'complete', report
    assert refusals and len(sleeps) == 1 and 1 <= sleeps[0] <= 61


def test_minute_headroom_still_waits_after_retries_run_out(runtime, monkeypatch):
    def reserve(*args, **kwargs):
        raise ValueError('dream_minute_headroom')

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(dream_turns, 'reserve', reserve)
    monkeypatch.setattr(dream_agent.asyncio, 'sleep', no_sleep)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['status'] == 'waiting', report


def test_minute_hold_counts_cached_prompt_at_its_price_fraction():
    from utils.dream_cost import price_weighted_tokens

    raw = 200000 + 32768
    weighted = price_weighted_tokens(
        'gemini', 'gemini-3.8-flash', prompt_tokens=200000, cached_tokens=180000, completion_tokens=32768
    )
    assert weighted < raw // 3
