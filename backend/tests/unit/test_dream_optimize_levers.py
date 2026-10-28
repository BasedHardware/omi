"""Dream efficiency levers, structured telemetry and defect reports fail open."""

import asyncio
import json
import logging
import uuid
from copy import deepcopy

import pytest

from config import dream_levers
from config.dream_session import HEAVY_TOKENS, LIGHT_TOKENS, MEDIUM_TOKENS, SessionLimits
from database import dream_feedback
from models.agent_tools import DEFECT_TOOL, ReportDefect, tool_schemas
from tests.unit.test_dream_cleanup_edits import records, UID
from tests.unit.test_dream_harness_runtime import runtime, store  # noqa: F401  (fixtures)
from tests.unit.test_dream_session import call
from utils import dream_agent, dream_seed, dream_telemetry
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.guards import feedback_rejection
from utils.agent_capabilities.session import Session
from utils.dream_harness_transport import MAIN_LANE
from utils.llm.shaped_agent import LoopStop, Turn

# --- lever arms ---------------------------------------------------------------------------------


def test_levers_default_to_shadow_and_serve_only_a_cohort(monkeypatch):
    for name in dream_levers.PER_OWNER:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + '_SERVE_PERCENT', raising=False)
    assert set(dream_levers.arms('owner-a').values()) == {'shadow'}
    monkeypatch.setenv(dream_levers.IDLE_SKIP_SERVE_PERCENT_ENV, '100')
    assert dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, 'owner-a') == 'serve'
    monkeypatch.setenv(dream_levers.IDLE_SKIP_SERVE_PERCENT_ENV, '0')
    assert dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, 'owner-a') == 'shadow'
    monkeypatch.setenv(dream_levers.IDLE_SKIP_MODE_ENV, 'off')
    assert dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, 'owner-a') == 'off'
    monkeypatch.setenv(dream_levers.IDLE_SKIP_MODE_ENV, 'serve')
    assert dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, 'owner-a') == 'serve'


def test_lever_cohorts_are_salted_per_lever(monkeypatch):
    monkeypatch.setenv(dream_levers.IDLE_SKIP_SERVE_PERCENT_ENV, '50')
    monkeypatch.setenv(dream_levers.MATERIAL_BUDGET_SERVE_PERCENT_ENV, '50')
    owners = [f'owner-{index}' for index in range(400)]
    idle = {uid for uid in owners if dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, uid) == 'serve'}
    budget = {uid for uid in owners if dream_levers.arm(dream_levers.MATERIAL_BUDGET_MODE_ENV, uid) == 'serve'}
    assert 120 < len(idle) < 280 and 120 < len(budget) < 280
    assert idle != budget


