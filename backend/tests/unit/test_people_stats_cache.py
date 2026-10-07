"""People-stats cache: generation namespacing, fail-open reads, and writer invalidation hooks.

The cache in ``database.people_stats_cache`` serves only the aggregate
person_id -> stats map behind ``GET /v1/users/people?include_stats=true``.
Everything here is hermetic: ``_FakeRedis`` models value+TTL with an injected
clock, and ``_Store`` is a path-keyed Firestore double exposing the
transaction/batch surface ``@firestore.transactional`` and
``run_transactional`` drive.
"""

import base64
import copy
import json
import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from google.api_core.exceptions import Aborted, AlreadyExists

import database.conversation_finalization_jobs as finalization_jobs
import database.conversations as conversations_db
import database.people_stats_cache as people_stats_cache
import database.proactivity as proactivity_db
import database.recording_sessions as recording_sessions_db
import database.redis_db as redis_db
import database.smart_merge as smart_merge_db
from database.people_stats_cache import invalidate_people_stats_cache
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
    StrictFirestoreTransaction,
)
from tests.unit.test_conversation_scan import _people_client, _segments, _stored
from utils.other.list_budget import ListReadBudget
from utils.people_stats import collect_people_stats

UID = 'test-uid'
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeRedis:
    """value+TTL store on an injected clock; ``fail_ops`` forces named ops to raise."""

    def __init__(self, clock):
        self._clock = clock
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self.fail_ops: set = set()
        self.ops: List[str] = []

    def _purge(self, key):
        expires = self._expiry.get(key)
        if expires is not None and self._clock() >= expires:
            self._store.pop(key, None)
            self._expiry.pop(key, None)

    def get(self, key):
        self.ops.append('get')
        if 'get' in self.fail_ops:
            raise ConnectionError('redis down')
        self._purge(key)
        return self._store.get(key)

    def set(self, key, value, ex=None, nx=False, **_kwargs):
        self.ops.append('set')
        if 'set' in self.fail_ops:
            raise ConnectionError('redis down')
        self._purge(key)
        if nx and self._store.get(key) is not None:
            return None
        self._store[key] = value
        if ex:
            self._expiry[key] = self._clock() + ex
        else:
            self._expiry.pop(key, None)
        return True

    def delete(self, *keys):
        self.ops.append('delete')
        if 'delete' in self.fail_ops:
            raise ConnectionError('redis down')
        return sum(int(self._store.pop(key, None) is not None) for key in keys)

    def exists(self, key):
        self._purge(key)
        return int(key in self._store)


def _cache_key(path: str) -> str:
    return f'cache:{base64.b64encode(path.encode("utf-8")).decode("utf-8")}'


def _budget(max_documents: int = 25000, seconds: float = 20.0, clock=None) -> ListReadBudget:
    now = clock() if clock else 1000.0
    return ListReadBudget(
        deadline_monotonic=now + seconds,
        max_documents=max_documents,
        clock=clock or (lambda: now),
        started_monotonic=now,
    )


@pytest.fixture
def fake_redis(monkeypatch):
    now = [1000.0]
    fake = _FakeRedis(clock=lambda: now[0])
    monkeypatch.setattr(redis_db, 'r', fake)
    monkeypatch.setattr(people_stats_cache, '_bounded_client', fake)
    return fake, now


def _scan_docs(count: int = 1100) -> List[dict]:
    return [_stored(f'c{i}', i) for i in range(count)]


def test_repeated_route_calls_scan_once_then_serve_the_cache_hit(monkeypatch, fake_redis):
    fake, _now = fake_redis
    http, client = _people_client(monkeypatch, _scan_docs(1100))
    params = {'include_stats': 'true', 'include_speech_samples': 'false'}

    first = http.get('/v1/users/people', params=params)
    assert first.status_code == 200
    assert client.raw_reads == 1000
    assert first.json()[0]['conversation_count'] == 1000

    second = http.get('/v1/users/people', params=params)
    assert second.status_code == 200
    assert client.raw_reads == 1000
    assert second.json() == first.json()


