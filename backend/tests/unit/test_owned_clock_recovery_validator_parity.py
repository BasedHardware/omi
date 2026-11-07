"""The recovery recognizer's response validator meets the shared ownership contract.

The fenced recovery lane validated recognizer words with the strict
``validate_words`` tolerance alone, so a trailing clock past the capture or a
wholly-outside ghost raised ``word_clock`` and the whole second recognition
was classified as an invalid response — the same unit, the same audio, the
same clock defect, quarantined again. The lane now validates through the
shared ``bounded_window_words``: wholly-outside clocks drop, straddlers clamp,
malformed in-domain clocks still fail, and an owned-words-empty response is
the honest ``empty_asr`` (or ``MultilingualEmpty`` for the multilingual
recognizer) the disposition ladder already settles.

These tests pin the lane from its pure validator and through the same
``at_stage`` wrapper its callers use: geometry, both empty branches, the
raise surface, and parity with the GPU window function. Kept words retain
the recognizer's ``text`` alongside the added ``word`` key, exactly as the
lane has always passed recognizer rows through.
"""

import pytest

from utils.batch_pipeline.recovery_disposition import RecoveryFailure, at_stage
from utils.batch_pipeline.recovery_recognizers import MultilingualEmpty, validate_response
from utils.batch_pipeline.word_validation import BatchValidationError, bounded_window_words

SPANS = [{'start': 0.0, 'end': 0.5}]


def word(text, start, end):
    return {'text': text, 'timestamp': [start, end], 'word': text}


def raw_word(text, start, end):
    return {'text': text, 'timestamp': [start, end]}


def validate(raw, duration=0.5, multilingual=False, language='en'):
    return validate_response((list(raw), language), duration, SPANS, multilingual=multilingual)


# --- Tail overshoot clamps ----------------------------------------------------------


def test_recovery_word_ending_past_the_tolerance_clamps_to_the_capture():
    words, language = validate([raw_word('kept', 0.1, 0.8)])
    assert words == [word('kept', 0.1, 0.5)] and language == 'en'


def test_recovery_word_ending_within_the_tolerance_clamps_too():
    words, _language = validate([raw_word('kept', 0.1, 0.51)])
    assert words == [word('kept', 0.1, 0.5)]


def test_recovery_word_starting_exactly_at_the_capture_end_drops_while_kept_words_survive():
    words, _language = validate([raw_word('kept', 0.1, 0.3), raw_word('tail', 0.5, 0.6)])
    assert words == [word('kept', 0.1, 0.3)]


def test_recovery_words_wholly_past_the_capture_classify_as_empty_asr():
    # Every claimed word lies past the captured extent: the capture owns no
    # words, so the response is an honest empty, not an invalid one.
    with pytest.raises(RecoveryFailure) as raised:
        validate([raw_word('t1', 0.6, 0.7), raw_word('t2', 0.8, 0.9)])
    assert raised.value.reason == 'empty_asr'


# --- Pre-window ghost clocks drop ----------------------------------------------------


def test_recovery_ghost_clock_drops_while_kept_and_tail_geometry_resolves():
    words, _language = validate([raw_word('ghost', -3.0, -1.0), raw_word('kept', 0.1, 0.3), raw_word('tail', 0.5, 0.6)])
    assert words == [word('kept', 0.1, 0.3)]


def test_recovery_ghost_and_kept_word_leaves_only_the_kept_word():
    words, _language = validate([raw_word('ghost', -3.0, -1.0), raw_word('kept', 0.1, 0.3)])
    assert words == [word('kept', 0.1, 0.3)]


def test_recovery_ghost_straddling_zero_clamps_to_the_capture_start():
    words, _language = validate([raw_word('kept', -0.1, 0.3)])
    assert words == [word('kept', 0.0, 0.3)]


# --- Empty classifications -------------------------------------------------------------


def test_recovery_ghost_only_response_is_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        validate([raw_word('ghost', -3.0, -1.0)])
    assert raised.value.stage == 'response_validation' and raised.value.reason == 'empty_asr'


def test_recovery_tail_only_response_is_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        validate([raw_word('tail', 0.5, 0.6)])
    assert raised.value.reason == 'empty_asr'


