"""Pre-window ghost parity: a clock ending before its window is unowned, not a clock defect.

The loop sensor's `batch_quarantined ... stage=word_clocks worker_reason=word_clock`
signature burns one quarantine per ASR hypothesis in which a clock ends before
its own window begins. TDT start-state ghosts are the documented mechanism (the
padded retry exists for the same decoder behavior): a window cut from
mid-utterance audio can have the predecessor's tail anchored at negative
window-local time. `bounded_window_words` already declared such a word unowned
— the midpoint rule rejects it — but the pre-filter raised `WORD_CLOCK` on it,
discarding every kept word of an already-paid hypothesis and quarantining the
capture for a fenced second recognition that cannot recover a word the window
never contained. The wholly-outside drop is now symmetric: before the window
(``end < 0`` or zero end with a negative start) drops exactly like past the
window (``start >= duration``); clocks malformed inside the window's domain
(inverted, non-finite, unparsable) still fail closed.

These tests pin the completed boundary from every observable surface: the pure
ownership function (drop boundaries at sample precision across prod window
lengths), the malformed-clock raises that must survive it, the kept-word
clamp/sequence contracts that must not move, the pipeline envelope (a
ghost-only unit rides the ordinary `empty_asr` machinery; a unit with kept
words publishes them; a ghost-only retry is a valid empty the padded retry
may answer), the padded-retry adapter (whose left-padding band is exactly the
ghost producer), the shared-home re-export, and the reason-code surface.
"""

import pytest
import numpy as np

from config.batch_pipeline_providers import ProviderConfig
from diarizer.batch_pipeline import PipelineWorker
from diarizer.batch_pipeline import bounded_window_words as diarizer_bounded_window_words
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
    bounded_window_words,
    validate_words,
)

RATE = 16000
SAMPLE = 1 / RATE