def test_lever_errors_fail_open_to_off(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('parse')

    monkeypatch.setattr(dream_levers.refactor_modes, 'mode', broken)
    assert dream_levers.arm(dream_levers.NO_PROGRESS_STOP_MODE_ENV, 'owner-a') == 'off'
    assert dream_levers.arm(dream_levers.PAYOFF_ORDER_MODE_ENV, None) == 'off'


def test_payoff_order_is_global_mode_only(monkeypatch):
    monkeypatch.setenv(dream_levers.PAYOFF_ORDER_MODE_ENV, 'serve')
    assert dream_levers.arm(dream_levers.PAYOFF_ORDER_MODE_ENV, None) == 'serve'
    monkeypatch.delenv(dream_levers.PAYOFF_ORDER_MODE_ENV)
    assert dream_levers.arm(dream_levers.PAYOFF_ORDER_MODE_ENV, None) == 'shadow'


def test_material_budget_never_raises_the_ceiling():
    assert dream_agent.material_tokens(0, HEAVY_TOKENS) == LIGHT_TOKENS
    assert dream_agent.material_tokens(4, HEAVY_TOKENS) == LIGHT_TOKENS
    assert dream_agent.material_tokens(5, HEAVY_TOKENS) == MEDIUM_TOKENS
    assert dream_agent.material_tokens(16, HEAVY_TOKENS) == HEAVY_TOKENS
    assert dream_agent.material_tokens(40, MEDIUM_TOKENS) == MEDIUM_TOKENS
    assert dream_agent.material_tokens(0, 20000) == 20000


# --- telemetry ----------------------------------------------------------------------------------


def _pass_report(**extra):
    run_id = str(uuid.uuid4())
    return {
        'status': 'complete',
        'run_id': run_id,
        'trigger': 'schedule',
        'stop_reason': 'deadline',
        'size_bucket': 'heavy',
        'tokens': 1200,
        'price_weighted_tokens': 900,
        'outcomes': [
            {'key': 'k1', 'kind': 'retire_memory', 'status': 'applied'},
            {'key': 'k2', 'kind': 'spelling', 'status': 'verifier_disagree'},
        ],
        'timing': {'wait_ms': 1500, 'waits': 2},
        'levers': {'idle_skip': {'arm': 'shadow', 'would_skip': True}},
        'defect_reports': {'attempt': 1, 'rejected_feedback_input_overlap': 1},
        **extra,
    }


def test_pass_record_carries_counts_and_never_free_text(caplog):
    report = _pass_report(
        reason='owner jane@example.com said hello',
        error_type='Traceback (most recent call last)',
        stop_reason='users/abc123/conversations/xyz',
    )
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_telemetry.record_pass(report)
    payload = json.loads(caplog.records[-1].getMessage())
    assert payload['event'] == 'dream_pass'
    assert payload['run_id'] == report['run_id']
    assert payload['reason'] == 'other' and payload['error_type'] == 'other' and payload['stop_reason'] == 'other'
    assert payload['applied'] == {'retire_memory': 1}
    assert payload['outcomes'] == {'applied': 1, 'verifier_disagree': 1}
    assert payload['wait_ms'] == 1500 and payload['levers']['idle_skip'] == {'arm': 'shadow', 'would_skip': True}
    assert 'jane' not in caplog.text and 'abc123' not in caplog.text


def test_pass_record_rejects_non_uuid_ids(caplog):
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_telemetry.record_pass(_pass_report(run_id='synthetic-owner-uid'))
    payload = json.loads(caplog.records[-1].getMessage())
    assert payload['run_id'] == 'none'
    assert 'synthetic-owner-uid' not in caplog.text


def test_pass_record_inherits_the_sweep_id(caplog):
    sweep_id = str(uuid.uuid4())
    token = dream_telemetry.SWEEP_ID.set(sweep_id)
    try:
        with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
            dream_telemetry.record_pass(_pass_report())
    finally:
        dream_telemetry.SWEEP_ID.reset(token)
    assert json.loads(caplog.records[-1].getMessage())['sweep_id'] == sweep_id


def test_telemetry_kill_switch_and_errors_never_raise(monkeypatch, caplog):
    monkeypatch.setenv('DREAM_TELEMETRY_V2_ENABLED', 'false')
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_telemetry.record_pass(_pass_report())
        dream_telemetry.record_sweep({}, [])
    assert not [r for r in caplog.records if r.getMessage().startswith('{')]
    monkeypatch.delenv('DREAM_TELEMETRY_V2_ENABLED')

    def broken(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(dream_telemetry, 'pass_payload', broken)
    monkeypatch.setattr(dream_telemetry, 'sweep_payload', broken)
    dream_telemetry.record_pass({'status': 'complete'})
    dream_telemetry.record_sweep({}, [])


def test_sweep_record_counts_owners_not_retry_attempts(caplog):
    done = {'status': 'complete', 'outcomes': [{'status': 'applied', 'kind': 'spelling'}], 'tokens': 10}
    idle = {'status': 'not_admitted', 'reason': 'idle_no_material'}
    starved = {'status': 'waiting', 'reason': 'reserved_capacity'}
    reports = [
        {'status': 'waiting', 'reason': 'reserved_capacity'},
        {'status': 'waiting', 'reason': 'reserved_capacity'},
        done,
        idle,
        starved,
    ]
    sweep = {
        'sweep_id': str(uuid.uuid4()),
        'caller': 'scheduler',
        'scheduled_at': '2026-10-28T09:00:00Z',
        'due_owners': 5,
        'owners_started': 3,
        'owners_unreached': 2,
        'finals': [done, idle, starved],
    }
    with caplog.at_level(logging.INFO, logger='utils.dream_telemetry'):
        dream_telemetry.record_sweep(sweep, reports)
    payload = json.loads(caplog.records[-1].getMessage())
    assert payload['attempts'] == 5
    assert payload['final_status'] == {'complete': 1, 'not_admitted': 1, 'waiting': 1}
    assert payload['not_admitted'] == {'idle_no_material': 1}
    assert payload['waiting_attempts'] == {'reserved_capacity': 3}
    assert payload['applied'] == 1 and payload['owners_unreached'] == 2
    assert payload['scheduled_at'] == '2026-10-28T09:00:00+00:00'


# --- defect reports -----------------------------------------------------------------------------


def _defect(text, **extra):
    return ReportDefect(component='dream', failure_class='routing', severity='warning', reproduction=text, **extra)


def test_report_defect_is_offered_only_to_dream_with_a_sink():
    assert DEFECT_TOOL not in {tool['function']['name'] for tool in tool_schemas(authority='dream')}
    assert DEFECT_TOOL not in {tool['function']['name'] for tool in tool_schemas(authority='user', defect_reports=True)}
    assert DEFECT_TOOL in {tool['function']['name'] for tool in tool_schemas(authority='dream', defect_reports=True)}


def _session(**fields):
    return Session(
        'synthetic-owner',
        object(),
        SessionLimits(),
        {'targets': [], 'vocabulary': []},
        authority='dream',
        **fields,
    )


def test_defect_tool_is_unknown_without_a_sink():
    session = _session()
    responses = asyncio.run(
        session.execute(
            [
                call(
                    DEFECT_TOOL,
                    {'component': 'dream', 'failure_class': 'routing', 'severity': 'warning', 'reproduction': 'x'},
                )
            ]
        )
    )
    assert session.rejections['agent_unknown_tool'] == 1
    assert 'agent_unknown_tool' in responses[0]['content']


def test_defect_tool_routes_to_the_sink():
    seen = []

    async def sink(item):
        seen.append(item)
        return {'status': 'recorded'}

    session = _session(defect_sink=sink)
    responses = asyncio.run(
        session.execute(
            [
                call(
                    DEFECT_TOOL,
                    {
                        'component': 'dream',
                        'failure_class': 'routing',
                        'severity': 'warning',
                        'reproduction': 'search returned stale page cursor',
                    },
                )
            ]
        )
    )
    assert isinstance(seen[0], ReportDefect) and seen[0].count == 1
    assert '"recorded"' in responses[0]['content']
    assert session.counters['tool:report_defect'] == 1


def test_after_execute_can_end_the_loop_without_finish():
    async def stop(current):
        return True

    session = _session(after_execute=stop)
    result = asyncio.run(session.execute([call('read', {'refs': ['conversations/unknown']})]))
    assert isinstance(result, LoopStop) and result.value is None and session.finish is None


def test_looser_privacy_gate():
    inputs = {
        'records': {
            'conversations/conv-alpha-123': {
                'title': 'Jane Smith planning call',
                'status': 'completed',
                'transcript': 'we agreed to ship the robot arm prototype next tuesday after lunch with the team',
            }
        }
    }
    # Short field labels and single capitalized words no longer block a generic report.
    dream_feedback.validate(_defect('read of completed conversation returned empty transcript segments'), inputs, [])
    dream_feedback.validate(_defect('Search returned no results for a Planning query'), inputs, [])
    # Multi-word names, explicit vocabulary and 8-word verbatim spans still block.
    with pytest.raises(ValueError, match='feedback_vocabulary_overlap'):
        dream_feedback.validate(_defect('summary for jane smith was wrong'), inputs, [])
    with pytest.raises(ValueError, match='feedback_vocabulary_overlap'):
        dream_feedback.validate(_defect('term zorblax was misspelled'), inputs, ['Zorblax'])
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(_defect('saw: agreed to ship the robot arm prototype next tuesday'), inputs, [])
    # Language words in fixed category fields no longer reject; in free text they still do.
    assert feedback_rejection(_defect('cursor reused across collections')) is None
    assert feedback_rejection(_defect('translation of english summary failed')) == 'language_not_defect'


# --- pass-level levers (scripted model, dry run) ------------------------------------------------


def _scripted(owner_records, limits, monkeypatch):
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )


def test_history_compaction_serve_elides_old_tool_results(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.HISTORY_COMPACT_MODE_ENV, 'serve')
    monkeypatch.setenv('DREAM_HISTORY_COMPACT_TRIGGER_TOKENS', '1000')
    monkeypatch.setenv('DREAM_HISTORY_COMPACT_KEEP_RESULTS', '2')
    monkeypatch.setattr(dream_agent, 'COMPACT_MIN_CHARS', 10)
    limits = SessionLimits(bucket='light', turns=16, tools=16, read_bytes=640000, read_call_bytes=64000, tokens=900000)
    owner_records = EvidenceRecords(records(runtime))
    _scripted(owner_records, limits, monkeypatch)
    seen = []

    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        step = len(seen) + 1
        seen.append(deepcopy(messages))
        tool_call = (
            call('read', {'refs': ['conversations/one']}, index=step)
            if step <= 6
            else call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, index=step)
        )
        return Turn(
            tokens=5000,
            prompt_tokens=5000,
            completion_tokens=0,
            cached_tokens=0,
            tool_calls=(tool_call,),
            messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert report['status'] == 'complete', report
    final = seen[-1]
    tools = [message for message in final if message.get('role') == 'tool']
    elided = [message for message in tools if message['content'] == dream_agent.ELIDED_TOOL_RESULT]
    assert elided and tools[-1]['content'] != dream_agent.ELIDED_TOOL_RESULT
    assert len(tools) - len(elided) >= 2
    # Seed and system prompt are untouched.
    assert final[:2] == seen[0][:2]
    compaction = report['levers']['history_compact']
    assert compaction['arm'] == 'serve' and compaction['compactions'] >= 1 and compaction['elided_chars'] > 0


def test_history_compaction_shadow_changes_nothing(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.HISTORY_COMPACT_MODE_ENV, 'shadow')
    monkeypatch.setenv('DREAM_HISTORY_COMPACT_TRIGGER_TOKENS', '1000')
    monkeypatch.setenv('DREAM_HISTORY_COMPACT_KEEP_RESULTS', '2')
    monkeypatch.setattr(dream_agent, 'COMPACT_MIN_CHARS', 10)
    limits = SessionLimits(bucket='light', turns=16, tools=16, read_bytes=640000, read_call_bytes=64000, tokens=900000)
    owner_records = EvidenceRecords(records(runtime))
    _scripted(owner_records, limits, monkeypatch)
    seen = []

    async def model(uid, lane, mount, messages):
        step = len(seen) + 1
        seen.append(deepcopy(messages))
        tool_call = (
            call('read', {'refs': ['conversations/one']}, index=step)
            if step <= 6
            else call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, index=step)
        )
        return Turn(
            tokens=5000,
            prompt_tokens=5000,
            completion_tokens=0,
            cached_tokens=0,
            tool_calls=(tool_call,),
            messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    assert all(message.get('content') != dream_agent.ELIDED_TOOL_RESULT for message in seen[-1])
    compaction = report['levers']['history_compact']
    assert compaction['fired'] and compaction['compactions'] == 0 and compaction['would_elide_chars'] > 0


def _idle_reader(count):
    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        count.append(1)
        step = len(count)
        tool_call = (
            call('read', {'refs': ['conversations/one']}, index=step)
            if step <= 12
            else call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, index=step)
        )
        return Turn(
            tokens=20000,
            prompt_tokens=20000,
            completion_tokens=0,
            cached_tokens=0,
            tool_calls=(tool_call,),
            messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
        )

    return model