def test_recovery_ghost_and_tail_only_response_is_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        validate([raw_word('ghost', -3.0, -1.0), raw_word('tail', 0.6, 0.7)])
    assert raised.value.reason == 'empty_asr'


def test_recovery_ghost_only_response_is_multilingual_empty_when_multilingual():
    with pytest.raises(MultilingualEmpty) as raised:
        validate([raw_word('ghost', -3.0, -1.0)], multilingual=True)
    assert raised.value.duration == 0.5 and raised.value.spans == SPANS


def test_recovery_tail_only_response_is_multilingual_empty_when_multilingual():
    with pytest.raises(MultilingualEmpty) as raised:
        validate([raw_word('tail', 0.6, 0.7)], multilingual=True)
    assert raised.value.reason == 'empty_asr'


def test_recovery_empty_raw_response_stays_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        validate([])
    assert raised.value.reason == 'empty_asr'


def test_recovery_multilingual_empty_is_itself_an_empty_asr_failure():
    error = MultilingualEmpty(0.5, SPANS)
    assert error.stage == 'response_validation' and error.reason == 'empty_asr'


# --- Malformed in-domain clocks still raise ---------------------------------------------


def test_recovery_reversed_in_window_clocks_raise_word_clock():
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate([raw_word('bad', 0.3, 0.2)])


def test_recovery_reversed_across_zero_clocks_raise_word_clock():
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate([raw_word('bad', 0.6, -0.1)])


def test_recovery_nan_clock_raises_word_clock():
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate([{'text': 'bad', 'timestamp': [0.1, float('nan')]}])


def test_recovery_blank_token_raises_word_sequence():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        validate([raw_word('  ', 0.1, 0.3)])


def test_recovery_unparseable_timestamp_raises_word_shape():
    with pytest.raises(BatchValidationError, match='word_shape'):
        validate([{'text': 'bad', 'timestamp': 'nope'}])


def test_recovery_wrong_response_shape_raises():
    with pytest.raises(ValueError, match='response shape'):
        validate_response('nope', 0.5, SPANS, multilingual=False)


def test_recovery_empty_detected_language_raises():
    with pytest.raises(ValueError, match='response language'):
        validate([raw_word('kept', 0.1, 0.3)], language='')


def test_recovery_raise_through_the_callers_at_stage_wrapper_is_invalid_response():
    # recovery_recognizers wraps this validator in
    # at_stage('response_validation', 'invalid_response', ...): a raw
    # BatchValidationError must surface as that bounded recovery failure.
    with pytest.raises(RecoveryFailure) as raised:
        at_stage('response_validation', 'invalid_response', lambda: validate([raw_word('bad', 0.3, 0.2)]))
    assert raised.value.stage == 'response_validation' and raised.value.reason == 'invalid_response'


def test_recovery_empty_through_the_callers_at_stage_wrapper_stays_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        at_stage('response_validation', 'invalid_response', lambda: validate([]))
    assert raised.value.reason == 'empty_asr'


def test_recovery_multilingual_empty_passes_through_the_callers_at_stage_wrapper():
    with pytest.raises(MultilingualEmpty):
        at_stage(
            'response_validation',
            'invalid_response',
            lambda: validate_response(([raw_word('ghost', -3.0, -1.0)], 'en'), 0.5, SPANS, multilingual=True),
        )


# --- Payload-word contracts ---------------------------------------------------------------


def test_recovery_kept_words_carry_both_the_source_text_and_the_word_key():
    words, _language = validate([raw_word('kept', 0.1, 0.3)])
    assert words == [word('kept', 0.1, 0.3)]


def test_recovery_words_preserve_extra_keys():
    words, _language = validate([{'text': 'kept', 'timestamp': [0.1, 0.3], 'confidence': 0.9}])
    assert words == [{'text': 'kept', 'timestamp': [0.1, 0.3], 'word': 'kept', 'confidence': 0.9}]


def test_recovery_kept_word_order_is_preserved():
    words, _language = validate([raw_word('a', 0.05, 0.1), raw_word('b', 0.2, 0.3)])
    assert [row['word'] for row in words] == ['a', 'b']


