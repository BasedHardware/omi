"""Synthetic pass-selection and retrieval regressions; never customer data."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.dream_agent import Caps
from utils import dream_agent, dream_context, dream_diagnostics, dream_metrics, dream_reads


def snapshots(count):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    items = [
        {'collection': 'conversations', 'id': str(i), 'version': str(i), 'last_changed_at': now} for i in range(count)
    ]
    return [SimpleNamespace(to_dict=lambda item=item: item) for item in items], now


def test_unused_context_allocation_returns_to_targets_without_consuming_unread(monkeypatch):
    dirty, now = snapshots(35)
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', lambda *a, **k: dirty)
    calls = []

    def read(uid, ref, **kwargs):
        calls.append(ref)
        return {'structured': {'title': 'Synthetic toy boat'}, 'transcript_segments': [{'text': 'Solar boat ' * 100}]}

    monkeypatch.setattr(dream_reads, 'read_record', read)
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])
    report = {}
    rows, consumed = dream_reads.read_changes('synthetic', {'started_at': now}, Caps(), diagnostics=report)
    assert len(rows.targets) > 4
    assert len(consumed) == len(rows.targets) < 35
    assert {f"{item['collection']}/{item['id']}" for item in consumed} == rows.targets
    assert report['dirty_counts']['admitted'] == len(consumed)
    assert report['dirty_counts']['budget_deferred'] == 32 - len(consumed)
    assert len(calls) == len(set(calls))


def test_bounded_reads_distinguish_three_targets_and_permanent_misses(monkeypatch):
    dirty, now = snapshots(35)
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', lambda *a, **k: dirty)
    monkeypatch.setattr(
        dream_reads,
        'read_record',
        lambda uid, ref, **k: {'content': 'Toy boat'} if ref.endswith(('/0', '/1', '/2')) else None,
    )
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])
    report = {}
    rows, consumed = dream_reads.read_changes('synthetic', {'started_at': now}, Caps(), diagnostics=report)
    assert len(rows.targets) == len(consumed) == 3
    assert report['dirty_counts'] == {
        'fetched': 32,
        'attempted': 32,
        'found': 3,
        'admitted': 3,
        'unavailable': 29,
        'failed': 0,
        'newer': 0,
        'budget_deferred': 0,
        'permanent': 29,
        'transient': 0,
        'permanent_acknowledged': 0,
        'transient_expired': 0,
    }
    assert {item['id'] for item in consumed} == {'0', '1', '2'}


def test_context_metadata_probe_admits_short_real_neighbour():
    targets = dream_context.EvidenceRecords(
        {
            f'conversations/synthetic-{i}': {'transcript_segments': [{'text': 'Nuvrah solar boat ' * 40}]}
            for i in range(3)
        }
    )
    probe = dream_context.EvidenceRecords(
        {
            **targets,
            'conversations/context': {
                'name': 'x' * 120,
                'content': 'x' * 1500,
                'transcript_segments': [{'text': 'x' * 1500}],
            },
        },
        targets=targets.targets,
    )
    fitting = [
        Caps(tokens=t)
        for t in range(16000, 25000, 1000)
        if not dream_context.fits_pass(probe, Caps(tokens=t))
        and dream_context.fits_pass(
            dream_context.EvidenceRecords({**targets, 'conversations/context': {}}, targets=targets.targets),
            Caps(tokens=t),
        )
    ]
    assert fitting
    calls = []
    rows = dream_context.add_context(
        targets,
        [
            (
                'conversations/context',
                lambda: calls.append('read') or {'transcript_segments': [{'text': 'Nuvra'}]},
                'lexical',
            )
        ],
        fitting[0],
    )
    assert calls == ['read'] and 'conversations/context' in rows
    assert rows.targets == targets.targets


def test_owner_retrieval_dry_run_exercises_all_paths_without_admission_or_writes(monkeypatch):
    target = {
        'conversations/private-target': {
            'created_at': datetime(2030, 1, 1, tzinfo=timezone.utc),
            'transcript_segments': [{'text': 'Zuvrah', 'person_id': 'private-person'}],
        }
    }
    forbidden = Mock(side_effect=AssertionError('dry run invoked effect/admission/inference'))
    for name in ('acquire', 'finish', 'reserve_questions', 'assert_lease', 'mark_dirty'):
        monkeypatch.setattr(dream_reads.dream_store, name, forbidden)
    monkeypatch.setattr(dream_agent, 'plan_pass', forbidden)
    monkeypatch.setattr(dream_reads.dream_store, 'vocabulary', lambda uid: [])

    def fail(*a, **k):
        raise RuntimeError('private-provider-body')

    monkeypatch.setattr(dream_reads, 'read_entity_record', fail)
    monkeypatch.setattr(dream_context.action_items, 'get_action_items', fail)
    monkeypatch.setattr(dream_context, 'subject_memory_refs', lambda *a: ['memory_items/private-linked'])
    monkeypatch.setattr(
        dream_context, 'keyword_search_conversation_ids', lambda **k: ['private-lex', 'private-lex', 'private-target']
    )
    monkeypatch.setattr(dream_context.vector_db, 'query_vectors', fail)
    monkeypatch.setattr(dream_context.vector_db, 'index', object())
    monkeypatch.setattr(
        dream_context,
        'MemoryService',
        lambda: SimpleNamespace(
            search=lambda *a, **k: [SimpleNamespace(memory=SimpleNamespace(id='private-semantic'))]
        ),
    )

    def temporal(uid, collection, *a):
        if collection == 'conversations':
            return fail()
        return [{'id': 'private-screen', 'ocrText': 'private-screen-content'}]

    monkeypatch.setattr(dream_context, 'temporal_neighbours', temporal)
    monkeypatch.setattr(dream_reads, 'read_record', lambda *a, **k: {'content': 'private-content'})
    result = asyncio.run(dream_agent.dry_run_retrieval('private-owner', target, caps=Caps(tokens=100000)))
    assert result['role_counts'] == {'target': 1, 'context': 4}
    expected = {
        'links': (4, 2, 1, 2, 0),
        'lexical': (2, 3, 1, 0, 2),
        'semantic': (3, 1, 1, 1, 0),
        'temporal': (2, 1, 1, 1, 0),
    }
    for path, values in expected.items():
        counts = result['retrieval_counts'][path]
        assert tuple(counts[k] for k in ('attempted', 'found', 'added', 'failed', 'duplicate')) == values
        assert counts['unavailable'] == counts['budget_skipped'] == 0
    assert result['triage_fits'] and 'private-' not in json.dumps(result)
    forbidden.assert_not_called()


def test_failures_and_visibility_misses_are_distinct_and_later_candidates_survive():
    from fastapi import HTTPException

    def hidden():
        raise HTTPException(404, 'private-body')

    def broken():
        raise RuntimeError('private-provider-body')

    report = {}
    rows = dream_context.add_context(
        {'people/a': {'name': 'Toy'}},
        [
            ('people/hidden', hidden, 'links'),
            ('people/broken', broken, 'links'),
            ('people/ok', {'name': 'Boat'}, 'links'),
        ],
        Caps(),
        diagnostics=report,
    )
    assert 'people/ok' in rows
    counts = report['retrieval_counts']['links']
    assert (counts['failed'], counts['unavailable'], counts['added']) == (1, 1, 1)


def test_reports_and_metrics_publish_only_closed_count_labels(caplog):
    report = dream_diagnostics.initialize({'status': 'complete'})
    report['retrieval_counts']['lexical']['failed'] = 2
    report['retrieval_counts']['private-path'] = {'private-label': 99}
    report['dirty_counts']['unavailable'] = 32
    report['dirty_counts']['private-label'] = 99
    before = dream_metrics.RETRIEVAL.labels('lexical', 'failed')._value.get()
    dirty_before = dream_metrics.DIRTY_READS.labels('unavailable')._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(report)
    assert dream_metrics.RETRIEVAL.labels('lexical', 'failed')._value.get() == before + 2
    assert dream_metrics.DIRTY_READS.labels('unavailable')._value.get() == dirty_before + 32
    assert 'private-' not in caplog.text
    assert 'retrieval_counts' in caplog.text and 'dirty_counts' in caplog.text


def test_unconfigured_conversation_vector_index_is_counted_as_failed(monkeypatch):
    from database import vector_db

    monkeypatch.setattr(vector_db, 'index', None)
    with pytest.raises(RuntimeError, match='index unavailable'):
        dream_context.semantic_conversation_refs('synthetic', 'synthetic')
    assert vector_db.query_vectors('synthetic', 'synthetic') == []


def test_reclaimed_targets_stop_at_reasoning_limit_before_reading_overflow(monkeypatch):
    dirty, now = snapshots(35)
    calls = []
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', lambda *a, **k: dirty)
    monkeypatch.setattr(dream_reads, 'read_record', lambda uid, ref, **k: calls.append(ref) or {'content': 'Toy boat'})
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])
    report = {}
    rows, consumed = dream_reads.read_changes('synthetic', {'started_at': now}, Caps(tokens=100000), diagnostics=report)
    assert len(rows.targets) == len(consumed) == len(calls) == dream_context.REASONING_TARGET_LIMIT
    assert report['dirty_counts']['budget_deferred'] == 24
    assert report['target_context_counts'] == {'retrieval_seeded': 4, 'contextless': 4}


def test_structured_query_terms_survive_long_transcript():
    row = {
        'structured': {'title': 'Zuvrah boat', 'overview': 'Nuvra factory'},
        'transcript_segments': [{'text': 'sailing mountain river furniture landscape desert ' * 1000}],
    }
    terms = dream_context.query_terms(row)
    assert 'zuvrah' in terms and 'nuvra' in terms
    assert 'title' not in terms and 'overview' not in terms


def test_later_path_retries_transient_hydration_failure():
    calls = []

    def read():
        calls.append('read')
        if len(calls) == 1:
            raise RuntimeError('private-provider-body')
        return {'content': 'Toy boat'}

    report = {}
    rows = dream_context.add_context(
        {'people/a': {'name': 'Toy'}},
        [('people/recovered', read, 'lexical'), ('people/recovered', read, 'semantic')],
        Caps(),
        diagnostics=report,
    )
    assert 'people/recovered' in rows and len(calls) == 2
    assert report['retrieval_counts']['lexical']['failed'] == 1
    assert report['retrieval_counts']['semantic']['added'] == 1
    assert report['retrieval_counts']['semantic']['duplicate'] == 0


@pytest.mark.parametrize(
    'row', [None, {'discarded': True}, {'deleted': True}, {'deleted': True, 'sync_merged_into': 'synthetic-successor'}]
)
def test_permanent_conversation_states_are_not_transient_locks(monkeypatch, row):
    monkeypatch.setattr(
        dream_reads.conversations, 'get_conversations_by_id_without_photos', lambda *a: [row] if row else []
    )
    assert dream_reads.read_record('synthetic', 'conversations/permanent') is None


def test_locked_conversation_is_transient(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        dream_reads.conversations, 'get_conversations_by_id_without_photos', lambda *a: [{'is_locked': True}]
    )
    with pytest.raises(HTTPException) as raised:
        dream_reads.read_record('synthetic', 'conversations/locked')
    assert raised.value.status_code == 423


@pytest.mark.parametrize('row', [None, {'deleted': True}, {'account_generation': 1}])
def test_permanent_task_states_are_acknowledgeable(monkeypatch, row):
    monkeypatch.setattr(dream_reads, 'get_task_workflow_control', lambda uid: SimpleNamespace(account_generation=2))
    monkeypatch.setattr(dream_reads.action_items, 'get_action_item', lambda *a: row)
    assert dream_reads.read_record('synthetic', 'action_items/permanent') is None


@pytest.mark.parametrize('generation,status', [(1, 'pending'), (2, 'accepted'), (2, 'expired')])
def test_wrong_generation_and_nonpending_candidates_are_permanent(monkeypatch, generation, status):
    monkeypatch.setattr(dream_reads, 'get_task_workflow_control', lambda uid: SimpleNamespace(account_generation=2))
    monkeypatch.setattr(
        dream_reads.candidates,
        'get_candidate',
        lambda *a: SimpleNamespace(account_generation=generation, status=SimpleNamespace(value=status)),
    )
    assert dream_reads.read_record('synthetic', 'candidates/permanent') is None


@pytest.mark.parametrize(
    'change,status',
    [
        ({'is_locked': True}, 423),
        ({'user_review': False}, None),
        ({'invalid_at': 'synthetic-invalid'}, None),
        ({'visibility': 'public'}, None),
    ],
)
def test_memory_lock_is_transient_but_disposition_is_permanent(monkeypatch, change, status):
    from fastapi import HTTPException

    row = SimpleNamespace(is_locked=False, user_review=True, invalid_at=None, visibility='private')
    row.__dict__.update(change)
    monkeypatch.setattr(dream_reads, 'read_canonical_memory_item', lambda *a: None)
    monkeypatch.setattr(dream_reads, 'MemoryService', lambda: SimpleNamespace(fetch=lambda *a: row))
    if status:
        with pytest.raises(HTTPException) as raised:
            dream_reads.read_record('synthetic', 'memories/permanent')
        assert raised.value.status_code == status
    else:
        assert dream_reads.read_record('synthetic', 'memories/permanent') is None
