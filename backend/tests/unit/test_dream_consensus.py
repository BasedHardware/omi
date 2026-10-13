"""Rung 1.2: independent samples, exact fragment citations and server identity."""

import asyncio
from datetime import datetime, timezone

import pytest

from config.dream_agent import Caps
from models.dream_agent import DreamReviewItem, Plan, SlowTask
from models.dream_edit import Edit, Term
from models.dream_refs import base_ref, cited_value
from utils import dream_agent, dream_guards, dream_metrics, dream_tools, dream_transport
from utils.dream_consensus import majority
from utils.dream_context import EvidenceRecords
from utils.llm.shaped_agent import Turn

UID = 'synthetic-consensus-owner'
REF = 'conversations/synthetic'
RECORD = {
    'transcript_segments': [
        {'id': 'first', 'start': 12.5, 'end': 14, 'text': 'Borza is a project.'},
        {'id': 'second', 'start': 20, 'end': 24, 'text': 'A different exact quote.'},
    ]
}


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', UID)
    monkeypatch.delenv('DREAM_AGENT_FULL_SAMPLES', raising=False)
    return Caps().for_uid(UID)


def edit(before='Borza', after='Borzah'):
    return Edit(
        kind='spelling', target=REF, before=before, after=after, reason='Synthetic term', evidence=[REF + '#first']
    )


def question(source_ref=REF + '#first', quote='Borza', **extra):
    return DreamReviewItem.model_validate(
        {
            'kind': 'spelling',
            'title': 'Which project name?',
            'source_ref': source_ref,
            'quote': quote,
            'spelling': {'term_id': 'synthetic', 'options': ['Borza', 'Borzah'], 'allow_custom': True},
            **extra,
        }
    )


def test_default_samples_and_all_retry_reservations(full, monkeypatch):
    assert full.samples == 3
    assert full.reservation_usd == 6 * 432768 * 0.00001
    assert Caps().for_uid('someone-else').samples == 1
    assert Caps().reservation_usd == 24000 * 0.00001
    monkeypatch.setenv('DREAM_AGENT_FULL_SAMPLES', '2')
    assert Caps().for_uid(UID).samples == 2
    monkeypatch.setenv('DREAM_AGENT_FULL_SAMPLES', '999')
    assert Caps().for_uid(UID).samples == 8


def test_votes_normalize_edits_and_count_once_per_sample():
    term = Term(kind='project', spelling='Borzah', evidence=[REF + '#first'])
    common = edit()
    q = question()
    plans = [
        Plan(edits=[common] * 8 + [edit('Unique', 'Guess')], questions=[q], vocabulary=[term]),
        Plan(edits=[edit(' Borza ', 'Borzah ')], questions=[question(item_id='invented')], vocabulary=[term]),
        Plan(edits=[edit('Different', 'Rewrite')]),
    ]
    sink = {}
    result = majority(plans, usage_sink=sink)
    assert result.edits == [common]
    assert len(result.questions) == len(result.vocabulary) == 1
    assert sink['consensus_threshold'] == 2
    assert sink['rejected'] == {'consensus_rejected': 2}
    assert majority([Plan(edits=[common] * 8), Plan(), Plan()]).edits == []


def test_two_returned_samples_require_both_and_one_requires_one():
    common = edit()
    assert majority([Plan(edits=[common]), Plan()]).edits == []
    assert majority([Plan(edits=[common]), Plan(edits=[common])]).edits == [common]
    assert majority([Plan(edits=[common])]).edits == [common]


