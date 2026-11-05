"""Window tail-word parity: a word past the captured extent is unowned, not a clock defect.

The loop sensor's `batch_quarantined ... stage=word_clocks worker_reason=word_clock`
signature (32/30m on 2026-11-04) burns one quarantine per ASR hypothesis in
which a word begins at or after its own window's end. The midpoint ownership
rule in `bounded_window_words` already declares such a word unowned — the
pre-filter `start >= duration` raise was the only thing converting that drop
into a unit-killing `WORD_CLOCK` failure that discarded every kept word of an
already-paid hypothesis and quarantined the unit for a fenced second
recognition that cannot recover a word the window never contained.

These tests pin the new boundary from every observable surface: the pure
ownership function (drop boundaries at sample precision across prod window
lengths), the malformed-clock raises that must survive it, the kept-word
clamp/sequence contracts that must not move, the pipeline envelope (a
tail-only unit now rides the ordinary `empty_asr` lane; a unit with kept words
publishes them), the padded-retry adapter (whose own midpoint filter already
prevented the shape), and the reason-code surface.
"""

import pytest
import numpy as np

from config.batch_pipeline_providers import ProviderConfig
from diarizer.batch_pipeline import PipelineWorker, bounded_window_words
from diarizer.batch_pipeline_models import ParakeetWords
from utils.batch_pipeline.contracts import (
    Priority,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
from utils.batch_pipeline.word_validation import (
    BatchValidationError,
    ValidationReason,
    validate_words,
)

RATE = 16000
SAMPLE = 1 / RATE


def window_result(hypothesis, duration=0.5, *, vad=None, recover_words=None, segment_ids=('synthetic-window',)):
    """Run synthetic units through the worker with scripted ASR hypotheses.

    A flat list is one hypothesis reused for every window; a list of lists is
    a per-window script. The VAD default is one span covering the capture, so
    durations under ``window_seconds`` produce exactly one window.
    """
    script = hypothesis if hypothesis and isinstance(hypothesis[0], list) else [hypothesis]

    class Provider:
        def transcribe_batch(self, samples):
            return [list(script[index % len(script)]) for index, _ in enumerate(samples)]

    saved = []

    def persist(item, payload):
        saved.append(payload)
        return 'synthetic:result'

    worker = PipelineWorker(
        config=ProviderConfig(context_seconds=0),
        language_of=lambda _: 'en',
        decode=lambda _: np.ones(int(duration * RATE), dtype=np.float32),
        vad=vad or (lambda _: [(0.0, duration)]),
        words_providers={'parakeet': Provider()},
        diarizers={'pyannote': lambda _: {'turns': []}},
        persist=persist,
        recover_words=recover_words,
    )
    items = [
        WorkItem(segment_id, 'synthetic-owner', 0.0, 'synthetic:audio', duration, Priority.DEEP)
        for segment_id in segment_ids
    ]
    return worker.process_batch(items), saved, worker


def recover_empty_result(words, duration=0.5, *, max_padded_seconds=272):
    """Drive the padded-retry adapter's clock boundary directly.

    ``words`` are padded-time clocks: the adapter pads two seconds of silence
    on the left and shifts recognized clocks back by exactly that offset.
    """
    adapter = ParakeetWords(None)
    adapter.transcribe_batch = lambda samples: [list(words)]
    samples = np.ones(int(duration * RATE), dtype=np.float32)
    return adapter.recover_empty(samples, max_padded_seconds)


def word(text, start, end):
    return {'word': text, 'timestamp': [start, end]}


# --- The tail word drops at the exact captured-extent boundary --------------------


def test_tail_word_starting_exactly_at_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 0.5, 0.6)], 0.5) == []


def test_tail_word_one_sample_past_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 0.5 + SAMPLE, 0.6)], 0.5) == []


def test_tail_word_one_millisecond_past_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 0.501, 0.6)], 0.5) == []


def test_tail_word_ten_milliseconds_past_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 0.51, 0.6)], 0.5) == []


def test_tail_word_half_a_second_past_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 1.0, 1.4)], 0.5) == []


def test_tail_word_whole_seconds_past_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 2.5, 3.0)], 0.5) == []


def test_tail_word_dropped_in_a_sub_tenth_second_window():
    assert bounded_window_words([word('tail', 0.11, 0.2)], 0.1) == []