def test_cache_hit_is_per_user_and_per_scan_cap(monkeypatch, fake_redis):
    fake, _now = fake_redis
    first_rows, first_pulled = _pull_counted([_conv('pA') for _ in range(3)])
    first = collect_people_stats(first_rows, scan_cap=2, uid='u-a', budget=_budget())
    assert first['pA']['conversation_count'] == 2
    assert len(first_pulled) == 2

    same_key_rows, same_key_pulled = _pull_counted([_conv('pA')])
    same_key = collect_people_stats(same_key_rows, scan_cap=2, uid='u-a', budget=_budget())
    assert same_key == first
    assert same_key_pulled == []

    other_user_rows, other_user_pulled = _pull_counted([_conv('pB')])
    other_user = collect_people_stats(other_user_rows, scan_cap=2, uid='u-b', budget=_budget())
    assert other_user['pB']['conversation_count'] == 1
    assert len(other_user_pulled) == 1

    other_cap_rows, other_cap_pulled = _pull_counted([_conv('pA') for _ in range(3)])
    other_cap = collect_people_stats(other_cap_rows, scan_cap=3, uid='u-a', budget=_budget())
    assert other_cap['pA']['conversation_count'] == 3
    assert len(other_cap_pulled) == 3


def test_route_without_include_stats_performs_no_cache_io(monkeypatch, fake_redis):
    fake, _now = fake_redis
    http, client = _people_client(monkeypatch, _scan_docs(0))
    resp = http.get('/v1/users/people', params={'include_speech_samples': 'false'})
    assert resp.status_code == 200
    assert client.raw_reads == 0
    assert fake.ops == []


def test_entry_ttl_expiry_forces_a_rescan(monkeypatch, fake_redis):
    fake, now = fake_redis
    http, client = _people_client(monkeypatch, _scan_docs(3))
    params = {'include_stats': 'true', 'include_speech_samples': 'false'}

    assert http.get('/v1/users/people', params=params).status_code == 200
    assert client.raw_reads == 3

    now[0] += people_stats_cache.PEOPLE_STATS_ENTRY_TTL_SECONDS + 1
    assert http.get('/v1/users/people', params=params).status_code == 200
    assert client.raw_reads == 6


def _conv(person_id: str, **extra):
    return {
        'started_at': T0,
        'transcript_segments': _segments(person_id),
        **extra,
    }


def _generation(fake, uid=UID):
    return fake._store[f'people_stats:v1:{uid}:generation']


def _seed_entry(fake, uid, generation, payload, cap=1000):
    fake.set(_cache_key(people_stats_cache._entry_path(uid, generation, cap)), json.dumps(payload), ex=60)


def _pull_counted(rows):
    pulled = []

    def gen():
        for row in rows:
            pulled.append(row)
            yield row

    return gen(), pulled


def test_empty_stats_map_is_a_legitimate_hit(monkeypatch, fake_redis):
    fake, _now = fake_redis
    generation = people_stats_cache.current_generation(UID)
    _seed_entry(fake, UID, generation, {'schema_version': 1, 'stats': {}})
    rows, pulled = _pull_counted([_conv('p1')])
    assert collect_people_stats(rows, uid=UID, budget=_budget()) == {}
    assert pulled == []


@pytest.mark.parametrize(
    'payload',
    [
        'not-a-dict',
        {'schema_version': 2, 'stats': {}},
        {'schema_version': 1, 'stats': 'oops'},
        {'schema_version': 1, 'stats': {'p1': {'conversation_count': True, 'talk_seconds': 0.0}}},
        {'schema_version': 1, 'stats': {'p1': {'conversation_count': -1}}},
        {'schema_version': 1, 'stats': {'p1': {'conversation_count': 1, 'auto_conversation_count': 5}}},
        {'schema_version': 1, 'stats': {'p1': 'not-a-mapping'}},
        {
            'schema_version': 1,
            'stats': {
                'p1': {
                    'conversation_count': 1,
                    'auto_conversation_count': 0,
                    'talk_seconds': 10**1000,
                }
            },
        },
        {
            'schema_version': 1,
            'stats': {
                'p1': {
                    'conversation_count': 1,
                    'auto_conversation_count': 0,
                    'talk_seconds': float('nan'),
                }
            },
        },
        {
            'schema_version': 1,
            'stats': {
                'p1': {
                    'conversation_count': 1,
                    'auto_conversation_count': 0,
                    'talk_seconds': 0.0,
                    'last_heard_at': 'not-a-date',
                }
            },
        },
        {
            'schema_version': 1,
            'stats': {
                'p1': {
                    'conversation_count': 1,
                    'auto_conversation_count': 0,
                    'talk_seconds': 0.0,
                    'last_heard_at': 42,
                }
            },
        },
    ],
)
def test_corrupted_entry_is_a_clean_miss(monkeypatch, fake_redis, payload):
    fake, _now = fake_redis
    generation = people_stats_cache.current_generation(UID)
    _seed_entry(fake, UID, generation, payload)
    rows, pulled = _pull_counted([_conv('p1')])
    stats = collect_people_stats(rows, uid=UID, budget=_budget())
    assert stats['p1']['conversation_count'] == 1
    assert pulled != []