@pytest.mark.asyncio
async def test_full_samples_are_concurrent_independent_identical_requests(full):
    all_started = asyncio.Event()
    calls = []

    async def turn(uid, lane, mount, messages):
        index = len(calls)
        calls.append((uid, lane, mount, messages))
        if len(calls) == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), 1)
        return Turn(value=Plan(edits=[edit()] if index < 2 else []), tokens=10)

    sink = {'tokens': 0}
    plan, tokens = await dream_agent.plan_pass(UID, {REF: RECORD}, full, turn=turn, usage_sink=sink)
    assert len(plan.edits) == 1
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    assert all(call[1] == dream_transport.MAIN_LANE for call in calls)
    assert tokens == sink['tokens'] == 30
    assert sink['samples_returned'] == 3 and sink['samples_failed'] == 0
    assert sink['consensus_threshold'] == 2 and not sink['usage_unknown']


@pytest.mark.asyncio
async def test_failed_sample_uses_survivors_and_preserves_partial_usage(full, monkeypatch):
    started = 0

    async def model(uid, lane, mount, messages, *, usage_sink, completion_limit):
        nonlocal started
        index = started
        started += 1
        usage_sink['tokens'] += 7 if index == 0 else 10
        if index == 0:
            usage_sink['usage_unknown'] = True
            raise RuntimeError('synthetic failure')
        usage_sink['usage_unknown'] = False
        return Turn(value=Plan(edits=[edit()]), tokens=10)

    monkeypatch.setattr(dream_transport, 'model_turn', model)
    sink = {'tokens': 0}
    result, tokens = await dream_agent.plan_pass(UID, {REF: RECORD}, full, usage_sink=sink)
    assert len(result.edits) == 1 and tokens == sink['tokens'] == 27
    assert sink['samples_returned'] == 2 and sink['samples_failed'] == 1
    assert sink['consensus_threshold'] == 2 and sink['usage_unknown']


@pytest.mark.asyncio
async def test_all_capacity_failures_wait_and_do_not_claim_usage(full):
    async def turn(*args):
        raise dream_transport.CapacityWait('synthetic')

    sink = {'tokens': 0}
    with pytest.raises(dream_transport.CapacityWait):
        await dream_agent.plan_pass(UID, {REF: RECORD}, full, turn=turn, usage_sink=sink)
    assert sink['samples_failed'] == 3 and sink['samples_returned'] == 0
    assert sink['tokens'] == 0 and not sink['usage_unknown']


@pytest.mark.parametrize('fragment', ['first', '12.5', '00:00:12.5'])
def test_fragment_quote_resolves_only_the_cited_segment(fragment):
    ref = REF + '#' + fragment
    assert base_ref(ref) == REF
    assert cited_value(ref, {REF: RECORD}) == RECORD['transcript_segments'][0]
    records = EvidenceRecords({REF: RECORD})
    records.context_mode = 'full'
    result = dream_guards.filter_plan(Plan(questions=[question(ref)]), records)
    assert len(result.questions) == 1 and result.questions[0].source_ref == ref
    invalid = Plan(questions=[question(ref, 'A different exact quote.')])
    sink = {}
    assert dream_guards.filter_plan(invalid, records, usage_sink=sink).questions == []
    assert sink['rejected'] == {'invalid_question_evidence': 1}


@pytest.mark.parametrize('fragment', ['unknown', '', 'nan', '999', '00:99:00'])
def test_unknown_fragment_never_widens_quote_verification(fragment):
    assert cited_value(REF + '#' + fragment, {REF: RECORD}) is None


def test_edit_citations_keep_fragments_and_unknown_base_is_rejected():
    records = EvidenceRecords({REF: RECORD})
    records.context_mode = 'full'
    item = edit()
    dream_tools.validate_edit(item, records)
    assert dream_guards.filter_plan(Plan(edits=[item]), records).edits[0].evidence == [REF + '#first']
    invalid = item.model_copy(update={'evidence': ['conversations/missing#first']})
    assert dream_guards.filter_plan(Plan(edits=[invalid]), records).edits == []


