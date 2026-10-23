"""Membership reuse ends with the request and never retains unavailable grants."""

import pytest

from database import fsr_read_cache as cache
from utils import rollout_cohorts as runtime


@pytest.mark.asyncio
async def test_scope_reuses_membership_after_process_ttl_and_closes(monkeypatch):
    calls = []
    local = runtime._TTLReads(lambda uid: calls.append(uid) or {'local': {'first-summary': True}})
    monkeypatch.setattr(runtime, '_cache', local)
    monkeypatch.setattr(runtime, '_background_submitter', lambda fn, *args: fn(*args))
    scope = cache.request_read_scope()
    await anext(scope)
    try:
        first = runtime._request_memberships('synthetic')
        first['local']['first-summary'] = False
        local.entries['synthetic'].expires = 0
        assert runtime._request_memberships('synthetic')['local']['first-summary'] is True
        assert calls == ['synthetic']
    finally:
        await scope.aclose()
    runtime._request_memberships('synthetic')
    assert calls == ['synthetic', 'synthetic']


@pytest.mark.asyncio
async def test_scope_is_bounded_per_user_and_does_not_cache_unknowns(monkeypatch):
    scope = cache.request_read_scope()
    await anext(scope)
    calls = []
    try:
        for uid in range(70):
            cache.cohort_memberships(str(uid), lambda: {})
        holder = cache._request.get()
        assert len(holder.cohort_values) == 64
        assert cache.cohort_memberships('unknown', lambda: calls.append(1)) is None
        assert cache.cohort_memberships('unknown', lambda: {'local': {}}) == {'local': {}}
        assert calls == [1]
        holder.closed = True
        assert cache.cohort_memberships('0', lambda: {'fresh': {}}) == {'fresh': {}}
    finally:
        await scope.aclose()


@pytest.mark.asyncio
async def test_kill_switch_and_fresh_reads_bypass_snapshot(monkeypatch):
    scope = cache.request_read_scope()
    await anext(scope)
    try:
        assert cache.cohort_memberships('user', lambda: {}) == {}
        with cache.fresh_reads():
            assert cache.cohort_memberships('user', lambda: {'new': {}}) == {'new': {}}
        monkeypatch.setenv('FSR_COHORT_REQUEST_CACHE', 'off')
        assert cache.cohort_memberships('user', lambda: {'new': {}}) == {'new': {}}
    finally:
        await scope.aclose()
