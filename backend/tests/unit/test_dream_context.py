"""Synthetic contract regressions; no provider or customer reads."""

import json
import asyncio

import pytest

from models.dream_agent import Triage, Cluster, Plan, Edit
from utils import dream_guards, dream_prompt, dream_agent, dream_context
from config.dream_agent import Caps
from utils.llm.shaped_agent import Turn


@pytest.mark.parametrize(
    'row,expected',
    [
        ({'structured': {'title': 'Existing title'}}, {'title': 'nonempty_field', 'overview': 'insufficient_speech'}),
        ({'user_title': 'My title'}, {'title': 'nonempty_field', 'overview': 'insufficient_speech'}),
        ({'structured': {'sections': [{}]}}, {'title': 'insufficient_speech', 'overview': 'nonempty_field'}),
        ({}, {'title': 'insufficient_speech', 'overview': 'insufficient_speech'}),
        ({'transcript_segments': [{'text': 'solar boat ' * 20}]}, {'title': 'editable', 'overview': 'editable'}),
    ],
)
def test_eligibility_survives_projection_and_uses_guard_primitive(row, expected):
    records = {'conversations/synthetic': row}
    payload = json.loads(dream_prompt.evidence_message(records, Triage, 12000)[0]['content'])
    assert payload['summary_eligibility']['conversations/synthetic'] == expected
    assert dream_guards.summary_eligibility(row) == expected


def test_full_speech_eligibility_is_computed_before_excerpt_truncation():
    row = {'transcript_segments': [{'text': 'solar boat ' * 2000}]}
    payload = json.loads(dream_prompt.evidence_message({'conversations/c': row}, Triage, 5000)[0]['content'])
    assert payload['summary_eligibility']['conversations/c']['title'] == 'editable'


def test_eligibility_eval_removes_wasted_offers():
    cases = [
        {'structured': {'title': 'Confirmed invented movie'}, 'transcript_segments': [{'text': 'solar boat ' * 20}]},
        {'transcript_segments': [{'text': 'This invented snippet has only eleven words about our toy boat.'}]},
    ]
    before = sum(2 for _ in cases)
    after = sum(value == 'editable' for row in cases for value in dream_guards.summary_eligibility(row).values())
    assert (before, after) == (4, 1)


def test_context_is_retained_in_both_stages_and_cannot_be_edited():
    records = dream_context.EvidenceRecords(
        {'conversations/a': {'transcript_segments': [{'text': 'Nuvrah'}]}, 'people/p': {'name': 'Nuvra'}},
        targets=['conversations/a'],
    )
    seen = []

    async def turn(uid, lane, mount, messages):
        payload = json.loads(messages[-1]['content'])
        seen.append(payload)
        assert payload['roles'] == {'conversations/a': 'target', 'people/p': 'context'}
        value = (
            Triage(clusters=[Cluster(refs=['conversations/a'], problem='spelling')])
            if len(seen) == 1
            else Plan(
                edits=[
                    Edit(
                        kind='spelling',
                        target='people/p',
                        before='Nuvra',
                        after='Nuvrah',
                        reason='Synthetic',
                        evidence=['people/p'],
                    )
                ]
            )
        )
        return Turn(value=value, tokens=100)

    result = asyncio.run(dream_agent.dry_run('synthetic', records, turn=turn))
    assert not result['plan']['edits']
    assert result['guard_decisions'] == {'context_target': 1}
    assert result['role_counts'] == {'target': 1, 'context': 1}
    assert len(seen) == 2


def test_merge_cannot_mutate_context_partner():
    edit = Edit(
        kind='merge_memories',
        target='memory_items/a',
        other='memory_items/b',
        before='',
        after='Toy fact',
        reason='Synthetic',
        evidence=['memory_items/a', 'memory_items/b'],
    )
    sink = {}
    assert not dream_guards.filter_plan(
        Plan(edits=[edit]), {'memory_items/a': {}, 'memory_items/b': {}}, targets=['memory_items/a'], usage_sink=sink
    ).edits
    assert sink['rejected'] == {'context_target': 1}


def test_neighbourhood_budget_stops_lazy_expensive_queries():
    targets = {'conversations/a': {'transcript_segments': [{'text': 'solar boat ' * 20}]}}
    touched = []

    def candidates():
        for i in range(100):
            touched.append(i)
            yield f'conversations/context-{i}', {'transcript_segments': [{'text': 'invented ' * 1000}]}

    records = dream_context.add_context(targets, candidates(), Caps())
    assert len(touched) < 100
    assert records.targets == set(targets)
    assert dream_context.fits_pass(records, Caps())


def test_lexical_query_uses_rare_terms_and_vocabulary_near_matches():
    terms = dream_context.query_terms(
        {'transcript_segments': [{'text': 'Nuvrah built a window for the garden.'}]}, [{'spelling': 'Nuvra'}]
    )
    assert 'nuvrah' in terms and 'Nuvra' in terms
    assert 'window' not in terms and 'garden' not in terms


