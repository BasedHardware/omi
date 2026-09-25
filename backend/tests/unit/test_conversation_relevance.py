"""The one relevance decision (utils/conversations/relevance.py).

These pin the orchestration: which tier decides, which tiers never run, and
what the stored record says. Rule content is pinned in
test_conversation_relevance_rules.py.
"""

from unittest.mock import MagicMock

import pytest

from utils.conversations.processing_trigger import PROCESSING_MODES, ProcessingTrigger, RelevancePolicy
from datetime import datetime, timedelta, timezone

from utils.conversations.relevance import (
    Neighbor,
    RelevanceDecision,
    find_neighbor,
    decide_relevance,
    final_relevance,
    sync_intake_decision,
)
from utils.conversations.relevance_rules import RULES_VERSION

LONG = [' '.join(f'topic{i}' for i in range(101))]


def _decide(
    *,
    trigger=ProcessingTrigger.CAPTURE_END,
    texts=('Coming over there in a second.',),
    speech_seconds=2.0,
    has_photos=False,
    user_kept=False,
    exempt=False,
    trusted_wake_word=False,
    model=None,
    calendar=None,
):
    model = model or MagicMock(return_value=False)
    calendar = calendar or MagicMock(return_value=False)
    decision = decide_relevance(
        trigger=trigger,
        texts=list(texts),
        speech_seconds=speech_seconds,
        has_photos=has_photos,
        user_kept=user_kept,
        exempt=exempt,
        trusted_wake_word=trusted_wake_word,
        model_discards=model,
        calendar_retains=calendar,
    )
    return decision, model, calendar


def test_every_trigger_has_a_mode():
    assert set(PROCESSING_MODES) == set(ProcessingTrigger)


def test_only_user_actions_skip_assessment():
    keep = {trigger for trigger, mode in PROCESSING_MODES.items() if mode.relevance is RelevancePolicy.KEEP}
    # SERVER_RECOVERY is not a user action, but it repairs a stale row the
    # pipeline never successfully finished; letting relevance discard the only
    # recovered copy would defeat the recovery itself.
    assert keep == {
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
        ProcessingTrigger.SERVER_RECOVERY,
    }


@pytest.mark.parametrize(
    'trigger',
    [ProcessingTrigger.CAPTURE_END, ProcessingTrigger.CLIENT_FINALIZE, ProcessingTrigger.SYNC_UPDATE],
)
def test_capture_paths_reach_the_model_for_ambiguous_speech(trigger):
    """The defect: sync and client finalize used to skip the gate entirely."""
    decision, model, _ = _decide(trigger=trigger, model=MagicMock(return_value=True))

    model.assert_called_once()
    assert decision == RelevanceDecision('discard', 'model', 'model_discard', trigger)


@pytest.mark.parametrize(
    'trigger', [ProcessingTrigger.FIRST_OPEN, ProcessingTrigger.USER_REPROCESS, ProcessingTrigger.MERGE]
)
def test_user_action_triggers_keep_without_any_tier(trigger):
    decision, model, calendar = _decide(trigger=trigger, texts=())

    assert decision == RelevanceDecision('keep', 'policy', trigger.value, trigger)
    model.assert_not_called()
    calendar.assert_not_called()


def test_a_restore_outranks_every_tier():
    decision, model, _ = _decide(user_kept=True, texts=('hmm',))

    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'user', 'restored')
    model.assert_not_called()


def test_exempt_identity_is_never_judged():
    decision, model, _ = _decide(exempt=True, texts=())

    assert (decision.verdict, decision.reason) == ('keep', 'exempt')
    model.assert_not_called()


def test_long_speech_is_kept_by_rule_without_a_model_call():
    decision, model, _ = _decide(texts=LONG)

    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'rule', 'substantial_length')
    model.assert_not_called()


def test_rule_discard_still_yields_to_a_calendar_meeting():
    decision, model, calendar = _decide(texts=('hmm',), calendar=MagicMock(return_value=True))

    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'override', 'calendar_overlap')
    model.assert_not_called()
    calendar.assert_called_once()


def test_rule_discard_without_a_meeting():
    decision, model, _ = _decide(texts=('hmm', 'mm'))

    assert (decision.verdict, decision.decided_by, decision.reason) == ('discard', 'rule', 'filler_only')
    model.assert_not_called()


def test_keep_verdicts_never_consult_the_calendar():
    _, _, calendar = _decide(model=MagicMock(return_value=False))

    calendar.assert_not_called()


