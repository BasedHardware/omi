"""Pipeline lab speaker scorecards (``speakers/score.py``) on synthetic truth: attribution is identity-blind,
owner precision/recall and naming read the identities, and rates with nothing to measure are null."""

import pytest

from testing.pipeline_lab.speakers.score import pool, score_conversation

# Two voices, alternating 2 s turns; one word per second (synthetic text).
TRUTH = {
    'kind': 'synthetic',
    'turns': [
        {'start': 0.0, 'end': 2.0, 'speaker': 'owner'},
        {'start': 2.0, 'end': 4.0, 'speaker': 'person-a'},
        {'start': 4.0, 'end': 6.0, 'speaker': 'owner'},
        {'start': 6.0, 'end': 8.0, 'speaker': 'stranger'},
    ],
    'identities': {'owner': 'user', 'person-a': 'person-a', 'stranger': None},
}
WORDS = [{'start': t + 0.2, 'end': t + 0.7, 'text': f'word{t}'} for t in range(8)]


def _turn(start, end, voice, *, user=False, person=None):
    return {
        'start': start,
        'end': end,
        'speaker': f'SPEAKER_{voice:02d}',
        'speaker_id': voice,
        'speaker_id_scope': 'final:batch:conversation:c',
        'is_user': user,
        'person_id': person,
    }


def test_a_perfect_labelling_scores_one():
    turns = [
        _turn(0, 2, 0, user=True),
        _turn(2, 4, 1, person='person-a'),
        _turn(4, 6, 0, user=True),
        _turn(6, 8, 2),
    ]
    card = score_conversation(WORDS, TRUTH, turns)
    assert card['words'] == 8
    assert card['attribution'] == 1.0
    assert card['owner_precision'] == card['owner_recall'] == 1.0
    assert card['named_accuracy'] == 1.0  # owner and the enrolled person, both right
    assert card['wrong_name_rate'] == 0.0
    assert card['named_coverage'] == 0.75  # the stranger is unnamed, correctly
    assert (card['predicted_voices'], card['truth_voices'], card['speaker_count_error']) == (3, 3, 0)


def test_attribution_is_identity_blind_but_naming_is_not():
    swapped = [
        _turn(0, 2, 0, person='person-a'),
        _turn(2, 4, 1, user=True),
        _turn(4, 6, 0, person='person-a'),
        _turn(6, 8, 2),
    ]
    card = score_conversation(WORDS, TRUTH, swapped)
    assert card['attribution'] == 1.0  # the voices are grouped right
    assert card['owner_precision'] == 0.0 and card['owner_recall'] == 0.0
    assert card['named_accuracy'] == 0.0
    assert card['wrong_name_rate'] == 0.75  # six words carry a wrong name


def test_no_claims_leave_owner_precision_null_and_coverage_zero():
    anonymous = [_turn(0, 2, 0), _turn(2, 4, 1), _turn(4, 6, 0), _turn(6, 8, 2)]
    card = score_conversation(WORDS, TRUTH, anonymous)
    assert card['owner_precision'] is None  # nothing claimed: nothing to measure
    assert card['owner_recall'] == 0.0
    assert card['named_coverage'] == 0.0 and card['owner_claimed'] == 0


def test_one_voice_for_everything_loses_attribution_and_a_named_stranger_is_a_wrong_name():
    merged = [_turn(0, 8, 0, user=True)]
    card = score_conversation(WORDS, TRUTH, merged)
    assert card['attribution'] == 0.5  # the owner's four words of eight
    assert card['owner_precision'] == 0.5 and card['owner_recall'] == 1.0
    assert card['wrong_name_rate'] == 0.5  # the person's and the stranger's words, labelled as the owner
    assert card['predicted_voices'] == 1 and card['speaker_count_error'] == -2


def test_pooled_rates_are_sums_not_averages():
    good = score_conversation(WORDS, TRUTH, [_turn(0, 8, 0, user=True)])
    empty = score_conversation(WORDS[:2], {'turns': TRUTH['turns'][:1], 'identities': {'owner': 'user'}}, [])
    pooled = pool([good, empty])
    assert pooled['words'] == good['words'] + empty['words'] == 10
    assert pooled['owner_recall'] == pytest.approx(4 / 6, abs=1e-4)
    assert pooled['conversations'] == 2
