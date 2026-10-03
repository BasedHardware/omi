"""EXP-005 and paid admission: synthetic data, providers and persistence only."""

import hashlib
import json
import threading
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis
import pytest
import yaml

from config.jev_decisions import JEV_MAX_STATE_CHARS, mentor_jev_shadow_enabled
from config.plan_catalog import PAID_PLAN_TYPES, PlanType
from tests.unit.test_realtime_integrations_usage_tracking import integration_harness  # noqa: F401
from utils import executors, mentor_admission as admission_module, mentor_jev_shadow as shadow, metrics
from utils.conversations import jev_shadow as shared
from utils.llm import jev_client
from database import jev_shadow as store

SECRET = 'PRIVATE_TRANSCRIPT_NEVER_STORED_5921'
MESSAGES = [{'text': SECRET, 'is_user': True}, {'text': 'other speaker', 'is_user': False}]


@pytest.fixture
def admission(monkeypatch):
    # Dependency initialization belongs to setup, not the behavioral call-phase budget.
    from utils import managed_compute  # noqa: F401

    lookup = MagicMock(return_value=None)
    monkeypatch.setattr(admission_module.users_db, 'get_user_valid_subscription', lookup)
    monkeypatch.setattr(admission_module, 'get_customer_firestore_client', lambda: 'fake-client')
    fallback = MagicMock()
    monkeypatch.setattr(admission_module, 'record_fallback', fallback)
    return lookup, fallback


@pytest.mark.parametrize('plan', [None, PlanType.basic, *PAID_PLAN_TYPES])
def test_paid_plan_admission_uses_canonical_resolution(admission, plan, caplog):
    lookup, fallback = admission
    lookup.return_value = SimpleNamespace(plan=plan) if plan is not None else None
    with caplog.at_level('INFO'):
        assert admission_module.mentor_plan_allows_evaluation('synthetic') is (plan in PAID_PLAN_TYPES)
    lookup.assert_called_once_with('synthetic', firestore_client='fake-client', provision=False)
    fallback.assert_not_called()
    if plan not in PAID_PLAN_TYPES:
        assert 'mentor_plan_admission outcome=skipped reason=basic_not_entitled' in caplog.text


@pytest.mark.parametrize('failure', ['lookup', 'unknown_plan'])
def test_lookup_failure_is_counted_fail_open(admission, failure, caplog):
    lookup, fallback = admission
    if failure == 'lookup':
        lookup.side_effect = RuntimeError(SECRET)
    else:
        lookup.return_value = SimpleNamespace(plan='future_plan')
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is True
    fallback.assert_called_once()
    assert 'outcome=fail_open' in caplog.text
    assert SECRET not in caplog.text


@pytest.fixture
def pipeline(integration_harness, monkeypatch):  # noqa: F811
    app = integration_harness.app
    monkeypatch.setenv('MENTOR_GATE_DEBOUNCE_ENABLED', 'false')
    monkeypatch.setenv('MENTOR_JEV_SHADOW_ENABLED', 'true')
    app.get_mentor_notification_frequency.return_value = 3
    app.evaluate_relevance.return_value = SimpleNamespace(
        is_relevant=True, relevance_score=0.9, context_summary=SECRET, reasoning=SECRET
    )
    app.generate_notification.return_value = SimpleNamespace(
        notification_text='Useful synthetic advice', confidence=0.9, reasoning=SECRET, category='advice'
    )
    app.validate_notification.return_value = SimpleNamespace(approved=True, reasoning=SECRET)
    monkeypatch.setattr(
        app,
        'send_app_notification',
        MagicMock(return_value=SimpleNamespace(status=SimpleNamespace(value='dispatched'), delivered=1)),
    )
    records = []
    monkeypatch.setattr(
        shadow, 'submit_mentor_shadow', lambda uid, state, record: records.append((state, dict(record)))
    )
    return app, records


def test_free_skip_precedes_all_model_and_context_calls(pipeline):
    app, records = pipeline
    app.mentor_plan_allows_evaluation.return_value = False
    assert app._process_mentor_proactive_notification('synthetic', MESSAGES) is None
    for call in (app.evaluate_relevance, app.generate_notification, app.validate_notification, app.get_prompt_memories):
        call.assert_not_called()
    assert records == []


