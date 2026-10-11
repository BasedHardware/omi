"""Behavioral dream safety tests; no providers, credentials or customer records."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from config.dream_agent import Caps, eligible
from database import dream_feedback, dream_store, dream_dirty
from models.dream_agent import Feedback, Plan, Edit, Triage, Cluster, Term, FrameQuestion, SlowTask
from utils import dream_agent, dream_tools, dream_transport, dream_prompt
from utils.llm import shaped_agent
from tests.support.dream_firestore import DreamFirestore

UID = 'synthetic-owner'
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


@pytest.fixture
def admission(monkeypatch):
    database = DreamFirestore()
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
    monkeypatch.delenv('DREAM_AGENT_TESTFLIGHT_MIN_BUILD', raising=False)
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    assert eligible(UID, {})
    assert not eligible('stranger', {'dream_release_channel': 'testflight'})
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'true')
    assert not eligible('stranger', {'dream_release_channel': 'testflight', 'dream_app_build': 300})
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_MIN_BUILD', '300')
    assert eligible('stranger', {'dream_release_channel': 'testflight', 'dream_app_build': 300})
    assert not eligible('stranger', {'dream_release_channel': 'testflight', 'dream_app_build': 299})
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


@pytest.mark.parametrize('reproduction', ['Mira', 'mIrA!'])
def test_feedback_rejects_unlisted_name_from_nested_transcript(reproduction):
    inputs = {
        'conversations/c1': {
            'transcript_segments': [{'text': 'Mira will send the proposal.'}],
        }
    }
    with pytest.raises(ValueError, match='feedback_vocabulary_overlap'):
        dream_feedback.validate(feedback(reproduction), inputs, [])


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
    lease = {'run_id': 'synthetic-run', 'mode': 'shadow', 'watermark': dream_store.EPOCH, 'score': 1}
    records = {'conversations/c1': {'id': 'c1', 'structured': {'title': 'Meeting'}}}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setattr(dream_store, 'acquire', lambda *a, **k: lease)
    monkeypatch.setattr(dream_store, 'assert_lease', lambda *a, **k: None)
    monkeypatch.setattr(dream_agent.dream_reads, 'read_changes', lambda *a: (records, []))
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


def test_completed_watermark_preserves_arrivals_and_encrypts_report(admission):
    lease = dream_store.acquire(UID, Caps(), now=NOW, firestore_client=admission)
    state = admission.rows[('dream_users', UID)]
    state.update(score=4)
    from datetime import timedelta

    consumed = [{'version': 'read-version', 'last_changed_at': NOW}]
    state_path = ('dream_users', UID, 'dirty')
    admission.rows[(*state_path, 'read')] = {'version': 'read-version', 'last_changed_at': NOW}
    admission.rows[(*state_path, 'arrival')] = {
        'version': 'arrival-version',
        'last_changed_at': NOW + timedelta(seconds=1),
    }
    dream_store.finish(
        UID,
        lease,
        {'proposed': {'private': 'synthetic text'}},
        success=True,
        consumed=consumed,
        firestore_client=admission,
    )
    state = admission.rows[('dream_users', UID)]
    assert state['watermark'] == NOW and state['score'] == 4
    assert (*state_path, 'read') not in admission.rows
    assert (*state_path, 'arrival') in admission.rows
    assert state['lease'] is None
    report = admission.rows[('users', UID, 'dream_runs', lease['run_id'])]
    assert 'review_encrypted_v1' in report['source']
    assert 'synthetic text' not in str(report)


def test_timeout_retains_lease_and_spend_reservation(admission):
    lease = dream_store.acquire(UID, Caps(), now=NOW, firestore_client=admission)
    dream_store.finish(UID, lease, {'status': 'failed'}, success=False, release=False, firestore_client=admission)
    assert admission.rows[('dream_users', UID)]['lease'] == lease
    assert admission.rows[('dream_users', UID)]['watermark'] == dream_store.EPOCH
    assert admission.rows[('dream_spend', NOW.date().isoformat())]['reserved_usd'] == pytest.approx(0.24)


def test_dirty_notification_supports_keyword_only_invocations(monkeypatch):
    captured = []
    monkeypatch.setenv('DREAM_AGENT_MODE', 'on')
    monkeypatch.setattr(dream_dirty, 'mark_dirty', lambda *args: captured.append(args))
    fn = dream_dirty.after_write('action_items')(lambda uid, action_item_data: 'new-id')
    assert fn(uid=UID, action_item_data={'description': 'Synthetic'}) == 'new-id'
    assert captured == [(UID, [('action_items', 'new-id')])]


def test_feedback_storage_has_no_uid_and_rotates_distinct_hash(monkeypatch):
    from types import SimpleNamespace

    stored = []
    document = SimpleNamespace(set=lambda row: stored.append(row))
    database = SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: document))
    monkeypatch.setenv('DREAM_AGENT_FEEDBACK_SALT', 'synthetic-secret-with-at-least-32-characters')
    for day in (8, 8, 15):
        dream_feedback.store(
            UID, feedback(), {'text': 'source material'}, [], now=NOW.replace(day=day), firestore_client=database
        )
    assert all(UID not in str(row) for row in stored)
    assert stored[0]['distinct'] == stored[1]['distinct']
    assert stored[0]['distinct'] != stored[2]['distinct']


def test_excerpts_keep_transcript_evidence_when_summary_is_large():
    excerpt = dream_prompt.excerpts(
        {
            'conversations/c1': {
                'structured': {'title': 'x' * 10000},
                'transcript_segments': [{'text': 'Synthetic misspelled name'}],
            }
        },
        chars=160,
    )['conversations/c1']
    assert 'Synthetic misspelled name' in excerpt


def test_large_input_stops_before_gateway_access(monkeypatch):
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **kw: pytest.fail('gateway accessed'))
    with pytest.raises(ValueError, match='dream_input_token_budget'):
        asyncio.run(
            dream_transport.model_turn(
                UID,
                dream_transport.MAIN_LANE,
                dream_prompt.mount(Plan, 100),
                [{'role': 'user', 'content': 'x' * 10000}],
            )
        )


def test_evidence_shrinks_to_the_triage_budget():
    oversized = {f'screen/{i}': {'ocr_text': 'Synthetic screen words ' * 100} for i in range(50)}
    with pytest.raises(ValueError, match='dream_evidence_token_budget'):
        dream_prompt.evidence_message(oversized, Triage, 6000)
    records = dict(list(oversized.items())[:4])
    messages = dream_prompt.evidence_message(records, Triage, 6000)
    assert len(__import__('json').loads(messages[0]['content'])['records']) == 4
    framed = dream_prompt.mount(Triage, 6000, dream_prompt.TRIAGE_INSTRUCTIONS).messages(messages)
    assert dream_transport.input_ceiling(framed, Triage.model_json_schema()) + 768 <= 6000


def test_canonical_dirty_hook_uses_committed_id_when_input_has_no_id(monkeypatch):
    calls = []
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setattr(dream_dirty, 'mark_dirty', lambda *a: calls.append(a))
    writer = dream_dirty.after_write('memory_items')(lambda uid, data: 'canonical-generated-id')
    writer(uid=UID, data={'content': 'Synthetic new memory'})
    assert calls == [(UID, [('memory_items', 'canonical-generated-id')])]


@pytest.mark.parametrize('kind', ['title', 'overview'])
def test_summary_proposals_are_shadow_only(monkeypatch, pass_context, kind):
    records = pass_context[1]
    records['conversations/c1'] = {
        'id': 'c1',
        'structured': {'title': '', 'overview': ''},
        'transcript_segments': [{'text': 'We will build a toy boat. ' * 7}],
    }
    edit = Edit(
        kind=kind,
        target='conversations/c1',
        before='',
        after=(
            'Building a toy boat' if kind == 'title' else '## Toy boat\n\n- We will build and test a toy boat tomorrow.'
        ),
        reason='Missing heading',
        evidence=['conversations/c1'],
    )
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(Plan(edits=[edit]), 100)))
    monkeypatch.setattr(dream_tools, 'apply_edit', lambda *a: pytest.fail('shadow mutated conversation'))
    result = asyncio.run(dream_agent.run_pass(UID))
    assert result['status'] == 'complete'
    assert result['proposed']['edits'] == [edit.model_dump()]
    assert result['outcomes'][0]['status'] == 'shadow'


def test_feedback_record_ref_is_removed_before_shadow_persistence(monkeypatch, pass_context):
    plan = Plan(feedback=[feedback('The defect affects conversations/c1.')])
    monkeypatch.setattr(dream_agent, 'plan_pass', AsyncMock(return_value=(plan, 100)))
    result = asyncio.run(dream_agent.run_pass(UID))
    assert result['proposed']['feedback'] == []
    assert result['outcomes'] == [{'tool': 'feedback', 'status': 'privacy_rejected'}]
