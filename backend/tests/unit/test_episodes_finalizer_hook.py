"""The finalizer's episode hook runs after fanout completion and can never fail finalization."""

import asyncio

import pytest

from config import episodes as config
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)


def _run_blocking_recorder(calls, rows=None):
    async def fake(_executor, function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is finalizer.conversations_db.get_conversation:
            return (rows or {}).get(args[1])
        return function(*args, **kwargs)

    return fake


def test_hook_passes_the_processed_row_and_trigger(monkeypatch):
    calls = []
    seen = []
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **k: seen.append((a, k)) or 'reconciled')
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert seen == [(('u', 'c1', {'id': 'c1'}), {'trigger': 'capture_end', 'absorbed_from': None})]


def test_hook_swallows_errors_and_skips_missing_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))

    def boom(*args, **kwargs):
        raise RuntimeError('episode store down')

    monkeypatch.setattr(finalizer, 'record_episode_finalized', boom)
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', None, ProcessingTrigger.CAPTURE_END))
    assert len(calls) == 1


def test_hook_is_time_bounded(monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(finalizer, 'run_blocking', slow)
    monkeypatch.setattr(finalizer, 'EPISODE_FINALIZE_TIMEOUT_SECONDS', 0.01)
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))


def test_absorb_hook_follows_the_donor_to_its_survivor(monkeypatch):
    calls = []
    seen = []
    donor = {'id': 'n', 'smart_merge': {'role': 'donor', 'survivor_id': 'p'}}
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls, {'n': donor}))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **k: seen.append((a, k)))
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert seen == [(('u', 'p', donor), {'trigger': 'capture_end', 'absorbed_from': 'n'})]


def test_absorb_hook_reads_nothing_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert calls == []