@pytest.mark.parametrize(
    'end',
    [
        'gate_reject',
        'gate_error',
        'draft_reject',
        'draft_error',
        'critic_reject',
        'critic_error',
        'send',
        'dispatch_failed',
        'zero_tokens',
    ],
)
def test_pipeline_records_gate_and_downstream_outcomes_without_changing_result(pipeline, end):
    app, records = pipeline
    if end == 'gate_reject':
        app.evaluate_relevance.return_value.is_relevant = False
    elif end == 'gate_error':
        app.evaluate_relevance.side_effect = RuntimeError('synthetic gate failure')
    elif end == 'draft_reject':
        app.generate_notification.return_value.confidence = 0.0
    elif end == 'draft_error':
        app.generate_notification.side_effect = RuntimeError('synthetic draft failure')
    elif end == 'critic_reject':
        app.validate_notification.return_value.approved = False
    elif end == 'critic_error':
        app.validate_notification.side_effect = RuntimeError('synthetic critic failure')
    elif end == 'dispatch_failed':
        app.send_app_notification.return_value.status.value = 'failed'
    elif end == 'zero_tokens':
        app.send_app_notification.return_value.delivered = 0
    result = app._process_mentor_proactive_notification('synthetic', MESSAGES)
    assert (result is not None) is (end in {'send', 'dispatch_failed', 'zero_tokens'})
    state, record = records[0]
    assert f'User: {SECRET}' in state and 'Other: other speaker' in state
    assert SECRET not in json.dumps(record, default=str)
    assert record['notification_sent'] is (end == 'send')
    assert record['luna_gate_passed'] is (None if end == 'gate_error' else end != 'gate_reject')
    if end.endswith('error'):
        assert (
            record['pipeline_failure']
            == {'gate_error': 'gate_failed', 'draft_error': 'generate_failed', 'critic_error': 'critic_failed'}[end]
        )
    if end == 'send':
        assert record['draft_passed'] is True and record['critic_passed'] is True


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('MENTOR_JEV_SHADOW_ENABLED', 'true')
    monkeypatch.setenv('MENTOR_JEV_SHADOW_DAILY_CAP', '2')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(shared, '_get_shadow_redis', lambda deadline: redis)
    monkeypatch.setattr(shadow, '_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(executors, 'get_jev_shadow_executor', MagicMock())

    def submit(_pool, fn, *args):
        future = Future()
        fn(*args)
        future.set_result(None)
        return future

    monkeypatch.setattr(executors, 'submit_with_context', submit)
    ask = MagicMock(return_value=jev_client.JevAnswers('typesafe/jev-1.13', {'worth_telling': {'noul': 0.08}}))
    monkeypatch.setattr(jev_client, 'ask_jev', ask)
    records, outcomes = [], []
    monkeypatch.setattr(
        store, 'write_jev_shadow', lambda uid, rid, record, **kw: records.append((uid, rid, dict(record))) or True
    )
    monkeypatch.setattr(metrics, 'record_jev_shadow_outcome', lambda lane, outcome: outcomes.append((lane, outcome)))
    return SimpleNamespace(redis=redis, ask=ask, records=records, outcomes=outcomes)


def _attempt():
    with shadow.mentor_shadow_attempt('synthetic', MESSAGES, 3) as record:
        record.update(luna_gate_verdict=False, luna_gate_score=0.1, luna_gate_passed=False)


def test_shadow_record_is_content_free_and_uses_existing_writer_and_ids(worker):
    _attempt()
    uid, rid, record = worker.records[0]
    assert uid == 'synthetic'
    assert len(rid) == 32
    assert record['uid_hash'] == hashlib.sha256(uid.encode()).hexdigest()
    assert SECRET not in json.dumps(record, default=str)
    assert record['jev_score'] == 0.08
    assert record['frequency'] == 3 and record['evaluated_at'].tzinfo is not None
    assert record['jev_outcome'] == 'ok'
    assert set(record) == {
        'evaluated_at',
        'frequency',
        'luna_gate_verdict',
        'luna_gate_score',
        'luna_gate_passed',
        'draft_passed',
        'critic_passed',
        'notification_sent',
        'dispatch_status',
        'pipeline_failure',
        'luna_gate_latency_ms',
        'pipeline_latency_ms',
        'lane',
        'evaluation_id',
        'uid_hash',
        'question_version',
        'state_chars',
        'jev_score',
        'jev_outcome',
        'served_model',
        'jev_latency_ms',
        'shadow_latency_ms',
    }
    kwargs = worker.ask.call_args.kwargs
    assert kwargs['max_attempts'] == 1 and kwargs['record_decision_metrics'] is False
    assert worker.ask.call_args.args[1]['worth_telling']['type'] == 'noul'
    assert 'instructions' in worker.ask.call_args.args[1]['worth_telling']


def test_daily_cap_shared_across_users_and_pods(worker, monkeypatch):
    _attempt()
    with shadow.mentor_shadow_attempt('another-user', MESSAGES, 4):
        pass
    monkeypatch.setattr(shadow, '_slots', threading.BoundedSemaphore(2))  # second host, same Redis
    _attempt()
    assert worker.ask.call_count == 2
    assert ('mentor', 'cap') in worker.outcomes
    assert len(worker.redis.keys('jev:shadow:mentor:20*')) == 1


@pytest.mark.parametrize('cap', ['0', '-1', 'invalid'])
def test_bad_cap_admits_no_calls(worker, monkeypatch, cap):
    monkeypatch.setenv('MENTOR_JEV_SHADOW_DAILY_CAP', cap)
    _attempt()
    worker.ask.assert_not_called()


@pytest.mark.parametrize('failure', ['none', 'raise', 'redis', 'persist', 'schedule'])
def test_shadow_failures_do_not_escape_and_model_failures_are_recorded(worker, monkeypatch, failure):
    if failure == 'none':
        worker.ask.return_value = None
    elif failure == 'raise':
        worker.ask.side_effect = RuntimeError(SECRET)
    elif failure == 'redis':
        monkeypatch.setattr(shared, '_get_shadow_redis', MagicMock(side_effect=RuntimeError(SECRET)))
    elif failure == 'persist':
        monkeypatch.setattr(store, 'write_jev_shadow', MagicMock(side_effect=RuntimeError(SECRET)))
    elif failure == 'schedule':
        monkeypatch.setattr(executors, 'submit_with_context', MagicMock(side_effect=RuntimeError(SECRET)))
    _attempt()
    if failure in {'none', 'raise'}:
        assert worker.records[0][2]['jev_score'] is None
        assert worker.records[0][2]['jev_outcome'] == 'jev_failed'
    if failure == 'redis':
        worker.ask.assert_not_called()
    assert worker.outcomes
    assert SECRET not in json.dumps(worker.records, default=str)


def test_state_is_truncated_before_queueing(worker):
    with shadow.mentor_shadow_attempt('synthetic', [{'text': '中' * 40_000, 'is_user': True}], 1):
        pass
    assert len(worker.ask.call_args.args[0]) <= JEV_MAX_STATE_CHARS
    assert worker.records[0][2]['state_chars'] <= JEV_MAX_STATE_CHARS


def test_queued_work_is_bounded_nonblocking_and_cancellation_releases_slots(worker, monkeypatch):
    tasks = []

    def queue(_pool, fn, *args):
        future = Future()
        tasks.append((future, fn, args))
        return future

    monkeypatch.setattr(executors, 'submit_with_context', queue)
    _attempt()
    _attempt()
    _attempt()
    assert len(tasks) == 2 and ('mentor', 'dropped') in worker.outcomes
    worker.ask.assert_not_called()
    assert worker.redis.keys() == []
    tasks[0][0].cancel()
    _attempt()
    assert len(tasks) == 3
    tasks[1][0].cancel()
    tasks[2][0].cancel()


def test_snapshot_does_not_keep_mutable_pipeline_messages(worker, monkeypatch):
    captured = []
    monkeypatch.setattr(shadow, 'submit_mentor_shadow', lambda uid, state, record: captured.append(state))
    messages = [{'text': 'original evidence', 'is_user': True}]
    with shadow.mentor_shadow_attempt('synthetic', messages, 3):
        messages[0]['text'] = 'later mutation'
    assert 'original evidence' in captured[0] and 'later mutation' not in captured[0]


def test_unexpected_submission_exception_cannot_change_pipeline_return(worker, monkeypatch):
    monkeypatch.setattr(shadow, 'submit_mentor_shadow', MagicMock(side_effect=RuntimeError(SECRET)))
    with shadow.mentor_shadow_attempt('synthetic', MESSAGES, 3):
        result = 'unchanged live result'
    assert result == 'unchanged live result'


@pytest.mark.parametrize('stage,expected', [('dev', True), ('prod', False), ('local', False), ('', False)])
def test_unset_kill_switch_is_only_dev_on(monkeypatch, stage, expected):
    monkeypatch.delenv('MENTOR_JEV_SHADOW_ENABLED', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    assert mentor_jev_shadow_enabled() is expected


def test_kill_switch_prevents_queue_and_redis(worker, monkeypatch):
    monkeypatch.setenv('MENTOR_JEV_SHADOW_ENABLED', 'false')
    _attempt()
    worker.ask.assert_not_called()
    assert not worker.redis.keys() and not worker.records


def test_runtime_env_and_charts_enable_debounce_and_shadow_on_all_mentor_hosts():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    manifest = yaml.load((root / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for stage in ('prod', 'dev'):
        env = manifest['environments'][stage]
        hosts = [env['gke'][name]['env'] for name in ('pusher', 'backend-listen')]
        hosts.append(env['cloud_run']['services']['backend']['env'])
        for host in hosts:
            assert host['MENTOR_GATE_DEBOUNCE_ENABLED']['value'] == 'true'
            assert host['MENTOR_JEV_SHADOW_ENABLED']['value'] == 'true'
            assert host['MENTOR_JEV_SHADOW_DAILY_CAP']['value'] == '1400'
            assert not {'MENTOR_GATE_MIN_NEW_WORDS', 'MENTOR_GATE_MIN_SECONDS', 'MENTOR_GATE_DAILY_CAP'} & host.keys()
        for name, suffix in [('pusher', 'pusher'), ('backend-listen', 'backend_listen')]:
            chart = yaml.load(
                (root / f'charts/{name}/{stage}_omi_{suffix}_values.yaml').read_text(), Loader=yaml.CSafeLoader
            )
            values = {entry['name']: entry.get('value') for entry in chart['env']}
            for flag in ('MENTOR_GATE_DEBOUNCE_ENABLED', 'MENTOR_JEV_SHADOW_ENABLED', 'MENTOR_JEV_SHADOW_DAILY_CAP'):
                assert values[flag] == env['gke'][name]['env'][flag]['value']
