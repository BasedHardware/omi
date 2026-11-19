"""Stored recap references must address live, owner-scoped feedback targets."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from threading import Barrier, Event, Lock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.daily_summary import DailySummaryResponse
from models.memories import MemoryDB
from routers import memories, users
from utils import daily_summary_validation as validation
from utils.memory import recap_review

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
UID = 'test-owner'


def _memory(mid, **fields):
    return MemoryDB(
        id=mid, uid=UID, content=f'current {mid}', category='interesting', created_at=NOW, updated_at=NOW, **fields
    )


def _summary(*ids):
    return DailySummaryResponse.model_validate(
        {
            'id': 'recap',
            'date': '2026-11-14',
            'memories_learned': [
                {'memory_id': mid, 'content': 'old snapshot', 'category': 'interesting'} for mid in ids
            ],
            'stats': {'memories_learned_count': len(ids)},
        }
    )


class _Store:
    def __init__(self):
        self.docs = {}
        self.live = {}
        self.receipts = {}
        self.reads = []
        self.queries = []
        self.batches = []
        self.writes = []

    def document(self, path):
        store = self

        class Ref:
            id = path.rsplit('/', 1)[-1]
            _path = path

            def get(self, **kwargs):
                store.reads.append(path)
                data = store.docs.get(path)
                return SimpleNamespace(id=self.id, exists=data is not None, to_dict=lambda: deepcopy(data))

        return Ref()

    def get_all(self, refs, **kwargs):
        self.batches.append(([ref._path for ref in refs], kwargs))
        # Firestore does not guarantee input order.
        for ref in reversed(refs):
            data = self.docs.get(ref._path)
            yield SimpleNamespace(id=ref.id, exists=data is not None, to_dict=lambda d=data: deepcopy(d))

    def collection(self, path):
        store = self

        class Query:
            def document(self, document_id):
                return SimpleNamespace(collection=lambda name: store.collection(f'{path}/{document_id}/{name}'))

            def where(self, *, filter):
                assert filter.field_path == 'retracted_memory_ids' and filter.op_string == 'array_contains'
                self.mid = filter.value
                store.queries.append((path, self.mid))
                return self

            def limit(self, limit):
                self.bound = limit
                return self

            def stream(self, **kwargs):
                return [SimpleNamespace(to_dict=lambda r=r: deepcopy(r)) for r in store.receipts.get(self.mid, [])][
                    : self.bound
                ]

        return Query()

    def active(self, mid, **fields):
        self.docs[f'users/{UID}/memory_items/{mid}'] = {
            'uid': UID,
            'memory_id': mid,
            'status': 'active',
            'version': 1,
            'tier': 'long_term',
            'processing_state': 'processed',
            'content': f'current {mid}',
            'source_state': 'active',
            'sensitivity_labels': [],
            'visibility': 'private',
            'user_asserted': True,
            'captured_at': NOW,
            'updated_at': NOW,
            'ledger_commit_id': 'test-commit',
            'ledger_sequence': 1,
            'valid_to': fields.get('invalid_at'),
            'promotion': {k: fields[k] for k in ('is_locked', 'user_review') if k in fields},
        }
        self.live[mid] = _memory(mid, **fields)

    def closed(self, mid, **fields):
        self.active(mid)
        self.live.pop(mid)
        self.docs[f'users/{UID}/memory_items/{mid}'].update(status='superseded', **fields)


@pytest.fixture
def store(monkeypatch):
    db = _Store()

    class Service:
        def __init__(self, **kwargs):
            assert kwargs.get('db_client') in (db, None)

        def fetch(self, uid, mid):
            assert uid == UID
            result = db.live.get(mid)
            if isinstance(result, Exception):
                raise result
            if result is None:
                raise HTTPException(404, 'Memory not found')
            return result

        def review(self, uid, mid, value):
            self.fetch(uid, mid)
            db.writes.append(('review', mid, value))

        def update_content(self, uid, mid, value):
            result = self.fetch(uid, mid).model_copy(update={'content': value})
            db.writes.append(('edit', mid, value))
            return result

    monkeypatch.setattr(recap_review, 'MemoryService', Service)
    monkeypatch.setattr(recap_review, 'get_firestore_client', lambda: db)
    monkeypatch.delenv('DAILY_RECAP_LEARNING_REFS_ENABLED', raising=False)
    db.service = Service
    return db


def _refresh(store, *ids):
    return recap_review.refresh_recap_learning_refs(UID, [_summary(*ids)], firestore_client=store)[0]


def test_production_shape_retained_legacy_tombstone_does_not_offer_dead_controls(store, monkeypatch):
    # Observed shape: both memory stores absent, a legacy tombstone remains,
    # and the recap still carries the old memory_id/content/category/captured_at.
    store.docs[f'users/{UID}/memory_historical_overrides/gone'] = {
        'uid': UID,
        'memory_id': 'gone',
        'status': 'tombstoned',
        'origin': 'legacy',
    }
    store.active('keep')
    original = _summary('gone', 'keep')
    before = original.model_dump()
    monkeypatch.setattr(users.daily_summaries_db, 'get_daily_summary', lambda *_: before)
    result = users.get_daily_summary('recap', uid=UID)
    assert [ref.memory_id for ref in result.memories_learned] == ['keep']
    assert result.stats.memories_learned_count == 1
    assert original.model_dump() == before
    assert store.writes == []


@pytest.mark.parametrize('pointer', recap_review.SUCCESSOR_FIELDS)
def test_explicit_successors_keep_current_text_and_feedback_identity_together(store, pointer):
    store.closed('old', **{pointer: 'current'})
    store.active('current')
    result = _refresh(store, 'old')
    assert result.memories_learned[0].memory_id == 'current'
    assert result.memories_learned[0].content == 'current current'
    assert store.queries == []
    assert store.writes == []


def test_tombstone_with_explicit_successor_is_followed(store):
    store.docs[f'users/{UID}/memory_historical_overrides/old'] = {
        'uid': UID,
        'memory_id': 'old',
        'status': 'tombstoned',
        'replaced_by': 'current',
    }
    store.active('current')
    assert _refresh(store, 'old').memories_learned[0].memory_id == 'current'


def test_source_reextraction_one_to_one_live_successor_is_followed(store):
    store.receipts['old'] = [{'uid': UID, 'retracted_memory_ids': ['old'], 'committed_memory_ids': ['current']}]
    store.active('current')
    assert _refresh(store, 'old').memories_learned[0].memory_id == 'current'


def test_production_source_reextraction_chain_recovers_retired_intermediate(store):
    # Production has a retained tombstone -> one-to-one replacement -> another
    # one-to-one replacement. Stopping after the first missing target loses a
    # live learning even though every step has an explicit committed receipt.
    for source, target in [('old', 'middle'), ('middle', 'current')]:
        store.docs[f'users/{UID}/memory_historical_overrides/{source}'] = {
            'uid': UID,
            'memory_id': source,
            'status': 'tombstoned',
            'origin': 'legacy',
        }
        store.receipts[source] = [{'uid': UID, 'retracted_memory_ids': [source], 'committed_memory_ids': [target]}]
    store.active('current')
    before = deepcopy(store.docs)
    result = _refresh(store, 'old')
    assert result.memories_learned[0].memory_id == 'current'
    assert result.memories_learned[0].content == 'current current'
    assert store.docs == before and store.writes == []


def test_successor_hop_limit_and_response_deadline_are_bounded(store, monkeypatch):
    for index in range(recap_review.MAX_SUCCESSOR_HOPS + 1):
        store.closed(f'old-{index}', superseded_by=f'old-{index + 1}')
    assert _refresh(store, 'old-0').memories_learned == _summary('old-0').memories_learned
    assert len(store.reads) == recap_review.MAX_SUCCESSOR_HOPS - 1
    calls = iter([0, recap_review.MAX_RESPONSE_READ_SECONDS])
    monkeypatch.setattr(
        recap_review, 'time', SimpleNamespace(monotonic=lambda: next(calls, recap_review.MAX_RESPONSE_READ_SECONDS))
    )
    events = []
    monkeypatch.setattr(recap_review, 'record_fallback', lambda **event: events.append(event))
    assert _refresh(store, 'old-0').model_dump() == _summary('old-0').model_dump()
    assert events[0]['outcome'] == 'degraded'


@pytest.mark.parametrize(
    'receipts',
    [
        [],
        [{'uid': UID, 'retracted_memory_ids': ['old'], 'committed_memory_ids': ['one', 'two']}],
        [{'uid': 'foreign', 'retracted_memory_ids': ['old'], 'committed_memory_ids': ['one']}],
        [{'uid': UID, 'retracted_memory_ids': ['old'], 'committed_memory_ids': ['one']}] * 2,
    ],
)
def test_source_sets_and_ambiguous_or_foreign_receipts_never_guess_a_successor(store, receipts):
    store.receipts['old'] = receipts
    store.active('one')
    store.active('two')
    expected = (
        [] if receipts and receipts[0].get('uid') == UID and len(receipts) == 1 else _summary('old').memories_learned
    )
    assert _refresh(store, 'old').memories_learned == expected


def test_many_to_one_source_consolidation_keeps_the_live_successor(store):
    receipt = {'uid': UID, 'retracted_memory_ids': ['old', 'other'], 'committed_memory_ids': ['one']}
    store.receipts['old'] = [receipt]
    store.receipts['other'] = [receipt]
    store.active('one')
    result = _refresh(store, 'old', 'other')
    assert [ref.memory_id for ref in result.memories_learned] == ['one']


def test_successor_chain_deduplicates_and_stops_cycles(store):
    store.closed('old', superseded_by='middle')
    store.closed('middle', canonical_memory_id='current')
    store.active('current')
    assert [r.memory_id for r in _refresh(store, 'old', 'current').memories_learned] == ['current']
    store.closed('a', superseded_by='b')
    store.closed('b', superseded_by='a')
    assert _refresh(store, 'a').memories_learned == []


def test_depth_limit_does_not_poison_a_shorter_card_in_the_same_response(store):
    for index in range(recap_review.MAX_SUCCESSOR_HOPS):
        store.closed(f'node-{index}', superseded_by=f'node-{index + 1}')
    store.active(f'node-{recap_review.MAX_SUCCESSOR_HOPS}')
    result = _refresh(store, 'node-0', f'node-{recap_review.MAX_SUCCESSOR_HOPS - 2}')
    assert [ref.memory_id for ref in result.memories_learned] == ['node-0', f'node-{recap_review.MAX_SUCCESSOR_HOPS}']


def test_live_canonical_root_may_name_itself(store):
    store.active('current')
    store.docs[f'users/{UID}/memory_items/current']['canonical_memory_id'] = 'current'
    assert _refresh(store, 'current').memories_learned[0].memory_id == 'current'


def test_retired_conflicts_are_omitted_but_unverified_owner_identity_preserves_snapshot(store):
    store.closed('old', superseded_by='one', canonical_memory_id='two')
    store.active('one')
    store.active('two')
    assert _refresh(store, 'old').memories_learned == []
    store.docs[f'users/{UID}/memory_items/old'] = {'uid': 'foreign', 'memory_id': 'old', 'replaced_by': 'one'}
    assert _refresh(store, 'old').memories_learned == _summary('old').memories_learned


@pytest.mark.parametrize('mid', ['', 'a/b', ' old '])
def test_invalid_id_cannot_form_a_document_path(store, mid):
    assert _refresh(store, mid).model_dump() == _summary(mid).model_dump()
    assert store.reads == []


@pytest.mark.parametrize('fields', [{'is_locked': True}, {'invalid_at': NOW}])
def test_invalidated_target_is_omitted_but_locked_target_preserves_snapshot(store, fields):
    store.active('target', **fields)
    expected = _summary('target').memories_learned if fields.get('is_locked') else []
    assert _refresh(store, 'target').memories_learned == expected


def test_batch_provider_fault_keeps_snapshot_and_reports_no_private_content(store, monkeypatch, caplog):
    def broken_document(path):
        raise RuntimeError('PRIVATE_MEMORY_DO_NOT_LOG')

    monkeypatch.setattr(store, 'document', broken_document)
    store.active('later')
    events = []
    monkeypatch.setattr(recap_review, 'record_fallback', lambda **event: events.append(event))
    assert _refresh(store, 'fault', 'later').model_dump() == _summary('fault', 'later').model_dump()
    assert not any(path.endswith('/later') for path in store.reads)
    assert len(events) == 1 and events[0]['outcome'] == 'degraded'
    assert 'PRIVATE_MEMORY_DO_NOT_LOG' not in caplog.text


def test_kill_switch_and_empty_recaps_do_not_read(store, monkeypatch):
    original = _summary('old')
    monkeypatch.setenv('DAILY_RECAP_LEARNING_REFS_ENABLED', 'false')
    assert recap_review.refresh_recap_learning_refs(UID, [original]) == [original]
    monkeypatch.delenv('DAILY_RECAP_LEARNING_REFS_ENABLED')
    assert recap_review.refresh_recap_learning_refs(UID, [_summary()])[0].memories_learned == []
    assert store.reads == []


def test_list_and_detail_share_resolution_and_candidate_validation_stays_pure(store, monkeypatch):
    store.closed('old', superseded_by='current')
    store.active('current')
    raw = _summary('old').model_dump()
    monkeypatch.setattr(users.daily_summaries_db, 'get_daily_summaries', lambda *_, **__: [raw])
    monkeypatch.setattr(users.daily_summaries_db, 'get_daily_summary', lambda *_: raw)
    listed = users.get_daily_summaries(limit=30, offset=0, uid=UID)['summaries']
    detailed = users.get_daily_summary('recap', uid=UID)
    assert listed[0].memories_learned == detailed.memories_learned
    store.reads.clear()
    assert (
        validation.require_daily_summary(raw, uid=UID, operation='generation_candidate').memories_learned[0].memory_id
        == 'old'
    )
    assert store.reads == []


def test_http_recap_successor_supports_released_right_wrong_and_fix_requests(store, monkeypatch):
    store.closed('old', superseded_by='current')
    store.active('current')
    monkeypatch.setattr(users.daily_summaries_db, 'get_daily_summary', lambda *_: _summary('old').model_dump())
    monkeypatch.setattr(memories, 'MemoryService', store.service)
    monkeypatch.setattr(memories.db_client_module, 'db', store)
    monkeypatch.setattr(memories, '_validate_mutable_memory', lambda uid, mid, **_: store.service().fetch(uid, mid))
    monkeypatch.setattr(memories, 'record_memory_feedback', lambda *_: None)
    monkeypatch.setattr(memories, 'record_product_event', lambda *_, **__: None)
    app = FastAPI()
    app.add_api_route('/v1/users/daily-summaries/{summary_id}', users.get_daily_summary, methods=['GET'])
    app.add_api_route('/v3/memories/{memory_id}/review', memories.review_memory, methods=['POST'])
    app.add_api_route('/v3/memories/{memory_id}', memories.edit_memory, methods=['PATCH'])
    for route in app.routes:
        if hasattr(route, 'dependant'):
            for dep in route.dependant.dependencies:
                app.dependency_overrides[dep.call] = lambda: UID
    with TestClient(app) as client:
        response = client.get('/v1/users/daily-summaries/recap')
        assert response.status_code == 200
        mid = response.json()['memories_learned'][0]['memory_id']
        assert mid == 'current'
        assert client.post(f'/v3/memories/{mid}/review?value=true').status_code == 200
        assert client.post(f'/v3/memories/{mid}/review?value=false').status_code == 200
        assert client.patch(f'/v3/memories/{mid}', json={'value': 'user correction'}).status_code == 200
    assert store.writes == [
        ('review', 'current', True),
        ('review', 'current', False),
        ('edit', 'current', 'user correction'),
    ]


@pytest.mark.parametrize('failure', ['batch', 'resolution', 'fetch'])
def test_provider_exception_keeps_all_stored_cards_and_counts(store, monkeypatch, failure):
    summaries = [_summary('old', 'other'), _summary('third')]
    for summary in summaries:
        summary.memories_learned_count = 9
        summary.stats.memories_learned_count = 12
    before = [s.model_dump() for s in summaries]

    def broken(*args, **kwargs):
        raise RuntimeError('PRIVATE_DO_NOT_LOG')

    if failure == 'batch':
        monkeypatch.setattr(store, 'get_all', broken)
    elif failure == 'resolution':
        monkeypatch.setattr(recap_review, '_source_successor', broken)
    else:
        for mid in ['old', 'other', 'third']:
            store.docs[f'users/{UID}/memories/{mid}'] = {'id': mid}
        monkeypatch.setattr(store.service, 'fetch', broken)
    result = recap_review.refresh_recap_learning_refs(UID, summaries, firestore_client=store)
    assert [s.model_dump() for s in result] == before
    assert [s.model_dump() for s in summaries] == before
    assert store.writes == []


@pytest.mark.parametrize('blocked_stage', ['batch', 'fetch'])
def test_whole_deadline_includes_batch_and_memory_service_fetch_without_late_mutation(
    store, monkeypatch, blocked_stage
):
    # Controlled time makes expiry deterministic while a real provider worker
    # stays blocked until after the response has returned.
    from concurrent.futures import ThreadPoolExecutor

    pool = ThreadPoolExecutor(max_workers=4)
    monkeypatch.setattr(recap_review, 'db_executor', pool)
    clock = [0.0]
    monkeypatch.setattr(recap_review, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    started, release, finished = Event(), Event(), Event()
    original = [_summary('slow', 'untouched')]
    before = original[0].model_dump()
    original_get_all = store.get_all

    def blocked(*args, **kwargs):
        started.set()
        try:
            assert release.wait(10)
            return _memory('slow')
        finally:
            finished.set()

    if blocked_stage == 'fetch':
        store.docs[f'users/{UID}/memories/slow'] = {'id': 'slow'}
        monkeypatch.setattr(store.service, 'fetch', blocked)

        def expire(pending, *, timeout, return_when):
            assert started.wait(5)
            assert timeout == recap_review.MAX_RESPONSE_READ_SECONDS
            clock[0] = recap_review.MAX_RESPONSE_READ_SECONDS
            return set(), set(pending)

        monkeypatch.setattr(recap_review, 'wait', expire)
    else:
        # Future.result itself is the batch wait boundary.
        from concurrent.futures import Future

        original_result = Future.result

        def result(future, timeout=None):
            if timeout is not None:
                assert started.wait(5)
                assert timeout == recap_review.MAX_RESPONSE_READ_SECONDS
                clock[0] = recap_review.MAX_RESPONSE_READ_SECONDS
                raise TimeoutError()
            return original_result(future, timeout=timeout)

        def blocked_batch(*args, **kwargs):
            blocked()
            return original_get_all(*args, **kwargs)

        monkeypatch.setattr(store, 'get_all', blocked_batch)
        monkeypatch.setattr(Future, 'result', result)
    try:
        result = recap_review.refresh_recap_learning_refs(UID, original, firestore_client=store)
        assert result[0].model_dump() == before
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(5)
        pool.shutdown(wait=True, cancel_futures=True)
    assert result[0].model_dump() == before
    assert original[0].model_dump() == before
    assert store.writes == []


def test_hundred_recap_page_batches_direct_live_and_bounds_remaining_resolution(store, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    summaries = [_summary(f'live-{n}', f'live-{n+100}', f'old-{n}') for n in range(100)]
    for n in range(200):
        store.active(f'live-{n}')
    for n in range(100):
        store.closed(f'old-{n}')
    called = []
    active = [0, 0]
    lock = Lock()
    first_wave = Barrier(recap_review.MAX_CONCURRENT_RESOLUTIONS)
    original_resolve = recap_review._resolve_one

    def tracked(uid, mid, *args):
        with lock:
            called.append(mid)
            active[0] += 1
            active[1] = max(active)
            first = len(called) <= recap_review.MAX_CONCURRENT_RESOLUTIONS
        try:
            if first:
                first_wave.wait(timeout=5)
            return original_resolve(uid, mid, *args)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(recap_review, '_resolve_one', tracked)
    # A larger shared executor proves the per-request limit is the bound.
    with ThreadPoolExecutor(max_workers=12) as pool:
        monkeypatch.setattr(recap_review, 'db_executor', pool)
        result = recap_review.refresh_recap_learning_refs(UID, summaries, firestore_client=store)
    assert len(store.batches) == 1 and len(store.batches[0][0]) == 300
    assert store.batches[0][1]['retry'] is None
    assert 0 < store.batches[0][1]['timeout'] <= recap_review.MAX_RESPONSE_READ_SECONDS
    assert len(called) == 100 and all(mid.startswith('old-') for mid in called)
    assert active[1] == recap_review.MAX_CONCURRENT_RESOLUTIONS
    assert store.reads == []  # initial canonical snapshots are reused, including retired rows
    assert len(store.queries) == 100
    for n, summary in enumerate(result):
        assert [r.memory_id for r in summary.memories_learned] == [f'live-{n}', f'live-{n+100}']
        assert summary.stats.memories_learned_count == 2
    assert store.writes == []


def test_only_failed_reference_falls_back_and_successful_successor_still_substitutes(store, monkeypatch):
    store.closed('old', superseded_by='current')
    store.active('current')
    store.docs[f'users/{UID}/memories/fault'] = {'id': 'fault'}
    store.live['fault'] = RuntimeError('provider down')
    result = _refresh(store, 'old', 'fault')
    assert [r.memory_id for r in result.memories_learned] == ['current', 'fault']
    assert result.memories_learned[1] == _summary('fault').memories_learned[0]
    assert result.stats.memories_learned_count == 2