def test_oversized_entry_is_a_miss_and_oversized_result_is_not_stored(monkeypatch, fake_redis):
    fake, _now = fake_redis
    generation = people_stats_cache.current_generation(UID)
    big = {
        'schema_version': 1,
        'stats': {'p' * 300000: {'conversation_count': 1, 'auto_conversation_count': 0, 'talk_seconds': 0.0}},
    }
    _seed_entry(fake, UID, generation, big)
    rows, pulled = _pull_counted([_conv('p1')])
    assert collect_people_stats(rows, uid=UID, budget=_budget())['p1']['conversation_count'] == 1
    assert pulled != []

    huge_stats = {
        f'p{i}': {
            'conversation_count': 1,
            'last_heard_at': None,
            'talk_seconds': 0.0,
            'auto_conversation_count': 0,
        }
        for i in range(30000)
    }
    people_stats_cache.write_people_stats_cache(UID, generation, 500, huge_stats)
    assert _cache_key(people_stats_cache._entry_path(UID, generation, 500)) not in fake._store


def test_restore_stats_rejects_non_string_person_keys():
    entry = {'conversation_count': 1, 'auto_conversation_count': 0, 'talk_seconds': 0.0}
    assert people_stats_cache._restore_stats({5: entry}) is None
    assert people_stats_cache._restore_stats({'p1': entry}) is not None


def test_last_heard_at_round_trips_through_iso_strings(monkeypatch, fake_redis):
    fake, _now = fake_redis
    heard = datetime(2026, 1, 5, 12, 30, tzinfo=timezone.utc)
    people_stats_cache.write_people_stats_cache(
        UID,
        'g1',
        1000,
        {'p1': {'conversation_count': 2, 'last_heard_at': heard, 'talk_seconds': 7.5, 'auto_conversation_count': 1}},
    )
    restored = people_stats_cache.read_people_stats_cache(UID, 'g1', 1000)
    assert restored['p1']['last_heard_at'] == heard
    assert restored['p1']['talk_seconds'] == 7.5


