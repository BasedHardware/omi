"""Failure-isolated, content-free proactive-judgment contracts."""

from datetime import datetime, timedelta, timezone
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import utils.task_intelligence.proactive_engine as engine
from models.chat_first import (
    ChatFirstSubject,
    ConversationLinkSpec,
    QuestionCardSpec,
    QuestionOption,
)
from utils.task_intelligence.chat_first_eligibility import ChatFirstEligibility
from utils.conversations.meeting_treatment import (
    MIN_MEETING_DURATION_SECONDS,
    MIN_TRANSCRIBED_SPEECH_SECONDS,
    deduplicated_transcribed_speech_seconds,
    is_meeting_treatment_eligible,
)

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
SUBJECT = ChatFirstSubject(kind='goal', id='goal-1')


@pytest.fixture(autouse=True)
def _no_sparse_cold_start(monkeypatch):
    monkeypatch.setattr(engine.intent_db, 'has_active_sparse_cold_start_sequence', lambda *args, **kwargs: False)


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


def test_cold_start_decision_table_requires_both_canonical_facts():
    assert engine.classify_cold_start_profile(canonical_goal_count=0, open_task_count=0) == 'sparse'
    assert engine.classify_cold_start_profile(canonical_goal_count=1, open_task_count=0) == 'sparse'
    assert engine.classify_cold_start_profile(canonical_goal_count=0, open_task_count=1) == 'sparse'
    assert engine.classify_cold_start_profile(canonical_goal_count=1, open_task_count=1) == 'rich'


def test_sparse_cold_start_suppresses_agent_tier_without_calling_the_judge(monkeypatch):
    monkeypatch.setattr(engine.intent_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(engine.intent_db, 'has_active_sparse_cold_start_sequence', lambda *args, **kwargs: True)
    monkeypatch.setattr(
        engine.intent_db,
        'admit_agent_judgment',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('agent admission must stay quiet')),
    )
    judge = _Judge(engine.ProactiveSelection(blocks=[_question()]))

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result.outcome == 'suppressed_by_cold_start'
    assert judge.calls == 0