@pytest.mark.parametrize('arm', ['shadow', 'serve'])
def test_no_progress_stop(runtime, monkeypatch, arm):
    monkeypatch.setenv(dream_levers.NO_PROGRESS_STOP_MODE_ENV, arm)
    monkeypatch.setenv('DREAM_NO_PROGRESS_BATCHES', '3')
    monkeypatch.setenv('DREAM_NO_PROGRESS_MIN_TOKEN_SHARE', '0.1')
    limits = SessionLimits(bucket='light', turns=32, tools=32, read_bytes=640000, read_call_bytes=64000, tokens=400000)
    owner_records = EvidenceRecords(records(runtime))
    _scripted(owner_records, limits, monkeypatch)
    count = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_idle_reader(count), dry_run=True))
    lever = report['levers']['no_progress_stop']
    assert report['status'] == 'complete', report
    assert lever['arm'] == arm and lever['fired'] and lever['batch'] == 3
    if arm == 'serve':
        assert report['stop_reason'] == 'no_progress' and len(count) == 3
    else:
        assert report['stop_reason'] == 'finished' and len(count) == 13
        assert lever['staged_after'] == 0 and lever['tokens_after'] > 0


def test_material_budget_serve_shrinks_limits(runtime, monkeypatch):
    monkeypatch.setenv(dream_levers.MATERIAL_BUDGET_MODE_ENV, 'serve')
    limits = SessionLimits(
        bucket='heavy', turns=16, tools=16, read_bytes=640000, read_call_bytes=64000, tokens=HEAVY_TOKENS
    )
    owner_records = EvidenceRecords(records(runtime))
    _scripted(owner_records, limits, monkeypatch)
    count = []
    report = asyncio.run(dream_agent.run_pass(UID, turn=_idle_reader(count), dry_run=True))
    lever = report['levers']['material_budget']
    assert lever == {'arm': 'serve', 'tokens_before': HEAVY_TOKENS, 'tokens_after': LIGHT_TOKENS}
    assert report['token_limit'] == LIGHT_TOKENS
    assert report['material'] == 0