def test_tail_word_dropped_in_a_tenth_second_window():
    assert bounded_window_words([word('tail', 0.1, 0.2)], 0.1) == []


def test_tail_word_dropped_in_a_quarter_second_window():
    assert bounded_window_words([word('tail', 0.25, 0.4)], 0.25) == []


def test_tail_word_dropped_in_a_one_second_window():
    assert bounded_window_words([word('tail', 1.0, 1.5)], 1.0) == []


def test_tail_word_dropped_in_a_one_and_a_half_second_window():
    assert bounded_window_words([word('tail', 1.5, 2.0)], 1.5) == []


def test_tail_word_dropped_in_a_two_second_window():
    assert bounded_window_words([word('tail', 2.0, 2.5)], 2.0) == []


def test_tail_word_dropped_in_a_three_second_window():
    assert bounded_window_words([word('tail', 3.0, 3.5)], 3.0) == []


def test_tail_word_dropped_in_a_four_second_window():
    assert bounded_window_words([word('tail', 4.0, 4.5)], 4.0) == []


def test_tail_word_dropped_in_a_five_second_window():
    assert bounded_window_words([word('tail', 5.0, 5.5)], 5.0) == []


def test_tail_word_dropped_in_a_six_second_window():
    assert bounded_window_words([word('tail', 6.0, 6.5)], 6.0) == []


def test_tail_word_dropped_in_an_eight_second_window():
    assert bounded_window_words([word('tail', 8.0, 9.0)], 8.0) == []


def test_tail_word_dropped_in_a_ten_second_window():
    assert bounded_window_words([word('tail', 10.0, 10.5)], 10.0) == []


def test_tail_word_dropped_in_a_fifteen_second_window():
    assert bounded_window_words([word('tail', 15.0, 15.5)], 15.0) == []


def test_tail_word_dropped_in_a_twenty_second_window():
    assert bounded_window_words([word('tail', 20.0, 20.5)], 20.0) == []


def test_tail_word_dropped_in_a_thirty_second_window():
    assert bounded_window_words([word('tail', 30.0, 30.5)], 30.0) == []


def test_tail_word_dropped_in_a_minute_window():
    assert bounded_window_words([word('tail', 60.0, 60.5)], 60.0) == []


def test_tail_word_dropped_in_a_max_unit_window():
    assert bounded_window_words([word('tail', 120.0, 120.5)], 120.0) == []


def test_tail_word_dropped_far_past_a_sub_frame_window():
    assert bounded_window_words([word('tail', 0.5, 0.6)], 0.02) == []


def test_tail_drop_yields_an_empty_hypothesis_not_a_partial_one():
    result = bounded_window_words([word('tail', 0.5, 0.6), word('tail2', 0.7, 0.9)], 0.5)
    assert result == []


def test_several_tail_words_are_all_dropped():
    result = bounded_window_words([word('a', 0.5, 0.55), word('b', 0.6, 0.7), word('c', 0.8, 0.9)], 0.5)
    assert result == []


def test_duplicate_tail_words_are_all_dropped():
    result = bounded_window_words([word('tail', 0.5, 0.6), word('tail', 0.5, 0.6)], 0.5)
    assert result == []


def test_tail_word_with_zero_length_span_at_the_window_end_is_dropped():
    assert bounded_window_words([word('tail', 0.5, 0.5)], 0.5) == []


def test_tail_drop_at_a_zero_duration_window_yields_empty():
    assert bounded_window_words([word('tail', 0.0, 0.1)], 0.0) == []


def test_tail_word_input_dict_is_not_mutated():
    row = word('tail', 0.5, 0.6)
    bounded_window_words([row], 0.5)
    assert row == word('tail', 0.5, 0.6)


def test_tail_word_does_not_appear_in_the_returned_rows():
    result = bounded_window_words([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], 0.5)
    assert result == [word('kept', 0.1, 0.2)]


# --- The tail drop composes with kept words ---------------------------------------


def test_kept_word_before_a_tail_word_survives():
    result = bounded_window_words([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], 0.5)
    assert result == [word('kept', 0.1, 0.2)]


def test_kept_word_after_a_tail_word_survives():
    result = bounded_window_words([word('tail', 0.5, 0.6), word('kept', 0.1, 0.2)], 0.5)
    assert result == [word('kept', 0.1, 0.2)]


