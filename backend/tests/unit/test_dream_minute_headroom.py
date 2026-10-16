"""The shared minute counts reserved burndown; a full minute pauses a pass instead of discarding it."""

import asyncio
from datetime import datetime, timezone

from config.dream_agent import Caps
from database import dream_store, dream_turns
from tests.unit.test_dream_harness_runtime import runtime, scripted, store, UID
from utils import dream_agent
from utils.dream_cost import minute_burndown_tokens, price_weighted_tokens
from utils.llm.shaped_agent import Turn

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def _minute_total(runtime):
    return sum(
        row.get('tokens', 0)
        for key, row in runtime.rows.items()
        if key[0] == 'dream_scheduler' and str(key[1]).startswith('headroom-')
    )


def test_minute_burndown_counts_cached_at_a_tenth_and_output_at_five():
    weighted = price_weighted_tokens(
        'gemini', 'gemini-3.8-flash', prompt_tokens=200000, cached_tokens=180000, completion_tokens=32768
    )
    assert weighted == 70768
    assert minute_burndown_tokens('gemini', 'gemini-3.8-flash', weighted_tokens=weighted, completion_tokens=32768) == (
        20000 + 18000 + 5 * 32768
    )


def test_minute_hold_and_settlement_use_burndown_without_leaks(runtime):
    caps = Caps(tokens=96000, tokens_per_minute=2000000)
    lease = dream_store.acquire(UID, caps, now=NOW)
    assert lease
    dream_turns.reserve(UID, lease['run_id'], 201840, caps, now=NOW)
    assert _minute_total(runtime) == 201840
    settled = Turn(tokens=208000, prompt_tokens=200000, completion_tokens=8000, cached_tokens=180000)
    settled.price_weighted_tokens = 46000
    dream_turns.settle(UID, lease['run_id'], settled)
    assert _minute_total(runtime) == 46000 + 4 * 8000
    assert all(row.get('tokens', 0) >= 0 for key, row in runtime.rows.items() if str(key[1]).startswith('headroom-'))

    dream_turns.reserve(UID, lease['run_id'], 1000, caps, now=NOW)
    unweighted = Turn(tokens=900, prompt_tokens=800, completion_tokens=100, cached_tokens=0)
    dream_turns.settle(UID, lease['run_id'], unweighted)
    # A missing weight keeps the raw charge (never drops tokens) plus the output top-up.
    assert _minute_total(runtime) == 46000 + 4 * 8000 + 900 + 4 * 100


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
    assert len(refusals) == 1 and len(sleeps) == 1 and 1 <= sleeps[0] <= 61


def test_minute_headroom_retries_three_times_then_waits(runtime, monkeypatch):
    attempts = []
    sleeps = []

    def reserve(*args, **kwargs):
        attempts.append(args[2])
        raise ValueError('dream_minute_headroom')

    async def no_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(dream_turns, 'reserve', reserve)
    monkeypatch.setattr(dream_agent.asyncio, 'sleep', no_sleep)
    report = asyncio.run(dream_agent.run_pass(UID, turn=scripted([True, True])))
    assert report['status'] == 'waiting', report
    assert len(attempts) == 4 and len(sleeps) == 3
