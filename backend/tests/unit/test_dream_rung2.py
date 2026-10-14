"""Consensus automation and attention admission through real reversible writers."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from config.dream_agent import Caps, auto_apply_kinds
from database import dream_store, memory_ledger, review_changes, review_store
from models.dream_agent import Cluster, Triage, FullPlan, FullReviewItem, Plan
from models.dream_edit import Edit, FullEdit
from tests.support.dream_firestore import DreamFirestore
from utils import dream_agent, dream_tools, dream_transport, dream_metrics
from utils.dream_consensus import majority, unanimous_spelling
from utils.dream_context import EvidenceRecords
from utils.llm.shaped_agent import Turn

REAL_DEMOTED_TYPES = dream_store.demoted_types
UID = 'synthetic-rung2-owner'
REF = 'conversations/toy'
ROW = {
    'id': 'toy',
    'data_protection_level': 'enhanced',
    'structured': {'title': 'Qorby workshop', 'overview': 'Qorby workshop overview'},
    'transcript_segments': [
        {'id': 's1', 'start': 10, 'end': 12, 'text': 'Qorby met Qorby. Alpha Beta Gamma Delta.'},
        {'id': 's2', 'start': 20, 'end': 22, 'text': 'Qorby elsewhere.'},
    ],
}


def edit(**kw):
    return FullEdit.model_validate(
        {
            'kind': 'spelling',
            'target': REF + '#s1',
            'before': 'Qorby',
            'after': 'Qorbee',
            'reason': 'Synthetic correction',
            'evidence': [REF + '#s1'],
            'value': 5,
            **kw,
        }
    )


def question(quote='Alpha', value=4):
    return FullReviewItem(
        kind='spelling',
        title='Which project name?',
        source_ref=REF + '#s1',
        quote=quote,
        spelling={'term_id': quote, 'options': [quote, quote + 'a'], 'allow_custom': True},
        value=value,
        why_it_matters='Clarifies a project name for future work.',
    )


@pytest.fixture
def store(monkeypatch):
    db = DreamFirestore()
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', UID)
    monkeypatch.setenv('DREAM_AGENT_FULL_SAMPLES', '3')
    monkeypatch.setenv('DREAM_AGENT_AUTO_APPLY_KINDS', 'title,overview')
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(memory_ledger, 'transactional', lambda fn: fn)
    db.rows[('users', UID)] = {}
    db.rows[('users', UID, 'conversations', 'toy')] = dream_tools.conversations.encode_conversation_for_write(
        UID, deepcopy(ROW), 'enhanced'
    )
    lease = {'run_id': 'synthetic-run', 'mode': 'on'}
    db.rows[('dream_users', UID)] = {'lease': lease}
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: lease)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_store, 'finish', lambda *a, **k: None)

    def read_changes(*args, **kwargs):
        row = dream_tools.conversations.prepare_conversation_for_read(
            deepcopy(db.rows[('users', UID, 'conversations', 'toy')]), UID
        )
        return EvidenceRecords({REF: row}), []

    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', read_changes)
    monkeypatch.setattr(dream_tools, 'proposal_record', lambda uid, ref, snapshot: read_changes()[0][ref])
    return db


def run(plans, *, caps=None, uid=UID):
    samples = iter(plans)

    async def turn(uid, lane, mount, messages):
        if mount.schema is not FullPlan:
            if mount.schema is Triage:
                return Turn(value=Triage(clusters=[Cluster(refs=[REF], problem='spelling')]), tokens=10)
        value = next(samples)
        return Turn(value=value, tokens=10)

    return asyncio.run(dream_agent.run_pass(uid, turn=turn, caps=caps or Caps()))


def stored_row(db):
    return dream_tools.conversations.prepare_conversation_for_read(
        deepcopy(db.rows[('users', UID, 'conversations', 'toy')]), UID
    )


def proposals(db):
    return [
        review_store.decode_doc(UID, value)
        for path, value in db.rows.items()
        if path[:-1] == ('users', UID, 'review_proposals')
    ]


def test_unanimity_is_scoped_journaled_undoable_and_suppressed(store):
    report = run([FullPlan(edits=[edit()])] * 3)
    assert report['status'] == 'complete'
    assert report['auto_applied_unanimous'] == 1 and report['questions_offered'] == 0
    assert report['proposed']['edits'][0]['agreement'] == report['proposed']['edits'][0]['samples'] == 3
    assert report['proposed']['edits'][0]['policy'] == 'auto'
    row = stored_row(store)
    assert row['transcript_segments'][0]['text'].startswith('Qorbee met Qorbee.')
    assert row['transcript_segments'][1] == ROW['transcript_segments'][1]
    assert row['structured'] == ROW['structured']
    journals = [
        review_store.decode_doc(UID, v) for p, v in store.rows.items() if p[:-1] == ('users', UID, 'review_changes')
    ]
    assert len(journals) == 1 and journals[0]['edit_key'].startswith('dream:spelling:')
    change = journals[0]['change']
    review_changes.set_undone(UID, change['change_id'], True)
    assert stored_row(store)['transcript_segments'] == ROW['transcript_segments']
    report = run([FullPlan(edits=[edit()])] * 3)
    assert report['auto_applied_unanimous'] == 0 and report['outcomes'][0]['status'] == 'suppressed'


@pytest.mark.parametrize('returned', [1, 2])
def test_returned_sample_count_controls_unanimity(store, returned):
    plans = [FullPlan(edits=[edit()])] * returned
    result = majority(plans)
    assert unanimous_spelling(result.edits[0]) is (returned == 2)

    # The remaining requested samples fail; K is the returned count.
    async def turn(*args):
        if plans:
            return Turn(value=plans.pop(), tokens=10)
        raise RuntimeError('Synthetic sample failure')

    report = asyncio.run(dream_agent.run_pass(UID, turn=turn))
    assert report['status'] == 'complete' and report['samples_returned'] == returned
    assert report['auto_applied_unanimous'] == int(returned == 2)
    assert report['questions_offered'] == int(returned == 1)


def test_majority_becomes_answerable_spelling_question(store):
    report = run([FullPlan(edits=[edit()]), FullPlan(edits=[edit()]), FullPlan()])
    assert report['status'] == 'complete' and report['auto_applied_unanimous'] == 0
    assert report['suggested_majority'] == report['questions_offered'] == 1
    assert stored_row(store)['transcript_segments'] == ROW['transcript_segments']
    offered = proposals(store)[0]
    assert offered['item']['kind'] == 'spelling' and offered['source']['spelling_edit']['target'] == REF + '#s1'
    assert dream_tools.answer_spelling(UID, offered['source'], 'Qorbee')
    assert stored_row(store)['transcript_segments'][0]['text'].startswith('Qorbee')


def test_grounded_majority_still_auto_applies(store, monkeypatch):
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [{'spelling': 'Qorbee', 'authorship': 'user_authored'}])
    store.rows[('users', UID, 'dream_vocabulary', 'current')] = review_store.encode_doc(
        UID, {'source': [{'spelling': 'Qorbee', 'authorship': 'user_authored'}]}
    )
    report = run([FullPlan(edits=[edit()]), FullPlan(edits=[edit()]), FullPlan()])
    assert report['status'] == 'complete' and report['proposed']['edits'][0]['policy'] == 'auto'
    assert report['auto_applied_unanimous'] == report['questions_offered'] == 0
    assert stored_row(store)['transcript_segments'][0]['text'].startswith('Qorbee')


def test_bounded_owner_cannot_use_unanimity_or_full_policy(store, monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', 'someone-else')
    assert auto_apply_kinds(UID) == {'title', 'overview'}
    item = majority([FullPlan(edits=[edit()])] * 3).edits[0]
    with pytest.raises(ValueError, match='ungrounded_spelling'):
        dream_tools.apply_unanimous_edit(UID, item, {REF: ROW})
    bounded = Edit.model_validate(edit().model_dump(exclude={'value'}))
    report = run([Plan(edits=[bounded])])
    assert report['status'] == 'complete' and report['proposed']['edits'][0]['policy'] == 'suggest'
    assert 'auto_applied_unanimous' not in report
    assert stored_row(store)['transcript_segments'] == ROW['transcript_segments']
    assert (
        'value' not in Edit.model_fields
        and 'value' not in Plan.model_json_schema()['$defs']['DreamReviewItem']['properties']
    )


def test_undo_rate_demotion_stops_unanimity(store, monkeypatch):
    run([FullPlan(edits=[edit()])] * 3)
    journal_path, journal = next(
        (p, review_store.decode_doc(UID, v))
        for p, v in store.rows.items()
        if p[:-1] == ('users', UID, 'review_changes')
    )
    review_changes.set_undone(UID, journal['change']['change_id'], True)
    # Exercise the real demotion query against the resulting Undo journal.
    query = SimpleNamespace()
    query.where = lambda **kw: query
    query.order_by = lambda *a, **kw: query
    query.limit = lambda n: query
    query.stream = lambda: iter([SimpleNamespace(to_dict=lambda: store.rows[journal_path])])
    query_db = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda uid: SimpleNamespace(collection=lambda name: query))
    )
    caps = Caps(undo_min_samples=1, undo_rate=0.2)
    assert REAL_DEMOTED_TYPES(UID, caps, firestore_client=query_db) == {'spelling'}
    monkeypatch.setattr(
        dream_store, 'demoted_types', lambda uid, caps: REAL_DEMOTED_TYPES(uid, caps, firestore_client=query_db)
    )
    # A different semantic edit is not suppressed, so demotion is the stopping condition.
    changed = edit(before='Alpha', after='Alphah')
    report = run([FullPlan(edits=[changed])] * 3, caps=caps)
    assert report['status'] == 'complete' and report['auto_applied_unanimous'] == 0
    assert report['proposed']['edits'][0]['policy'] == 'suggest'
    assert stored_row(store)['transcript_segments'] == ROW['transcript_segments']


def test_questions_rank_agreement_then_value_and_share_cap(store):
    strong = question('Alpha', 3)
    valuable = question('Beta', 5)
    lower = question('Gamma', 3)
    trivia = question('Delta', 2)
    # Spelling majority and direct questions compete in one ranked offer list.
    report = run(
        [
            FullPlan(edits=[edit()], questions=[valuable, lower, trivia]),
            FullPlan(edits=[edit()], questions=[valuable, lower, strong]),
            FullPlan(questions=[strong, trivia]),
        ]
    )
    # Three questions have 2 votes: value 5 wins; the edit also has value 5.
    assert report['status'] == 'complete'
    assert [p['item']['spelling']['term_id'] for p in proposals(store)][:1] == ['Beta']
    assert len(proposals(store)) == report['questions_offered'] == 3
    assert report['questions_dropped_low_value'] == 1
    assert report['suggested_majority'] == 1
    assert store.rows[('dream_users', UID)]['questions'] == 3
    again = run([FullPlan(questions=[question('Delta', 5)])] * 3)
    assert again['questions_offered'] == 0 and len(proposals(store)) == 3


def test_unanimous_question_outranks_higher_value_majority(store):
    strong, valuable = question('Alpha', 3), question('Beta', 5)
    report = run(
        [FullPlan(questions=[valuable, strong]), FullPlan(questions=[valuable, strong]), FullPlan(questions=[strong])]
    )
    assert report['status'] == 'complete'
    assert [p['item']['spelling']['term_id'] for p in proposals(store)] == ['Alpha', 'Beta']


def test_duplicate_direct_question_preserves_slot_for_next_rank(store):
    run([FullPlan(questions=[question('Alpha')])] * 3)
    report = run([FullPlan(questions=[question('Alpha', 5), question('Beta', 3)])] * 3)
    assert report['questions_offered'] == 1
    assert store.rows[('dream_users', UID)]['questions'] == 2
    assert len(proposals(store)) == 2


def test_identity_questions_share_atomic_admission_with_spelling(store, monkeypatch):
    read = dream_agent.dream_reads.read_changes

    def with_people(*args, **kwargs):
        records, dirty = read(*args, **kwargs)
        records.update({'people/left': {'name': 'Toy Left'}, 'people/right': {'name': 'Toy Right'}})
        records.targets.update({'people/left', 'people/right'})
        return records, dirty

    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', with_people)
    identity = FullReviewItem(
        kind='same_person',
        title='Are these the same person?',
        source_ref=REF,
        quote='Qorby',
        same_person={
            'left': {'entity_id': 'person:left', 'type': 'person', 'name': 'Toy Left'},
            'right': {'entity_id': 'person:right', 'type': 'person', 'name': 'Toy Right'},
            'reason': 'Synthetic ambiguity',
        },
        value=5,
        why_it_matters='Clarifies who future references describe.',
    )
    report = run([FullPlan(questions=[identity, question()])] * 3)
    assert report['status'] == 'complete' and report['questions_offered'] == 2
    assert [p['item']['kind'] for p in proposals(store)] == ['same_person', 'spelling']
    assert store.rows[('dream_users', UID)]['questions'] == 2


def test_full_edit_cap_still_bounds_unanimous_apply(store, monkeypatch):
    applied = []
    monkeypatch.setattr(
        dream_tools, 'apply_unanimous_edit', lambda uid, edit, records: applied.append(edit.after) or 'applied'
    )
    edits = [edit(after='Qorbee' + str(index)) for index in range(26)]
    report = run([FullPlan(edits=edits)] * 3)
    assert report['status'] == 'complete' and report['auto_applied_unanimous'] == 25
    assert len(applied) == 25 and report['rejected']['edit_cap'] == 1


@pytest.mark.parametrize('value', [None, 1, 2])
def test_low_value_edit_questions_never_spend_attention(store, value):
    report = run([FullPlan(edits=[edit(value=value)]), FullPlan(edits=[edit(value=value)]), FullPlan()])
    assert report['status'] == 'complete' and report['questions_offered'] == 0
    assert report['questions_dropped_low_value'] == 1 and proposals(store) == []
    assert store.rows[('dream_users', UID)].get('questions', 0) == 0


def test_question_schema_requires_value_and_generic_explanation():
    payload = question().model_dump(mode='json', exclude={'value', 'why_it_matters'})
    with pytest.raises(ValidationError):
        FullReviewItem.model_validate(payload)
    assert dream_transport.parse_response(FullPlan, {'questions': [payload]}).questions == []
    assert 'trivial acronym casing is 1' in FullEdit.model_fields['value'].description


def test_decision_metrics_are_counts_only(caplog):
    before = {key: dream_metrics.DECISIONS.labels(key)._value.get() for key in dream_metrics.DECISION_COUNTS}
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass({'context_mode': 'full', 'status': 'complete', **{key: 2 for key in before}})
    assert all(dream_metrics.DECISIONS.labels(key)._value.get() == value + 2 for key, value in before.items())
    assert 'Qorby' not in caplog.text and 'questions_offered' in caplog.text


@pytest.mark.parametrize('from_edit', [True, False], ids=['edit-derived', 'direct-full-question'])
def test_full_ranked_questions_keep_encrypted_spelling_context(store, monkeypatch, from_edit):
    row = deepcopy(ROW)
    row['transcript_segments'][0]['is_user'] = True
    row['transcript_segments'][1]['person_id'] = 'alex'
    store.rows[('users', UID, 'conversations', 'toy')] = dream_tools.conversations.encode_conversation_for_write(
        UID, row, 'enhanced'
    )
    original_read = dream_agent.dream_reads.read_changes

    def with_known_speaker(*args, **kwargs):
        records, dirty = original_read(*args, **kwargs)
        records['people/alex'] = {'name': 'Alex'}
        return records, dirty

    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', with_known_speaker)
    proposal = FullPlan(edits=[edit(value=4)]) if from_edit else FullPlan(questions=[question(value=4)])
    # Two-of-three consensus routes through offer_questions, then either
    # suggest_spelling or ask_ranked; both use the real encrypted queue writer.
    report = run([proposal, proposal, FullPlan()])
    assert report['status'] == 'complete' and report['questions_offered'] == 1
    assert store.rows[('dream_users', UID)]['questions'] == 1
    queued = proposals(store)
    assert len(queued) == 1
    saved = queued[0]
    context = saved['item']['spelling']['context']
    assert context['conversation_title'] == ROW['structured']['title']
    assert context['main_index'] == 0 and len(context['segments']) == 2
    assert [s['speaker_label'] for s in context['segments']] == ['You', 'Alex']
    assert context['segments'][0]['text'][context['quote_start'] : context['quote_end']] == saved['item']['quote']
    assert saved['source']['records'][REF]['transcript_segments'][0]['id'] == 's1'
    assert saved['source']['speaker_names'] == {'alex': 'Alex'}
    raw = [value for path, value in store.rows.items() if 'review_proposals' in path]
    assert len(raw) == 1 and 'review_encrypted_v1' in raw[0]['item']
    assert 'Qorby workshop' not in str(raw[0]) and 'Alex' not in str(raw[0])
