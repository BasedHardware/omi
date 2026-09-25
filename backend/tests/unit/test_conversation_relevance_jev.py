"""The Jev model tier of conversation relevance (relevance.py + relevance_jev.py, #14835).

Pins: flag default off; the tier order (restore -> rules -> model -> calendar)
is unchanged; Jev replaces conv_discard only when supplied; discard strictly
above the threshold; any Jev failure keeps; the stored record and metric say
which tier decided. All transcripts are synthetic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config import jev_decisions
from models.transcript_segment import TranscriptSegment
from utils import metrics
from utils.conversations import relevance_jev
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import JEV_DISCARD_THRESHOLD, RelevanceDecision, decide_relevance
from utils.llm.jev_client import JevAnswers

AMBIGUOUS = ('Coming over there in a second.',)
TRIGGER = ProcessingTrigger.CAPTURE_END


def _decide(*, jev=None, model=None, calendar=None, texts=AMBIGUOUS, user_kept=False):
    model = model if model is not None else MagicMock(return_value=True)
    calendar = calendar or MagicMock(return_value=False)
    decision = decide_relevance(
        trigger=TRIGGER,
        texts=list(texts),
        speech_seconds=2.0,
        has_photos=False,
        user_kept=user_kept,
        exempt=False,
        trusted_wake_word=False,
        model_discards=model,
        calendar_retains=calendar,
        jev_discard_probability=jev,
    )
    return decision, model, calendar


def test_flags_default_off(monkeypatch):
    monkeypatch.delenv(jev_decisions.CONVERSATION_RELEVANCE_JEV_ENABLED_ENV, raising=False)
    monkeypatch.delenv(jev_decisions.MEMORY_OWNER_JEV_FLIP_ENABLED_ENV, raising=False)
    assert jev_decisions.conversation_relevance_jev_enabled() is False
    assert jev_decisions.memory_owner_jev_flip_enabled() is False

    monkeypatch.setenv(jev_decisions.CONVERSATION_RELEVANCE_JEV_ENABLED_ENV, 'true')
    assert jev_decisions.conversation_relevance_jev_enabled() is True


def test_without_a_jev_thunk_the_model_tier_and_record_are_unchanged():
    decision, model, _ = _decide(jev=None)

    model.assert_called_once()
    assert decision == RelevanceDecision('discard', 'model', 'model_discard', TRIGGER)
    assert 'jev' not in decision.as_record()


def test_jev_above_threshold_discards_without_calling_conv_discard():
    decision, model, _ = _decide(jev=lambda: 0.97)

    model.assert_not_called()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('discard', 'jev', 'jev_discard')
    record = decision.as_record()
    assert record['decided_by'] == 'jev'
    assert record['jev'] == {'p_discard': 0.97, 'threshold': JEV_DISCARD_THRESHOLD, 'model': 'typesafe/jev-1.13'}


@pytest.mark.parametrize('p_discard', [JEV_DISCARD_THRESHOLD, 0.5, 0.0])
def test_jev_at_or_below_threshold_keeps(p_discard):
    decision, model, calendar = _decide(jev=lambda: p_discard)

    model.assert_not_called()
    calendar.assert_not_called()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'jev_keep')
    assert decision.as_record()['jev']['p_discard'] == p_discard


def test_jev_failure_keeps_visibly():
    decision, model, _ = _decide(jev=lambda: None)

    model.assert_not_called()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'jev_error')


def test_calendar_overlap_still_overrides_a_jev_discard_and_keeps_the_probability():
    decision, _, calendar = _decide(jev=lambda: 0.99, calendar=MagicMock(return_value=True))

    calendar.assert_called_once()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'override', 'calendar_overlap')
    assert decision.as_record()['jev']['p_discard'] == 0.99


def test_earlier_tiers_still_decide_before_jev():
    jev = MagicMock(return_value=0.99)

    restored, _, _ = _decide(jev=jev, user_kept=True)
    by_rule, _, _ = _decide(jev=jev, texts=('Um.',))

    jev.assert_not_called()
    assert restored.decided_by == 'user'
    assert by_rule.decided_by == 'rule'


def test_a_plan_that_withholds_the_model_also_withholds_jev():
    jev = MagicMock(return_value=0.99)
    decision = decide_relevance(
        trigger=TRIGGER,
        texts=list(AMBIGUOUS),
        speech_seconds=2.0,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=lambda: False,
        jev_discard_probability=jev,
    )

    jev.assert_not_called()
    assert (decision.decided_by, decision.reason) == ('policy', 'model_withheld')


def test_jev_is_a_bounded_metric_label(monkeypatch):
    seen = []
    counter = MagicMock()
    counter.labels.side_effect = lambda **labels: seen.append(labels) or MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_DECISION_TOTAL', counter)

    metrics.record_conversation_relevance(
        trigger='capture_end', verdict='discard', decided_by='jev', reason='jev_discard'
    )

    assert seen == [{'trigger': 'capture_end', 'verdict': 'discard', 'decided_by': 'jev', 'reason': 'jev_discard'}]


def _segments():
    return [
        TranscriptSegment(
            text='Remind me to call the plumber', speaker='SPEAKER_00', speaker_id=0, is_user=True, start=0, end=2
        ),
        TranscriptSegment(text='   ', speaker='SPEAKER_01', speaker_id=1, is_user=False, start=2, end=3),
        TranscriptSegment(text='Tomorrow at nine.', speaker='SPEAKER_01', speaker_id=1, is_user=False, start=3, end=4),
    ]


def test_state_is_the_shipped_transcript_and_word_count_without_the_duration_clause():
    transcript = relevance_jev.relevance_transcript(_segments())
    state = relevance_jev.relevance_state(transcript)

    assert transcript == 'User: Remind me to call the plumber\n\nSpeaker 1: Tomorrow at nine.'
    assert state == f'Transcript:\n```\n{transcript}\n```\nWord count: 12 words.'
    assert 'duration' not in state.lower() and '2 minutes' not in state


def test_question_is_wording_b():
    question = relevance_jev.QUESTIONS['worth_keeping']

    assert question['type'] == 'noul'
    assert 'Losing a real memory is much worse than keeping a bit of noise.' in question['instructions']


def test_jev_tier_applies_only_to_short_non_empty_transcripts():
    assert relevance_jev.jev_tier_applies('User: pick up the kids at five')
    assert not relevance_jev.jev_tier_applies('   ')
    assert not relevance_jev.jev_tier_applies('User: ' + ' '.join(['word'] * 101))


def test_discard_probability_is_one_minus_worth_keeping(monkeypatch):
    asked = {}

    def fake_ask(state, questions, *, lane):
        asked.update(state=state, questions=questions, lane=lane)
        return JevAnswers(served_model=None, answers={'worth_keeping': {'noul': 0.25}})

    monkeypatch.setattr(relevance_jev, 'ask_jev', fake_ask)

    assert relevance_jev.jev_discard_probability('User: hello there') == pytest.approx(0.75)
    assert asked['lane'] == 'conversation_relevance'
    assert asked['questions'] is relevance_jev.QUESTIONS


def test_no_answer_is_none(monkeypatch):
    monkeypatch.setattr(relevance_jev, 'ask_jev', lambda *args, **kwargs: None)

    assert relevance_jev.jev_discard_probability('User: hello there') is None