def test_naive_last_heard_at_restores_as_utc(monkeypatch, fake_redis):
    fake, _now = fake_redis
    generation = people_stats_cache.current_generation(UID)
    _seed_entry(
        fake,
        UID,
        generation,
        {
            'schema_version': 1,
            'stats': {
                'p1': {
                    'conversation_count': 1,
                    'auto_conversation_count': 0,
                    'talk_seconds': 1.0,
                    'last_heard_at': '2026-01-05T12:30:00',
                }
            },
        },
    )
    restored = people_stats_cache.read_people_stats_cache(UID, generation, 1000)
    assert restored['p1']['last_heard_at'] == datetime(2026, 1, 5, 12, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('op', ['get', 'set'])
def test_redis_failures_fail_open_and_the_request_still_succeeds(monkeypatch, fake_redis, op):
    fake, _now = fake_redis
    fake.fail_ops.add(op)
    rows = [_conv('p1')]
    stats = collect_people_stats(iter(rows), uid=UID, budget=_budget())
    assert stats['p1']['conversation_count'] == 1


def test_redis_failure_on_generation_lookups_disables_cache_only(monkeypatch, fake_redis):
    fake, _now = fake_redis
    fake.fail_ops.update({'get', 'set'})
    invalidate_people_stats_cache(UID)
    assert people_stats_cache.current_generation(UID) is None


def test_generation_and_invalidation_failures_record_fallback_telemetry(monkeypatch, fake_redis):
    fake, _now = fake_redis
    fake.fail_ops.update({'get', 'set'})
    events = []
    monkeypatch.setattr(people_stats_cache, 'record_fallback', lambda **kw: events.append(kw))
    assert people_stats_cache.current_generation(UID) is None
    invalidate_people_stats_cache(UID)
    assert len(events) == 2
    for event in events:
        assert event['component'] == 'other'
        assert event['from_mode'] == 'cached'
        assert event['to_mode'] == 'uncached'
        assert event['reason'] == 'connection_lost'
        assert event['outcome'] == 'recovered'


def test_invalid_stats_are_never_stored(monkeypatch, fake_redis):
    fake, _now = fake_redis
    for stats in (
        {'p1': {'conversation_count': -1, 'last_heard_at': None, 'talk_seconds': 0.0, 'auto_conversation_count': 0}},
        {
            'p1': {
                'conversation_count': 1,
                'last_heard_at': None,
                'talk_seconds': float('inf'),
                'auto_conversation_count': 0,
            }
        },
        {'p1': {'conversation_count': 1, 'last_heard_at': None, 'talk_seconds': 'loud', 'auto_conversation_count': 0}},
    ):
        people_stats_cache.write_people_stats_cache(UID, 'g1', 1000, stats)
        assert _cache_key(people_stats_cache._entry_path(UID, 'g1', 1000)) not in fake._store


def test_truncated_scan_is_never_stored_and_the_next_call_rescans(monkeypatch, fake_redis):
    fake, _now = fake_redis
    budget = _budget(max_documents=2)
    budget.mark_exhausted('documents')
    collect_people_stats(iter([_conv('p1'), _conv('p1')]), uid=UID, budget=budget)
    assert [key for key in fake._store if key.startswith('cache:')] == []
    rows, pulled = _pull_counted([_conv('p1')])
    assert collect_people_stats(rows, uid=UID, budget=_budget())['p1']['conversation_count'] == 1
    assert pulled != []


def test_invalidation_during_the_scan_retires_the_pending_write(monkeypatch, fake_redis):
    fake, _now = fake_redis
    initial_generation = people_stats_cache.current_generation(UID)
    assert initial_generation is not None
    retired_path = _cache_key(people_stats_cache._entry_path(UID, initial_generation, 1000))

    def gen():
        yield _conv('p1')
        invalidate_people_stats_cache(UID)
        yield _conv('p2')

    stats = collect_people_stats(gen(), uid=UID, budget=_budget())
    assert stats['p1']['conversation_count'] == 1
    generation = _generation(fake)
    assert generation != initial_generation
    assert retired_path not in fake._store
    assert people_stats_cache.read_people_stats_cache(UID, generation, 1000) is None


def test_invalidation_after_a_write_makes_the_entry_unreachable(monkeypatch, fake_redis):
    fake, _now = fake_redis
    collect_people_stats(iter([_conv('p1')]), uid=UID, budget=_budget())
    generation_before = _generation(fake)
    invalidate_people_stats_cache(UID)
    assert _generation(fake) != generation_before
    rows, pulled = _pull_counted([_conv('p1'), _conv('p1')])
    stats = collect_people_stats(rows, uid=UID, budget=_budget())
    assert stats['p1']['conversation_count'] == 2
    assert pulled != []


def _apply_patch(row: dict, patch: dict) -> None:
    for key, value in patch.items():
        parts = key.split('.')
        node = row
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value


class _TestDocument(StrictFirestoreDocument):
    """Strict document plus the non-transactional direct-CRUD surface the hooked writers use."""

    def collection(self, name):
        return _TestCollection(self._database, (*self.path, name))

    def collections(self):
        depth = len(self.path) + 2
        children = {
            path[:-1] for path in self._database.rows if len(path) == depth and path[: len(self.path)] == self.path
        }
        return [_TestCollection(self._database, child) for child in children]

    def set(self, data, merge=False):
        if merge and self.path in self._database.rows:
            _apply_patch(self._database.rows[self.path], data)
        else:
            self._database.rows[self.path] = copy.deepcopy(data)

    def update(self, data):
        if self.path not in self._database.rows:
            raise RuntimeError('missing row')
        _apply_patch(self._database.rows[self.path], data)

    def delete(self, *_args, **_kwargs):
        self._database.rows.pop(self.path, None)

    def create(self, data):
        if self.path in self._database.rows:
            raise AlreadyExists('document exists')
        self._database.rows[self.path] = copy.deepcopy(data)


class _DirectQuery:
    """Non-transactional equality scan; transactional reads keep the shared strict guard."""

    def __init__(self, database, path, filters=(), limit=None):
        self._database = database
        self._path = path
        self._filters = filters
        self._limit = limit

    def where(self, *args, filter=None, **_kwargs):
        assert filter is not None and not args
        return _DirectQuery(self._database, self._path, self._filters + (filter,), self._limit)

    def limit(self, count):
        return _DirectQuery(self._database, self._path, self._filters, count)

    def stream(self, **_kwargs):
        depth = len(self._path) + 1
        rows = []
        for path, data in self._database.rows.items():
            if len(path) != depth or path[: len(self._path)] != self._path:
                continue
            if all(data.get(node.field_path) == node.value for node in self._filters):
                snapshot = StrictFirestoreSnapshot(copy.deepcopy(data))
                snapshot.reference = _TestDocument(self._database, path)
                rows.append(snapshot)
        return iter(rows[: self._limit])


class _TestCollection(StrictFirestoreCollection):
    def document(self, name):
        return _TestDocument(self._database, (*self._path, name))

    def where(self, *args, filter=None, **kwargs):
        if args or filter is None or kwargs:
            return super().where(*args, filter=filter, **kwargs)
        return _DirectQuery(self._database, self._path, (filter,))

    def limit(self, count):
        return _DirectQuery(self._database, self._path, (), count)

    def stream(self, **_kwargs):
        return _DirectQuery(self._database, self._path, ()).stream()


class _TestTransaction(StrictFirestoreTransaction):
    """Strict transaction plus the merge-set/upsert/create-as-AlreadyExists surface."""

    def set(self, ref, data, merge=False):
        self._assert_reference_belongs(ref)
        self.has_written = True
        if merge and ref.path in self._database.rows:
            _apply_patch(self._database.rows[ref.path], data)
        else:
            self._database.rows[ref.path] = copy.deepcopy(data)
        self.sets.append((ref.path, copy.deepcopy(data)))

    def upsert(self, ref, data):
        self.set(ref, data, merge=True)

    def create(self, ref, data):
        self._assert_reference_belongs(ref)
        self.has_written = True
        if ref.path in self._database.rows:
            raise AlreadyExists('document exists')
        payload = copy.deepcopy(data)
        self.creates.append((ref.path, payload))
        self._database.rows[ref.path] = payload


class _TestBatch:
    """Non-transactional write batch for the direct-CRUD unlock writer."""

    def __init__(self, database):
        self._database = database
        self._ops = []

    def update(self, ref, data):
        self._ops.append(lambda: ref.update(data))

    def set(self, ref, data, merge=False):
        self._ops.append(lambda: ref.set(data, merge=merge))

    def delete(self, ref):
        self._ops.append(ref.delete)

    def commit(self):
        ops, self._ops = self._ops, []
        for op in ops:
            op()
        self._database.batch_commits += 1


class _TestStore(StrictFirestore):
    """Strict read-before-write store plus direct-CRUD, batch, and equality-scan adapters."""

    def __init__(self, rows: Optional[Dict[tuple, dict]] = None, **kwargs):
        super().__init__(rows, **kwargs)
        self.batch_commits = 0

    def collection(self, name):
        return _TestCollection(self, (name,))

    def document(self, path):
        parts = tuple(part for part in path.split('/') if part)
        return _TestDocument(self, parts)

    def transaction(self):
        transaction = _TestTransaction(self, allow_reads_after_writes=self._allow_reads_after_writes)
        self.transactions.append(transaction)
        return transaction

    def batch(self):
        return _TestBatch(self)

    def conv_path(self, uid, cid):
        return ('users', uid, 'conversations', cid)

    def seed_conv(self, uid, cid, **fields):
        self.rows[self.conv_path(uid, cid)] = {'id': cid, **fields}


@pytest.fixture
def writer_env(monkeypatch):
    store = _TestStore()
    invalidated: List[str] = []
    monkeypatch.setattr(conversations_db, 'db', store)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda uid: invalidated.append(uid))
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'leave_capture_group', lambda *a, **k: None)
    monkeypatch.setattr(conversations_db, 'delete_collection_recursive', lambda *a, **k: None)
    return store, invalidated