def test_model_identity_is_overwritten_even_when_missing_or_malformed(monkeypatch):
    now = datetime.now(timezone.utc)
    item = question(item_id='invented-id', created_at='not-a-date')
    assert item.item_id != 'invented-id' and item.item_id.startswith('spelling:')
    assert item.created_at >= now
    captured = []
    monkeypatch.setattr(
        dream_tools.review_store, 'enqueue_review_proposal', lambda uid, item, **kw: captured.append(item)
    )
    dream_tools.ask(
        UID, item.model_copy(update={'item_id': 'forged', 'created_at': datetime(2024, 1, 1)}), {REF: RECORD}
    )
    assert captured[0].item_id != 'forged' and captured[0].created_at >= now
    dream_tools.ask(UID, question(), {REF: RECORD})
    assert captured[0].item_id == captured[1].item_id
    assert captured[0].source_ref == REF + '#first'


def test_consensus_metrics_are_counts_only(caplog):
    before = dream_metrics.REJECTED.labels('consensus_rejected')._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(
            {
                'status': 'complete',
                'samples_requested': 3,
                'samples_returned': 2,
                'samples_failed': 1,
                'consensus_threshold': 2,
                'rejected': {'consensus_rejected': 4},
            }
        )
    assert dream_metrics.REJECTED.labels('consensus_rejected')._value.get() == before + 4
    assert 'samples_requested=3 samples_returned=2 samples_failed=1 consensus_threshold=2' in caplog.text
    assert 'Borza' not in caplog.text


def test_capitalization_votes_preserve_direction():
    forward = edit('borza', 'Borza')
    reverse = edit('Borza', 'borza')
    assert majority([Plan(edits=[forward]), Plan(edits=[reverse]), Plan()]).edits == []
    assert majority([Plan(edits=[forward]), Plan(edits=[forward]), Plan()]).edits == [forward]


@pytest.mark.asyncio
async def test_one_survivor_and_cancellation_preserve_usage(full, monkeypatch):
    count = 0

    async def turn(*args):
        nonlocal count
        count += 1
        if count < 3:
            raise dream_transport.PreTokenFailure('synthetic')
        return Turn(value=Plan(edits=[edit()]), tokens=9)

    sink = {'tokens': 0}
    result, tokens = await dream_agent.plan_pass(UID, {REF: RECORD}, full, turn=turn, usage_sink=sink)
    assert len(result.edits) == 1 and tokens == 9
    assert sink['samples_returned'] == 1 and sink['samples_failed'] == 2 and sink['consensus_threshold'] == 1

    async def cancelled(uid, lane, mount, messages, *, usage_sink, completion_limit):
        usage_sink['tokens'] = 7
        usage_sink['usage_unknown'] = True
        await asyncio.Event().wait()

    monkeypatch.setattr(dream_transport, 'model_turn', cancelled)
    sink = {'tokens': 0}
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.02):
            await dream_agent.plan_pass(UID, {REF: RECORD}, full, usage_sink=sink)
    assert sink['tokens'] == 21 and sink['usage_unknown']
    assert sink['samples_failed'] == 3


def test_fragment_task_provenance_keeps_segment_and_coordinates(monkeypatch):
    captured = []
    monkeypatch.setattr(
        dream_tools, 'get_task_workflow_control', lambda uid: type('Control', (), {'account_generation': 0})()
    )
    monkeypatch.setattr(
        dream_tools.candidates, 'create_candidate', lambda uid, candidate, **kw: captured.append(candidate)
    )
    dream_tools.propose_task(UID, SlowTask(description='Synthetic followup', evidence=[REF + '#first']), {REF: RECORD})
    ref = captured[0].root.evidence_refs[0]
    assert ref.id == 'synthetic' and ref.transcript_segment_ids == ['first']
    assert ref.start_seconds == 12.5 and ref.end_seconds == 14


def test_majority_union_retains_schema_array_caps():
    a = [edit('term' + str(index), 'fixed' + str(index)) for index in range(75)]
    plans = [Plan(edits=a[:50]), Plan(edits=a[25:]), Plan(edits=a[:25] + a[50:])]
    assert len(majority(plans).edits) == 50
