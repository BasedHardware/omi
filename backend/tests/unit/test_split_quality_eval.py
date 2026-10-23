"""Fixed-denominator split qualification without model inference."""

from copy import deepcopy

import pytest

from scripts.diarization_eval.split_quality import qualify, validate_units


def units(boundary=None):
    if boundary is None:
        return [{'offset': 0, 'payload': {'audio_seconds': 10}}]
    return [
        {'offset': 0, 'payload': {'audio_seconds': boundary}},
        {'offset': boundary, 'payload': {'audio_seconds': 10 - boundary}},
    ]


def manifest():
    return {
        'crop_seconds': 10,
        'unsplit': units(),
        'cases': [units(4), units(6)],
        'reference_words': [{'start': 3, 'end': 5, 'speaker': 'voice'}, {'start': 5, 'end': 7, 'speaker': 'voice'}],
        'identity_table': {'voice': {'is_user': True}},
        'excluded_spans': [],
    }


def score(truth, turns, identities, **kwargs):
    return {
        'words': len(truth),
        'owner_enrolled_words': len(truth),
        'owner_enrolled_accuracy': turns,
        'engineering_gate': 'PASS' if turns >= 0.9 else 'FAIL',
    }


def test_split_gate_uses_identical_frozen_words_and_per_case_loss():
    frozen = manifest()
    calls = []

    def scorer(truth, *args, **kwargs):
        calls.append(deepcopy(truth))
        return score(truth, *args, **kwargs)

    result = qualify(frozen, project=lambda value: 0.93 if len(value) == 1 else 0.92, scorer=scorer)
    assert result['split_gate'] == 'PASS'
    assert calls == [frozen['reference_words']] * 3
    assert all(case['mid_speech_boundary'] for case in result['splits'])
    result = qualify(frozen, project=lambda value: 0.95 if len(value) == 1 else 0.92, scorer=score)
    assert result['split_gate'] == 'FAIL'


@pytest.mark.parametrize('change', ['missing', 'overlap', 'repeat', 'no-mid-speech'])
def test_incomplete_or_unproven_splits_cannot_pass(change):
    data = manifest()
    if change == 'missing':
        data['cases'][0][1]['offset'] += 1
    elif change == 'overlap':
        data['cases'][0][1]['offset'] -= 1
    elif change == 'repeat':
        data['cases'][1] = data['cases'][0]
    else:
        data['reference_words'] = [{'start': 0, 'end': 1, 'speaker': 'voice'}]
    with pytest.raises(ValueError):
        qualify(data, project=lambda value: 0.95, scorer=score)


def test_changed_denominator_and_missing_identity_evidence_fail():
    data = manifest()
    counter = 0

    def scorer(truth, turns, identities, **kwargs):
        nonlocal counter
        counter += 1
        result = score(truth, turns, identities)
        if counter > 1:
            result['owner_enrolled_words'] -= 1
        return result

    assert qualify(data, project=lambda value: 0.95, scorer=scorer)['split_gate'] == 'FAIL'
    result = qualify(
        data,
        project=lambda value: None,
        scorer=lambda *a, **k: {'words': 2, 'owner_enrolled_words': 0, 'owner_enrolled_accuracy': None},
    )
    assert result['split_gate'] == 'FAIL'