def _conv_payload(cid='c1', **extra):
    return {
        'id': cid,
        'status': 'in_progress',
        'discarded': False,
        'data_protection_level': 'standard',
        'transcript_segments': [],
        'structured': {},
        **extra,
    }


def test_upsert_conversation_invalidates_the_cache(writer_env):
    store, invalidated = writer_env
    conversations_db.upsert_conversation_with_lifecycle('u1', _conv_payload())
    assert store.rows[store.conv_path('u1', 'c1')]['id'] == 'c1'
    assert invalidated == ['u1']


def test_persist_processing_result_invalidates_on_commit_only(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='in_progress')
    assert conversations_db.persist_processing_result_with_lifecycle('u1', _conv_payload(status='completed')) is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert (
        conversations_db.persist_processing_result_with_lifecycle('u1', _conv_payload('missing', status='completed'))
        is False
    )
    assert invalidated == []


def test_create_conversation_if_absent_invalidates_on_create_only(writer_env):
    store, invalidated = writer_env
    assert conversations_db.create_conversation_if_absent_with_lifecycle('u1', _conv_payload()) is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert conversations_db.create_conversation_if_absent_with_lifecycle('u1', _conv_payload()) is False
    assert invalidated == []


def test_update_conversation_invalidates_on_applied_update(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='in_progress')
    assert conversations_db.update_conversation('u1', 'c1', {'starred': True}) is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert conversations_db.update_conversation('u1', 'missing', {'starred': True}) is False
    assert invalidated == []


