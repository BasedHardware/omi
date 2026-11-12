"""Unit test proving account deletion marker is not memoized in request scope (Issue #24647).

Request-scoped memoization via fsr_read_cache.memo (lever request_read_dedupe) can
outlive a concurrent account deletion because writer Redis invalidations do not clear
other in-flight request contexts. The deletion marker status must rely strictly on
the shared Redis negative cache (with writer generation fencing) and must never be
memoized in request scope.
"""

import json
import fakeredis
import pytest
import time

from database import account_deletion_marker as deletion
from database import fsr_read_cache as cache
from database import firestore_tier_context as tier, privacy_check_metrics as metrics
from database.account_deletion_marker import account_deletion_blocks_user_work
from tests.unit.test_fsr_s4_caches import Store


@pytest.mark.parametrize('plan,group', [('unlimited_v2', 'unlimited_v2'), ('basic', 'free'), (None, 'unattributed')])
def test_deletion_marker_metrics_use_existing_request_plan_without_extra_reads(env, plan, group):
    store, redis = env
    token = tier._request_owner.set(tier._RequestOwner('u', plan, time.monotonic() + 60))
    before = metrics.READS.labels('deletion_marker', 'live', 'miss', group)._value.get()
    checks = metrics.CHECKS.labels('deletion_marker', 'live', 'allow', group)._value.get()
    try:
        assert deletion.get_user_deletion_wipe_status('u') is None
    finally:
        tier._request_owner.reset(token)
    assert len(store.reads) == 1
    assert metrics.READS.labels('deletion_marker', 'live', 'miss', group)._value.get() == before + 1
    assert metrics.CHECKS.labels('deletion_marker', 'live', 'allow', group)._value.get() == checks + 1


@pytest.fixture
def env(monkeypatch):
    store = Store()
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(deletion, 'account_deletion_firestore_client', lambda **kwargs: store)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    cache._configs.clear()
    return store, redis


def enable_levers(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))
    cache._configs.clear()


@pytest.mark.asyncio
async def test_deletion_marker_not_memoized_in_request_scope_across_concurrent_deletion(env, monkeypatch):
    """Issue #24647: A concurrent account deletion must be observed by subsequent checks in an active request scope."""
    store, redis = env
    enable_levers(monkeypatch, 'request_read_dedupe', 'deletion_marker_cache')

    scope = cache.request_read_scope()
    await anext(scope)
    try:
        # Initial check during request authentication: user has no deletion marker
        assert deletion.get_user_deletion_wipe_status('u') is None
        assert not account_deletion_blocks_user_work('u')

        # A concurrent request writes the deletion marker and fences Redis
        store.docs['account_deletions/u'] = {'wipe_status': 'pending'}
        root = cache._root('deletion_marker_cache', 'u')
        redis.eval(cache._BEGIN, 2, root + ':generation', root + ':writers', 'concurrent-writer-token', 60)

        # Later check within the SAME request scope (e.g. app-owner verification)
        # must see the pending deletion, not the stale memoized None.
        status = deletion.get_user_deletion_wipe_status('u')
        assert status == 'pending'
        assert account_deletion_blocks_user_work('u')
    finally:
        await scope.aclose()


@pytest.mark.asyncio
async def test_request_read_dedupe_does_not_memoize_deletion_marker(env, monkeypatch):
    """When deletion_marker_cache is disabled, request_read_dedupe must not memoize the marker."""
    store, redis = env
    enable_levers(monkeypatch, 'request_read_dedupe')

    scope = cache.request_read_scope()
    await anext(scope)
    try:
        for _ in range(3):
            assert deletion.get_user_deletion_wipe_status('u') is None
        # Deletion marker must not be memoized by request dedupe; all 3 reads query the store
        assert len(store.reads) == 3
    finally:
        await scope.aclose()