def test_kept_words_on_both_sides_of_a_tail_word_survive_in_order():
    result = bounded_window_words([word('a', 0.1, 0.2), word('tail', 0.5, 0.6), word('b', 0.3, 0.4)], 0.5)
    assert result == [word('a', 0.1, 0.2), word('b', 0.3, 0.4)]


def test_tail_word_between_kept_words_does_not_break_the_sequence_pointer():
    # 'b' starts before the dropped tail's start; a pointer advanced by the
    # tail would falsely raise word_sequence on it.
    result = bounded_window_words([word('a', 0.1, 0.2), word('tail', 0.9, 1.0), word('b', 0.3, 0.4)], 0.5)
    assert result == [word('a', 0.1, 0.2), word('b', 0.3, 0.4)]


def test_two_kept_words_after_a_tail_word_stay_monotonic():
    result = bounded_window_words([word('tail', 0.9, 1.0), word('a', 0.1, 0.2), word('b', 0.3, 0.4)], 0.5)
    assert [row['word'] for row in result] == ['a', 'b']


def test_kept_word_after_a_tail_word_keeps_its_unclamped_clocks():
    result = bounded_window_words([word('tail', 0.9, 1.0), word('kept', 0.2, 0.3)], 0.5)
    assert result == [word('kept', 0.2, 0.3)]


def test_tail_word_does_not_change_kept_word_end_clamping():
    result = bounded_window_words([word('kept', 0.44, 0.54), word('tail', 0.5, 0.6)], 0.5)
    assert result == [word('kept', 0.44, 0.5)]


def test_tail_word_does_not_change_negative_start_clamping():
    result = bounded_window_words([word('kept', -0.1, 0.1), word('tail', 0.5, 0.6)], 0.5)
    assert result == [word('kept', 0.0, 0.1)]


def test_tail_word_and_midpoint_rule_agree_at_the_boundary():
    # start == duration drops by the new boundary; midpoint == duration drops
    # by the long-standing ownership rule. Both verdicts must stay identical.
    assert bounded_window_words([word('edge', 0.5, 0.6)], 0.5) == bounded_window_words([word('edge', 0.45, 0.55)], 0.5)


def test_word_starting_just_inside_the_end_with_midpoint_inside_is_kept():
    result = bounded_window_words([word('kept', 0.49, 0.5)], 0.5)
    assert result == [word('kept', 0.49, 0.5)]


def test_word_starting_exactly_at_half_duration_is_kept_and_clamped():
    result = bounded_window_words([word('kept', 0.25, 0.6)], 0.5)
    assert result == [word('kept', 0.25, 0.5)]


def test_blank_tail_word_is_dropped_without_a_sequence_raise():
    assert bounded_window_words([word('  ', 0.5, 0.6)], 0.5) == []


def test_nonstring_tail_word_is_dropped_without_a_sequence_raise():
    result = bounded_window_words([{'word': None, 'timestamp': [0.5, 0.6]}], 0.5)
    assert result == []


def test_reversed_tail_words_only_do_not_raise_word_sequence():
    result = bounded_window_words([word('b', 0.9, 1.0), word('a', 0.6, 0.7)], 0.5)
    assert result == []


def test_blank_kept_word_after_a_tail_word_still_raises():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('tail', 0.9, 1.0), word('  ', 0.1, 0.2)], 0.5)


def test_kept_word_after_multiple_tails_is_the_only_result_row():
    result = bounded_window_words([word('t1', 0.5, 0.6), word('t2', 0.7, 0.8), word('kept', 0.2, 0.3)], 0.5)
    assert result == [word('kept', 0.2, 0.3)]


def test_many_kept_words_with_scattered_tails_preserve_order():
    rows = [
        word('a', 0.05, 0.1),
        word('t1', 0.5, 0.6),
        word('b', 0.15, 0.2),
        word('t2', 0.7, 0.8),
        word('c', 0.25, 0.3),
        word('t3', 0.9, 1.0),
    ]
    result = bounded_window_words(rows, 0.5)
    assert result == [word('a', 0.05, 0.1), word('b', 0.15, 0.2), word('c', 0.25, 0.3)]


# --- Malformed clocks still raise, with or without a dropped tail sibling ----------


def test_nan_start_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', float('nan'), 0.4)], 0.5)


def test_nan_end_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.1, float('nan'))], 0.5)


def test_infinite_start_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', float('inf'), 0.4)], 0.5)


