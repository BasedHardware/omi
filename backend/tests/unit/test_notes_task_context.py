"""Empty-pool proof preserves legacy task eligibility and Pinecone ordering."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from database import action_items as items
from database import action_item_dedup as dedup
from testing.import_isolation import load_module_fresh, stub_modules

NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=7)


class Query:
    """Immutable query fake: ordered cursor excludes absent fields, includes strings."""

    def __init__(self, rows, reads, field=None, cutoff=None, fields=None, cap=None):
        self.rows, self.reads = rows, reads
        self.field, self.cutoff, self.fields, self.cap = field, cutoff, fields, cap

    def collection(self, name):
        assert name in ('users', 'action_items')
        return self

    def document(self, uid):
        assert uid == 'owner'
        return self

    def order_by(self, field):
        return Query(self.rows, self.reads, field)

    def start_at(self, bound):
        assert set(bound) == {self.field}
        return Query(self.rows, self.reads, self.field, bound[self.field])

    def select(self, fields):
        return Query(self.rows, self.reads, self.field, self.cutoff, fields)

    def limit(self, cap):
        return Query(self.rows, self.reads, self.field, self.cutoff, self.fields, cap)

    def stream(self, *, timeout, retry):
        assert timeout == 2
        assert retry is dedup.FIRESTORE_NO_RETRY
        assert self.cap == 8
        assert set(self.fields) == {'completed', 'status', 'conversation_id', 'updated_at', 'created_at'}
        matches = [
            row
            for row in self.rows
            if isinstance(row.get(self.field), str)
            or (isinstance(row.get(self.field), datetime) and row[self.field] >= self.cutoff)
        ][: self.cap]
        self.reads.append((self.field, len(matches)))
        return [
            SimpleNamespace(to_dict=lambda row=row: {k: v for k, v in row.items() if k in self.fields})
            for row in matches
        ]


def probe(rows, excluded=None):
    reads = []
    result = dedup.may_have_recent_dedup_candidates(
        'owner', CUTOFF, excluded or set(), firestore_client=Query(rows, reads)
    )
    return result, reads


@pytest.mark.parametrize(
    'rows',
    [
        [],
        [{'completed': True, 'updated_at': NOW}],
        [{'completed': False, 'updated_at': CUTOFF - timedelta(seconds=1)}],
        [{'completed': False}],
        [{'status': 'completed', 'completed': None, 'created_at': NOW}],
        [{'completed': False, 'updated_at': CUTOFF - timedelta(days=1), 'created_at': NOW}],
    ],
)
def test_no_eligible_items_proves_empty(rows):
    result, reads = probe(rows)
    assert result is False
    assert len(reads) == 2


@pytest.mark.parametrize(
    'row',
    [
        {'completed': False, 'updated_at': NOW},
        {'completed': False, 'created_at': NOW},
        {'created_at': NOW},
        {'completed': None, 'created_at': NOW},
        {'updated_at': None, 'created_at': NOW},
        {'created_at': NOW.isoformat()},
        {'updated_at': NOW.isoformat()},
        {'updated_at': 'malformed', 'created_at': NOW},
        {'updated_at': CUTOFF},
    ],
)
def test_recent_open_and_legacy_rows_keep_pinecone(row):
    assert probe([row])[0] is True


def test_excluded_conversations_and_merge_sources():
    rows = [{'created_at': NOW, 'conversation_id': cid} for cid in ('current', 'source')]
    assert probe(rows, {'current', 'source'})[0] is False
    assert probe(rows + [{'created_at': NOW, 'conversation_id': 'other'}], {'current', 'source'})[0] is True


def test_scan_exhaustion_is_inconclusive_and_bounded():
    result, reads = probe([{'completed': True, 'updated_at': NOW} for _ in range(100)])
    assert result is True
    assert reads == [('updated_at', 8)]


@pytest.fixture(scope='module')
def context():
    vector = ModuleType('database.vector_db')
    vector.find_similar_action_items = Mock()
    with stub_modules({'database.vector_db': vector}):
        yield load_module_fresh(
            'notes_task_context_test',
            str(Path(__file__).resolve().parents[2] / 'utils/conversations/notes_task_context.py'),
        )


@pytest.fixture
def flow(context, monkeypatch):
    pinecone = Mock(return_value=[{'action_item_id': 'task', 'score': 0.9}])
    hydrate = Mock(return_value=[{'id': 'task', 'created_at': datetime.now(timezone.utc)}])
    monkeypatch.setattr(context, 'find_similar_action_items', pinecone)
    monkeypatch.setattr(items, 'get_action_items_by_ids', hydrate)
    return context, pinecone, hydrate


def test_empty_pool_skips_pinecone_and_hydration(flow, monkeypatch):
    context, pinecone, hydrate = flow
    monkeypatch.setattr(context, 'may_have_recent_dedup_candidates', lambda *a: False)
    assert context.fetch_dedup_candidates_for_query('owner', 'query') == []
    pinecone.assert_not_called()
    hydrate.assert_not_called()


def test_nonempty_pool_keeps_existing_query_and_order(flow, monkeypatch):
    context, pinecone, hydrate = flow
    monkeypatch.setattr(context, 'may_have_recent_dedup_candidates', lambda *a: True)
    result = context.fetch_dedup_candidates_for_query('owner', 'query')
    assert result == hydrate.return_value
    pinecone.assert_called_once_with('owner', 'query', threshold=0.6, limit=10)


def test_probe_error_retains_pinecone(flow, monkeypatch):
    context, pinecone, hydrate = flow
    monkeypatch.setattr(context, 'may_have_recent_dedup_candidates', Mock(side_effect=RuntimeError('unavailable')))
    fallback = Mock()
    monkeypatch.setattr(context, 'record_fallback', fallback)
    assert context.fetch_dedup_candidates_for_query('owner', 'query') == hydrate.return_value
    pinecone.assert_called_once()
    assert fallback.call_args.kwargs['to_mode'] == 'pinecone'


def test_exclusions_reach_probe_and_hydrated_filter(flow, monkeypatch):
    context, _, hydrate = flow
    check = Mock(return_value=True)
    monkeypatch.setattr(context, 'may_have_recent_dedup_candidates', check)
    conversation = SimpleNamespace(
        id='current', external_data={'merge_metadata': {'source_conversation_ids': ['source']}}
    )
    now = datetime.now(timezone.utc)
    hydrate.return_value = [{'conversation_id': cid, 'created_at': now} for cid in ('current', 'source', 'other')]
    assert context.fetch_dedup_candidates_for_query('owner', 'query', conversation) == [hydrate.return_value[-1]]
    assert check.call_args.args[2] == {'current', 'source'}


def test_blank_query_reads_nothing(flow, monkeypatch):
    context, pinecone, _ = flow
    check = Mock()
    monkeypatch.setattr(context, 'may_have_recent_dedup_candidates', check)
    assert context.fetch_dedup_candidates_for_query('owner', '  ') == []
    check.assert_not_called()
    pinecone.assert_not_called()
