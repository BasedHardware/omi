"""Both real cache layers enabled: dependency failures cannot gain a 90-second lease."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError

from database import candidates, s5_candidates_cache as compat, staged_promote_cache as cache
from routers import staged_tasks as route
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_staged_promote_empty_cache import (
    EMPTY,
    STAGED_PROMOTE_ROUTE,
    candidate,
    serving,
    storage,
)
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged


@pytest.fixture
def coupled(serving, monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    monkeypatch.setenv('CANDIDATES_COMPATIBILITY_CACHE_TTL_SECONDS', '30')
    monkeypatch.setattr(route, 'load_compatibility_candidates', compat.load_compatibility_candidates)
    return serving


def create_pending(monkeypatch, store):
    strict = StrictFirestore()
    strict.rows = store.rows
    with monkeypatch.context() as patch:
        patch.setattr(candidates, 'db', strict)
        patch.setattr(candidates.firestore, 'transactional', lambda fn: fn)
        return candidates.create_candidate(
            'owner',
            proposal_from_legacy_staged({'id': 'new', 'description': 'Committed pending task'}),
            idempotency_key='coupled-cache-write',
            account_generation=7,
            now=datetime.now(timezone.utc),
        )


def reject_compatibility_sets(monkeypatch, redis, *, after_apply=False):
    real_set = redis.set

    def set_value(key, value, **kwargs):
        if key == compat._version_key('owner') and not kwargs.get('nx'):
            if after_apply:
                real_set(key, value, **kwargs)
            raise ConnectionError('synthetic compatibility invalidation failure')
        return real_set(key, value, **kwargs)

    monkeypatch.setattr(redis, 'set', set_value)


def stored():
    return cache.OPERATIONS.labels(outcome='stored')._value.get()


@pytest.mark.parametrize('recovery', ['ttl', 'compatibility_rotation'])
def test_real_candidate_write_with_failed_compat_set_never_extends_stale_empty(coupled, storage, monkeypatch, recovery):
    client, store, selected, _ = coupled
    clock, redis = storage
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY  # Seeds BOTH empty caches.
    before = stored()
    old_compatibility = redis.get(compat._version_key('owner'))
    with monkeypatch.context() as failure:
        reject_compatibility_sets(failure, redis)
        created = create_pending(failure, store)
        assert redis.get(compat._version_key('owner')) == old_compatibility
        for _ in range(3):
            assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY  # Baseline's <=30s stale compatibility hit.
            assert stored() == before  # Never promoted into a new 90s marker.
        assert redis.get(cache._version_key('owner')) == cache.BUSY
    if recovery == 'ttl':
        clock.seconds += 31
    else:
        assert compat.invalidate_after_write(lambda uid: 'committed')('owner') == 'committed'
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with(created.candidate_id, uid='owner')
    assert stored() == before


@pytest.mark.parametrize('dependency_fails', [False, True])
def test_partial_commit_error_is_preserved_once_and_compatibility_invalidates_in_finally(
    coupled, storage, monkeypatch, dependency_fails
):
    client, store, selected, _ = coupled
    clock, redis = storage
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    before = stored()
    old = redis.get(compat._version_key('owner'))
    failure = RuntimeError('durable prefix followed by failure')
    calls = []

    @compat.invalidate_after_write
    def mutation(uid):
        calls.append(uid)
        store.rows['users/owner/candidates/canonical'] = candidate()
        raise failure

    with monkeypatch.context() as patch:
        if dependency_fails:
            reject_compatibility_sets(patch, redis)
        with pytest.raises(RuntimeError) as raised:
            mutation('owner')
    assert raised.value is failure and calls == ['owner']
    if dependency_fails:
        assert redis.get(compat._version_key('owner')) == old
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
        clock.seconds += 31
    else:
        assert redis.get(compat._version_key('owner')) != old
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')
    assert stored() == before


def test_read_during_write_cannot_fill_and_failed_completion_keeps_busy(coupled, storage, monkeypatch):
    client, store, selected, _ = coupled
    _, redis = storage
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    before = stored()
    real_eval = redis.eval

    def eval_value(script, *args):
        if script == cache._END_WRITE:
            raise ConnectionError('synthetic failed final fence')
        return real_eval(script, *args)

    monkeypatch.setattr(redis, 'eval', eval_value)

    @compat.invalidate_after_write
    def mutation(uid):
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
        assert stored() == before
        store.rows['users/owner/candidates/canonical'] = candidate()
        return 'committed'

    assert mutation('owner') == 'committed'
    assert redis.get(cache._version_key('owner')) == cache.BUSY
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')
    assert stored() == before


@pytest.mark.parametrize('second_fails', [False, True])
def test_overlapping_writer_completion_cannot_release_another_writer(storage, monkeypatch, second_fails):
    _, redis = storage
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    origin = Mock(return_value=[])

    @compat.invalidate_after_write
    def second(uid):
        return 'second'

    @compat.invalidate_after_write
    def first(uid):
        with monkeypatch.context() as failure:
            if second_fails:
                reject_compatibility_sets(failure, redis)
            assert second(uid) == 'second'
        before = stored()
        assert cache.load_projection(uid, 7, origin) == []
        assert stored() == before  # first is still mutating after second completed.
        return 'first'

    assert first('owner') == 'first'
    assert origin.call_count == 1
    cache.load_projection('owner', 7, origin)
    cache.load_projection('owner', 7, origin)
    assert origin.call_count == (3 if second_fails else 2)  # Failure stays bypassed; healthy recovers 90s cache.


@pytest.mark.parametrize('script', [cache._BEGIN_WRITE, cache._END_WRITE], ids=['begin_reply_lost', 'end_reply_lost'])
def test_unknown_fence_reply_does_not_retry_mutation_or_hide_its_error(storage, monkeypatch, script):
    _, redis = storage
    real_eval = redis.eval

    def uncertain(actual, *args):
        result = real_eval(actual, *args)
        if actual == script:
            raise ConnectionError('script ran; reply lost')
        return result

    monkeypatch.setattr(redis, 'eval', uncertain)
    error = ValueError('original mutation error')
    mutation = Mock(side_effect=error)
    with pytest.raises(ValueError) as raised:
        cache.invalidate_around_write(mutation)('owner')
    assert raised.value is error
    mutation.assert_called_once_with('owner')
    if script == cache._BEGIN_WRITE:
        assert redis.get(cache._version_key('owner')) == cache.BUSY


def test_uncertain_compatibility_set_reply_poison_is_conservative(coupled, storage, monkeypatch):
    client, store, _, _ = coupled
    _, redis = storage
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    before = stored()
    reject_compatibility_sets(monkeypatch, redis, after_apply=True)
    create_pending(monkeypatch, store)
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True  # Compat actually rotated.
    assert redis.get(cache._version_key('owner')) == cache.BUSY
    assert stored() == before


@pytest.mark.parametrize('failure_point', ['key', 'random'])
def test_cache_metadata_failure_preserves_mutation_error_once(storage, monkeypatch, failure_point):
    unavailable = Mock(side_effect=OSError('synthetic cache metadata failure'))
    monkeypatch.setattr(cache, '_version_key' if failure_point == 'key' else 'uuid4', unavailable)
    original = ValueError('original mutation error')
    mutation = Mock(side_effect=original)
    with pytest.raises(ValueError) as raised:
        cache.invalidate_around_write(mutation)('owner')
    assert raised.value is original
    mutation.assert_called_once_with('owner')
