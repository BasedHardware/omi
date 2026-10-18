"""Real promote projection, counted offline reads, and versioned negative-cache races."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from redis.crc import key_slot

from database import candidates, s5_candidates_cache, staged_promote_cache as cache, staged_tasks, workstreams
from models.candidate import CandidateRecord
from models.task_intelligence import TaskWorkflowControl
from routers import staged_tasks as route
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_external_list_nested_budget import Store, Query, Ref
from utils.observability.external_lists import (
    EXTERNAL_LIST_HTTP_TOTAL,
    ExternalListMetricsMiddleware,
    STAGED_PROMOTE_ROUTE,
)
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
EMPTY = b'{"promoted":false,"reason":"No staged tasks available","promoted_task":null}'
FLAG = 'OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED'


def test_coordinator_keys_share_cluster_slot_and_isolate_owners():
    version = cache._version_key('owner').encode()
    other_version = cache._version_key('other-owner').encode()

    assert key_slot(version) == key_slot(version + b':writers')
    assert version != other_version
    assert key_slot(version) != key_slot(other_version)
    assert cache.compatibility_version_key('owner') == 'fsr:s5:candidates:version:owner'


class Clock:
    seconds = 1000.0

    def time(self):
        return self.seconds

    monotonic = time


class Redis:
    def __init__(self, clock):
        self.clock, self.data, self.expiry, self.calls = clock, {}, {}, []

    def get(self, key):
        self.calls.append(('get', key, {}))
        if self.expiry.get(key, float('inf')) <= self.clock.time() * 1000:
            self.data.pop(key, None)
        return self.data.get(key)

    def set(self, key, value, *, ex=None, pxat=None, nx=False):
        self.calls.append(('set', key, {'ex': ex, 'pxat': pxat, 'nx': nx}))
        if nx and key in self.data and self.expiry[key] > self.clock.time() * 1000:
            return False
        self.data[key] = value
        self.expiry[key] = pxat if pxat is not None else (self.clock.time() + ex) * 1000 if ex else float('inf')
        return True

    def eval(self, script, count, version_key, writers_key, *args):
        # Model the three atomic commands for unit fault/interleaving tests.
        # The production Lua itself is separately exercised with local Redis.
        self.calls.append(('eval', version_key, {'script': script}))
        if script == cache._READ_VERSION:
            if writers_key in self.data:
                return cache.BUSY
            version = self.get(version_key)
            if not version:
                self.set(version_key, args[0], ex=int(args[1]))
                version = args[0]
            return version
        self.set(version_key, cache.BUSY)
        writers = self.data.setdefault(writers_key, {})
        if script == cache._BEGIN_WRITE:
            if 'poison' in writers:
                return 0
            writers[args[0]] = '1'
            return 1
        assert script == cache._END_WRITE
        if args[0] not in writers or args[1] != 1:
            writers['poison'] = '1'
        writers.pop(args[0], None)
        if not writers:
            self.data.pop(writers_key)
            self.set(version_key, args[2], ex=int(args[3]))
            return 1
        return 0


@pytest.fixture
def storage(monkeypatch):
    clock = Clock()
    redis = Redis(clock)
    monkeypatch.setattr(cache, 'time', clock)
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(s5_candidates_cache, '_redis', lambda: redis)
    monkeypatch.delenv(FLAG, raising=False)
    return clock, redis


class Rows(dict):
    # Share one backing store with the ordering-strict transaction fake, whose
    # refs use tuple paths, and the counted query fixture, whose paths are strings.
    @staticmethod
    def key(key):
        return '/'.join(key) if isinstance(key, tuple) else key

    def __getitem__(self, key):
        return super().__getitem__(self.key(key))

    def __setitem__(self, key, value):
        super().__setitem__(self.key(key), value)

    def __contains__(self, key):
        return super().__contains__(self.key(key))

    def get(self, key, default=None):
        return super().get(self.key(key), default)


class Reference(Ref):
    def collection(self, path):
        return Collection(self.store, self.path + '/' + path)

    def set(self, data):
        self.store.rows[self.path] = data

    def update(self, data):
        self.store.rows[self.path].update(data)

    def delete(self):
        self.store.rows.pop(self.path, None)


class Collection(Query):
    def document(self, doc_id):
        return Reference(self.store, self.path + '/' + doc_id)


class Firestore(Store):
    def collection(self, path):
        return Collection(self, path)


def candidate(status='pending', generation=7, row_id='legacy'):
    proposal = proposal_from_legacy_staged({'id': row_id, 'description': 'A task'})
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id='canonical',
        account_generation=generation,
        idempotency_key='offline-test',
        status=status,
        created_at=NOW,
        resolved_at=NOW if status != 'pending' else None,
        resolution_reason=status if status != 'pending' else None,
        result_task_id='existing-task' if status == 'accepted' else None,
    ).model_dump(mode='python')


@pytest.fixture
def serving(monkeypatch, storage):
    store = Firestore(Rows())
    monkeypatch.setattr(staged_tasks, 'db', store)
    monkeypatch.setattr(candidates, 'db', store)
    monkeypatch.setattr(route.task_control_db, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(route, 'load_compatibility_candidates', lambda uid, generation, loader: loader())
    store.rows['users/owner/task_intelligence_control/state'] = TaskWorkflowControl(account_generation=7).model_dump()
    app = FastAPI()
    app.include_router(route.router)
    app.add_middleware(ExternalListMetricsMiddleware)
    owner = SimpleNamespace(uid='owner')
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: owner.uid
    selected = Mock(return_value={'promoted': True, 'reason': None, 'promoted_task': None})
    monkeypatch.setattr(route, 'promote_staged_task_by_id', selected)
    return TestClient(app), store, selected, owner


def billed(store):
    return store.physical + sum(count == 0 for _, _, _, count in store.windows)


def reset(store):
    store.physical = store.streams = store.batch_gets = 0
    store.windows.clear()


@pytest.mark.parametrize('history', [False, True])
def test_empty_cold_and_60_second_warm_poll_match_flag_off_bytes(serving, storage, monkeypatch, history):
    client, store, selected, _ = serving
    clock, redis = storage
    if history:
        for i in range(300):
            store.rows[f'users/owner/candidates/terminal-{i}'] = candidate('rejected', row_id=f'gone-{i}')
        for i in range(200):
            store.rows[f'users/owner/staged_tasks/completed-{i}'] = {'completed': True}
        for i in range(120):
            store.rows[f'users/owner/candidates/other-generation-{i}'] = candidate(generation=8)
        for i in range(80):
            record = candidate()
            record['evidence_refs'][0]['id'] = f'non-staged-evidence-{i}'
            record['source_surface'] = 'chat'
            CandidateRecord.model_validate(record)
            store.rows[f'users/owner/candidates/non-staged-{i}'] = record
    counter = cache.OPERATIONS.labels(outcome='hit')
    before = counter._value.get()
    cold = client.post(STAGED_PROMOTE_ROUTE)
    assert cold.status_code == 200 and cold.content == EMPTY
    cold_reads, cold_queries = billed(store), store.streams
    assert cold_queries == 2 and cold_reads == (581 if history else 3)
    assert all(window[2] != 1 for window in store.windows)  # No new probe RPCs.
    clock.seconds += 60
    reset(store)
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    assert store.physical == billed(store) == 1 and store.streams == 0  # Fresh control fence only.
    assert counter._value.get() == before + 1
    selected.assert_not_called()
    monkeypatch.setenv(FLAG, ' FaLsE ')
    redis.calls.clear()
    reset(store)
    off = client.post(STAGED_PROMOTE_ROUTE)
    assert off.status_code == 200 and off.content == cold.content
    assert billed(store) == cold_reads and store.streams == cold_queries and not redis.calls
    print(f'empty history={history}: cold/off={cold_reads} modeled reads, warm60s=1 control read, zero scan queries')


@pytest.mark.parametrize(
    'kind',
    [
        'legacy_missing_fields',
        'completed',
        'hidden_legacy',
        'rejected_suppresses_legacy',
        'candidate',
        'accepted_suppresses_legacy',
        'other_generation',
        'malformed_candidate',
    ],
)
def test_projection_selection_and_cold_read_counts_unchanged(serving, storage, monkeypatch, kind):
    client, store, selected, _ = serving
    if kind in {
        'legacy_missing_fields',
        'completed',
        'hidden_legacy',
        'accepted_suppresses_legacy',
        'rejected_suppresses_legacy',
    }:
        store.rows['users/owner/staged_tasks/legacy'] = {'description': 'A task'}
        if kind == 'hidden_legacy':
            store.rows['users/owner/staged_tasks/legacy']['hidden'] = True
        if kind == 'completed':
            store.rows['users/owner/staged_tasks/legacy']['completed'] = True
    if kind in {'candidate', 'accepted_suppresses_legacy', 'rejected_suppresses_legacy', 'other_generation'}:
        status = (
            'accepted'
            if kind == 'accepted_suppresses_legacy'
            else 'rejected' if kind == 'rejected_suppresses_legacy' else 'pending'
        )
        store.rows['users/owner/candidates/canonical'] = candidate(status, 8 if kind == 'other_generation' else 7)
    if kind == 'malformed_candidate':
        store.rows['users/owner/candidates/broken'] = {'status': 'pending'}
    on = client.post(STAGED_PROMOTE_ROUTE)
    on_selection, on_reads, on_queries = selected.call_args_list[:], billed(store), store.streams
    selected.reset_mock()
    reset(store)
    monkeypatch.setenv(FLAG, 'false')
    off = client.post(STAGED_PROMOTE_ROUTE)
    assert off.status_code == on.status_code == 200 and off.content == on.content
    assert selected.call_args_list == on_selection
    assert billed(store) == on_reads and store.streams == on_queries
    if kind in {'legacy_missing_fields', 'hidden_legacy', 'candidate'}:
        selected.assert_called_once_with('canonical' if kind == 'candidate' else 'legacy', uid='owner')
        assert not any(value == '1' for value in storage[1].data.values())
    else:
        assert off.content == EMPTY
        selected.assert_not_called()


def test_real_legacy_create_invalidates_cached_empty(serving, storage):
    client, store, selected, _ = serving
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    storage[0].seconds += 1800
    created = staged_tasks.create_staged_task('owner', 'New historical task')
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with(created['id'], uid='owner')


def test_real_candidate_create_invalidates_cached_empty(serving, storage, monkeypatch):
    client, store, selected, _ = serving
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    storage[0].seconds += 1800
    strict = StrictFirestore()
    strict.rows = store.rows
    with monkeypatch.context() as patch:
        patch.setattr(candidates, 'db', strict)
        patch.setattr(candidates.firestore, 'transactional', lambda fn: fn)
        created = candidates.create_candidate(
            'owner',
            proposal_from_legacy_staged({'id': 'new', 'description': 'New pending'}),
            idempotency_key='create-after-empty',
            account_generation=7,
            now=datetime.now(timezone.utc),
        )
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with(created.candidate_id, uid='owner')


def test_generation_change_and_owner_isolation_keep_fence_first(serving):
    client, store, selected, owner = serving
    store.rows['users/owner/candidates/canonical'] = candidate(generation=8)
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    store.rows['users/owner/task_intelligence_control/state']['account_generation'] = 8
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')
    owner.uid = 'other-owner'
    store.rows['users/other-owner/staged_tasks/new'] = {'description': 'Other owner'}
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    assert selected.call_args.args == ('new',) and selected.call_args.kwargs == {'uid': 'other-owner'}


@pytest.mark.parametrize('value', ['', '0', 'true', 'off'])
def test_cache_is_on_unless_false(serving, storage, monkeypatch, value):
    client, store, _, _ = serving
    monkeypatch.setenv(FLAG, value)
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    reset(store)
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    assert billed(store) == 1 and store.streams == 0


def test_auth_failure_measured_before_control_or_cache(serving, storage):
    client, store, _, _ = serving

    def unauthorized():
        raise HTTPException(401)

    client.app.dependency_overrides[route.auth.get_current_user_uid] = unauthorized
    counter = EXTERNAL_LIST_HTTP_TOTAL.labels(route=STAGED_PROMOTE_ROUTE, outcome='auth_error')
    before = counter._value.get()
    assert client.post(STAGED_PROMOTE_ROUTE).status_code == 401
    assert counter._value.get() == before + 1
    assert store.streams == store.physical == 0 and not storage[1].calls
    assert client.get(STAGED_PROMOTE_ROUTE).status_code == 405
    assert counter._value.get() == before + 1


def test_ttl_is_one_hour_and_fill_cannot_extend_projection_start(storage):
    clock, redis = storage
    calls = []

    def loader():
        calls.append(1)
        clock.seconds += 10
        return []

    cache.load_projection('u', 7, loader)
    marker = next(key for key, value in redis.data.items() if value == '1')
    assert redis.expiry[marker] == 4600000  # Started at 1000, not fill time 1010.
    clock.seconds = 4599
    assert cache.load_projection('u', 7, loader) == [] and len(calls) == 1
    clock.seconds = 4600
    cache.load_projection('u', 7, loader)
    assert len(calls) == 2


def test_already_expired_fill_is_skipped(storage):
    clock, redis = storage

    def slow():
        clock.seconds += cache.TTL_SECONDS
        return []

    cache.load_projection('u', 7, slow)
    assert not any(value == '1' for value in redis.data.values())


def test_write_between_scan_and_late_fill_cannot_poison_new_version(storage):
    _, redis = storage

    def empty_before_write():
        cache.invalidate_around_write(lambda uid: None)('u')
        return []

    cache.load_projection('u', 7, empty_before_write)
    assert not any(value == '1' for value in redis.data.values())
    pending = [{'id': 'new'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


def test_write_after_fill_comparison_only_strands_old_version_key(storage, monkeypatch):
    _, redis = storage
    real_set = redis.set

    def raced_set(key, value, **kwargs):
        if kwargs.get('pxat'):
            cache.invalidate('u')
        return real_set(key, value, **kwargs)

    monkeypatch.setattr(redis, 'set', raced_set)
    cache.load_projection('u', 7, lambda: [])
    pending = [{'id': 'committed-after-version-check'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


@pytest.mark.parametrize('fails', [False, True])
def test_scan_during_write_is_fenced_after_success_or_partial_failure(storage, fails):
    @cache.invalidate_around_write
    def mutation(uid):
        cache.load_projection(uid, 7, lambda: [])  # Captures the before-write version.
        if fails:
            raise RuntimeError('partial batch write')
        return 'committed'

    if fails:
        with pytest.raises(RuntimeError, match='partial batch'):
            mutation('u')
    else:
        assert mutation('u') == 'committed'
    pending = [{'id': 'durably-created'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


@pytest.mark.parametrize('evict', ['during_fill', 'after_fill', 'version_expiry'])
def test_missing_or_evicted_version_never_reuses_old_marker(storage, evict):
    clock, redis = storage
    key = cache._version_key('u')

    def empty():
        if evict == 'during_fill':
            redis.data.pop(key)
        return []

    cache.load_projection('u', 7, empty)
    if evict == 'version_expiry':
        redis.expiry[key] = clock.time() * 1000
    else:
        redis.data.pop(key, None)
    pending = [{'id': 'new'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


@pytest.mark.parametrize('phase', ['read', 'fill_check', 'fill', 'invalidate'])
def test_redis_faults_fail_open_and_preserve_mutation_result(storage, monkeypatch, phase):
    _, redis = storage
    fallback = Mock()
    monkeypatch.setattr(cache, 'record_fallback', fallback)
    real_get, real_set = redis.get, redis.set
    gets = {}

    def broken_get(key):
        gets[key] = gets.get(key, 0) + 1
        if phase == 'read' or (phase == 'fill_check' and key == cache._version_key('u') and gets[key] == 2):
            raise RuntimeError('offline')
        return real_get(key)

    def broken_set(key, value, **kwargs):
        if phase == 'invalidate' or (phase == 'fill' and kwargs.get('pxat')):
            raise RuntimeError('offline')
        return real_set(key, value, **kwargs)

    monkeypatch.setattr(redis, 'get', broken_get)
    monkeypatch.setattr(redis, 'set', broken_set)
    loader = Mock(return_value=[])
    assert cache.load_projection('u', 7, loader) == []
    loader.assert_called_once_with()
    assert cache.invalidate_around_write(lambda uid: 'committed')('u') == 'committed'
    assert fallback.called


def test_origin_failure_is_never_retried_or_cached(storage):
    loader = Mock(side_effect=ValueError('origin error'))
    with pytest.raises(ValueError, match='origin error'):
        cache.load_projection('u', 7, loader)
    loader.assert_called_once_with()
    assert not any(value == '1' for value in storage[1].data.values())


def test_version_disappearing_at_lookup_does_not_retry_origin_error(storage, monkeypatch):
    monkeypatch.setattr(storage[1], 'get', lambda key: None)
    loader = Mock(side_effect=ValueError('origin error'))
    with pytest.raises(ValueError, match='origin error'):
        cache.load_projection('u', 7, loader)
    loader.assert_called_once_with()


def test_invalidation_during_hit_lookup_rechecks_version(storage, monkeypatch):
    _, redis = storage
    cache.load_projection('u', 7, lambda: [])
    real_get = redis.get

    def raced_get(key):
        result = real_get(key)
        if result == '1':
            cache.invalidate('u')
        return result

    monkeypatch.setattr(redis, 'get', raced_get)
    pending = [{'id': 'newly-committed'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


def test_writers_invalidate_flag_off_revision_entries(storage, monkeypatch):
    cache.load_projection('u', 7, lambda: [])
    monkeypatch.setenv(FLAG, 'false')
    assert cache.invalidate_around_write(lambda uid: 'ok')('u') == 'ok'
    monkeypatch.delenv(FLAG)
    pending = [{'id': 'newly-written'}]
    assert cache.load_projection('u', 7, lambda: pending) == pending


def test_long_ttl_kill_switch_restores_90_seconds(storage, monkeypatch):
    clock, _ = storage
    monkeypatch.setenv('OMI_STAGED_PROMOTE_LONG_TTL_ENABLED', 'false')
    origin = Mock(return_value=[])
    cache.load_projection('u', 7, origin)
    clock.seconds += 89
    cache.load_projection('u', 7, origin)
    assert origin.call_count == 1
    clock.seconds += 1
    cache.load_projection('u', 7, origin)
    assert origin.call_count == 2


def test_long_ttl_kill_switch_bypasses_an_existing_one_hour_marker(storage, monkeypatch):
    clock, redis = storage
    origin = Mock(return_value=[])
    cache.load_projection('u', 7, origin)
    hour_marker = next(key for key, value in redis.data.items() if value == '1')
    clock.seconds += 10
    monkeypatch.setenv('OMI_STAGED_PROMOTE_LONG_TTL_ENABLED', 'false')
    cache.load_projection('u', 7, origin)
    assert origin.call_count == 2
    assert redis.get(hour_marker) == '1'  # Still present, but never read with the lever off.
    clock.seconds += 89
    cache.load_projection('u', 7, origin)
    assert origin.call_count == 2
    clock.seconds += 1
    cache.load_projection('u', 7, origin)
    assert origin.call_count == 3
