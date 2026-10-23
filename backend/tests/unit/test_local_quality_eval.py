"""Synthetic local identity scorecard contracts; no private fixtures or services."""

import json

import pytest

from utils.stt.diarization_eval import aggregate_scorecards, model_reference_wer, score_recording


def word(start=0, speaker='owner', text='hello'):
    return {'start': start, 'end': start + 0.5, 'speaker': speaker, 'text': text}


def turn(start=0, **kwargs):
    return {'start': start, 'end': start + 0.5, 'speaker': 'voice', 'text': 'hello', **kwargs}


def test_crop_offsets_and_no_fitted_identity_mapping():
    truth = [word(10), word(11, 'person')]
    turns = [turn(is_user=True), turn(1, person_id='p', speaker='second')]
    identities = {'owner': {'is_user': True}, 'person': {'person_id': 'p'}}
    result = score_recording(truth, turns, identities, crop_start=10)
    assert result['strict_all_word_accuracy'] == 1
    assert result['engineering_gate'] == 'PASS'
    swapped = score_recording(truth, turns[::-1], identities, crop_start=10)
    assert swapped['strict_all_word_accuracy'] == 1  # Input ordering is irrelevant.
    turns[0]['is_user'] = False
    turns[0]['person_id'] = 'p'
    turns[1]['person_id'] = None
    turns[1]['is_user'] = True
    result = score_recording(truth, turns, identities, crop_start=10)
    assert result['strict_all_word_accuracy'] == 0
    assert result['hungarian_oracle_diagnostic']['accuracy_1to1'] == 1
    assert result['wrong_name_words'] == result['false_owner_words'] == 1
    assert result['wrong_name_false_owner_rate'] == 1


def test_unknown_anonymous_does_not_equal_hand_named_identity():
    result = score_recording([word(speaker='stranger')], [turn()], {})
    assert result['strict_all_word_accuracy'] == 0
    assert result['owner_enrolled_accuracy'] is None
    assert result['anonymous_voices'] == 1
    assert result['engineering_gate'] == 'NOT_EVALUATED'
    assert result['hungarian_oracle_diagnostic']['accuracy_1to1'] == 1


def test_persisted_overlapping_groups_keep_their_actual_identity_claims():
    truth = [word(0), word(1, 'person'), word(3)]
    turns = [turn(0, end=4, is_user=True), turn(1, person_id='p', speaker='second')]
    result = score_recording(truth, turns, {'owner': {'is_user': True}, 'person': {'person_id': 'p'}})
    # Equal overlap prefers the earlier persisted group; no truth-driven remap.
    assert result['strict_all_word_correct'] == 2
    assert result['false_owner_words'] == 1
    assert result['predicted_voices'] == 2


def test_deletions_do_not_improve_fixed_clock_identity():
    truth = [word(0), word(1, text='missing'), word(2, text='last')]
    turns = [turn(is_user=True), turn(2, text='last', person_id='wrong')]
    result = score_recording(truth, turns, {'owner': {'is_user': True}})
    assert result['strict_all_word_accuracy'] == pytest.approx(1 / 3)
    assert result['abstention_words'] == 1
    assert result['end_to_end_alignment']['deletions'] == 1
    assert result['end_to_end_alignment']['aligned_word_coverage'] == pytest.approx(2 / 3)
    assert result['engineering_gate'] == 'FAIL'


def test_unequal_asr_tokenization_uses_reference_word_denominator():
    result = score_recording(
        [word(text='hello, world!')], [turn(text='Hello world', is_user=True)], {'owner': {'is_user': True}}
    )
    assert result['words'] == 1
    assert result['end_to_end_alignment']['reference_tokens'] == 2
    assert result['end_to_end_alignment']['aligned_words'] == 1
    assert result['strict_all_word_accuracy'] == 1


def test_all_excluded_never_passes():
    result = score_recording(
        [word(), word(1, 'noise'), word(2, 'unsure')], [], {'owner': {'is_user': True}}, excluded_spans=[(0, 0.2)]
    )
    assert result['words'] == 0
    assert result['ignored_words'] == 2
    assert result['enrollment_excluded_words'] == 1
    assert result['strict_all_word_accuracy'] is None
    assert result['engineering_gate'] == 'NOT_EVALUATED'
    assert aggregate_scorecards([result])['engineering_gate'] == 'NOT_EVALUATED'


