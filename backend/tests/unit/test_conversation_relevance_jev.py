"""The Jev model tier of conversation relevance (relevance.py + relevance_jev.py, #14835).

Pins: flag default off; the tier order (restore -> rules -> model -> calendar)
is unchanged; Jev replaces conv_discard only when supplied; its comparison is
strict above the threshold by default, with inclusive comparison opt-in; Jev
failures advance to cheaper arms; the stored record and metric say which tier
decided. All transcripts are synthetic.
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


@pytest.fixture(autouse=True)
def isolated_relevance_circuits():
    from utils.conversations.relevance_circuit import get_relevance_circuit

    get_relevance_circuit.cache_clear()
    yield
    get_relevance_circuit.cache_clear()


@pytest.fixture(autouse=True)
def default_jev_discard_policy(monkeypatch):
    monkeypatch.delenv('CONVERSATION_RELEVANCE_JEV_DISCARD_THRESHOLD', raising=False)
    monkeypatch.delenv('CONVERSATION_RELEVANCE_JEV_DISCARD_INCLUSIVE', raising=False)


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


def test_percentage_cohort_defaults_off(monkeypatch):
    monkeypatch.delenv(jev_decisions.CONVERSATION_RELEVANCE_JEV_PERCENT_ENV, raising=False)
    assert jev_decisions.relevance_arm('conversation') == 'nano'
    monkeypatch.setenv(jev_decisions.CONVERSATION_RELEVANCE_JEV_PERCENT_ENV, '100')
    assert jev_decisions.relevance_arm('conversation') == 'jev'


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
    assert record['jev'] == {
        'p_discard': 0.97,
        'threshold': JEV_DISCARD_THRESHOLD,
        'comparison': '>',
        'model': 'typesafe/jev-1.13',
    }


def test_jev_unset_cutoff_keeps_exactly_at_default_threshold():
    decision, _, _ = _decide(jev=lambda: 0.80)

    assert JEV_DISCARD_THRESHOLD == 0.80
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'jev_keep')
    assert decision.as_record()['jev'] == {
        'p_discard': 0.8,
        'threshold': 0.8,
        'comparison': '>',
        'model': 'typesafe/jev-1.13',
    }


def test_jev_inclusive_cutoff_discards_at_threshold(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_DISCARD_INCLUSIVE', 'true')
    decision, _, _ = _decide(jev=lambda: 0.80)

    assert (decision.verdict, decision.decided_by, decision.reason) == ('discard', 'jev', 'jev_discard')
    assert decision.as_record()['jev']['threshold'] == 0.8
    assert decision.as_record()['jev']['comparison'] == '>='


def test_jev_out_of_range_cutoff_falls_back_to_default(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_DISCARD_THRESHOLD', '0.96')
    decision, _, _ = _decide(jev=lambda: 0.90)

    assert (decision.verdict, decision.decided_by, decision.reason) == ('discard', 'jev', 'jev_discard')
    assert decision.as_record()['jev']['threshold'] == JEV_DISCARD_THRESHOLD
    assert decision.as_record()['jev']['comparison'] == '>'


def test_jev_invalid_inclusive_value_defaults_to_strict(monkeypatch):
    monkeypatch.setenv('CONVERSATION_RELEVANCE_JEV_DISCARD_INCLUSIVE', 'sometimes')
    decision, _, _ = _decide(jev=lambda: 0.80)

    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'jev_keep')
    assert decision.as_record()['jev']['comparison'] == '>'


@pytest.mark.parametrize('p_discard', [JEV_DISCARD_THRESHOLD, 0.5, 0.0])
def test_jev_at_or_below_threshold_keeps(p_discard):
    decision, model, calendar = _decide(jev=lambda: p_discard)

    model.assert_not_called()
    calendar.assert_not_called()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'jev', 'jev_keep')
    assert decision.as_record()['jev']['p_discard'] == p_discard


def test_jev_failure_uses_model_visibly():
    decision, model, _ = _decide(jev=lambda: None)

    model.assert_called_once()
    assert (decision.verdict, decision.decided_by, decision.reason) == ('discard', 'model', 'jev_fallback_model')


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

    assert transcript == 'You: Remind me to call the plumber\n\nSpeaker A: Tomorrow at nine.'
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


@pytest.fixture
def oct14_shape():
    """Synthetic replay of sparse backchannels; not private incident transcripts."""
    return [
        (['yeah, I think so.'] * 7, 'discard'),
        (["okay, I don't know."] * 7, 'discard'),
        (['uh, well, you know.'] * 7, 'discard'),
        (['yeah.'] * 120, 'discard'),
        (['yeah, I think so.'] * 7 + ['Buy milk.'], 'keep'),
        (['Call mom before five.'], 'keep'),
        (['Sarah.'], 'keep'),
        (['Dentist at 3:30.'], 'keep'),
        (['Yes.'], 'keep'),
        (['明天下午三点开会。'], 'keep'),
    ]


def _failed_model(on_error, _neighbor):
    on_error(RuntimeError('unavailable'))
    return False


def test_oct14_shape_benchmark(oct14_shape):
    for texts, expected in oct14_shape:
        decision, _, _ = _decide(jev=lambda: None, model=_failed_model, texts=texts)
        assert decision.verdict == expected, texts
        assert decision.decided_by == ('rule' if len(texts) == 120 else 'deterministic')
        if len(texts) == 7 or expected == 'keep':
            assert decision.reason in {'jev_fallback_deterministic', 'circuit_open'}


@pytest.mark.parametrize('with_jev', [False, True])
@pytest.mark.parametrize('raises', [False, True])
def test_failed_model_advances_to_deterministic(with_jev, raises, monkeypatch):
    from utils.conversations import relevance

    transitions = MagicMock()
    monkeypatch.setattr(relevance, 'record_fallback', transitions)

    def model(on_error, adjacent):
        if raises:
            raise TimeoutError()
        return _failed_model(on_error, adjacent)

    decision, _, _ = _decide(jev=(lambda: None) if with_jev else None, model=model, texts=['yeah, I think so.'] * 7)
    assert (decision.verdict, decision.decided_by, decision.reason) == (
        'discard',
        'deterministic',
        'jev_fallback_deterministic' if with_jev else 'model_fallback_deterministic',
    )
    assert transitions.call_count == (2 if with_jev else 1)
    assert transitions.call_args.kwargs == dict(
        component='conversation_relevance',
        from_mode='model',
        to_mode='deterministic',
        reason='timeout' if raises else 'transport_error',
        outcome='degraded',
    )


@pytest.mark.parametrize('discard', [False, True])
def test_model_fallback_preserves_transition(discard, monkeypatch):
    from utils.conversations import relevance

    transitions = MagicMock()
    monkeypatch.setattr(relevance, 'record_fallback', transitions)
    decision, _, _ = _decide(jev=lambda: None, model=MagicMock(return_value=discard))
    assert decision.reason == 'jev_fallback_model'
    assert decision.verdict == ('discard' if discard else 'keep')
    transitions.assert_called_once_with(
        component='conversation_relevance',
        from_mode='jev',
        to_mode='model',
        reason='unavailable',
        outcome='degraded',
    )


@pytest.mark.parametrize('outcome', ['success', 'http_error', 'transport_error', 'timeout', 'unconfigured'])
def test_primary_scorer_outcome_counter(outcome, monkeypatch):
    counter = MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_SCORER_TOTAL', counter)

    def ask(*args, outcome_observer, **kwargs):
        outcome_observer(outcome)
        return JevAnswers(None, {'worth_keeping': {'noul': 0.75}}) if outcome == 'success' else None

    monkeypatch.setattr(relevance_jev, 'ask_jev', ask)
    result = relevance_jev.jev_discard_probability('User: buy milk', record_outcome=True)
    assert result == (0.25 if outcome == 'success' else None)
    counter.labels.assert_called_once_with(arm='jev', outcome=outcome)
    counter.labels.return_value.inc.assert_called_once()


@pytest.mark.parametrize('has_photos,trusted_wake_word', [(True, False), (False, True)])
def test_unavailable_models_preserve_rule_skips(has_photos, trusted_wake_word):
    decision = decide_relevance(
        trigger=TRIGGER,
        texts=['um'],
        speech_seconds=0.1,
        has_photos=has_photos,
        trusted_wake_word=trusted_wake_word,
        user_kept=False,
        exempt=False,
        model_discards=_failed_model,
        calendar_retains=lambda: False,
    )
    assert decision.verdict == 'keep'
    assert decision.reason == 'model_fallback_deterministic'


def test_deterministic_fallback_preserves_calendar():
    decision, _, calendar = _decide(
        jev=lambda: None, model=_failed_model, texts=['yeah, I think so.'] * 7, calendar=MagicMock(return_value=True)
    )
    assert (decision.verdict, decision.reason) == ('keep', 'calendar_overlap')
    calendar.assert_called_once()


def test_withheld_models_keep_ambiguous_band_without_paid_calls(monkeypatch):
    from utils.conversations import relevance

    transitions = MagicMock()
    monkeypatch.setattr(relevance, 'record_fallback', transitions)
    jev = MagicMock()
    decision = decide_relevance(
        trigger=TRIGGER,
        texts=['yeah, I think so.'] * 7,
        speech_seconds=900,
        has_photos=False,
        trusted_wake_word=False,
        user_kept=False,
        exempt=False,
        model_discards=None,
        calendar_retains=lambda: False,
        jev_discard_probability=jev,
    )
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'policy', 'model_withheld')
    jev.assert_not_called()
    transitions.assert_not_called()


def test_degraded_reasons_are_metric_labels(monkeypatch):
    counter = MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_DECISION_TOTAL', counter)
    for arm, reason in [('model', 'jev_fallback_model'), ('deterministic', 'jev_fallback_deterministic')]:
        metrics.record_conversation_relevance(trigger='capture_end', verdict='discard', decided_by=arm, reason=reason)
        counter.labels.assert_called_with(trigger='capture_end', verdict='discard', decided_by=arm, reason=reason)


def test_shared_transition_counter_emits_on_degraded_paths(monkeypatch):
    from utils.observability import fallback

    counter = MagicMock()
    monkeypatch.setattr(fallback, 'OMI_FALLBACK_TOTAL', counter)
    _decide(jev=lambda: None, model=_failed_model)
    assert counter.labels.call_count == 2
    counter.labels.assert_any_call(
        component='conversation_relevance',
        from_mode='jev',
        to_mode='model',
        reason='unavailable',
        outcome='degraded',
    )
    counter.labels.assert_any_call(
        component='conversation_relevance',
        from_mode='model',
        to_mode='deterministic',
        reason='transport_error',
        outcome='degraded',
    )
    assert counter.labels.return_value.inc.call_count == 2


def test_chain_accepts_another_arm_without_changing_the_runner():
    from utils.conversations.relevance import DecisionArm, _decision_chain

    skipped = MagicMock()
    answer = RelevanceDecision('keep', 'model', 'model_keep', TRIGGER)
    assert (
        _decision_chain(
            [
                DecisionArm('unavailable', lambda: False, skipped),
                DecisionArm('no_answer', lambda: True, lambda: None),
                DecisionArm('future_provider', lambda: True, lambda: answer),
                DecisionArm('unused', lambda: True, skipped, paid=False),
            ]
        )
        == answer
    )
    skipped.assert_not_called()