# --- admission, parking and ordering (Firestore fake) -------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from config.dream_agent import Caps  # noqa: E402
from database import dream_scheduler, dream_store  # noqa: E402
from tests.unit.test_dream_queue import queue, seed, UID as QUEUE_UID, NOW  # noqa: E402,F401


def test_skip_idle_parks_a_hunt_with_no_material(queue):
    queue.rows[('dream_due', QUEUE_UID)] = {'due_at': NOW}
    denied = {}
    assert dream_store.acquire(QUEUE_UID, Caps(), now=NOW, denial_sink=denied, skip_idle=True) is None
    assert denied == {'reason': 'idle_no_material'}
    assert ('dream_due', QUEUE_UID) not in queue.rows


def test_skip_idle_still_admits_owners_with_dirty_work(queue):
    seed(queue, 2)
    lease = dream_store.acquire(QUEUE_UID, Caps(), now=NOW, skip_idle=True)
    assert lease is not None and lease['hunt'] is False


def test_hunt_lease_marks_would_skip_in_shadow(queue):
    lease = dream_store.acquire(QUEUE_UID, Caps(), now=NOW)
    assert lease is not None and lease['hunt'] is True


def test_denial_reasons_are_named(queue):
    denied = {}
    assert dream_store.acquire(QUEUE_UID, Caps(passes=0), now=NOW, denial_sink=denied) is None
    assert denied['reason'] == 'daily_pass_cap'
    queue.rows[('dream_users', QUEUE_UID)] = {'last_attempt_at': NOW, 'size_bucket': 'light'}
    denied = {}
    assert dream_store.acquire(QUEUE_UID, Caps(), now=NOW + timedelta(minutes=1), denial_sink=denied) is None
    assert denied['reason'] == 'not_due'