def test_retrieval_tiers_are_owner_scoped_and_cheapest_first(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(dream_context.action_items, 'get_action_items', lambda uid, **kwargs: [{'id': 'task'}])
    monkeypatch.setattr(
        dream_context,
        'MemoryService',
        lambda: SimpleNamespace(read=lambda uid, **kwargs: [], search=lambda uid, query, **kwargs: []),
    )
    monkeypatch.setattr(dream_context, 'keyword_search_conversation_ids', lambda **kwargs: ['lexical'])
    monkeypatch.setattr(dream_context.vector_db, 'query_vectors', lambda query, uid, **kwargs: ['semantic'])
    monkeypatch.setattr(dream_context.conversations, 'get_conversations', lambda uid, **kwargs: [{'id': 'adjacent'}])
    monkeypatch.setattr(dream_context.screen_activity, 'get_screen_activity', lambda uid, **kwargs: [{'id': 'frame'}])

    def read(uid, ref):
        calls.append((uid, ref))
        return {'name': 'Nuvra'}

    targets = {
        'conversations/a': {
            'created_at': datetime(2030, 1, 1, tzinfo=timezone.utc),
            'transcript_segments': [{'text': 'Nuvrah', 'person_id': 'p'}],
        }
    }
    rows = list(
        dream_context.context_candidates('synthetic-owner', targets, [], read_record=read, read_entity_record=read)
    )
    assert [ref for ref, _ in rows] == [
        'entity/person:p',
        'action_items/task',
        'conversations/lexical',
        'conversations/semantic',
        'conversations/adjacent',
        'screen/frame',
    ]
    assert all(uid == 'synthetic-owner' for uid, _ in calls)


def test_invisible_neighbours_are_excluded():
    records = dream_context.add_context({'people/target': {'name': 'Nuvra'}}, [('people/hidden', None)], Caps())
    assert list(records) == ['people/target']


def test_decomposed_accents_do_not_multiply_summary_words():
    import unicodedata

    speech = unicodedata.normalize('NFD', 'tiếng ' * 20)
    row = {'transcript_segments': [{'text': speech}]}
    assert dream_guards.summary_eligibility(row) == {'title': 'insufficient_speech', 'overview': 'insufficient_speech'}
    assert dream_guards.has_summary_speech(speech, 20)
    assert not dream_guards.has_summary_speech(speech, 21)


def test_empty_target_retrieval_never_touches_memory_store(monkeypatch):
    monkeypatch.setattr(dream_context, 'MemoryService', lambda: pytest.fail('idle retrieval read memory'))
    assert list(dream_context.context_candidates('synthetic', {}, [], read_record=None, read_entity_record=None)) == []


def test_canonical_neighbourhood_unavailability_fails_pass(monkeypatch):
    from types import SimpleNamespace

    def unavailable(uid, **kwargs):
        assert kwargs['authoritative'] is True
        raise RuntimeError('synthetic canonical outage')

    monkeypatch.setattr(dream_context, 'MemoryService', lambda: SimpleNamespace(read=unavailable))
    with pytest.raises(RuntimeError, match='synthetic canonical outage'):
        list(
            dream_context.context_candidates(
                'synthetic', {'people/a': {'name': 'Nuvra'}}, [], read_record=None, read_entity_record=None
            )
        )


def test_dense_repeated_triage_metadata_is_compacted_and_budgeted():
    rows = dream_context.EvidenceRecords(
        {
            'people/' + 'a' * 100: {'name': 'Synthetic Nuvra'},
            'people/' + 'b' * 100: {'name': 'Synthetic Nuvrah'},
        }
    )
    triage = Triage(clusters=[Cluster(problem='duplicates', refs=list(rows) * 10) for _ in range(12)])
    hints = dream_context.cluster_hints(triage, rows)
    assert hints == {'clusters': [{'problem': 'duplicates', 'refs': sorted(rows)}]}
    caps = Caps()
    assert dream_context.fits_pass(rows, caps)
    messages = dream_prompt.evidence_message(rows, Triage, dream_prompt.triage_budget(caps))
    ceiling = dream_context.input_ceiling(
        dream_prompt.mount(Triage, dream_prompt.triage_budget(caps), dream_prompt.TRIAGE_INSTRUCTIONS).messages(
            messages
        ),
        Triage.model_json_schema(),
    )
    dream_prompt.evidence_message(
        rows,
        Plan,
        caps.tokens - ceiling - dream_prompt.COMPLETION_RESERVE,
        clusters=hints,
        names=dream_prompt.person_names(rows),
    )


def test_merge_question_cannot_mutate_context_entity():
    from datetime import datetime, timezone
    from models.review import ReviewItem, SamePersonItem, EntitySummary

    left = EntitySummary(entity_id='person:a', type='person', name='Synthetic Nuvra')
    right = EntitySummary(entity_id='person:b', type='person', name='Synthetic Nuvrah')
    question = ReviewItem(
        item_id='synthetic',
        kind='same_person',
        title='Same person?',
        created_at=datetime.now(timezone.utc),
        same_person=SamePersonItem(left=left, right=right, reason='Synthetic'),
    )
    records = {'people/a': left.model_dump(), 'entity/person:b': right.model_dump()}
    sink = {}
    assert not dream_guards.filter_plan(
        Plan(questions=[question]), records, targets=['people/a'], usage_sink=sink
    ).questions
    assert sink['rejected'] == {'context_target': 1}
    assert dream_guards.filter_plan(Plan(questions=[question]), records, targets=records).questions == [question]
