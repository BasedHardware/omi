"""Behavioral dream safety tests; no providers, credentials or customer records."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from config.dream_agent import Caps, eligible
from database import dream_feedback, dream_store, dream_dirty
from models.dream_agent import Feedback, Plan, Edit, Triage, Cluster, Term, FrameQuestion, SlowTask
from utils import dream_agent, dream_tools, dream_transport
from utils.llm import shaped_agent
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'synthetic-owner'
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture
def admission(monkeypatch):
    database = StrictFirestore()
    database.rows[('users', UID)] = {}
    database.rows[('dream_users', UID)] = {'sequence': 2, 'watermark': 0, 'score': 2}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    # Strict fixture validates read-before-write; the production transactional
    # decorator is replaced solely by its invocation over that fixture.
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    return database


def test_scheduler_refuses_overlapping_claim_even_next_day(admission):
    first = dream_store.acquire(UID, Caps(), now=NOW, firestore_client=admission)
    assert first is not None
    assert dream_store.acquire(UID, Caps(), now=NOW, firestore_client=admission) is None
    later = NOW.replace(day=9)
    assert dream_store.acquire(UID, Caps(), now=later, firestore_client=admission) is None
    assert admission.rows[('dream_users', UID)]['passes'] == 1
    assert admission.rows[('dream_spend', NOW.date().isoformat())]['reserved_usd'] == pytest.approx(0.24)


@pytest.mark.parametrize(
    'caps', [Caps(passes=0), Caps(tokens=0), Caps(edits=0), Caps(daily_usd=0.23), Caps(max_usd_per_token=0)]
)
def test_caps_stop_admission_before_any_write(admission, caps):
    before = deepcopy(admission.rows)
    assert dream_store.acquire(UID, caps, now=NOW, firestore_client=admission) is None
    assert admission.rows == before


def test_per_day_pass_cap(admission):
    admission.rows[('dream_users', UID)].update(day='2026-10-08', passes=2)
    assert dream_store.acquire(UID, Caps(), now=NOW, firestore_client=admission) is None


def test_explicit_cohort_and_store_exit(monkeypatch):
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    assert eligible(UID, {})
    assert not eligible('stranger', {'dream_release_channel': 'testflight'})
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'true')
    assert eligible('stranger', {'dream_release_channel': 'testflight'})
    assert not eligible('stranger', {'dream_release_channel': 'app_store'})


def feedback(reproduction='Invented robot examples demonstrate a synthetic failure.'):
    return Feedback(
        component='notes',
        failure_class='spelling',
        severity='warning',
        count=1,
        latency_ms=2,
        error_rate=0.1,
        reproduction=reproduction,
    )


@pytest.mark.parametrize(
    'text', ['ALICE works at Quiet Works', 'Today We Discussed New Launch Plans', 'José ordered robots']
)
def test_feedback_rejects_vocabulary_and_four_word_overlap(text):
    with pytest.raises(ValueError):
        dream_feedback.validate(
            feedback(text),
            {'source': 'Today we discussed new launch plans'},
            [{'spelling': 'Alice'}, {'spelling': 'José'}],
        )


def test_feedback_rejects_overlap_across_fields():
    with pytest.raises(ValueError):
        dream_feedback.validate(feedback('One two three four'), ['One two', 'three four'], [])


def test_feedback_accepts_invented_reproduction():
    dream_feedback.validate(feedback(), {'content': 'Personal meeting information'}, [{'spelling': 'Alice'}])


def test_aggregate_hides_rare_patterns_and_does_not_double_count_salts():
    rows = [{'epoch': 'week1', 'pattern': 'p', 'distinct': str(i), **feedback().model_dump()} for i in range(19)]
    assert dream_feedback.aggregate(rows * 2) == []
    rows.append({'epoch': 'week2', 'pattern': 'p', 'distinct': 'nineteenth-person-new-hash', **feedback().model_dump()})
    assert dream_feedback.aggregate(rows) == []
    rows.append({'epoch': 'week1', 'pattern': 'p', 'distinct': '20', **feedback().model_dump()})
    aggregate = dream_feedback.aggregate(rows)
    assert len(aggregate) == 1 and aggregate[0]['distinct_users'] == 20
    assert 'reproduction' not in aggregate[0] and 'distinct' not in aggregate[0]


@pytest.fixture
def pass_context(monkeypatch):
    lease = {'run_id': 'synthetic-run', 'mode': 'shadow', 'watermark': 0, 'sequence': 1, 'score': 1}
    records = {'conversations/c1': {'id': 'c1', 'structured': {'title': 'Meeting'}}}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: lease)
    monkeypatch.setattr(dream_store, 'assert_lease', lambda *a, **k: None)
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (records, 1))
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_agent.review_changes, 'agent_change_allowed', lambda *a: True)
    saved = []
    monkeypatch.setattr(dream_store, 'finish', lambda *a, **k: saved.append((a, k)))
    return lease, records, saved


def test_shadow_never_invokes_any_effect_and_records_safe_report(monkeypatch, pass_context):
    plan = Plan(
        edits=[
            Edit(
                kind='spelling',
                target='conversations/c1',
                before='Meting',
                after='Meeting',
                reason='Spelling',
                evidence=['conversations/c1'],
            )
        ],
        vocabulary=[Term(kind='jargon', spelling='Widget', evidence=['conversations/c1'])],
        frames=[FrameQuestion(screen_ref='screen/1', question='What image?')],
        slow_tasks=[SlowTask(description='Follow up later', evidence=['conversations/c1'])],
        feedback=[feedback(), feedback('Widget')],
    )
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(plan, 123)))

    def forbidden(*a, **k):
        pytest.fail('shadow executed a mutating tool')

    for fn in ('apply_edit', 'ask', 'request_frame', 'propose_task'):
        monkeypatch.setattr(dream_tools, fn, forbidden)
    monkeypatch.setattr(dream_store, 'save_vocabulary', forbidden)
    monkeypatch.setattr(dream_feedback, 'store', forbidden)
    result = asyncio.run(dream_agent.run_pass(UID))
    assert result['status'] == 'complete'
    assert result['tokens'] == 123
    assert len(result['proposed']['feedback']) == 1
    assert all(outcome['status'] in {'shadow', 'privacy_rejected'} for outcome in result['outcomes'])
    assert pass_context[2][0][1]['success'] is True


def test_undo_markers_and_edit_caps_stop_effects(monkeypatch, pass_context):
    lease, _, _ = pass_context
    lease['mode'] = 'on'
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    edits = [
        Edit(
            kind='spelling',
            target='conversations/c1',
            before=before,
            after='Meeting',
            reason='Spelling',
            evidence=['conversations/c1'],
        )
        for before in ('blocked', 'one', 'two')
    ]
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(Plan(edits=edits), 100)))
    monkeypatch.setattr(
        dream_agent.review_changes, 'agent_change_allowed', lambda uid, key: key != dream_tools.edit_key(edits[0])
    )
    applied = []
    monkeypatch.setattr(dream_tools, 'apply_edit', lambda *a: applied.append(a[1].before) or 'applied')
    result = asyncio.run(dream_agent.run_pass(UID, caps=Caps(edits=1)))
    assert applied == ['one']
    assert [o['status'] for o in result['outcomes']] == ['suppressed', 'applied', 'edit_cap']


def test_demotion_and_kill_switch(monkeypatch, pass_context):
    lease, _, _ = pass_context
    lease['mode'] = 'on'
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    edit = Edit(
        kind='spelling',
        target='conversations/c1',
        before='one',
        after='Meeting',
        reason='Spelling',
        evidence=['conversations/c1'],
    )
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(Plan(edits=[edit]), 1)))
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: {'spelling'})
    assert asyncio.run(dream_agent.run_pass(UID))['outcomes'][0]['status'] == 'suggest_only'
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'off')
    assert asyncio.run(dream_agent.run_pass(UID))['outcomes'][0]['status'] == 'shadow'


def test_empty_triage_never_buys_reasoning():
    lanes = []

    async def turn(uid, lane, mount, messages):
        lanes.append(lane)
        return shaped_agent.Turn(value=Triage(), tokens=123)

    plan, tokens = asyncio.run(dream_agent.plan_pass(UID, {}, Caps(), turn=turn))
    assert plan == Plan() and tokens == 123 and lanes == [dream_transport.TRIAGE_LANE]


def test_two_stage_clusters_and_combined_budget():
    seen = []

    async def turn(uid, lane, mount, messages):
        seen.append((lane, mount.budget.tokens, messages))
        value = Triage(clusters=[Cluster(refs=['conversations/c1'], problem='spelling')]) if len(seen) == 1 else Plan()
        return shaped_agent.Turn(value=value, tokens=100)

    asyncio.run(
        dream_agent.plan_pass(
            UID,
            {'conversations/c1': {'text': 'Evidence'}, 'memory_items/m1': {'content': 'irrelevant'}},
            Caps(),
            turn=turn,
        )
    )
    assert seen[1][1] == 23900
    assert 'irrelevant' not in str(seen[1][2])


def test_harness_token_budget_prevents_tool_effect():
    async def turn(mount, messages):
        return shaped_agent.Turn(tool_calls=('write',), tokens=100)

    execute = AsyncMock()
    result = asyncio.run(
        shaped_agent.run_loop(
            shaped_agent.Mount(tools=('write',), budget=shaped_agent.Budget(turns=2, tool_calls=2, tokens=100)),
            [],
            turn,
            execute,
        )
    )
    assert result.reason == 'token_budget'
    execute.assert_not_called()


def test_dirty_hook_uses_created_task_id_and_suppresses_dream_writes(monkeypatch):
    calls = []
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_dirty, 'mark_dirty', lambda *a: calls.append(a))
    fn = dream_dirty.after_write('action_items')(lambda uid, data: 'generated-task')
    fn(UID, {'description': 'Something'})
    assert calls == [(UID, [('action_items', 'generated-task')])]
    token = dream_dirty.dream_writing.set(True)
    try:
        fn(UID, {})
    finally:
        dream_dirty.dream_writing.reset(token)
    assert len(calls) == 1