def test_voice_count_uses_scope_and_channel_not_person_name():
    truth = [word(i) for i in range(3)]
    turns = [turn(i, speaker_id=i, speaker_id_scope=str(i), person_id='p') for i in range(3)]
    result = score_recording(truth, turns, {'owner': {'person_id': 'p'}})
    assert result['predicted_voices'] == 3
    assert result['speaker_count_within_one'] is False
    assert result['engineering_gate'] == 'FAIL'


def test_linked_canonical_voice_is_counted_once_across_original_unit_scopes():
    turns = [turn(i, speaker_id=0, speaker_id_scope=str(i), is_user=True) for i in range(3)]
    result = score_recording([word(i) for i in range(3)], turns, {'owner': {'is_user': True}})
    assert result['predicted_voices'] == 1
    assert result['engineering_gate'] == 'PASS'


def test_model_reference_diagnostic_has_sdi_and_identical_normalization():
    result = model_reference_wer('ONE, two three', 'one four extra three')
    assert result['reference_kind'] == 'model_reference_not_truth'
    assert result['substitutions'] == 1
    assert result['insertions'] == 1
    assert result['deletions'] == 0
    assert result['wer'] == pytest.approx(2 / 3)
    assert model_reference_wer('', 'extra')['wer'] is None


def test_aggregate_gate_does_not_hide_failed_recording_count():
    good = score_recording([word()], [turn(is_user=True)], {'owner': {'is_user': True}})
    bad = score_recording(
        [word(i) for i in range(3)],
        [turn(i, speaker=str(i), is_user=True) for i in range(3)],
        {'owner': {'is_user': True}},
    )
    assert aggregate_scorecards([good, bad])['engineering_gate'] == 'FAIL'


def test_aggregates_never_disclose_text_labels_or_identity():
    result = score_recording(
        [word(speaker='secret-label', text='secret-text')],
        [turn(text='secret-text', person_id='secret-person', speaker='secret-channel')],
        {'secret-label': {'person_id': 'secret-person'}},
        model_reference='secret-text',
    )
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('kwargs', [{'crop_start': float('nan')}, {'excluded_spans': [(2, 1)]}])
def test_invalid_clocks_rejected(kwargs):
    with pytest.raises(ValueError):
        score_recording([word()], [turn()], {}, **kwargs)


def test_unaligned_output_voices_still_count():
    result = score_recording(
        [word()],
        [turn(is_user=True), turn(2, speaker='extra-1'), turn(3, speaker='extra-2')],
        {'owner': {'is_user': True}},
    )
    assert result['predicted_voices'] == 3
    assert result['engineering_gate'] == 'FAIL'


def test_pool_retains_oracle_and_coverage_diagnostics():
    row = score_recording([word()], [turn(is_user=True)], {'owner': {'is_user': True}}, model_reference='hello')
    pooled = aggregate_scorecards([row, row])
    assert pooled['hungarian_oracle_diagnostic']['words'] == 2
    assert pooled['end_to_end_alignment']['aligned_words'] == 2
    assert pooled['model_reference_wer']['wer'] == 0


def test_cli_emits_aggregates_and_sanitizes_private_failures(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    truth = tmp_path / 'private-labels.json'
    turns = tmp_path / 'private-turns.json'
    identities = tmp_path / 'private-identities.json'
    truth.write_text(json.dumps({'secret-recording': [word(speaker='secret-label', text='secret-text')]}))
    turns.write_text(json.dumps({'secret-recording': [turn(person_id='secret-person', text='secret-text')]}))
    identities.write_text(json.dumps({'secret-label': {'person_id': 'secret-person'}}))
    command = [
        sys.executable,
        str(root / 'scripts/diarization_eval/score.py'),
        '--truth',
        str(truth),
        '--turns',
        str(turns),
        '--identity-table',
        str(identities),
    ]
    env = {**os.environ, 'PYTHONPATH': str(root)}
    success = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    assert json.loads(success.stdout)['pooled']['engineering_gate'] == 'PASS'
    assert 'secret' not in success.stdout + success.stderr
    truth.write_text('private malformed secret-text')
    failure = subprocess.run(command, env=env, capture_output=True, text=True)
    assert failure.returncode == 1
    assert json.loads(failure.stderr)['status'] == 'FAILED'
    assert 'secret' not in failure.stdout + failure.stderr
    assert str(tmp_path) not in failure.stderr


def test_end_to_end_retains_unaligned_asr_insertions():
    result = score_recording(
        [word()], [turn(is_user=True), turn(2, text='hallucination')], {'owner': {'is_user': True}}
    )
    assert result['end_to_end_alignment']['insertions'] == 1