def test_delete_conversation_invalidates_before_child_cleanup(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='completed')
    conversations_db.delete_conversation('u1', 'c1')
    assert store.conv_path('u1', 'c1') not in store.rows
    assert invalidated == ['u1']


def test_delete_conversation_invalidates_cache_when_proactivity_cleanup_fails(writer_env, monkeypatch):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='completed')

    def fail_purge(**kwargs):
        raise RuntimeError('source cleanup failed')

    monkeypatch.setattr(proactivity_db, 'purge_source_items', fail_purge)
    with pytest.raises(RuntimeError, match='source cleanup failed'):
        conversations_db.delete_conversation('u1', 'c1')
    assert store.conv_path('u1', 'c1') not in store.rows
    assert invalidated == ['u1']


def test_transition_conversation_status_invalidates(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='in_progress')
    conversations_db.transition_conversation_status('u1', 'c1', 'processing')
    assert store.rows[store.conv_path('u1', 'c1')]['status'] == 'processing'
    assert invalidated == ['u1']


def test_claim_conversation_status_invalidates_on_claim_including_discard(writer_env, monkeypatch):
    store, invalidated = writer_env
    from models.conversation_enums import ConversationStatus

    monkeypatch.setattr(
        conversations_db, 'extra_updates_with_bound_client_processing', lambda uid, current, extra: dict(extra)
    )
    store.seed_conv('u1', 'c1', status=ConversationStatus.in_progress.value)
    claimed = conversations_db.claim_conversation_status(
        'u1',
        'c1',
        ConversationStatus.in_progress,
        ConversationStatus.processing,
        extra_updates={'discarded': True},
    )
    assert claimed is True
    row = store.rows[store.conv_path('u1', 'c1')]
    assert row['status'] == 'processing' and row['discarded'] is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert (
        conversations_db.claim_conversation_status(
            'u1', 'c1', ConversationStatus.in_progress, ConversationStatus.processing
        )
        is False
    )
    assert invalidated == []


def test_discard_and_restore_both_invalidate(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='completed')
    conversations_db.set_conversation_as_discarded('u1', 'c1')
    assert store.rows[store.conv_path('u1', 'c1')]['discarded'] is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert conversations_db.restore_conversation_from_discarded('u1', 'c1') is True
    assert invalidated == ['u1']


def test_discard_by_relevance_invalidates_on_discard_only(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='completed')
    assert conversations_db.discard_by_relevance('u1', 'c1', {'verdict': 'discard'}) is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert conversations_db.discard_by_relevance('u1', 'c1', {'verdict': 'discard'}) is False
    assert invalidated == []


def test_update_conversation_finished_at_invalidates(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='in_progress')
    conversations_db.update_conversation_finished_at('u1', 'c1', T0)
    assert store.rows[store.conv_path('u1', 'c1')]['finished_at'] == T0
    assert invalidated == ['u1']


def test_assign_conversation_speaker_invalidates_before_observers(writer_env, monkeypatch):
    store, invalidated = writer_env
    import database.speaker_assignment_effects as effects
    import database.speaker_learning_jobs as learning

    events = []

    def record_invalidation(uid):
        invalidated.append(uid)
        events.append(('invalidate', uid))

    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', record_invalidation)
    current = {'id': 'c1', 'transcript_segments': [{'id': 's0', 'person_id': 'p1'}]}
    monkeypatch.setattr(
        effects,
        'run_assignment_transaction',
        lambda client, assign: (current, {'person_id': 'p1'}, [], [{'id': 's0'}]),
    )
    monkeypatch.setattr(learning, 'extract_learning_receipt_markers', lambda *a, **k: None)
    monkeypatch.setattr(
        learning,
        'record_speaker_learning_job_events',
        lambda *_a, **_k: events.append(('learning_events', None)),
    )
    monkeypatch.setattr(
        conversations_db,
        'record_speaker_review',
        lambda uid, *_a, **_k: events.append(('speaker_review', uid)),
    )

    conversations_db.assign_conversation_speaker('u1', 'c1', person_id='p1', segment_ids=['s0'], firestore_client=store)
    assert invalidated == ['u1']
    assert events == [('invalidate', 'u1'), ('speaker_review', 'u1'), ('learning_events', None)]


def test_update_conversation_segments_invalidates_on_applied_write(writer_env):
    store, invalidated = writer_env
    store.seed_conv('u1', 'c1', status='in_progress', transcript_segments=[])
    result = conversations_db.update_conversation_segments(
        'u1',
        'c1',
        [{'id': 's0', 'speaker_id': 0, 'is_user': True, 'start': 0, 'end': 1, 'text': 'hi'}],
        firestore_client=store,
    )
    assert result is True
    assert invalidated == ['u1']

    invalidated.clear()
    assert conversations_db.update_conversation_segments('u1', 'missing', [], firestore_client=store) is False
    assert invalidated == []


