"""Rung 1.2: independent samples, exact fragment citations and server identity."""

import asyncio
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock

from config.dream_agent import Caps
from models.dream_agent import DreamReviewItem, Plan, SlowTask
from models.dream_edit import Edit, Term
from models.dream_refs import base_ref, cited_value
from utils import dream_agent, dream_capacity, dream_guards, dream_metrics, dream_tools, dream_transport
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


class ManualClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture(autouse=True)
def isolated_capacity(monkeypatch):
    # Patch the lazy state seam rather than clearing another test's cached state.
    local = dream_capacity.LocalCapacity()
    monkeypatch.setattr(dream_capacity, '_local', lambda: local)
    return local


@pytest.fixture
def full(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_CONTEXT_MODE', 'full')
    monkeypatch.setenv('DREAM_AGENT_FULL_CONTEXT_UIDS', UID)
    monkeypatch.delenv('DREAM_AGENT_FULL_SAMPLES', raising=False)
    monkeypatch.setattr(dream_agent.dream_capacity, 'wait_for_capacity', AsyncMock(return_value=False))
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
    assert [item.model_dump() for item in result.edits] == [common.model_dump()]
    assert result.edits[0].agreement == 2 and result.edits[0].samples == 3
    assert result.questions[0].agreement == result.vocabulary[0].agreement == 2
    assert len(result.questions) == len(result.vocabulary) == 1
    assert sink['consensus_threshold'] == 2
    assert sink['rejected'] == {'consensus_rejected': 2}
    assert majority([Plan(edits=[common] * 8), Plan(), Plan()]).edits == []


def test_two_returned_samples_require_both_and_one_requires_one():
    common = edit()
    assert majority([Plan(edits=[common]), Plan()]).edits == []
    assert majority([Plan(edits=[common]), Plan(edits=[common])]).edits[0].agreement == 2
    assert majority([Plan(edits=[common])]).edits[0].agreement == 1


@pytest.mark.asyncio
async def test_full_samples_are_sequential_independent_identical_requests(full):
    calls = []
    active = 0

    async def turn(uid, lane, mount, messages):
        nonlocal active
        assert active == 0
        active += 1
        index = len(calls)
        calls.append((uid, lane, mount, messages))
        await asyncio.sleep(0)
        active -= 1
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
    assert (
        majority([Plan(edits=[forward]), Plan(edits=[forward]), Plan()]).edits[0].model_dump() == forward.model_dump()
    )


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
    assert sink['tokens'] == 7 and sink['usage_unknown']
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


@pytest.mark.asyncio
async def test_capacity_retry_is_same_sample_and_does_not_add_a_vote(full, monkeypatch):
    wait = AsyncMock(return_value=True)
    monkeypatch.setattr(dream_agent.dream_capacity, 'wait_for_capacity', wait)
    calls = 0

    async def turn(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise dream_transport.CapacityWait('dream_capacity_wait')
        return Turn(value=Plan(edits=[edit()]), tokens=10)

    sink = {'tokens': 0}
    result, tokens = await dream_agent.plan_pass(UID, {REF: RECORD}, full, turn=turn, usage_sink=sink)
    assert calls == 4 and wait.await_count == 1
    assert len(result.edits) == 1 and tokens == sink['tokens'] == 30
    assert sink['samples_returned'] == 3 and sink['consensus_threshold'] == 2
    assert sink['capacity_retries'] == 1 and sink['samples_capacity_wait'] == 1
    assert not sink['usage_unknown']


@pytest.mark.asyncio
async def test_capacity_retry_exhaustion_still_uses_the_one_survivor(full, monkeypatch):
    monkeypatch.setattr(dream_agent.dream_capacity, 'wait_for_capacity', AsyncMock(return_value=True))
    calls = 0

    async def turn(*args):
        nonlocal calls
        calls += 1
        if calls <= 4:
            raise dream_transport.CapacityWait('dream_capacity_wait')
        return Turn(value=Plan(edits=[edit()]), tokens=10)

    sink = {'tokens': 0}
    result, tokens = await dream_agent.plan_pass(UID, {REF: RECORD}, full, turn=turn, usage_sink=sink)
    assert calls == 5 and len(result.edits) == 1 and tokens == 10
    assert sink['samples_returned'] == 1 and sink['samples_failed'] == 2 and sink['consensus_threshold'] == 1
    assert sink['capacity_retries'] == 2 and not sink['usage_unknown']


@pytest.mark.asyncio
@pytest.mark.parametrize('headroom', [480.0, 480.01])
async def test_remaining_deadline_keeps_returned_sample_without_starting_another(
    full, clock, isolated_capacity, monkeypatch, headroom
):
    calls = 0
    # Even a saturated reservation must not affect a provider-free fake turn.
    isolated_capacity.cooldowns['gemini-2.5-flash'] = float('inf')
    available = AsyncMock(side_effect=AssertionError('fake turn consulted provider capacity'))
    monkeypatch.setattr(dream_capacity, 'available_model', available)

    async def turn(*args):
        nonlocal calls
        calls += 1
        clock.advance(0.02)
        return Turn(value=Plan(edits=[edit()]), tokens=10)

    sink = {'tokens': 0}
    result, tokens = await dream_agent.plan_pass(
        UID, {REF: RECORD}, full, turn=turn, usage_sink=sink, deadline=clock() + headroom, clock=clock
    )
    assert calls == 1 and len(result.edits) == 1 and tokens == 10
    assert sink['samples_requested'] == 3 and sink['samples_attempted'] == 1 and sink['samples_returned'] == 1
    available.assert_not_awaited()
    dream_capacity.wait_for_capacity.assert_not_awaited()
    assert sink['consensus_threshold'] == 1 and not sink['usage_unknown']


@pytest.mark.asyncio
async def test_cooldown_wait_honors_deadline_and_rechecks_capacity(monkeypatch, clock):
    from utils import dream_capacity

    slept = AsyncMock(side_effect=clock.advance)
    available = AsyncMock(return_value='reserved')
    monkeypatch.setattr(dream_capacity.asyncio, 'sleep', slept)
    monkeypatch.setattr(dream_capacity, 'available_model', available)
    now = clock()
    assert not await dream_capacity.wait_for_capacity(now + 599, 480, clock=clock)
    assert slept.await_count == available.await_count == 0
    assert await dream_capacity.wait_for_capacity(now + 700, 480, clock=clock)
    slept.assert_awaited_once_with(120)
    assert clock() == now + 120
    # A second cooldown no longer fits the original deadline.
    assert not await dream_capacity.wait_for_capacity(now + 700, 480, clock=clock)
    assert slept.await_count == available.await_count == 1
    available.return_value = None
    assert not await dream_capacity.wait_for_capacity(clock() + 700, 480, clock=clock)
    assert slept.await_count == available.await_count == 2


@pytest.mark.parametrize(
    'message,code',
    [
        ('dream_settlement_limit', 'dream_settlement_limit'),
        ('dream_reasoning_budget', 'dream_reasoning_budget'),
        ('dream_private transcript words', None),
        ('private provider response', None),
    ],
)
def test_error_codes_only_log_exact_owned_values(message, code, caplog):
    assert dream_metrics.error_code(ValueError(message)) == code
    assert dream_metrics.error_code(RuntimeError(message)) is None
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(
            {
                'status': 'failed',
                'error_type': 'ValueError',
                'error_code': message,
                'context_mode': 'full',
                'samples_requested': 3,
                'samples_returned': 1,
                'samples_failed': 2,
            }
        )
    assert 'error_code=' + (code or 'none') in caplog.text
    if code is None:
        assert message not in caplog.text


@pytest.mark.parametrize('fragment', ['first', '12.5', '00:00:12.5'])
def test_fragment_target_and_evidence_validate_by_base_but_keep_scope(fragment):
    from utils import dream_grounding

    records = EvidenceRecords(
        {
            REF: RECORD,
            'conversations/independent': {'transcript_segments': [{'id': 'support', 'text': 'Borzah is our project.'}]},
        }
    )
    records.context_mode = 'full'
    item = edit().model_copy(update={'target': REF + '#' + fragment, 'evidence': ['conversations/independent#support']})
    dream_tools.validate_edit(item, records)
    result = dream_guards.filter_plan(Plan(edits=[item]), records)
    assert result.edits == [item]
    assert dream_grounding.spelling_grounding_rejection(item, records) is None
    unsupported = item.model_copy(update={'evidence': [REF + '#second']})
    same_conversation = {
        REF: {'transcript_segments': [RECORD['transcript_segments'][0], {'id': 'second', 'text': 'Borzah'}]}
    }
    assert dream_grounding.spelling_grounding_rejection(unsupported, same_conversation) == 'ungrounded_spelling'
    unknown = item.model_copy(update={'target': 'conversations/missing#' + fragment})
    assert dream_guards.filter_plan(Plan(edits=[unknown]), records).edits == []
    wrong = item.model_copy(update={'target': REF + '#second'})
    assert dream_guards.filter_plan(Plan(edits=[wrong]), records).edits == []


@pytest.mark.asyncio
async def test_capacity_retry_carries_known_prior_usage_into_same_sample_budget(full, monkeypatch):
    monkeypatch.setattr(dream_agent.dream_capacity, 'wait_for_capacity', AsyncMock(return_value=True))
    budgets = []

    async def model(uid, lane, mount, messages, *, usage_sink, completion_limit):
        budgets.append(mount.budget.tokens)
        if len(budgets) == 1:
            usage_sink['tokens'] += 100
            usage_sink['usage_unknown'] = False
            raise dream_transport.CapacityWait('dream_capacity_wait')
        usage_sink['tokens'] += 10
        usage_sink['usage_unknown'] = False
        return Turn(value=Plan(), tokens=10)

    monkeypatch.setattr(dream_transport, 'model_turn', model)
    sink = {'tokens': 0}
    await dream_agent.plan_pass(UID, {REF: RECORD}, full, usage_sink=sink)
    assert budgets == [2 * full.tokens, 2 * full.tokens - 100, 2 * full.tokens, 2 * full.tokens]
    assert sink['tokens'] == 130 and not sink['usage_unknown']