@pytest.mark.parametrize('texts', [('hmm',), ("Hey Omi, don't forget to send the budget.",)])
def test_a_trusted_wake_word_is_judged_only_by_the_model(texts):
    decision, model, _ = _decide(texts=texts, trusted_wake_word=True)

    model.assert_called_once()
    assert decision.reason == 'model_keep'


def test_photos_bypass_the_transcript_rules():
    decision, model, _ = _decide(texts=(), has_photos=True)

    model.assert_called_once()
    assert decision.decided_by == 'model'


def test_model_failure_keeps_and_says_so():
    def failing(on_error, _neighbor):
        on_error(RuntimeError('provider down'))
        return False

    decision, _, calendar = _decide(model=failing)

    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'model', 'model_error')
    calendar.assert_not_called()


def test_record_is_attributable():
    decision = RelevanceDecision('discard', 'rule', 'filler_only', ProcessingTrigger.SYNC_UPDATE)

    assert decision.as_record() == {
        'verdict': 'discard',
        'decided_by': 'rule',
        'reason': 'filler_only',
        'trigger': 'sync_update',
        'rules_version': RULES_VERSION,
    }
    assert sync_intake_decision('filler_only')['trigger'] == 'sync_intake'


def test_stored_decision_reports_the_structuring_models_empty_title():
    kept = RelevanceDecision('keep', 'policy', 'user_reprocess', ProcessingTrigger.USER_REPROCESS)

    assert final_relevance(kept, discarded=False) is kept
    assert final_relevance(kept, discarded=True) == RelevanceDecision(
        'discard', 'model', 'empty_title', ProcessingTrigger.USER_REPROCESS
    )
    assert final_relevance(None, discarded=True) is None


def test_withheld_model_keeps_what_the_rules_cannot_settle():
    """Free-tier desktop: the rules still run; the ambiguous middle is kept."""
    decision = decide_relevance(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['Coming over there in a second.'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=MagicMock(return_value=False),
    )
    assert (decision.verdict, decision.decided_by, decision.reason) == ('keep', 'policy', 'model_withheld')

    filler = decide_relevance(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['Mm-hmm.'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=None,
        calendar_retains=MagicMock(return_value=False),
    )
    assert (filler.verdict, filler.decided_by, filler.reason) == ('discard', 'rule', 'filler_only')


T0 = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def _row(conversation_id, start_offset, end_offset, **fields):
    row = {
        'id': conversation_id,
        'started_at': T0 + timedelta(seconds=start_offset),
        'finished_at': T0 + timedelta(seconds=end_offset),
    }
    row.update(fields)
    return row


def test_neighbor_is_the_nearest_visible_conversation_inside_the_boundary_gap():
    rows = [
        _row('far', -900, -300),
        _row('near-before', -600, -40),
        _row('hidden', -30, -5, discarded=True),
        _row('after', 70, 400),
    ]
    neighbor = find_neighbor(
        rows, conversation_id='me', started_at=T0, finished_at=T0 + timedelta(seconds=3), gap_seconds=120
    )
    assert neighbor == Neighbor('near-before', 40.0, 'before')


def test_no_neighbor_outside_the_gap_or_for_itself():
    rows = [_row('me', 0, 3), _row('far', -900, -121)]
    assert (
        find_neighbor(rows, conversation_id='me', started_at=T0, finished_at=T0 + timedelta(seconds=3), gap_seconds=120)
        is None
    )


def test_a_model_discard_next_to_a_kept_conversation_links_to_it():
    seen = []

    def model(_on_error, neighbor):
        seen.append(neighbor)
        return True

    decision, _, _ = _decide(model=model)
    assert seen == [None]
    assert decision.neighbor_id is None

    adjacent = Neighbor('meeting', 40.0, 'before')
    decision = decide_relevance(
        trigger=ProcessingTrigger.SYNC_UPDATE,
        texts=['Coming over there in a second.'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=lambda _on_error, neighbor: neighbor is adjacent,
        calendar_retains=MagicMock(return_value=False),
        neighbor=lambda: adjacent,
    )
    assert decision == RelevanceDecision(
        'discard', 'model', 'neighbor_fragment', ProcessingTrigger.SYNC_UPDATE, 'meeting'
    )
    assert decision.as_record()['neighbor_id'] == 'meeting'


def test_neighbor_is_never_looked_up_when_the_rules_settle():
    lookup = MagicMock(return_value=None)
    decision = decide_relevance(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=['Mm-hmm.'],
        speech_seconds=None,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=MagicMock(),
        calendar_retains=MagicMock(return_value=False),
        neighbor=lookup,
    )
    assert decision.reason == 'filler_only'
    lookup.assert_not_called()