def test_park_if_idle_keeps_owners_with_a_pending_score(queue):
    queue.rows[('dream_due', QUEUE_UID)] = {'due_at': NOW}
    queue.rows[('dream_users', QUEUE_UID)] = {'score': 2}
    assert dream_store.park_if_idle(QUEUE_UID) is False
    assert ('dream_due', QUEUE_UID) in queue.rows


def test_park_if_idle_is_transactional_with_the_dirty_count(queue):
    queue.rows[('dream_due', QUEUE_UID)] = {'due_at': NOW}
    seed(queue, 1)
    assert dream_store.park_if_idle(QUEUE_UID) is False
    assert ('dream_due', QUEUE_UID) in queue.rows
    for key in [key for key in queue.rows if key[:3] == ('dream_users', QUEUE_UID, 'dirty')]:
        del queue.rows[key]
    queue.rows[('dream_users', QUEUE_UID)] = {'score': 0}
    assert dream_store.park_if_idle(QUEUE_UID) is True
    assert ('dream_due', QUEUE_UID) not in queue.rows


def test_finish_parks_an_idle_owner_and_records_yield(queue):
    lease = dream_store.acquire(QUEUE_UID, Caps(), now=NOW)
    report = {'tokens': 5, 'outcomes': [{'key': 'a', 'kind': 'spelling', 'status': 'applied'}]}
    dream_store.finish(QUEUE_UID, lease, report, success=True, park_when_idle=True, now=NOW)
    assert ('dream_due', QUEUE_UID) not in queue.rows
    assert queue.rows[('dream_users', QUEUE_UID)]['last_yield'] == 1


