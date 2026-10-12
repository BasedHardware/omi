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

    def temporal(uid, collection, *a, **k):
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
    assert result['retrieval_failure_counts'] == {
        'links': {'RuntimeError': 2},
        'lexical': {},
        'semantic': {'RuntimeError': 1},
        'temporal': {'RuntimeError': 1},
    }
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
    report['retrieval_failure_counts']['temporal'] = {'TypeError': 4, 'private-class': 99}
    report['retrieval_failure_counts']['private-path'] = {'TypeError': 99}
    before = dream_metrics.RETRIEVAL.labels('lexical', 'failed')._value.get()
    dirty_before = dream_metrics.DIRTY_READS.labels('unavailable')._value.get()
    failures_before = dream_metrics.RETRIEVAL_FAILURES.labels('temporal', 'TypeError')._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(report)
    assert dream_metrics.RETRIEVAL.labels('lexical', 'failed')._value.get() == before + 2
    assert dream_metrics.DIRTY_READS.labels('unavailable')._value.get() == dirty_before + 32
    assert dream_metrics.RETRIEVAL_FAILURES.labels('temporal', 'TypeError')._value.get() == failures_before + 4
    assert 'private-' not in caplog.text
    assert 'retrieval_counts' in caplog.text and 'dirty_counts' in caplog.text
    assert 'retrieval_failure_counts' in caplog.text


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
        'user_title': 'Kuvra',
        'structured': {'title': 'Zuvrah boat', 'overview': 'Nuvra factory'},
        'transcript_segments': [{'text': 'sailing mountain river furniture landscape desert ' * 1000}],
    }
    terms = dream_context.query_terms(row)
    assert 'kuvra' in terms and 'zuvrah' in terms and 'nuvra' in terms
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


def test_eight_ordinary_speech_targets_search_without_rare_tokens_and_exclude_all_inputs(monkeypatch):
    from datetime import timedelta
    from database import dream_context_reads
    from tests.support.firestore_shape_recorder import RecordingFirestore

    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    # Every word was filtered out by the old rarity gate.
    speech = ['We work in the garden with the boat ' + word for word in ('one', 'two', 'three', 'four')]
    assert all(set(dream_context.tokens(words)) <= dream_context.common_words() for words in speech)
    records = {
        f'conversations/target-{i}': {'created_at': now, 'transcript_segments': [{'text': speech[i % 4]}]}
        for i in range(8)
    }
    lexical, semantic, windows = [], [], []
    monkeypatch.setattr(dream_context.action_items, 'get_action_items', lambda *a, **k: [])
    monkeypatch.setattr(dream_context, 'keyword_search_conversation_ids', lambda **k: lexical.append(k['query']) or [])
    monkeypatch.setattr(dream_context, 'semantic_conversation_refs', lambda query, uid: semantic.append(query) or [])
    monkeypatch.setattr(dream_context, 'MemoryService', lambda: SimpleNamespace(search=lambda *a, **k: []))
    monkeypatch.setattr(
        dream_reads, 'read_record', lambda *a, **k: {'transcript_segments': [{'text': 'Toy neighbour'}]}
    )

    # Reproduce the actual pre-#21237 shared dependency left by dream-only overlays.
    def old_control(uid):
        return SimpleNamespace(account_generation=0)

    monkeypatch.setattr(dream_context_reads, 'get_task_workflow_control', old_control)

    def temporal(uid, collection, start, anchor, end, **kwargs):
        windows.append((collection, start, end, kwargs['excluded_ids']))
        if collection == 'conversations':
            return [{'id': 'outside-input'}]
        return dream_context_reads.temporal_neighbours(
            uid, collection, start, anchor, end, firestore_client=RecordingFirestore(), **kwargs
        )

    monkeypatch.setattr(dream_context, 'temporal_neighbours', temporal)
    result = asyncio.run(dream_agent.dry_run_retrieval('synthetic', records, caps=Caps(tokens=100000), vocabulary=[]))
    assert len(lexical) == len(semantic) == 4
    assert all('garden' in query and 'boat' in query for query in lexical)
    assert semantic == speech
    assert result['retrieval_counts']['lexical']['attempted'] == 4
    assert result['retrieval_counts']['semantic']['attempted'] == 8
    assert result['retrieval_counts']['temporal']['failed'] == 4
    assert result['retrieval_failure_counts']['temporal'] == {'TypeError': 4}
    assert result['target_context_counts'] == {'retrieval_seeded': 4, 'contextless': 4}
    assert result['role_counts'] == {'target': 8, 'context': 1} and result['triage_fits']
    for collection, start, end, excluded in windows:
        if collection == 'conversations':
            assert {f'target-{i}' for i in range(8)} <= excluded
            assert (start, end) == (now - timedelta(hours=24), now + timedelta(hours=24))
        else:
            assert (start, end) == (now - timedelta(hours=2), now + timedelta(hours=2))
    conversation_windows = [excluded for collection, _, _, excluded in windows if collection == 'conversations']
    assert 'outside-input' not in conversation_windows[0]
    assert all('outside-input' in excluded for excluded in conversation_windows[1:])
    assert 'synthetic' not in json.dumps(result) and 'garden' not in json.dumps(result)


def test_semantic_short_and_nonlatin_text_does_not_depend_on_lexical_gate(monkeypatch):
    queries = []
    monkeypatch.setattr(dream_context, 'semantic_conversation_refs', lambda query, uid: queries.append(query) or [])
    monkeypatch.setattr(dream_context, 'MemoryService', lambda: SimpleNamespace(search=lambda *a, **k: []))
    monkeypatch.setattr(dream_context, 'keyword_search_conversation_ids', lambda **k: [])
    report = {}
    list(
        dream_context.context_candidates(
            'synthetic',
            {'people/a': {'name': 'AI'}, 'people/b': {'name': '猫'}},
            [],
            read_record=None,
            read_entity_record=None,
            diagnostics=report,
        )
    )
    assert queries == ['AI', '猫']
    assert report['retrieval_counts']['lexical']['query_empty'] == 2
    assert report['retrieval_counts']['semantic']['query_empty'] == 0
    assert report['retrieval_counts']['semantic']['attempted'] == 4