def test_agent_judgment_cannot_mint_a_conversation_link(monkeypatch):
    monkeypatch.setattr(engine.intent_db, 'release_due_deferrals', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        engine.intent_db,
        'admit_agent_judgment',
        lambda *args, **kwargs: SimpleNamespace(existing_intent=None, newly_reserved=True),
    )
    monkeypatch.setattr(engine.intent_db, 'release_agent_judgment_admission', MagicMock())
    create_intent = MagicMock()
    monkeypatch.setattr(engine.intent_db, 'create_intent', create_intent)
    judge = _Judge(
        engine.ProactiveSelection(
            blocks=[
                _question(),
                ConversationLinkSpec(
                    type='conversationLink', conversation_id='ambient-1', summary='Meeting notes ready'
                ),
            ]
        )
    )

    result = engine.wake_after_commit(
        'user-1',
        _trigger(),
        judge=judge,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result.outcome == 'declined'
    create_intent.assert_not_called()


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


def test_desktop_meeting_arrival_persists_exact_conversation_link(monkeypatch):
    created = []
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: created.append(kwargs) or (SimpleNamespace(), True),
    )
    monkeypatch.setattr(engine, '_meter', lambda *args: None)

    engine.persist_capture_arrival_intent(
        'user-1',
        conversation_id='conversation-1',
        summary='Weekly planning',
        is_desktop_meeting=True,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert created[0]['continuity_key'] == 'capture:conversation-1'
    assert created[0]['blocks'][0].model_dump() == {
        'type': 'conversationLink',
        'conversation_id': 'conversation-1',
        'summary': 'Weekly planning',
        'recommended_action_items': [],
    }

    engine.persist_capture_arrival_intent(
        'user-1',
        conversation_id='conversation-2',
        summary='',
        is_desktop_meeting=True,
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert created[1]['blocks'][0].summary == 'Your meeting notes are ready.'


def test_meeting_recommendations_keep_bounded_open_user_commitments():
    structured = {
        'action_items': [
            {'description': ' Send the deck ', 'capture_owner': 'user', 'target_task_id': 'task-1'},
            {'description': 'Someone else reviews it', 'capture_owner': 'other'},
            {'description': 'Already sent', 'capture_owner': 'user', 'completed': True},
            {'description': 'Book the follow-up', 'capture_owner': 'user'},
        ]
    }

    recommendations = engine.recommended_meeting_action_items(structured)

    assert [item.model_dump() for item in recommendations] == [
        {'description': 'Send the deck', 'task_id': 'task-1'},
        {'description': 'Book the follow-up', 'task_id': None},
    ]


def test_desktop_meeting_adapter_uses_stored_role_and_skips_non_meeting_or_rotation(monkeypatch):
    persist = MagicMock()
    monkeypatch.setattr(engine, 'persist_capture_arrival_intent', persist)
    ambient = {
        'id': 'ambient-1',
        'source': 'desktop',
        'status': 'completed',
        'discarded': False,
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=MIN_MEETING_DURATION_SECONDS),
        'transcript_segments': [{'text': 'A substantive exchange', 'start': 0, 'end': MIN_TRANSCRIBED_SPEECH_SECONDS}],
        'structured': {'title': 'Ambient capture'},
        'external_data': {'conversation_role': 'ambient'},
    }
    meeting = {
        **ambient,
        'id': 'meeting-1',
        'structured': {'title': 'Design review'},
        'external_data': {'conversation_role': 'meeting'},
    }

    engine.persist_desktop_meeting_arrival('user-1', ambient)
    persist.assert_not_called()

    engine.persist_desktop_meeting_arrival('user-1', meeting)
    persist.assert_called_once_with(
        'user-1',
        conversation_id='meeting-1',
        summary='Design review',
        is_desktop_meeting=True,
        recommended_action_items=[],
    )

    persist.reset_mock()
    rotation = {
        **meeting,
        'id': 'meeting-rotation',
        'external_data': {
            'conversation_role': 'meeting',
            'conversation_finalization_reason': 'max_duration_rotation',
        },
    }
    engine.persist_desktop_meeting_arrival('user-1', rotation)
    persist.assert_not_called()


def test_meeting_treatment_requires_five_minutes_and_deduplicated_speech():
    eligible = {
        'source': 'desktop',
        'discarded': False,
        'started_at': NOW,
        'finished_at': NOW + timedelta(seconds=MIN_MEETING_DURATION_SECONDS),
        'external_data': {'conversation_role': 'meeting'},
        'transcript_segments': [
            {'text': 'first exchange', 'start': 0, 'end': 35},
            {'text': 'second exchange', 'start': 35, 'end': MIN_TRANSCRIBED_SPEECH_SECONDS},
        ],
    }
    assert is_meeting_treatment_eligible(eligible) is True

    short_call = {**eligible, 'finished_at': NOW + timedelta(seconds=MIN_MEETING_DURATION_SECONDS - 1)}
    assert is_meeting_treatment_eligible(short_call) is False

    duplicate_streams = {
        **eligible,
        'finished_at': NOW + timedelta(minutes=20),
        'transcript_segments': [
            {'text': 'remote stream from mic', 'start': 0, 'end': 45},
            {'text': 'same remote stream from system audio', 'start': 0, 'end': 45},
        ],
    }
    assert deduplicated_transcribed_speech_seconds(duplicate_streams['transcript_segments']) == 45
    assert is_meeting_treatment_eligible(duplicate_streams) is False


def test_proactive_failure_logs_redact_authenticated_uid(monkeypatch, caplog):
    uid = 'sensitive-user-123456'
    monkeypatch.setattr(
        engine,
        'wake_after_commit',
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError('timeout')),
    )
    caplog.set_level(logging.WARNING, logger=engine.__name__)

    result = engine.run_post_commit_wake(uid, _trigger())

    assert result.outcome == 'declined'
    assert uid not in caplog.text
    assert 'error=TimeoutError' in caplog.text


def test_capture_arrival_failure_logs_redact_authenticated_uid(monkeypatch, caplog):
    uid = 'sensitive-user-123456'
    monkeypatch.setattr(
        engine.intent_db,
        'create_intent',
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError('store unavailable')),
    )
    caplog.set_level(logging.WARNING, logger=engine.__name__)

    result = engine.persist_capture_arrival_intent(
        uid,
        conversation_id='capture-1',
        summary='New Omi capture',
        now=NOW,
        eligibility_resolver=lambda _uid: ChatFirstEligibility(enabled=True, account_generation=7),
    )

    assert result is None
    assert uid not in caplog.text
    assert 'error=TimeoutError' in caplog.text


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


def test_task_and_goal_wake_helpers_bind_the_committed_entity_identity(monkeypatch):
    calls = []

    def record(uid, trigger, **kwargs):
        calls.append((uid, trigger, kwargs))
        return engine.ProactiveWakeResult(outcome='no_candidate')

    monkeypatch.setattr(engine, 'run_post_commit_wake', record)

    assert engine.run_task_changed_wake('user-1', task_id='task-7', mutation_key='revision-3').outcome == 'no_candidate'
    assert engine.run_goal_changed_wake('user-1', goal_id='goal-9', mutation_key='revision-4').outcome == 'no_candidate'

    assert [(uid, trigger.kind, trigger.subject, trigger.continuity_key) for uid, trigger, _ in calls] == [
        ('user-1', 'task_changed', ChatFirstSubject(kind='task', id='task-7'), 'task:task-7:revision-3'),
        ('user-1', 'goal_changed', ChatFirstSubject(kind='goal', id='goal-9'), 'goal:goal-9:revision-4'),
    ]