def word(text, start, end):
    return {'word': text, 'timestamp': [start, end]}


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
    Clocks here use quarter-second magnitudes so the shift is float-exact.
    """
    adapter = ParakeetWords(None)
    adapter.transcribe_batch = lambda samples: [list(words)]
    samples = np.ones(int(duration * RATE), dtype=np.float32)
    return adapter.recover_empty(samples, max_padded_seconds)


# --- The pre-window ghost drops at every captured-extent boundary ---------------
def test_ghost_ending_before_a_0_02_second_window_drops():
    assert bounded_window_words([word('ghost', -0.005, -0.001)], 0.02) == []


def test_ghost_ending_before_a_0_1_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 0.1) == []


def test_ghost_ending_before_a_0_25_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 0.25) == []


def test_ghost_ending_before_a_0_5_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 0.5) == []


def test_ghost_ending_before_a_1_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 1.0) == []


def test_ghost_ending_before_a_2_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 2.0) == []


def test_ghost_ending_before_a_4_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 4.0) == []


def test_ghost_ending_before_a_8_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 8.0) == []


def test_ghost_ending_before_a_30_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 30.0) == []


def test_ghost_ending_before_a_600_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 600.0) == []


def test_ghost_ending_before_a_3600_0_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.001)], 3600.0) == []


def test_ghost_ending_one_sample_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.000125, -6.25e-05)], 0.5) == []


def test_ghost_ending_ten_samples_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.000625, -6.25e-05)], 0.5) == []


def test_ghost_ending_half_a_millisecond_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.001, -0.0005)], 0.5) == []


def test_ghost_ending_ten_milliseconds_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.01, -0.002)], 0.5) == []


def test_ghost_ending_fifty_milliseconds_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.1, -0.05)], 0.5) == []


def test_ghost_ending_an_eighth_of_the_window_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.249, -0.125)], 0.5) == []


def test_ghost_ending_half_the_window_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -0.5, -0.25)], 0.5) == []


def test_ghost_ending_whole_windows_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -2.0, -1.0)], 0.5) == []


def test_ghost_ending_far_past_the_window_before_a_half_second_window_drops():
    assert bounded_window_words([word('ghost', -100.0, -99.0)], 0.5) == []


def test_zero_end_with_negative_start_drops_at_every_negative_magnitude():
    for start in (-0.001, -0.01, -0.1, -1.0, -30.0):
        assert bounded_window_words([word('ghost', start, 0.0)], 0.5) == []


def test_negative_zero_start_with_zero_end_is_a_point_word_not_a_ghost():
    # -0.0 == 0.0: the start is not negative, the clock is ordering-legal,
    # and the midpoint rule owns the point at the window's first sample.
    assert bounded_window_words([word('edge', -0.0, 0.0)], 0.5) == [word('edge', 0.0, 0.0)]


def test_ghost_touching_zero_from_below_drops_but_straddler_past_zero_clamps():
    assert bounded_window_words([word('ghost', -0.01, -0.0)], 0.5) == []
    assert bounded_window_words([word('kept', -0.01, 0.01)], 0.5) == [word('kept', 0.0, 0.01)]


# --- Malformed clocks still raise; only wholly-outside words drop ---------------


def test_reversed_clocks_across_zero_still_raise():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', 0.6, -0.1)], 0.5)


def test_reversed_clocks_wholly_below_zero_still_raise():
    # start > end is malformed even outside the window's domain: the drop is
    # for ordering-legal ghosts only.
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', -0.1, -0.2)], 0.5)


def test_nan_end_with_negative_start_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', -0.5, float('nan'))], 0.5)


def test_nan_start_with_negative_end_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', float('nan'), -0.1)], 0.5)


def test_infinite_negative_end_still_raises():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('bad', -1.0, float('-inf'))], 0.5)


def test_unparseable_timestamp_still_raises_word_shape():
    with pytest.raises(BatchValidationError, match='word_shape'):
        bounded_window_words([{'word': 'bad', 'timestamp': 'nope'}], 0.5)


def test_blank_in_window_word_still_raises_word_sequence():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('  ', 0.1, 0.2)], 0.5)


def test_blank_ghost_drops_without_a_sequence_raise():
    # A wholly-outside word is unowned regardless of its token text: the
    # sequence gate only judges words the window could own.
    assert bounded_window_words([word('  ', -3.0, -1.0)], 0.5) == []


def test_none_text_ghost_drops_without_a_raise():
    assert bounded_window_words([{'word': None, 'timestamp': [-3.0, -1.0]}], 0.5) == []


def test_non_string_ghost_drops_without_a_raise():
    assert bounded_window_words([{'word': 12, 'timestamp': [-3.0, -1.0]}], 0.5) == []


def test_in_window_malformed_raise_survives_a_ghost_sibling():
    with pytest.raises(BatchValidationError, match='word_clock'):
        bounded_window_words([word('ghost', -3.0, -1.0), word('bad', 0.3, 0.2)], 0.5)


def test_in_window_blank_raise_survives_a_ghost_sibling():
    with pytest.raises(BatchValidationError, match='word_sequence'):
        bounded_window_words([word('ghost', -3.0, -1.0), word('  ', 0.3, 0.4)], 0.5)


# --- Ghosts and kept words: order, clamps, purity -------------------------------
def test_ghost_before_a_kept_word_drops_without_disturbing_it():
    assert bounded_window_words([word('ghost', -3.0, -1.0), word('kept', 0.1, 0.2)], 0.5) == [word('kept', 0.1, 0.2)]


def test_ghost_after_a_kept_word_drops_without_a_sequence_raise():
    assert bounded_window_words([word('kept', 0.1, 0.2), word('ghost', -3.0, -1.0)], 0.5) == [word('kept', 0.1, 0.2)]


def test_ghost_between_kept_words_drops_and_preserves_their_order():
    assert bounded_window_words([word('a', 0.1, 0.2), word('ghost', -3.0, -1.0), word('b', 0.3, 0.4)], 0.5) == [
        word('a', 0.1, 0.2),
        word('b', 0.3, 0.4),
    ]


def test_two_flanking_ghosts_drop_and_both_kept_words_survive():
    assert bounded_window_words(
        [word('g1', -5.0, -4.0), word('a', 0.1, 0.2), word('b', 0.3, 0.4), word('g2', -2.0, -1.0)], 0.5
    ) == [word('a', 0.1, 0.2), word('b', 0.3, 0.4)]


def test_three_ghosts_and_one_kept_word_leave_only_the_kept_word():
    assert bounded_window_words(
        [word('g1', -5.0, -4.0), word('g2', -3.0, -2.0), word('kept', 0.1, 0.2), word('g3', -1.0, -0.5)], 0.5
    ) == [word('kept', 0.1, 0.2)]


def test_ghost_and_tail_word_on_opposite_edges_both_drop():
    assert bounded_window_words([word('ghost', -3.0, -1.0), word('kept', 0.1, 0.2), word('tail', 0.5, 0.6)], 0.5) == [
        word('kept', 0.1, 0.2)
    ]


def test_ghost_straddler_and_tail_leave_the_clamped_straddler():
    assert bounded_window_words(
        [word('ghost', -3.0, -1.0), word('straddle', -0.1, 0.3), word('tail', 0.5, 0.6)], 0.5
    ) == [word('straddle', 0.0, 0.3)]


def test_ghost_and_a_point_word_at_the_window_start_leave_the_point():
    assert bounded_window_words([word('ghost', -3.0, -1.0), word('point', 0.0, 0.0)], 0.5) == [word('point', 0.0, 0.0)]


def test_duplicate_ghosts_all_drop():
    assert bounded_window_words([word('ghost', -3.0, -1.0), word('ghost', -3.0, -1.0)], 0.5) == []


def test_ghost_only_hypothesis_yields_an_empty_kept_set():
    assert bounded_window_words([word('ghost', -3.0, -1.0)], 0.5) == []


def test_ghost_and_negative_straddler_whose_midpoint_is_negative_both_drop():
    assert bounded_window_words([word('ghost', -3.0, -1.0), word('straddle', -0.2, 0.1)], 0.5) == []


def test_kept_words_keep_their_extra_keys_and_clamped_clocks():
    rows = [{'word': 'kept', 'timestamp': [-0.1, 0.3], 'confidence': 0.9}, {'word': 'ghost', 'timestamp': [-3.0, -1.0]}]
    assert bounded_window_words(rows, 0.5) == [{'word': 'kept', 'timestamp': [0.0, 0.3], 'confidence': 0.9}]


def test_ghost_input_rows_are_never_mutated():
    rows = [word('kept', 0.1, 0.2), word('ghost', -3.0, -1.0)]
    snapshot = [{'word': row['word'], 'timestamp': list(row['timestamp'])} for row in rows]
    bounded_window_words(rows, 0.5)
    assert rows == snapshot


def test_bounded_output_is_idempotent():
    once = bounded_window_words([word('ghost', -3.0, -1.0), word('kept', -0.1, 0.3), word('tail', 0.5, 0.6)], 0.5)
    assert bounded_window_words(once, 0.5) == once


def test_kept_output_always_passes_the_strict_validator():
    rows = [word('ghost', -3.0, -1.0), word('kept', -0.1, 0.3)]
    kept = bounded_window_words(rows, 0.5)
    assert validate_words(kept, 0.5) == kept


def test_empty_hypothesis_stays_empty():
    assert bounded_window_words([], 0.5) == []


# --- Pipeline envelope -----------------------------------------------------------


def test_ghost_only_unit_rides_the_empty_asr_lane_not_word_clocks():
    results, saved, _worker = window_result([word('ghost', -3.0, -1.0)])
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]
    assert saved == []


def test_ghost_and_tail_only_unit_also_rides_the_empty_asr_lane():
    results, saved, _worker = window_result([word('ghost', -3.0, -1.0), word('tail', 0.5, 0.6)])
    assert results == [ValidationFailureWork('synthetic-window', 'assemble_words', 'empty_asr')]
    assert saved == []


def test_unit_with_kept_words_publishes_them_despite_a_ghost():
    results, saved, _worker = window_result([word('ghost', -3.0, -1.0), word('kept', 0.1, 0.3)])
    assert results == [WorkResult('synthetic-window', 'synthetic:result')]
    assert saved[0]['words'] == [word('kept', 0.1, 0.3)]


def test_unit_with_kept_words_publishes_across_two_windows_with_ghosts():
    vad = lambda _: [(0.0, 0.2), (0.3, 0.5)]
    results, saved, _worker = window_result(
        [[word('ghost', -3.0, -1.0), word('kept', 0.05, 0.15)], [word('kept2', 0.02, 0.15), word('tail', 0.3, 0.4)]],
        0.5,
        vad=vad,
    )
    assert results == [WorkResult('synthetic-window', 'synthetic:result')]
    words = saved[0]['words']
    assert [row['word'] for row in words] == ['kept', 'kept2']


def test_malformed_clock_unit_still_fails_at_word_clocks_with_a_ghost_sibling():
    results, saved, worker = window_result([[word('ghost', -3.0, -1.0), word('bad', 0.3, 0.2)]])
    assert results == [ValidationFailureWork('synthetic-window', 'word_clocks', 'word_clock')]
    assert saved == []
    assert worker.counts['failed'] == 1


def test_ghost_only_failure_is_not_counted_as_silence():
    results, saved, worker = window_result([word('ghost', -3.0, -1.0)])
    assert worker.counts.get('silence', 0) == 0
    assert results


def test_reused_live_words_path_still_rejects_in_window_malformed_clocks():
    # The reused-live-receipt branch validates through the same strict
    # validator; a ghost would drop but an in-window reversal must still fail.
    with pytest.raises(BatchValidationError, match='word_clock'):
        validate_words([word('bad', 0.3, 0.2)], 0.5)


# --- Ghost-only hypotheses now reach the padded retry instead of a quarantine ----


def test_recovery_runs_for_a_ghost_only_hypothesis():
    calls = []

    def recover(samples, budget):
        calls.append(len(samples))
        return []

    results, saved, _worker = window_result([word('ghost', -3.0, -1.0)], recover_words=recover)
    assert calls and calls[0] >= int(0.5 * RATE)
    # A validated empty hypothesis is a valid retry input: the unit is held
    # for fenced recovery with the empty padded-retry evidence, not failed.
    result = results[0]
    assert isinstance(result, RecoveryWork)
    assert result.reason == 'empty_asr'
    assert result.padded_retry == 'empty' and result.padded_retry_empty is True
    assert saved == []


def test_ghost_only_unit_publishing_through_a_successful_retry():
    def recover(samples, budget):
        return [word('recovered', 0.1, 0.3)]

    results, saved, _worker = window_result([word('ghost', -3.0, -1.0)], recover_words=recover)
    assert results == [WorkResult('synthetic-window', 'synthetic:result')]
    assert saved
    assert all(0.0 <= row['timestamp'][0] <= row['timestamp'][1] <= 0.5 for row in saved[0]['words'])


def test_ghost_only_unit_with_a_failing_retry_stays_held_as_empty_asr():
    results, saved, _worker = window_result([word('ghost', -3.0, -1.0)], recover_words=lambda samples, budget: [])
    result = results[0]
    assert isinstance(result, RecoveryWork)
    assert result.reason == 'empty_asr'
    assert not saved


def test_kept_words_and_ghosts_stay_independent_across_units():
    results, saved, _worker = window_result(
        [[word('ghost', -3.0, -1.0), word('kept', 0.1, 0.3)], [word('kept2', 0.2, 0.4)]],
        0.5,
        segment_ids=('unit-a', 'unit-b'),
    )
    assert [result.segment_id for result in results] == ['unit-a', 'unit-b']
    assert len(saved) == 2
    texts = [{row['word'] for row in payload['words']} for payload in saved]
    assert {'kept'} in texts and {'kept2'} in texts


# --- Padded-retry adapter: the left padding band is the ghost producer -----------


def test_padded_retry_drops_a_clock_wholly_in_the_left_padding():
    # Padded time [0.5, 1.5] shifts back by the two-second left pad.
    assert recover_empty_result([word('ghost', 0.5, 1.5)], 0.5) == []


def test_padded_retry_drops_a_clock_straddling_zero_with_a_negative_midpoint():
    assert recover_empty_result([word('ghost', 1.0, 2.5)], 0.5) == []


def test_padded_retry_keeps_a_real_word_outside_the_padding_band():
    assert recover_empty_result([word('kept', 2.25, 2.5)], 0.5) == [word('kept', 0.25, 0.5)]


def test_padded_retry_keeps_a_left_edge_straddler_clamped_to_zero():
    assert recover_empty_result([word('kept', 1.75, 2.5)], 0.5) == [word('kept', 0.0, 0.5)]


def test_padded_retry_separates_padding_ghosts_from_real_words():
    result = recover_empty_result([word('ghost', 0.5, 1.5), word('ghost', 1.5, 2.0), word('kept', 2.25, 2.5)], 0.5)
    assert result == [word('kept', 0.25, 0.5)]


def test_padded_retry_drops_clocks_wholly_in_the_right_padding():
    # A real capture of 0.5s pads to 8.0s; shifted right-padding clocks land
    # far past the capture and the ownership rule rejects them.
    assert recover_empty_result([word('tail', 7.5, 7.75)], 0.5) == []


def test_padded_retry_drops_a_word_wholly_past_the_capture_end():
    assert recover_empty_result([word('tail', 3.0, 3.5)], 0.5) == []


def test_padded_retry_clamps_a_word_straddling_the_capture_end():
    assert recover_empty_result([word('kept', 2.0, 2.75)], 0.5) == [word('kept', 0.0, 0.5)]


def test_padded_retry_on_an_empty_response_stays_empty():
    assert recover_empty_result([], 0.5) == []


def test_padded_retry_ghost_and_real_word_composite_across_the_whole_band():
    result = recover_empty_result(
        [word('g1', 0.25, 0.75), word('g2', 1.25, 1.75), word('kept', 2.0, 2.25), word('tail', 6.0, 6.5)], 0.5
    )
    assert result == [word('kept', 0.0, 0.25)]


# --- Additional pure-function edges ------------------------------------------------


def test_deep_historical_ghost_many_minutes_before_a_small_window_drops():
    assert bounded_window_words([word('ghost', -7200.0, -3600.0)], 0.5) == []


def test_point_ghost_wholly_below_zero_drops():
    assert bounded_window_words([word('ghost', -1.0, -1.0)], 0.5) == []


def test_ghost_straddler_point_and_tail_composite_on_half_a_second():
    # Non-dropped clocks stay in raw ascending order, exactly as a window
    # hypothesis arrives; ghosts and tails may appear anywhere.
    rows = [
        word('ghost', -3.0, -1.0),
        word('straddle', -0.1, 0.4),
        word('point', 0.0, 0.0),
        word('kept', 0.2, 0.3),
        word('tail', 0.5, 0.55),
    ]
    assert bounded_window_words(rows, 0.5) == [
        word('straddle', 0.0, 0.4),
        word('point', 0.0, 0.0),
        word('kept', 0.2, 0.3),
    ]


def test_ghost_before_a_zero_length_point_word_is_owned_only_by_the_point():
    rows = [word('ghost', -0.5, -0.25), word('point', 0.0, 0.0)]
    assert bounded_window_words(rows, 0.5) == [word('point', 0.0, 0.0)]


# --- Shared home and reason-code surface ------------------------------------------


def test_diarizer_reexports_the_shared_ownership_function():
    from utils.batch_pipeline import word_validation

    assert diarizer_bounded_window_words is word_validation.bounded_window_words


def test_word_clock_reason_code_is_unchanged_for_in_domain_malformations():
    assert ValidationReason.WORD_CLOCK.value == 'word_clock'


def test_batch_validation_error_message_is_its_closed_reason():
    error = BatchValidationError(ValidationReason.WORD_CLOCK)
    assert str(error) == 'word_clock' and error.reason == 'word_clock'


def test_ghost_drop_raises_nothing_and_returns_a_list():
    assert isinstance(bounded_window_words([word('ghost', -3.0, -1.0)], 0.5), list)