def test_negative_infinite_end_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.1, float('-inf'))], 0.5)


def test_reversed_clocks_inside_the_window_still_raise():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.3, 0.2)], 0.5)


def test_reversed_clocks_past_the_window_still_raise():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.6, 0.5)], 0.5)


def test_reversed_clocks_exactly_at_the_boundary_still_raise():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.5, 0.4)], 0.5)


def test_negative_end_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', -0.4, -0.1)], 0.5)


def test_negative_end_past_the_window_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.6, -0.1)], 0.5)


def test_zero_end_with_negative_start_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', -0.1, 0.0)], 0.5)


def test_malformed_raise_survives_a_dropped_tail_sibling():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('tail', 0.9, 1.0), word('bad', 0.3, 0.2)], 0.5)


def test_unparseable_timestamp_text_still_raises_word_shape():
    with pytest.raises(BatchValidationError, match='word_shape'):
        bounded_window_words([{'word': 'bad', 'timestamp': 'nope'}], 0.5)


def test_missing_timestamp_element_still_raises_word_shape():
    with pytest.raises(BatchValidationError, match='word_shape'):
        bounded_window_words([{'word': 'bad', 'timestamp': [0.1]}], 0.5)


def test_extra_timestamp_element_still_raises_word_shape():
    with pytest.raises(BatchValidationError, match='word_shape'):
        bounded_window_words([{'word': 'bad', 'timestamp': [0.1, 0.2, 0.3]}], 0.5)


def test_reversed_kept_words_still_raise_word_sequence():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('b', 0.3, 0.4), word('a', 0.1, 0.2)], 0.5)


def test_blank_kept_word_still_raises_word_sequence():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('  ', 0.1, 0.2)], 0.5)


def test_nonstring_kept_word_still_raises_word_sequence():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([{'word': None, 'timestamp': [0.1, 0.2]}], 0.5)


def test_reason_tokens_stay_closed():
    assert ValidationReason.WORD_CLOCK.value == 'word_clock'
    assert ValidationReason.WORD_SHAPE.value == 'word_shape'
    assert ValidationReason.WORD_SEQUENCE.value == 'word_sequence'


def test_validation_reason_surface_is_unchanged():
    assert {reason.value for reason in ValidationReason} == {
        'unsupported_language',
        'word_shape',
        'word_clock',
        'word_sequence',
        'vad_nonfinite',
        'vad_order',
        'vad_bounds',
        'empty_asr',
        'no_owned_words',
    }


# --- Kept-word ownership contracts do not move -------------------------------------


def test_kept_word_end_clamps_to_duration_exactly():
    assert bounded_window_words([word('kept', 0.1, 0.6)], 0.5) == [word('kept', 0.1, 0.5)]


def test_kept_word_end_clamps_at_one_sample_precision():
    result = bounded_window_words([word('kept', 0.1, 0.5 + SAMPLE)], 0.5)
    assert result == [word('kept', 0.1, 0.5)]


def test_kept_word_negative_start_clamps_to_zero():
    assert bounded_window_words([word('kept', -0.1, 0.1)], 0.5) == [word('kept', 0.0, 0.1)]


def test_kept_word_midpoint_exactly_zero_is_kept():
    assert bounded_window_words([word('kept', -0.1, 0.1)], 0.5) == [word('kept', 0.0, 0.1)]


def test_kept_word_midpoint_just_below_zero_is_dropped():
    assert bounded_window_words([word('kept', -0.2, 0.19)], 0.5) == []


def test_kept_word_midpoint_exactly_at_duration_is_dropped():
    assert bounded_window_words([word('kept', 0.45, 0.55)], 0.5) == []


def test_kept_word_midpoint_just_under_duration_is_kept():
    result = bounded_window_words([word('kept', 0.44, 0.54)], 0.5)
    assert result == [word('kept', 0.44, 0.5)]


def test_integer_timestamps_still_coerce():
    assert bounded_window_words([{'word': 'kept', 'timestamp': [0, 0]}], 0.5) == [
        {'word': 'kept', 'timestamp': [0.0, 0.0]}
    ]


def test_string_timestamps_still_coerce():
    result = bounded_window_words([{'word': 'kept', 'timestamp': ['0.1', '0.2']}], 0.5)
    assert result == [word('kept', 0.1, 0.2)]


def test_empty_hypothesis_returns_empty():
    assert bounded_window_words([], 0.5) == []


