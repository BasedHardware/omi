"""Golden staged compatibility pages and billed-read proof through the real scan."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from database import candidates as candidates_db
from database import s5_candidates_cache as cache
from models.candidate import CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl
from routers import staged_tasks as router
from utils.task_intelligence.staged_migration import proposal_from_legacy_staged

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


class Redis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True


class Query:
    def __init__(self, rows, reads, cursor=None, size=None):
        self.rows, self.reads, self.cursor, self.size = rows, reads, cursor, size

    def where(self, *, filter):
        return Query([r for r in self.rows if r.to_dict().get(filter.field_path) == filter.value], self.reads)

    def order_by(self, *args, **kwargs):
        return self

    def start_after(self, cursor):
        return Query(self.rows, self.reads, cursor.id, self.size)

    def limit(self, n):
        return Query(self.rows, self.reads, self.cursor, n)

    def stream(self):
        start = next((i + 1 for i, r in enumerate(self.rows) if r.id == self.cursor), 0)
        rows = self.rows[start : start + self.size]
        self.reads[0] += max(1, len(rows))
        return iter(rows)


def candidate(i, status=CandidateStatus.pending):
    proposal = proposal_from_legacy_staged({'id': f'legacy-{i}', 'description': f'Task {i}', 'relevance_score': i})
    return CandidateRecord(
        **proposal.model_dump(mode='python'),
        candidate_id=f'c{i}',
        account_generation=7,
        idempotency_key=f'i{i}',
        created_at=NOW,
        status=status,
        resolved_at=NOW if status != CandidateStatus.pending else None,
        resolution_reason=status.value if status != CandidateStatus.pending else None,
    )


def install(monkeypatch, records):
    rows = [SimpleNamespace(id=r.candidate_id, to_dict=lambda r=r: r.model_dump(mode='python')) for r in records]
    rows.insert(1, SimpleNamespace(id='malformed', to_dict=lambda: {'account_generation': 7, 'created_at': NOW}))
    reads = [0]
    query = Query(rows, reads)
    monkeypatch.setattr(
        candidates_db,
        'db',
        SimpleNamespace(
            collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: query))
        ),
    )
    monkeypatch.setattr(cache, '_redis', lambda fake=Redis(): fake)
    monkeypatch.setattr(router, '_CANDIDATE_PAGE_SIZE', 4)
    monkeypatch.setattr(router, '_control', lambda _: TaskWorkflowControl(workflow_mode='read', account_generation=7))
    monkeypatch.setattr(
        router.staged_tasks_db,
        'get_active_staged_tasks_for_compatibility',
        lambda _: [
            {'id': 'legacy-0', 'description': 'suppressed resolved row'},
            {'id': 'unrepresented', 'description': 'historical visible row'},
            {'id': 'completed', 'description': 'hidden', 'completed': True},
        ],
    )
    return reads


@pytest.mark.parametrize('offset', [0, 2, 8, 100])
@pytest.mark.parametrize('limit', [1, 4, 100])
def test_golden_pages_keep_terminal_suppression_and_raw_cursor(monkeypatch, offset, limit):
    reads = install(monkeypatch, [candidate(0, CandidateStatus.rejected), *[candidate(i) for i in range(1, 8)]])
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    off = router.get_staged_tasks(limit=limit, offset=offset, uid='u')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    cold = router.get_staged_tasks(limit=limit, offset=offset, uid='u')
    before = reads[0]
    hit = router.get_staged_tasks(limit=limit, offset=offset, uid='u')
    assert off == cold == hit
    assert reads[0] == before
    assert all(r['id'] != 'legacy-0' for r in hit['items'])


def test_ten_polls_scan_once_and_writes_invalidate(monkeypatch):
    records = [candidate(i) for i in range(8)]
    reads = install(monkeypatch, records)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    for _ in range(10):
        router.get_staged_tasks(limit=4, offset=0, uid='u')
    assert reads[0] == 90  # eight valid rows + one malformed per full scan
    reads[0] = 0
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    for _ in range(10):
        router.get_staged_tasks(limit=4, offset=0, uid='u')
    assert reads[0] == 9

    @cache.invalidate_after_write
    def write(uid):
        return 'committed'

    assert write('u') == 'committed'
    router.get_staged_tasks(limit=4, offset=0, uid='u')
    assert reads[0] == 18


def test_concurrent_fill_is_not_blessed_with_new_version(monkeypatch):
    monkeypatch.setattr(cache, '_redis', lambda fake=Redis(): fake)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    calls = []

    @cache.invalidate_after_write
    def write(uid):
        pass

    def load():
        calls.append(1)
        write('u')
        return [candidate(1)]

    cache.load_compatibility_candidates('u', 7, load)
    cache.load_compatibility_candidates('u', 7, load)
    assert len(calls) == 2


def test_generation_uid_empty_and_redis_failure(monkeypatch):
    fake = Redis()
    monkeypatch.setattr(cache, '_redis', lambda: fake)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    calls = []

    def load():
        calls.append(1)
        return []

    for uid, generation in [('a', 1), ('a', 2), ('b', 1), ('a', 1)]:
        assert cache.load_compatibility_candidates(uid, generation, load) == []
    assert len(calls) == 3
    monkeypatch.setattr(fake, 'get', lambda _: (_ for _ in ()).throw(ConnectionError('down')))
    assert cache.load_compatibility_candidates('a', 1, load) == []
    assert len(calls) == 4


def test_off_reads_have_no_redis_io(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    monkeypatch.setattr(cache, '_redis', lambda: SimpleNamespace(set=lambda *a, **kw: pytest.fail('off Redis IO')))
    assert cache.load_compatibility_candidates('u', 7, lambda: []) == []


def test_lever_off_writer_still_invalidates_enabled_readers(monkeypatch):
    # Mixed rollout: an enabled revision warms the entry, then an off-config host mutates candidates.
    monkeypatch.setattr(cache, '_redis', lambda fake=Redis(): fake)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    calls = []

    def load():
        calls.append(1)
        return [candidate(len(calls))]

    cache.load_compatibility_candidates('u', 7, load)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    assert cache.invalidate_after_write(lambda uid: 'ok')('u') == 'ok'
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    cache.load_compatibility_candidates('u', 7, load)
    assert len(calls) == 2


@pytest.mark.parametrize('generation', [7, 8])
def test_real_score_writer_finally_invalidates_on_success_or_fence_error(monkeypatch, generation):
    fake = Redis()
    monkeypatch.setattr(cache, '_redis', lambda: fake)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    payload = candidate(1).model_dump(mode='python')
    candidate_ref = SimpleNamespace(get=lambda **kw: SimpleNamespace(exists=True, to_dict=lambda: payload))
    control_ref = SimpleNamespace(
        get=lambda **kw: SimpleNamespace(exists=True, to_dict=lambda: {'account_generation': 7})
    )
    writes = []

    def update(ref, patch):
        assert ref is candidate_ref
        writes.append(patch)
        payload.update(patch)

    monkeypatch.setattr(candidates_db, '_candidate_ref', lambda *args: candidate_ref)
    monkeypatch.setattr(candidates_db, '_task_control_ref', lambda *args: control_ref)
    monkeypatch.setattr(candidates_db, 'db', SimpleNamespace(transaction=lambda: SimpleNamespace(update=update)))
    monkeypatch.setattr(candidates_db.firestore, 'transactional', lambda fn: fn)

    def load():
        return [CandidateRecord.model_validate(payload)]

    cache.load_compatibility_candidates('u', 7, load)
    before = fake.get(cache._version_key('u'))
    if generation == 8:
        with pytest.raises(candidates_db.CandidateGenerationMismatchError):
            candidates_db.update_candidate_compatibility_score(
                'u', 'c1', relevance_score=99, account_generation=generation
            )
        assert not writes
        # Conservatively invalidate on errors too: a batch/transaction adapter
        # can commit a prefix before raising. The durable fence still rejects it.
        assert fake.get(cache._version_key('u')) != before
    else:
        result = candidates_db.update_candidate_compatibility_score(
            'u', 'c1', relevance_score=99, account_generation=generation
        )
        assert result.compatibility.relevance_score == 99
        assert fake.get(cache._version_key('u')) != before
        assert cache.load_compatibility_candidates('u', 7, load)[0].compatibility.relevance_score == 99
