"""A committed claim batch survives one failed original attempt without resends."""

import asyncio
from types import SimpleNamespace

import pytest

from utils.batch_pipeline import typed_provider


@pytest.mark.parametrize('failure_phase', ['provider', 'seal'])
def test_later_committed_claims_continue_after_first_failure(monkeypatch, failure_phase):
    claims = [{'recording_id': 'first'}, {'recording_id': 'second'}]
    visited = []
    runner = typed_provider.TypedProviderRunner(
        SimpleNamespace(units=SimpleNamespace(claim=lambda *a, **k: claims)),
        None,
        enabled=True,
        count=2,
        backlog_share=0,
        lease_seconds=30,
        effect_lease_seconds=60,
        partial_wait=30,
        health=object(),
        clock=lambda: 100,
    )

    async def execute(adapter, claim, *args, **kwargs):
        visited.append(claim['recording_id'])
        if claim is claims[0] and failure_phase == 'provider':
            raise RuntimeError('unknown vendor outcome')
        return SimpleNamespace(outcome='done')

    def sealed(identity):
        if identity == 'first' and failure_phase == 'seal':
            raise RuntimeError('unknown SQL commit outcome')
        return True

    async def run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(typed_provider, 'run_claimed_provider', execute)
    monkeypatch.setattr(runner, '_sealed', sealed)
    assert asyncio.run(runner.run_once(run_sync)) == ['second']
    assert visited == ['first', 'second']


def test_cancellation_is_not_swallowed_and_never_starts_later_claim(monkeypatch):
    runner = typed_provider.TypedProviderRunner(
        SimpleNamespace(units=SimpleNamespace(claim=lambda *a, **k: [{}, {}])),
        None,
        enabled=True,
        count=2,
        backlog_share=0,
        lease_seconds=30,
        effect_lease_seconds=60,
        partial_wait=30,
        health=object(),
        clock=lambda: 100,
    )
    calls = []

    async def execute(*a, **k):
        calls.append(1)
        raise asyncio.CancelledError()

    async def run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(typed_provider, 'run_claimed_provider', execute)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner.run_once(run_sync))
    assert calls == [1]