def test_kept_word_confidence_key_is_preserved():
    row = {'word': 'kept', 'timestamp': [0.1, 0.2], 'confidence': 0.9}
    assert bounded_window_words([row], 0.5) == [{'word': 'kept', 'timestamp': [0.1, 0.2], 'confidence': 0.9}]


def test_kept_rows_are_new_dicts_not_input_aliases():
    row = word('kept', 0.1, 0.2)
    result = bounded_window_words([row], 0.5)
    assert result[0] == row and result[0] is not row


def test_bounded_result_revalidates_under_the_unit_validator():
    result = bounded_window_words([word('a', 0.1, 0.2), word('tail', 0.5, 0.6), word('b', 0.3, 0.4)], 0.5)
    assert validate_words(result, 0.5) == result


def test_tail_drop_is_idempotent():
    rows = [word('a', 0.1, 0.2), word('tail', 0.5, 0.6), word('b', 0.3, 0.4)]
    once = bounded_window_words(rows, 0.5)
    assert bounded_window_words(once, 0.5) == once


def test_unit_level_validator_still_rejects_the_tail_clock():
    # The strict unit-level surface keeps its +10 ms bound; the window drop is
    # an ownership decision, never a license for out-of-capture clocks.
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate_words([word('tail', 0.5, 0.6)], 0.5)


# --- Sample-precision boundary sweep around the captured extent --------------------


def test_tail_start_one_sample_before_the_end_is_owned():
    start = 0.5 - SAMPLE
    result = bounded_window_words([word('kept', start, 0.5)], 0.5)
    assert result == [word('kept', start, 0.5)]


def test_tail_start_two_samples_before_the_end_is_owned():
    start = 0.5 - 2 * SAMPLE
    result = bounded_window_words([word('kept', start, 0.5)], 0.5)
    assert result == [word('kept', start, 0.5)]


def test_tail_start_one_sample_after_the_end_is_unowned():
    assert bounded_window_words([word('tail', 0.5 + SAMPLE, 0.6)], 0.5) == []


def test_tail_start_two_samples_after_the_end_is_unowned():
    assert bounded_window_words([word('tail', 0.5 + 2 * SAMPLE, 0.6)], 0.5) == []


# --- Pipeline parity: the quarantine signature becomes publish or empty_asr --------


def test_tail_only_hypothesis_no_longer_fails_at_word_clocks():
    results, _saved, _worker = window_result([word('tail', 0.5, 0.6)])
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_hypothesis_stage_moves_off_word_clocks():
    results, _saved, _worker = window_result([word('tail', 0.5, 0.6)])
    assert results[0].stage == 'assemble_words' and results[0].reason == 'empty_asr'


def test_tail_only_unit_fails_in_tenth_second_window():
    results, _saved, _worker = window_result([word('tail', 0.1, 0.2)], 0.1)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_fails_in_one_second_window():
    results, _saved, _worker = window_result([word('tail', 1.0, 1.2)], 1.0)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_fails_in_two_second_window():
    results, _saved, _worker = window_result([word('tail', 2.0, 2.2)], 2.0)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_fails_in_four_second_window():
    results, _saved, _worker = window_result([word('tail', 4.0, 4.2)], 4.0)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_fails_in_eight_second_window():
    results, _saved, _worker = window_result([word('tail', 8.0, 8.2)], 8.0)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_counts_one_failed_unit():
    results, _saved, worker = window_result([word('tail', 0.5, 0.6)])
    assert worker.counts['failed'] == 1 and results[0].stage == 'assemble_words'


def test_tail_only_unit_never_logs_the_word_clocks_stage(caplog):
    window_result([word('tail', 0.5, 0.6)])
    assert all('stage=word_clocks' not in record.getMessage() for record in caplog.records)


def test_kept_word_with_tail_sibling_publishes_success():
    results, saved, _worker = window_result([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)])
    assert results == [WorkResult('synthetic-window', 'synthetic:result', 'success')]
    assert saved[0]['words'] == [word('kept', 0.1, 0.2)]


def test_published_words_exclude_the_tail_sibling():
    _results, saved, _worker = window_result([word('a', 0.05, 0.1), word('tail', 0.5, 0.6), word('b', 0.2, 0.3)])
    assert [row['word'] for row in saved[0]['words']] == ['a', 'b']