def test_recovery_detected_language_passes_through():
    _words, language = validate([raw_word('kept', 0.1, 0.3)], language='ja')
    assert language == 'ja'


def test_recovery_mixed_geometry_keeps_only_owned_words():
    words, _language = validate(
        [
            raw_word('ghost', -3.0, -1.0),
            raw_word('a', 0.05, 0.2),
            raw_word('straddle', 0.4, 0.55),
            raw_word('tail', 0.5, 0.62),
        ]
    )
    assert words == [word('a', 0.05, 0.2), word('straddle', 0.4, 0.5)]


# --- More multilingual and geometry coverage -------------------------------------------


def test_recovery_ghost_and_tail_only_response_is_multilingual_empty_when_multilingual():
    with pytest.raises(MultilingualEmpty) as raised:
        validate([raw_word('ghost', -3.0, -1.0), raw_word('tail', 0.5, 0.6)], multilingual=True)
    assert raised.value.duration == 0.5


def test_recovery_multilingual_lane_publishes_kept_words_normally():
    words, language = validate([raw_word('ghost', -3.0, -1.0), raw_word('kept', 0.1, 0.3)], multilingual=True)
    assert words == [word('kept', 0.1, 0.3)] and language == 'en'


def test_recovery_straddler_on_a_two_second_capture_clamps_to_the_start():
    words, _language = validate([raw_word('kept', -0.1, 0.4)], duration=2.0)
    assert words == [word('kept', 0.0, 0.4)]


def test_recovery_tail_drops_while_a_kept_word_survives_on_a_two_second_capture():
    words, _language = validate([raw_word('kept', 0.5, 1.0), raw_word('tail', 2.0, 2.1)], duration=2.0)
    assert words == [word('kept', 0.5, 1.0)]


def test_recovery_ghosts_between_kept_words_preserve_their_order():
    words, _language = validate([raw_word('a', 0.05, 0.1), raw_word('ghost', -1.0, -0.5), raw_word('b', 0.2, 0.3)])
    assert [row['word'] for row in words] == ['a', 'b']


def test_recovery_validator_never_mutates_the_spans():
    spans = [{'start': 0.0, 'end': 0.5}]
    validate_response(([raw_word('kept', 0.1, 0.3)], 'en'), 0.5, spans, multilingual=False)
    assert spans == [{'start': 0.0, 'end': 0.5}]


def test_recovery_clamped_output_passes_the_strict_validator_at_two_seconds():
    from utils.batch_pipeline.word_validation import validate_words

    words, _language = validate([raw_word('straddle', 0.1, 2.05)], duration=2.0)
    assert validate_words(words, 2.0) == words


# --- Parity with the GPU window function -----------------------------------------------------


def mapped(raw_rows):
    return [{'text': row['text'], 'word': row['text'], 'timestamp': row['timestamp']} for row in raw_rows]


def test_recovery_validator_matches_the_gpu_window_function_on_mixed_geometry():
    raw = [raw_word('ghost', -3.0, -1.0), raw_word('straddle', -0.1, 0.3), raw_word('kept', 0.2, 0.4)]
    words, _language = validate(raw)
    assert words == bounded_window_words(mapped(raw), 0.5)


def test_recovery_validator_matches_the_gpu_window_function_on_tail_geometry():
    raw = [raw_word('kept', 0.1, 0.2), raw_word('tail', 0.5, 0.62)]
    words, _language = validate(raw)
    assert words == bounded_window_words(mapped(raw), 0.5)


def test_recovery_validator_output_always_passes_the_strict_validator():
    from utils.batch_pipeline.word_validation import validate_words

    words, _language = validate([raw_word('straddle', -0.1, 0.55)])
    assert validate_words(words, 0.5) == words


def test_recovery_validator_never_mutates_the_raw_response():
    raw = [raw_word('ghost', -3.0, -1.0), raw_word('kept', 0.1, 0.3)]
    snapshot = [{'text': row['text'], 'timestamp': list(row['timestamp'])} for row in raw]
    validate(raw)
    assert raw == snapshot