def test_exception_class_counters_cover_query_and_hydration_without_private_labels():
    def broken():
        raise TypeError('private-provider-body')

    report = {}
    assert list(dream_context.query_candidates(report, 'temporal', broken)) == []
    dream_context.add_context({'people/a': {}}, [('people/b', broken, 'temporal')], Caps(), diagnostics=report)
    custom = type('private-account-name', (Exception,), {})('private-body')
    dream_diagnostics.path_failure(report, 'temporal', custom)
    assert report['retrieval_counts']['temporal']['failed'] == 3
    counts = dream_diagnostics.counts_only(report)
    assert counts['retrieval_failure_counts']['temporal'] == {'TypeError': 2, 'Exception': 1}
    assert 'private-' not in json.dumps(counts)


def test_temporal_exclusion_precedes_top_four_selection_with_bounded_overfetch():
    from datetime import timedelta
    from database.dream_context_reads import temporal_neighbours
    from tests.support.firestore_shape_recorder import RecordingFirestore

    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    db = RecordingFirestore()
    targets = [db.snapshot(f'users/synthetic/conversations/target-{i}', {'created_at': now}) for i in range(8)]
    neighbours = [
        db.snapshot(
            f'users/synthetic/conversations/context-{i}',
            {
                'created_at': now - timedelta(minutes=i + 1),
            },
        )
        for i in range(4)
    ]
    db.queue_results(targets + neighbours)
    db.queue_results(targets)
    rows = temporal_neighbours(
        'synthetic',
        'conversations',
        now - timedelta(days=1),
        now,
        now + timedelta(days=1),
        excluded_ids={f'target-{i}' for i in range(8)},
        firestore_client=db,
    )
    assert [row['id'] for row in rows] == [f'context-{i}' for i in range(4)]
    assert len(db.shapes) == 2 and all(shape.limit == 12 for shape in db.shapes)


@pytest.mark.parametrize('contraction', ["don't", "isn't", "didn't", "wouldn't", 'don’t'])
def test_contraction_fragments_do_not_suppress_ordinary_content_query(contraction):
    terms = dream_context.query_terms({'content': f'We {contraction} work in the garden with the boat'})
    assert {'work', 'garden', 'boat'} <= set(terms)
    assert not {'don', 'isn', 'didn', 'wouldn'} & set(terms)


def test_common_word_fallback_does_not_fuzzy_match_all_500_vocabulary_entries(monkeypatch):
    matcher = Mock(side_effect=AssertionError('ordinary tokens entered rare-term fuzzy matcher'))
    monkeypatch.setattr(dream_context, 'SequenceMatcher', matcher)
    vocabulary = [{'spelling': f'Zuvra-{i}'} for i in range(500)]
    terms = dream_context.query_terms({'content': 'garden boat window office computer ' * 100}, vocabulary)
    assert terms == ['garden', 'boat', 'window', 'office', 'computer']
    matcher.assert_not_called()


def test_scheduled_pending_targets_are_excluded_before_first_seed_temporal_selection(monkeypatch):
    from datetime import timedelta
    from database.dream_context_reads import temporal_neighbours
    from tests.support.firestore_shape_recorder import RecordingFirestore

    dirty, now = snapshots(8)
    calls, exclusions = [], []
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', lambda *a, **k: dirty)
    monkeypatch.setattr(dream_context.action_items, 'get_action_items', lambda *a, **k: [])
    monkeypatch.setattr(dream_context, 'keyword_search_conversation_ids', lambda **k: [])
    monkeypatch.setattr(dream_context, 'semantic_conversation_refs', lambda *a: [])
    monkeypatch.setattr(dream_context, 'MemoryService', lambda: SimpleNamespace(search=lambda *a, **k: []))

    def read(uid, ref, **kwargs):
        calls.append(ref)
        # Other seeds are a month away: they cannot repair the first window.
        offset = int(ref.split('/')[1]) if ref.split('/')[1].isdigit() else 0
        return {'created_at': now - timedelta(days=30 * offset), 'content': 'garden boat'}

    monkeypatch.setattr(dream_reads, 'read_record', read)

    def temporal(uid, collection, start, anchor, end, **kwargs):
        if collection != 'conversations' or anchor != now:
            return []
        assert calls == [f'conversations/{i}' for i in range(4)]
        exclusions.append(kwargs['excluded_ids'])
        db = RecordingFirestore()
        db.queue_results(
            [db.snapshot(f'users/synthetic/conversations/{i}', {'created_at': now}) for i in range(4, 8)]
            + [db.snapshot('users/synthetic/conversations/neighbour', {'created_at': now - timedelta(minutes=1)})]
        )
        db.queue_results([])
        return temporal_neighbours(uid, collection, start, anchor, end, firestore_client=db, **kwargs)

    monkeypatch.setattr(dream_context, 'temporal_neighbours', temporal)
    rows, consumed = dream_reads.read_changes('synthetic', {'started_at': now}, Caps(tokens=100000))
    assert exclusions == [{str(i) for i in range(8)}]
    assert 'conversations/neighbour' in rows and 'conversations/neighbour' not in rows.targets
    assert rows.targets == {f'conversations/{i}' for i in range(8)} and len(consumed) == 8
    assert len(calls) == 9  # Four initial targets, one neighbour, four reclaimed targets.