def test_published_word_clocks_stay_clamped_to_the_capture():
    _results, saved, _worker = window_result([word('kept', 0.4, 0.5), word('tail', 0.5, 0.9)])
    assert saved[0]['words'] == [word('kept', 0.4, 0.5)]


def test_publishing_unit_in_one_second_window():
    results, saved, _worker = window_result([word('kept', 0.2, 0.5), word('tail', 1.0, 1.2)], 1.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 0.2, 0.5)]


def test_publishing_unit_in_two_second_window():
    results, saved, _worker = window_result([word('kept', 1.0, 2.2), word('tail', 2.0, 2.4)], 2.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 1.0, 2.0)]


def test_publishing_unit_in_four_second_window():
    results, saved, _worker = window_result([word('kept', 3.0, 4.4), word('tail', 4.0, 4.4)], 4.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 3.0, 4.0)]


def test_publishing_unit_in_eight_second_window():
    results, saved, _worker = window_result([word('kept', 7.0, 8.4), word('tail', 8.0, 8.4)], 8.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 7.0, 8.0)]


def test_publishing_unit_in_tenth_second_window():
    results, saved, _worker = window_result([word('kept', 0.02, 0.12), word('tail', 0.1, 0.2)], 0.1)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 0.02, 0.1)]


def test_tail_sibling_does_not_mark_the_publishing_unit_failed():
    _results, _saved, worker = window_result([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)])
    assert worker.counts['failed'] == 0


def test_publishing_unit_emits_no_batch_worker_failed_log(caplog):
    window_result([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)])
    assert all('batch_worker_failed' not in record.getMessage() for record in caplog.records)


def test_publishing_unit_log_has_no_word_clocks_token(caplog):
    window_result([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)])
    assert all('word_clocks' not in record.getMessage() for record in caplog.records)


def test_malformed_word_still_fails_at_word_clocks_in_pipeline():
    results, saved, _worker = window_result([word('bad', -1, 0)])
    assert results == [ValidationFailureWork('synthetic-window', 'word_clocks', 'word_clock')]
    assert saved == []


def test_one_malformed_hypothesis_blocks_its_unit_once():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, _saved, worker = window_result([word('bad', 3, 2)], 0.5, vad=vad)
    assert results == [ValidationFailureWork('synthetic-window', 'word_clocks', 'word_clock')]
    assert worker.counts['failed'] == 1


def test_both_windows_tail_only_yields_one_empty_asr_failure():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, _saved, worker = window_result([[word('t1', 0.2, 0.3)], [word('t2', 0.2, 0.3)]], 0.5, vad=vad)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]
    assert worker.counts['failed'] == 1


def test_tail_word_in_the_first_window_keeps_the_second_windows_words():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, saved, _worker = window_result([[word('tail', 0.2, 0.3)], [word('kept', 0.05, 0.15)]], 0.5, vad=vad)
    assert results[0].outcome == 'success'
    assert saved[0]['words'] == [{'word': 'kept', 'timestamp': pytest.approx([0.35, 0.45])}]


def test_tail_word_in_the_second_window_keeps_the_first_windows_words():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, saved, _worker = window_result([[word('kept', 0.05, 0.15)], [word('tail', 0.2, 0.3)]], 0.5, vad=vad)
    assert results[0].outcome == 'success'
    assert saved[0]['words'] == [{'word': 'kept', 'timestamp': [0.05, 0.15]}]


def test_tail_only_first_window_with_real_second_window_publishes():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, saved, _worker = window_result([[word('tail', 0.2, 0.4)], [word('kept', 0.1, 0.2)]], 0.5, vad=vad)
    assert results[0].outcome == 'success'
    assert saved[0]['words'] == [{'word': 'kept', 'timestamp': [0.4, 0.5]}]


def test_silence_unit_without_windows_is_unaffected():
    results, saved, _worker = window_result([word('kept', 0.1, 0.2)], 0.5, vad=lambda _: [])
    assert results == [WorkResult('synthetic-window', 'synthetic:result', 'silence')]
    assert saved[0]['words'] == []


def test_plain_empty_hypothesis_keeps_the_empty_asr_envelope():
    results, _saved, _worker = window_result([])
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]


def test_tail_only_unit_rides_the_recovery_handoff_when_a_retry_exists():
    results, _saved, _worker = window_result([word('tail', 0.5, 0.6)], recover_words=lambda samples, bound: [])
    assert isinstance(results[0], RecoveryWork)
    assert results[0].reason == 'empty_asr' and results[0].padded_retry_empty is True