def test_assign_sync_conversation_invalidates_after_the_transaction(writer_env, monkeypatch):
    store, invalidated = writer_env
    import utils.sync.assignment as sync_assignment

    conversation = {'id': 'sync1', 'sync_merged_from': ['donor1']}
    monkeypatch.setattr(sync_assignment, 'assign_in_transaction', lambda *a, **k: (conversation, True, []))
    result = conversations_db.assign_sync_conversation(
        'u1', {'data_protection_level': 'standard', 'id': 'sync1'}, firestore_client=store
    )
    assert result[0]['id'] == 'sync1'
    assert invalidated == ['u1']


def test_assign_sync_conversation_invalidates_once_after_size_limit_retry(writer_env, monkeypatch):
    store, invalidated = writer_env
    import utils.sync.assignment as sync_assignment

    conversation = {'id': 'sync1', 'sync_merged_from': []}
    planned_calls = []

    def flaky_plan(transaction, user_ref, incoming, **kwargs):
        planned_calls.append(kwargs.get('full_ids'))
        if len(planned_calls) == 1:
            raise RuntimeError('sync rollover size limit')
        return (conversation, True, [])

    monkeypatch.setattr(sync_assignment, 'assign_in_transaction', flaky_plan)
    retries = []
    invalidated_before_return = []

    def fake_backstop(run, attempted_canonical):
        try:
            return run(frozenset())
        except RuntimeError:
            retries.append('retry')
            result = run(frozenset({'sync1'}))
            invalidated_before_return.append(len(invalidated))
            return result

    monkeypatch.setattr(sync_assignment, 'run_with_size_limit_backstop', fake_backstop)
    result = conversations_db.assign_sync_conversation(
        'u1', {'data_protection_level': 'standard', 'id': 'sync1'}, firestore_client=store
    )
    assert result[0]['id'] == 'sync1'
    assert planned_calls == [frozenset(), frozenset({'sync1'})]
    assert retries == ['retry']
    assert invalidated_before_return == [0]
    assert invalidated == ['u1']


def test_unlock_all_conversations_invalidates_after_every_batch_commit(writer_env):
    store, invalidated = writer_env
    for index in range(600):
        store.seed_conv('u1', f'l{index}', status='completed', is_locked=True)
    conversations_db.unlock_all_conversations('u1')
    assert invalidated == ['u1', 'u1']


def test_smart_merge_absorb_invalidates_after_absorbed_commit(writer_env, monkeypatch):
    store, invalidated = writer_env
    monkeypatch.setattr(smart_merge_db, 'invalidate_people_stats_cache', lambda uid: invalidated.append(uid))
    store.seed_conv(
        'u1',
        'surv',
        status='completed',
        transcript_segments=[],
        smart_merge={'revision': 3},
    )
    store.seed_conv('u1', 'donor', status='completed', transcript_segments=[])
    monkeypatch.setattr(smart_merge_db.audit_db, 'gate_skip', lambda *a, **k: smart_merge_db.audit_db.SKIPPED_ERROR)

    plan = lambda survivor, s_segs, donor, d_segs, ancestor_rows, last_fragment_row: (
        None,
        {'data_protection_level': 'standard', 'smart_merge': {'revision': 4}},
        {'deleted': True, 'smart_merge': {'role': 'donor', 'survivor_id': 'surv'}},
        {},
    )
    result = smart_merge_db.absorb_conversation(
        'u1', 'surv', 'donor', expected_revision=3, plan=plan, firestore_client=store
    )
    assert result.outcome == 'absorbed'
    assert invalidated == ['u1']


@pytest.mark.parametrize('deleted', [True, False])
def test_empty_conversation_cleanup_invalidates_after_delete(writer_env, monkeypatch, deleted):
    store, invalidated = writer_env
    monkeypatch.setattr(recording_sessions_db, 'invalidate_people_stats_cache', lambda uid: invalidated.append(uid))
    monkeypatch.setattr(
        recording_sessions_db,
        'firestore',
        SimpleNamespace(transactional=lambda fn: (lambda transaction: deleted)),
    )
    assert (
        recording_sessions_db.tombstone_and_delete_empty_conversation('u1', 'c1', None, firestore_client=store)
        is deleted
    )
    assert invalidated == (['u1'] if deleted else [])