def test_finish_without_parking_keeps_the_timed_hunt(queue):
    lease = dream_store.acquire(QUEUE_UID, Caps(), now=NOW)
    dream_store.finish(QUEUE_UID, lease, {'tokens': 5}, success=True, now=NOW)
    assert ('dream_due', QUEUE_UID) in queue.rows


def test_payoff_order_prefers_material_and_yield_but_ages_first(queue):
    now = NOW
    queue.rows[('dream_users', 'quiet')] = {'score': 0, 'last_yield': 0}
    queue.rows[('dream_users', 'busy')] = {'score': 30, 'last_yield': 0}
    queue.rows[('dream_users', 'fruitful')] = {'score': 2, 'last_yield': 8}
    queue.rows[('dream_users', 'aged')] = {'score': 0}
    rows = [
        ('aged', now - timedelta(hours=7)),
        ('quiet', now - timedelta(hours=1)),
        ('busy', now - timedelta(minutes=30)),
        ('fruitful', now - timedelta(minutes=10)),
        ('missing', now - timedelta(minutes=5)),
    ]
    ordered = dream_scheduler.payoff_order(rows, now, firestore_client=queue)
    assert ordered[0] == 'aged'
    assert ordered[1:3] == ['fruitful', 'busy']
    assert sorted(ordered) == sorted(uid for uid, _ in rows)


def test_discovery_parking_fails_open(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('cohort')

    monkeypatch.setattr(dream_scheduler.dream_levers, 'arm', broken)
    assert dream_scheduler._parked('owner', {'score': 0}) is False
    monkeypatch.setattr(dream_scheduler.dream_levers, 'arm', lambda name, uid: 'serve')
    monkeypatch.setattr(dream_scheduler, '_backlog_owed', lambda uid: False)
    assert dream_scheduler._parked('owner', {'score': 0}) is True
    assert dream_scheduler._parked('owner', {'score': 3}) is False


def test_defect_kill_switch_reads_only_false_words_as_off(monkeypatch):
    monkeypatch.setenv('DREAM_DEFECT_REPORTS_ENABLED', 'false')
    assert dream_levers.defect_reports_enabled() is False
    monkeypatch.setenv('DREAM_DEFECT_REPORTS_ENABLED', 'garbage')
    assert dream_levers.defect_reports_enabled() is True


def test_looser_gate_still_blocks_cross_field_spans_quotes_and_ids():
    inputs = {
        'records': {
            'conversations/conv-alpha-123': {
                # Adjacent transcript segments: a span across them is still copied speech.
                'segments': ['ship the robot arm', 'prototype next tuesday after lunch with everyone'],
                'segment_id': 'seg-991',
            }
        }
    }
    # Eight words spanning two fields still count as copied content.
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(_defect('the robot arm prototype next tuesday after lunch was lost'), inputs, [])
    with pytest.raises(ValueError, match='feedback_input_overlap'):
        dream_feedback.validate(_defect('summary said "after lunch" twice'), inputs, [])
    with pytest.raises(ValueError, match='feedback_record_reference'):
        dream_feedback.validate(_defect('segment seg-991 was dropped by read'), inputs, [])
    with pytest.raises(ValueError, match='feedback_record_reference'):
        dream_feedback.validate(_defect('read conv-alpha-123 returned nothing'), inputs, [])