def test_kept_and_tail_unit_still_publishes_with_a_retry_configured():
    results, saved, _worker = window_result(
        [word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], recover_words=lambda samples, bound: []
    )
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 0.1, 0.2)]


# --- The padded-retry adapter's own midpoint filter is unchanged -------------------


def test_recover_empty_still_filters_its_own_tail_word():
    # Padded clocks: (2.6, 2.7) shifts back to (0.6, 0.7), past the 0.5 s capture.
    assert recover_empty_result([word('tail', 2.6, 2.7)]) == []


def test_recover_empty_kept_word_survives_a_tail_sibling():
    result = recover_empty_result([word('kept', 2.1, 2.2), word('tail', 2.6, 2.7)])
    assert result == [{'word': 'kept', 'timestamp': pytest.approx([0.1, 0.2])}]


def test_recover_empty_tail_only_hypothesis_returns_empty():
    assert recover_empty_result([word('t1', 2.6, 2.7), word('t2', 2.8, 2.9)]) == []


def test_recover_empty_result_passes_the_unit_validator():
    result = recover_empty_result([word('kept', 2.1, 2.2), word('tail', 2.6, 2.7)])
    clocks = [row['timestamp'] for row in validate_words(result, 0.5)]
    assert len(clocks) == 1 and clocks[0] == pytest.approx([0.1, 0.2])


def test_recover_empty_oversize_still_returns_none(monkeypatch):
    import diarizer.batch_pipeline_models as models

    monkeypatch.setattr(models, 'padded_retry_fits', lambda samples, bound: False)
    assert recover_empty_result([word('kept', 0.1, 0.2)]) is None


def test_recover_empty_window_boundary_matches_the_worker_boundary():
    # The adapter shifts padded clocks by -2 s; a word starting exactly at the
    # real duration must drop there exactly like it drops in the worker.
    duration = 0.5
    assert recover_empty_result([word('tail', duration + 2.0, duration + 2.1)], duration) == []


# --- Real batch-geometry window lengths --------------------------------------------
#
# Forced cuts make batch windows of ``window_seconds`` (30 s), context padding
# stretches them to 32 s, and units reach ``max_unit_seconds`` (7200 s). The
# boundary is pinned at the lengths production actually cuts.


def test_tail_word_dropped_in_a_45_second_window():
    assert bounded_window_words([word('tail', 45.0, 45.5)], 45.0) == []


def test_tail_word_dropped_in_a_90_second_window():
    assert bounded_window_words([word('tail', 90.0, 90.5)], 90.0) == []


def test_tail_word_dropped_in_a_180_second_window():
    assert bounded_window_words([word('tail', 180.0, 180.5)], 180.0) == []


def test_tail_word_dropped_in_a_300_second_window():
    assert bounded_window_words([word('tail', 300.0, 300.5)], 300.0) == []


def test_tail_word_dropped_in_a_600_second_window():
    assert bounded_window_words([word('tail', 600.0, 600.5)], 600.0) == []


def test_tail_word_dropped_in_a_1800_second_window():
    assert bounded_window_words([word('tail', 1800.0, 1800.5)], 1800.0) == []


def test_tail_word_dropped_in_an_hour_window():
    assert bounded_window_words([word('tail', 3600.0, 3600.5)], 3600.0) == []


def test_tail_word_dropped_in_a_max_unit_window_7200_seconds():
    assert bounded_window_words([word('tail', 7200.0, 7200.5)], 7200.0) == []


def test_sequence_pointer_survives_a_tail_word_in_a_30_second_window():
    result = bounded_window_words([word('a', 1.0, 2.0), word('tail', 30.0, 30.5), word('b', 3.0, 4.0)], 30.0)
    assert result == [word('a', 1.0, 2.0), word('b', 3.0, 4.0)]


def test_sequence_pointer_survives_a_tail_word_in_a_600_second_window():
    result = bounded_window_words([word('a', 10.0, 20.0), word('tail', 600.0, 600.5), word('b', 30.0, 40.0)], 600.0)
    assert result == [word('a', 10.0, 20.0), word('b', 30.0, 40.0)]


def test_midpoint_ownership_unchanged_in_a_60_second_window():
    assert bounded_window_words([word('edge', 60.0, 60.2)], 60.0) == []
    assert bounded_window_words([word('kept', 59.8, 60.1)], 60.0) == [word('kept', 59.8, 60.0)]


