"""WQ13: query predicates reduce reads without removing recoverable work."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import firestore_read_levers as levers
from database import conversation_finalization_jobs as jobs

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(hours=2)
OLD = NOW - timedelta(days=30)


@dataclass
class Snapshot:
    path: str
    data: dict
    exists: bool = True

    @property
    def id(self):
        return self.path.rsplit('/', 1)[-1]

    @property
    def reference(self):
        return SimpleNamespace(path=self.path)

    def to_dict(self):
        return dict(self.data)

    def get(self):
        return self


@dataclass(frozen=True)
class Query:
    client: 'Client'
    collection: str
    filters: tuple = ()
    orders: tuple = ()
    cap: int = 100
    after: Snapshot | None = None

    def where(self, *args, filter=None):
        f = filter or SimpleNamespace(field_path=args[0], op_string=args[1], value=args[2])
        return replace(self, filters=(*self.filters, (f.field_path, f.op_string, f.value)))

    def order_by(self, field):
        return replace(self, orders=(*self.orders, field))

    def limit(self, value):
        return replace(self, cap=value)

    def start_after(self, snapshot):
        # Firestore needs the ordered field even when the cursor row itself no
        # longer matches the query. A pre-rollout cursor may lack that field.
        assert all(field in snapshot.data for field in self.orders)
        return replace(self, after=snapshot)

    def document(self, doc_id):
        return self.client.document(f'{self.collection}/{doc_id}')

    def stream(self):
        rows = [s for s in self.client.snapshots if s.path.split('/')[-2] == self.collection]
        for field, op, value in self.filters:
            if op == '==':
                rows = [s for s in rows if field in s.data and s.data[field] == value]
            elif op == 'in':
                rows = [s for s in rows if field in s.data and s.data[field] in value]
            elif op == '<=':
                rows = [s for s in rows if isinstance(s.data.get(field), datetime) and s.data[field] <= value]
            else:
                raise AssertionError(f'unhandled operator {op}')

        # The explicit field order and name tiebreak are used for both result
        # and cursor values; a cursor need not be in the matching result set.
        def key(s):
            return (*(s.data[field] for field in self.orders), s.path)

        rows.sort(key=key)
        if self.after is not None:
            rows = [s for s in rows if key(s) > key(self.after)]
        rows = rows[: self.cap]
        self.client.queries.append(self)
        self.client.reads += len(rows)
        return iter(rows)


class Client:
    def __init__(self, snapshots=(), documents=None):
        self.snapshots = list(snapshots)
        self.documents = documents or {}
        self.queries = []
        self.reads = 0

    def collection(self, name):
        return Query(self, name)

    def collection_group(self, name):
        return Query(self, name)

    def document(self, path):
        found = next((s for s in self.snapshots if s.path == path), None)
        return found or Snapshot(path, self.documents.get(path, {}), path in self.documents)

    def transaction(self):
        # Query tests stub the existing transactional cursor writer; no writes
        # or ownership operations are implemented by this query fake.
        return object()


def conversation(doc_id, **data):
    return Snapshot(f'users/u/conversations/{doc_id}', {'status': 'in_progress', **data})


def byok(doc_id, **data):
    return Snapshot(
        f'conversation_finalization_jobs/{doc_id}',
        {'status': 'queued', 'requires_byok': True, 'created_at': OLD, **data},
    )


@pytest.fixture(autouse=True)
def fixed_clock_and_default_off(monkeypatch):
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    for lifecycle_env in (
        'LIFECYCLE_V2_MODE',
        'LIFECYCLE_V2_MODE_SERVE_PERCENT',
        'LIFECYCLE_V2_MODE_SERVE_UID_SHA256S',
    ):
        monkeypatch.delenv(lifecycle_env, raising=False)
    monkeypatch.setenv('HOSTNAME', 'wq13-unit-host')


def enable(monkeypatch, percent=100):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', f'{{"finjob_candidate_queries":{percent}}}')


@pytest.mark.parametrize('raw', [None, '{}', '{"finjob_candidate_queries":0}', 'invalid'])
def test_lever_defaults_off(monkeypatch, raw):
    if raw is not None:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    assert levers.lever_percent('finjob_candidate_queries') == 0
    assert not jobs._candidate_queries_enabled()


def test_lever_uses_host_cohort(monkeypatch):
    enable(monkeypatch, 50)
    expected = levers.lever_enabled('finjob_candidate_queries', 'wq13-unit-host')
    assert jobs._candidate_queries_enabled() == expected


@pytest.mark.parametrize('on', [False, True])
def test_in_progress_pushes_inclusive_cutoff_before_pagination(monkeypatch, on):
    enable(monkeypatch, 100 if on else 0)
    rows = [conversation(f'a{i:03}', finished_at=NOW) for i in range(200)]
    rows += [conversation('missing'), conversation('z-stale', finished_at=CUTOFF)]
    client = Client(rows)
    result = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, max_scan=100, page_size=100, firestore_client=client
    )
    if on:
        assert [r['conversation_id'] for r in result['rows']] == ['z-stale']
        assert client.reads == 1
        assert result['exhausted']
        assert client.queries[0].filters == (('status', '==', 'in_progress'), ('finished_at', '<=', CUTOFF))
        assert client.queries[0].orders == ('finished_at',)
    else:
        assert len(result['rows']) == 100
        assert client.reads == 100
        assert not result['exhausted']
        assert client.queries[0].filters == (('status', '==', 'in_progress'),)
        assert client.queries[0].orders == ()


@pytest.mark.parametrize(
    ('mode_env', 'extra_env'),
    [
        ({'LIFECYCLE_V2_MODE': 'serve'}, {}),
        ({'LIFECYCLE_V2_MODE': 'shadow'}, {'LIFECYCLE_V2_MODE_SERVE_PERCENT': '5'}),
        ({'LIFECYCLE_V2_MODE': 'shadow'}, {'LIFECYCLE_V2_MODE_SERVE_UID_SHA256S': 'a' * 64}),
    ],
    ids=['serve', 'shadow-cohort-percent', 'shadow-cohort-digests'],
)
def test_in_progress_pushdown_withheld_while_lifecycle_v2_cohort_configured(monkeypatch, mode_env, extra_env):
    # A v2-serving uid can hold a missing finished_at with a stale
    # last_speech_at; the admission fence (speech_clock) accepts that row, so
    # this status-only catch-all must not push finished_at into the query
    # while any serve cohort can exist.
    enable(monkeypatch)
    for env, value in {**mode_env, **extra_env}.items():
        monkeypatch.setenv(env, value)
    rows = [conversation('missing'), conversation('z-stale', finished_at=CUTOFF)]
    client = Client(rows)
    result = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, max_scan=100, page_size=100, firestore_client=client
    )
    assert [r['conversation_id'] for r in result['rows']] == ['missing', 'z-stale']
    assert result['exhausted']
    assert client.queries[0].filters == (('status', '==', 'in_progress'),)
    assert client.queries[0].orders == ()


def test_in_progress_pushdown_active_while_lifecycle_v2_dormant_or_off(monkeypatch):
    # Dormant shadow (mode unset, percent 0, no digests) serves no uid, so
    # speech_clock stays on legacy finished_at and the pushdown remains
    # admission-equivalent. Explicit off behaves the same way.
    enable(monkeypatch)
    monkeypatch.setenv('LIFECYCLE_V2_MODE', 'off')
    rows = [conversation('missing'), conversation('z-stale', finished_at=CUTOFF)]
    client = Client(rows)
    result = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, max_scan=100, page_size=100, firestore_client=client
    )
    assert [r['conversation_id'] for r in result['rows']] == ['z-stale']
    assert client.queries[0].filters == (('status', '==', 'in_progress'), ('finished_at', '<=', CUTOFF))


def test_in_progress_no_cutoff_retains_status_scan_even_on(monkeypatch):
    enable(monkeypatch)
    client = Client([conversation('missing'), conversation('fresh', finished_at=NOW)])
    result = jobs.scan_in_progress_conversations(firestore_client=client)
    assert len(result['rows']) == 2
    assert client.queries[0].filters == (('status', '==', 'in_progress'),)
    assert client.queries[0].orders == ()


@pytest.mark.parametrize('percent', [None, 0, 100])
def test_content_due_scan_preserves_main_query_and_cutoff(monkeypatch, percent):
    if percent is not None:
        enable(monkeypatch, percent)
    client = Client(
        [
            conversation('content-due', has_content=True, finished_at=CUTOFF),
            conversation('empty-due', has_content=False, finished_at=OLD),
            conversation('content-fresh', has_content=True, finished_at=NOW),
        ]
    )
    result = jobs.scan_in_progress_conversations(
        finished_before=OLD, content_due_before=CUTOFF, firestore_client=client
    )
    assert [r['conversation_id'] for r in result['rows']] == ['content-due']
    assert client.queries[0].filters == (
        ('status', '==', 'in_progress'),
        ('has_content', '==', True),
        ('finished_at', '<=', CUTOFF),
    )
    assert client.queries[0].orders == ('finished_at',)


def test_in_progress_timestamp_order_cursor_ties_and_wrap(monkeypatch):
    enable(monkeypatch)
    client = Client(
        [
            conversation('a', finished_at=CUTOFF),
            conversation('b', finished_at=OLD),
            conversation('c', finished_at=CUTOFF),
        ]
    )
    first = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, page_size=1, max_scan=1, firestore_client=client
    )
    assert [r['conversation_id'] for r in first['rows']] == ['b']
    second = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF,
        page_size=1,
        max_scan=2,
        resume_after_path=first['resume_after_path'],
        firestore_client=client,
    )
    assert [r['conversation_id'] for r in second['rows']] == ['a', 'c']
    tail = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, resume_after_path=second['resume_after_path'], firestore_client=client
    )
    assert tail == {'rows': [], 'scanned': 0, 'resume_after_path': None, 'exhausted': True}


@pytest.mark.parametrize('cursor_kind', ['missing_field', 'deleted', 'fresh', 'terminal'])
def test_in_progress_cursor_survives_rollout_and_mutation(monkeypatch, cursor_kind):
    enable(monkeypatch)
    cursor = conversation('old-cursor')
    rows = [conversation('eligible', finished_at=CUTOFF)]
    if cursor_kind == 'fresh':
        cursor.data['finished_at'] = NOW
    elif cursor_kind == 'terminal':
        cursor.data.update(status='completed', finished_at=OLD)
    if cursor_kind != 'deleted':
        rows.append(cursor)
    client = Client(rows)
    first = jobs.scan_in_progress_conversations(
        finished_before=CUTOFF, resume_after_path=cursor.path, firestore_client=client
    )
    # A formerly fresh name cursor can start after the eligible range; wrapping
    # the persisted exhausted cursor must still discover the candidate.
    result = (
        first if first['rows'] else jobs.scan_in_progress_conversations(finished_before=CUTOFF, firestore_client=client)
    )
    assert [r['conversation_id'] for r in result['rows']] == ['eligible']


@pytest.mark.parametrize('on', [False, True])
def test_byok_active_predicate_excludes_terminal_prefix(monkeypatch, on):
    enable(monkeypatch, 100 if on else 0)
    rows = [byok(f'a{i:03}', status='completed') for i in range(200)]
    rows += [byok('b', status='dead_letter'), byok('z', updated_at=OLD)]
    client = Client(rows)
    result = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=timedelta(days=14), limit=100, max_scan=100, firestore_client=client
    )
    if on:
        assert [r['job_id'] for r in result['candidates']] == ['z']
        assert client.reads == 1
        assert client.queries[0].filters == (
            ('requires_byok', '==', True),
            ('status', 'in', ['queued', 'leased', 'blocked_byok']),
        )
    else:
        assert result['candidates'] == []
        assert client.reads == 100
        assert client.queries[0].filters == (('requires_byok', '==', True),)
    assert client.queries[0].orders == ()


def test_byok_keeps_activity_fallbacks_and_live_lease_fence(monkeypatch):
    enable(monkeypatch)
    rows = [
        byok('activity', status='blocked_byok', byok_last_activity_at=OLD, updated_at=NOW),
        byok('created-only'),
        byok('updated-string', updated_at=OLD.isoformat()),
        byok('fresh', byok_last_activity_at=NOW, updated_at=OLD),
        byok('live', status='leased', updated_at=OLD, lease_expires_at=NOW + timedelta(minutes=1)),
        byok('expired', status='leased', updated_at=OLD, lease_expires_at=NOW),
        byok('unknown', created_at=None),
    ]
    client = Client(rows)
    result = jobs.get_abandoned_byok_job_candidates(abandoned_after=timedelta(days=14), firestore_client=client)
    assert {r['job_id'] for r in result['candidates']} == {'activity', 'created-only', 'updated-string', 'expired'}


def test_byok_name_cursor_can_be_terminal_after_rollout(monkeypatch):
    enable(monkeypatch)
    cursor = byok('a', status='completed')
    client = Client([cursor, byok('b'), byok('c')])
    first = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=timedelta(days=14), limit=1, resume_after_path=cursor.path, firestore_client=client
    )
    assert [r['job_id'] for r in first['candidates']] == ['b']
    second = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=timedelta(days=14), resume_after_path=first['resume_after_path'], firestore_client=client
    )
    assert [r['job_id'] for r in second['candidates']] == ['c']
    assert second['exhausted'] and second['resume_after_path'] is None


@pytest.mark.parametrize('on', [False, True])
def test_reclaim_filters_byok_before_age_page_cap(monkeypatch, on):
    enable(monkeypatch, 100 if on else 0)
    rows = [byok(f'a{i:03}', requires_byok=False) for i in range(60)]
    rows += [byok('z-queued'), byok('z-leased', status='leased')]
    client = Client(rows)
    claimed = []
    advanced = []
    monkeypatch.setattr(
        jobs, 'claim_finalization_replay', lambda job_id, **kw: claimed.append(job_id) or {'status': 'blocked_byok'}
    )
    monkeypatch.setattr(jobs.firestore, 'transactional', lambda fn: lambda *args: advanced.append(args) or True)
    result = jobs.recover_stranded_byok_jobs(firestore_client=client)
    if on:
        assert claimed == ['z-queued', 'z-leased']
        assert result == {'scanned': 2, 'blocked': 2, 'errors': 0}
        assert client.queries[0].filters == (('requires_byok', '==', True), ('status', '==', 'queued'))
    else:
        assert claimed == ['z-leased']
        assert result == {'scanned': 51, 'blocked': 1, 'errors': 0}
        assert client.queries[0].filters == (('status', '==', 'queued'),)
    assert all(q.orders == ('created_at',) and q.cap == 50 for q in client.queries)
    assert len(advanced) == 2


@pytest.mark.parametrize('on', [False, True])
def test_processing_keeps_missing_legacy_fence_and_parseable_timestamps(monkeypatch, on):
    enable(monkeypatch, 100 if on else 0)
    client = Client(
        [
            conversation('legacy', status='processing'),
            conversation('stale-iso', status='processing', processing_admitted_at=OLD.isoformat()),
            conversation('fresh', status='processing', processing_admitted_at=NOW),
            conversation('job-owned', status='processing', finalization_job_id='j'),
        ]
    )
    result = jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(minutes=15), firestore_client=client)
    assert [(r['conversation_id'], r['legacy']) for r in result['candidates']] == [
        ('legacy', True),
        ('stale-iso', False),
    ]
    assert client.queries[0].filters == (('status', '==', 'processing'),)
