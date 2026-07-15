"""Failure-isolated, content-free proactive-judgment contracts."""

from datetime import datetime, timezone

import utils.task_intelligence.proactive_engine as engine
from models.chat_first import (
    ChatFirstSubject,
    QuestionCardSpec,
    QuestionOption,
)
from utils.task_intelligence.chat_first_eligibility import ChatFirstEligibility

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
SUBJECT = ChatFirstSubject(kind='goal', id='goal-1')


class _Judge:
    model_version = 'fixture.v1'

    def __init__(self, selection):
        self.selection = selection
        self.calls = 0

    def judge(self, candidates):
        self.calls += 1
        return self.selection


def _trigger():
    return engine.ProactiveWakeTrigger(kind='goal_changed', subject=SUBJECT, continuity_key='goal-1-complete')


def _question():
    return QuestionCardSpec(
        type='questionCard',
        question_id='question-1',
        text='What should happen next?',
        subject=SUBJECT,
        options=[QuestionOption(option_id='yes', label='Yes', prepared_answer='Yes')],
    )


def test_capability_off_wake_has_zero_feature_store_provider_and_metric_work(monkeypatch):
    monkeypatch.setattr(
        engine.intent_db,
        'release_due_deferrals',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('feature store must not run')),
    )
    monkeypatch.setattr(
        engine.intent_db,
        'get_budget_state',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('feature store must not run')),
    )
    monkeypatch.setattr(engine, '_meter', lambda *args: (_ for _ in ()).throw(AssertionError('metric must not run')))
    judge = _Judge(engine.ProactiveSelection(blocks=[_question()]))

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=False),
    )

    assert result.outcome == 'disabled'
    assert judge.calls == 0


def test_capability_off_deterministic_capture_has_zero_feature_store_and_metric_work(monkeypatch):
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('feature store must not run')),
    )
    monkeypatch.setattr(engine, '_meter', lambda *args: (_ for _ in ()).throw(AssertionError('metric must not run')))

    result = engine.persist_capture_arrival_intent(
        'user-1',
        conversation_id='capture-1',
        summary='New Omi capture',
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=False),
    )

    assert result is None


def test_capture_arrival_is_failure_isolated_and_bounds_the_persisted_summary(monkeypatch):
    created = []
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: created.append(kwargs) or (_ for _ in ()).throw(TimeoutError('store unavailable')),
    )

    result = engine.persist_capture_arrival_intent(
        'user-1',
        conversation_id='capture-1',
        summary='x' * 400,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result is None
    assert created[0]['blocks'][0].summary == 'x' * 200


def test_exhausted_budget_short_circuits_before_judge(monkeypatch):
    monkeypatch.setattr(engine.intent_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        engine.intent_db,
        'admit_agent_judgment',
        lambda *args, **kwargs: (_ for _ in ()).throw(engine.intent_db.ProactiveBudgetExhausted()),
    )
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('intent must not be created')),
    )
    judge = _Judge(engine.ProactiveSelection(blocks=[_question()]))

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result.outcome == 'budget_exhausted'
    assert judge.calls == 0


def test_empty_judgment_declines_without_consuming_or_creating(monkeypatch):
    monkeypatch.setattr(engine.intent_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        engine.intent_db,
        'admit_agent_judgment',
        lambda *args, **kwargs: engine.intent_db.AgentJudgmentAdmission(existing_intent=None, newly_reserved=True),
    )
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('decline must not create an intent')),
    )
    released = []
    monkeypatch.setattr(
        engine.intent_db,
        'release_agent_judgment_admission',
        lambda *args, **kwargs: released.append(kwargs),
    )
    judge = _Judge(None)

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result.outcome == 'declined'
    assert judge.calls == 1
    assert released == [{'continuity_key': 'goal-1-complete', 'account_generation': 7, 'now': NOW}]


def test_agent_admission_happens_before_the_judge_and_duplicate_wake_stays_quiet(monkeypatch):
    events = []
    monkeypatch.setattr(engine.intent_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        engine.intent_db,
        'admit_agent_judgment',
        lambda *args, **kwargs: events.append('admit')
        or engine.intent_db.AgentJudgmentAdmission(existing_intent=None, newly_reserved=False),
    )
    monkeypatch.setattr(
        engine.intent_db,
        'release_agent_judgment_admission',
        lambda *args, **kwargs: events.append('release'),
    )
    judge = _Judge(engine.ProactiveSelection(blocks=[_question()]))

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result.outcome == 'already_pending'
    assert events == ['admit']
    assert judge.calls == 0


def test_post_commit_wake_isolates_provider_or_store_failure(monkeypatch):
    monkeypatch.setattr(
        engine, 'wake_after_commit', lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError('timeout'))
    )

    result = engine.run_post_commit_wake('user-1', _trigger())

    assert result.outcome == 'declined'