def test_midpoint_ownership_unchanged_in_a_300_second_window():
    assert bounded_window_words([word('edge', 300.5, 300.8)], 300.0) == []
    assert bounded_window_words([word('kept', 299.8, 300.1)], 300.0) == [word('kept', 299.8, 300.0)]


# --- Retry spend: the drop must not buy a second GPU quantum -----------------------


def test_publishing_unit_with_a_tail_sibling_never_runs_the_empty_retry():
    calls = []

    def recover_words(samples, bound):
        calls.append(len(samples))
        return []

    results, saved, _worker = window_result(
        [word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], recover_words=recover_words
    )
    assert calls == [] and results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 0.1, 0.2)]


def test_tail_only_unit_runs_the_empty_retry_exactly_once():
    calls = []

    def recover_words(samples, bound):
        calls.append(len(samples))
        return []

    results, _saved, _worker = window_result([word('tail', 0.5, 0.6)], recover_words=recover_words)
    assert len(calls) == 1
    assert isinstance(results[0], RecoveryWork) and results[0].reason == 'empty_asr'


def test_tail_only_unit_retry_rides_the_padded_retry_evidence():
    results, _saved, _worker = window_result([word('tail', 0.5, 0.6)], recover_words=lambda samples, bound: [])
    assert results[0].padded_retry_empty is True


def test_recover_empty_receives_samples_padded_around_the_capture():
    adapter = ParakeetWords(None)
    seen = {}

    def transcribe(samples):
        seen['length'] = len(samples[0])
        return [[]]

    adapter.transcribe_batch = transcribe
    samples = np.ones(int(0.5 * RATE), dtype=np.float32)
    adapter.recover_empty(samples, 272)
    left = 2 * RATE
    right = max(2 * RATE, 8 * RATE - len(samples) - left)
    assert seen['length'] == len(samples) + left + right


# --- Batch and payload parity -------------------------------------------------------


def test_two_units_with_tail_siblings_publish_independently():
    results, saved, _worker = window_result([word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], segment_ids=('u1', 'u2'))
    assert [result.outcome for result in results] == ['success', 'success']
    assert len(saved) == 2 and all(payload['words'] == [word('kept', 0.1, 0.2)] for payload in saved)


def test_two_windows_kept_words_concatenate_in_window_order():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    scripts = [[word('first', 0.05, 0.15)], [word('second', 0.05, 0.15)]]
    _results, saved, _worker = window_result(scripts, 0.5, vad=vad)
    assert saved[0]['words'] == [
        {'word': 'first', 'timestamp': pytest.approx([0.05, 0.15])},
        {'word': 'second', 'timestamp': pytest.approx([0.35, 0.45])},
    ]


def test_published_rows_keep_provider_payload_keys():
    rows = [{'word': 'kept', 'timestamp': [0.1, 0.2], 'confidence': 0.75}, word('tail', 0.5, 0.6)]
    _results, saved, _worker = window_result(rows)
    assert saved[0]['words'] == [{'word': 'kept', 'timestamp': [0.1, 0.2], 'confidence': 0.75}]


def test_silence_counts_are_not_inflated_by_tail_words():
    _results, _saved, worker = window_result([word('kept', 0.1, 0.2)], 0.5, vad=lambda _: [])
    assert worker.counts['silence'] == 1 and worker.counts['failed'] == 0


def test_tail_drop_precedes_word_sequence_for_later_blank_kept_words():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('tail', 0.9, 1.0), word('kept', 0.1, 0.2), word('  ', 0.3, 0.4)], 0.5)


def test_publishing_unit_in_a_sixteen_second_window():
    results, saved, _worker = window_result([word('kept', 15.0, 16.2), word('tail', 16.0, 16.4)], 16.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 15.0, 16.0)]


def test_publishing_unit_in_a_24_second_window():
    results, saved, _worker = window_result([word('kept', 23.0, 24.2), word('tail', 24.0, 24.4)], 24.0)
    assert results[0].outcome == 'success' and saved[0]['words'] == [word('kept', 23.0, 24.0)]


def test_tail_only_unit_in_a_sixteen_second_window_rides_empty_asr():
    results, _saved, _worker = window_result([word('tail', 16.0, 16.2)], 16.0)
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]