def test_finalization_intent_retries_contention_and_invalidates_only_on_creation(writer_env, monkeypatch):
    store, invalidated = writer_env
    monkeypatch.setattr(finalization_jobs, 'invalidate_people_stats_cache', lambda uid: invalidated.append(uid))
    store.seed_conv('u1', 'c1', status='in_progress', has_content=True)

    transactional_calls = []
    original_transactional = finalization_jobs.firestore.transactional

    def fail_first_transactional_attempt(function):
        decorated = original_transactional(function)

        def invoke(transaction, *args, **kwargs):
            transactional_calls.append(transaction)
            if len(transactional_calls) == 1:
                raise Aborted('synthetic read contention')
            return decorated(transaction, *args, **kwargs)

        return invoke

    monkeypatch.setattr(finalization_jobs.firestore, 'transactional', fail_first_transactional_attempt)
    original_retry = finalization_jobs.run_with_transaction_contention_retry

    def retry_without_wait(transaction_factory, operation, **kwargs):
        return original_retry(
            transaction_factory,
            operation,
            **kwargs,
            sleep=lambda _delay: None,
            random_value=lambda: 0.0,
        )

    monkeypatch.setattr(finalization_jobs, 'run_with_transaction_contention_retry', retry_without_wait)

    intent = finalization_jobs.create_or_get_finalization_intent(
        'u1',
        'c1',
        requires_byok=False,
        finalization_admission=lambda conv: {
            'accepted': True,
            'terminal': False,
            'reason': '',
            'fanout_key': 'k1',
        },
        extra_updates={'external_data': {'origin': 'calendar'}},
        firestore_client=store,
    )
    assert intent['created'] is True
    assert len(transactional_calls) == 2
    assert transactional_calls[0] is not transactional_calls[1]
    row = store.rows[store.conv_path('u1', 'c1')]
    assert row['status'] == 'processing'
    assert invalidated == ['u1']

    repeated_intent = finalization_jobs.create_or_get_finalization_intent(
        'u1',
        'c1',
        requires_byok=False,
        finalization_admission=lambda conv: {
            'accepted': True,
            'terminal': False,
            'reason': '',
            'fanout_key': 'k1',
        },
        firestore_client=store,
    )
    assert repeated_intent['created'] is False
    assert invalidated == ['u1']


def test_cache_client_bounds_socket_io(monkeypatch):
    """A stalled Redis must not block conversation writers: the cache client carries socket timeouts."""
    built = {}

    class _Recorder:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(people_stats_cache, '_bounded_client', None)
    monkeypatch.setattr(redis_db.redis, 'Redis', _Recorder)
    monkeypatch.setenv('REDIS_DB_HOST', 'redis.internal')
    monkeypatch.setenv('REDIS_DB_PORT', '6380')
    monkeypatch.setenv('REDIS_DB_PASSWORD', 'cache-secret')
    assert isinstance(people_stats_cache._redis(), _Recorder)
    assert built['host'] == 'redis.internal'
    assert built['port'] == 6380
    assert built['password'] == 'cache-secret'
    assert built['socket_timeout'] == people_stats_cache.PEOPLE_STATS_REDIS_TIMEOUT_SECONDS
    assert built['socket_connect_timeout'] == people_stats_cache.PEOPLE_STATS_REDIS_TIMEOUT_SECONDS
    assert built['health_check_interval'] == 30
    assert 0 < people_stats_cache.PEOPLE_STATS_REDIS_TIMEOUT_SECONDS <= 0.5


def test_redis_client_construction_failure_fails_open(monkeypatch):
    monkeypatch.setattr(people_stats_cache, '_bounded_client', None)
    monkeypatch.setenv('REDIS_DB_HOST', 'redis.internal')
    monkeypatch.setenv('REDIS_DB_PORT', 'not-a-port')
    fallback_events = []
    monkeypatch.setattr(people_stats_cache, 'record_fallback', lambda **kwargs: fallback_events.append(kwargs))

    stats = collect_people_stats(iter([_conv('p1')]), uid=UID, budget=_budget())
    assert stats['p1']['conversation_count'] == 1
    people_stats_cache.invalidate_people_stats_cache(UID)
    assert fallback_events
    assert all(event['to_mode'] == 'uncached' for event in fallback_events)


def test_unconfigured_redis_disables_the_cache_without_error(monkeypatch):
    monkeypatch.setattr(people_stats_cache, '_bounded_client', None)
    monkeypatch.delenv('REDIS_DB_HOST', raising=False)
    assert people_stats_cache.current_generation('u1') is None
    assert people_stats_cache.read_people_stats_cache('u1', 'g1', 1000) is None
    people_stats_cache.write_people_stats_cache('u1', 'g1', 1000, {})
    people_stats_cache.invalidate_people_stats_cache('u1')
