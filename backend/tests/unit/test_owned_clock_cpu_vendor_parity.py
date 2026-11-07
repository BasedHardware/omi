"""Vendor response clocks meet the same ownership contract as the GPU window seam.

The CPU provider lane validated vendor words with the strict ``validate_words``
tolerance alone: a word beginning at or past the captured extent, or ending
beyond the EOF tolerance, raised ``word_clock`` and the vendor attempt was
classified as an invalid response — burning the attempt ladder and
quarantining a capture whose real words were already in the response. The GPU
worker learned the ownership rule in the window-tail and boundary-geometry
parity work; the vendor lane now validates through the same shared
``bounded_window_words``: wholly-outside clocks drop, edge-straddlers clamp
into the capture, malformed in-domain clocks still fail the response, and a
ghost-only response classifies as ``empty_asr`` — the honest terminal state
the empty ladder already knows how to settle — instead of a clock quarantine.

These tests pin the vendor lane from its public coroutine: boundary geometry,
the empty classification, the payload contract (language, provider, spans,
recovery version, speaker-fallback stripping, retained ``text``), the
malformed raises that stay ``invalid_response``, and lane parity with the
shared function.
"""

import asyncio
from unittest.mock import patch

import numpy as np
import pytest

from config.batch_conversation_speakers import VENDOR_SPEAKER_TURNS_ENV
from utils.batch_pipeline import provider_stt
from utils.batch_pipeline.contracts import Priority, WorkItem
from utils.batch_pipeline.recovery_disposition import RecoveryFailure
from utils.batch_pipeline.word_validation import BatchValidationError, bounded_window_words

RATE = 16000


def word(text, start, end):
    # Vendor kept words retain the source ``text`` alongside the added ``word``.
    return {'text': text, 'timestamp': [start, end], 'word': text}


def vendor_word(text, start, end, fallback=False):
    row = {'text': text, 'timestamp': [start, end]}
    if fallback:
        row['speaker_fallback'] = True
    return row


def work_item(duration=0.5):
    return WorkItem('vendor-unit', 'synthetic-owner', 0.0, 'synthetic:audio', duration, Priority.DEEP)


def pcm_bytes(duration=0.5):
    return (np.ones(int(duration * RATE), dtype=np.float32) * 1000.0).astype('<i2').tobytes()


def run_vendor(raw, detected='en', duration=0.5, service='modulate'):
    """One scripted vendor call through the real response validator."""

    async def fake_vendor(service, wav, seconds, language):
        return list(raw), detected

    async def call():
        with patch.object(provider_stt, '_vendor_words', fake_vendor):
            return await provider_stt.transcribe_async(
                work_item(duration),
                None,
                (pcm_bytes(duration), duration, [{'start': 0.0, 'end': duration}]),
                service=service,
            )

    return asyncio.run(call())


@pytest.fixture(autouse=True)
def _vendor_turns_off(monkeypatch):
    monkeypatch.setenv(VENDOR_SPEAKER_TURNS_ENV, 'false')


# --- Tail overshoot clamps instead of failing the response ------------------------


def test_vendor_word_ending_half_a_frame_past_the_capture_clamps():
    payload = run_vendor([vendor_word('kept', 0.1, 0.51)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.5)]


def test_vendor_word_ending_well_past_the_capture_clamps_to_the_extent():
    payload = run_vendor([vendor_word('kept', 0.1, 0.8)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.5)]


def test_vendor_word_starting_exactly_at_the_capture_end_drops_while_kept_words_survive():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3), vendor_word('tail', 0.5, 0.6)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.3)]


def test_vendor_word_one_sample_past_the_capture_end_drops_while_kept_words_survive():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3), vendor_word('tail', 0.5 + 1 / RATE, 0.6)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.3)]


def test_vendor_words_wholly_past_the_capture_drop_while_a_kept_word_survives():
    payload = run_vendor(
        [vendor_word('t1', 0.6, 0.7), vendor_word('kept', 0.2, 0.3), vendor_word('t2', 0.8, 0.9)], duration=0.5
    )
    assert payload['words'] == [word('kept', 0.2, 0.3)]


# --- Pre-window ghost clocks drop by the same rule --------------------------------


def test_vendor_ghost_and_kept_word_leaves_only_the_kept_word():
    payload = run_vendor([vendor_word('ghost', -3.0, -1.0), vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.3)]
    assert payload['audio_seconds'] == 0.5


def test_vendor_ghost_straddling_zero_clamps_to_the_capture_start():
    payload = run_vendor([vendor_word('kept', -0.1, 0.3)], duration=0.5)
    assert payload['words'] == [word('kept', 0.0, 0.3)]


# --- Ghost-only and tail-only responses classify as empty_asr ---------------------


def test_vendor_ghost_only_response_is_empty_asr_not_invalid_response():
    with pytest.raises(RecoveryFailure) as raised:
        run_vendor([vendor_word('ghost', -3.0, -1.0)], duration=0.5)
    assert raised.value.stage == 'response_validation' and raised.value.reason == 'empty_asr'


def test_vendor_tail_only_response_is_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        run_vendor([vendor_word('tail', 0.5, 0.6)], duration=0.5)
    assert raised.value.stage == 'response_validation' and raised.value.reason == 'empty_asr'


def test_vendor_ghost_and_tail_only_response_is_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        run_vendor([vendor_word('ghost', -3.0, -1.0), vendor_word('tail', 0.6, 0.7)], duration=0.5)
    assert raised.value.reason == 'empty_asr'


def test_vendor_empty_response_stays_empty_asr():
    with pytest.raises(RecoveryFailure) as raised:
        run_vendor([], duration=0.5)
    assert raised.value.reason == 'empty_asr'


# --- The payload contract does not move --------------------------------------------


def test_vendor_kept_words_carry_both_the_source_text_and_the_word_key():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.3)]


def test_vendor_payload_audio_seconds_matches_the_capture():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['audio_seconds'] == 0.5


def test_vendor_payload_carries_the_measured_speech_spans():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['speech_spans'] == [{'start': 0.0, 'end': 0.5}]


def test_vendor_payload_speech_seconds_counts_the_span_union():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['speech_seconds'] == 0.5


def test_vendor_payload_carries_the_detected_language():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], detected='pt-BR', duration=0.5)
    assert payload['language'] == 'pt-BR'


def test_vendor_payload_names_the_serving_provider():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['words_provider'] == 'modulate'


def test_vendor_payload_stamps_the_recovery_version():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5)
    assert payload['recovery_version'] == 1


def test_vendor_speaker_fallback_flag_is_stripped_from_words():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3, fallback=True)], duration=0.5)
    assert payload['words'] == [word('kept', 0.1, 0.3)]


def test_vendor_payload_turns_stay_empty_with_the_switch_off():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3, fallback=True)], duration=0.5)
    assert payload['diarization'] == {'turns': []}


def test_vendor_kept_words_preserve_extra_keys():
    raw = [{'text': 'kept', 'timestamp': [0.1, 0.3], 'confidence': 0.9}]
    payload = run_vendor(raw, duration=0.5)
    assert payload['words'] == [{'text': 'kept', 'timestamp': [0.1, 0.3], 'word': 'kept', 'confidence': 0.9}]


def test_vendor_kept_word_order_is_preserved():
    payload = run_vendor([vendor_word('a', 0.05, 0.1), vendor_word('b', 0.2, 0.3)], duration=0.5)
    assert [row['word'] for row in payload['words']] == ['a', 'b']


def test_vendor_multi_word_payload_clamps_only_the_edge_straddler():
    payload = run_vendor(
        [vendor_word('a', 0.05, 0.2), vendor_word('straddle', 0.4, 0.55), vendor_word('tail', 0.5, 0.6)], duration=0.5
    )
    assert payload['words'] == [word('a', 0.05, 0.2), word('straddle', 0.4, 0.5)]


# --- Malformed in-domain clocks still classify as invalid_response -----------------


def assert_invalid_response(machinery):
    with pytest.raises(RecoveryFailure) as raised:
        machinery()
    assert raised.value.stage == 'response_validation' and raised.value.reason == 'invalid_response'


def test_vendor_reversed_in_window_clocks_are_invalid_response():
    assert_invalid_response(lambda: run_vendor([vendor_word('bad', 0.3, 0.2)], duration=0.5))


def test_vendor_nan_clock_is_invalid_response():
    assert_invalid_response(lambda: run_vendor([{'text': 'bad', 'timestamp': [0.1, float('nan')]}], duration=0.5))


def test_vendor_blank_token_is_invalid_response():
    assert_invalid_response(lambda: run_vendor([vendor_word('  ', 0.1, 0.3)], duration=0.5))


def test_vendor_out_of_order_words_are_invalid_response():
    assert_invalid_response(lambda: run_vendor([vendor_word('b', 0.3, 0.4), vendor_word('a', 0.1, 0.2)], duration=0.5))


def test_vendor_unparseable_timestamp_is_invalid_response():
    assert_invalid_response(lambda: run_vendor([{'text': 'bad', 'timestamp': 'nope'}], duration=0.5))


def test_vendor_wrong_response_shape_is_invalid_response():
    assert_invalid_response(lambda: run_vendor('nope', duration=0.5))


def test_vendor_empty_detected_language_is_invalid_response():
    assert_invalid_response(lambda: run_vendor([vendor_word('kept', 0.1, 0.3)], detected='', duration=0.5))


def test_vendor_reversed_clock_response_carries_no_payload_words():
    # The raise happens before any payload exists: nothing partial is published.
    with pytest.raises(RecoveryFailure):
        run_vendor([vendor_word('kept', 0.1, 0.2), vendor_word('bad', 0.4, 0.3)], duration=0.5)


# --- Vendor speaker turns with the switch on ----------------------------------------


def test_vendor_turns_are_built_from_labelled_words_when_enabled(monkeypatch):
    monkeypatch.setenv(VENDOR_SPEAKER_TURNS_ENV, 'true')
    raw = [{'text': 'kept', 'timestamp': [0.1, 0.3], 'speaker': 'SPEAKER_00'}]
    payload = run_vendor(raw, duration=0.5)
    assert payload['diarization']['turns'] == [{'start': 0.1, 'end': 0.3, 'speaker': 'SPEAKER_00'}]


def test_vendor_turns_stay_empty_for_a_fallback_response_even_when_enabled(monkeypatch):
    monkeypatch.setenv(VENDOR_SPEAKER_TURNS_ENV, 'true')
    raw = [{'text': 'kept', 'timestamp': [0.1, 0.3], 'speaker': 'SPEAKER_00', 'speaker_fallback': True}]
    payload = run_vendor(raw, duration=0.5)
    assert payload['diarization']['turns'] == []


def test_vendor_turn_clamps_to_the_capture_when_enabled(monkeypatch):
    monkeypatch.setenv(VENDOR_SPEAKER_TURNS_ENV, 'true')
    raw = [{'text': 'straddle', 'timestamp': [0.1, 0.8], 'speaker': 'SPEAKER_01'}]
    payload = run_vendor(raw, duration=0.5)
    assert payload['diarization']['turns'] == [{'start': 0.1, 'end': 0.5, 'speaker': 'SPEAKER_01'}]


# --- Two-second-scale geometry --------------------------------------------------------


def test_vendor_ghost_drops_while_a_kept_word_survives_on_a_two_second_capture():
    payload = run_vendor([vendor_word('ghost', -4.0, -2.0), vendor_word('kept', 0.5, 1.0)], duration=2.0)
    assert payload['words'] == [word('kept', 0.5, 1.0)]


def test_vendor_straddler_on_a_two_second_capture_clamps_to_the_start():
    payload = run_vendor([vendor_word('kept', -0.1, 0.4)], duration=2.0)
    assert payload['words'] == [word('kept', 0.0, 0.4)]


def test_vendor_tail_drops_while_a_kept_word_survives_on_a_two_second_capture():
    payload = run_vendor([vendor_word('kept', 0.5, 1.0), vendor_word('tail', 2.0, 2.1)], duration=2.0)
    assert payload['words'] == [word('kept', 0.5, 1.0)]


def test_vendor_kept_mid_word_on_a_two_second_capture_is_untouched():
    payload = run_vendor([vendor_word('kept', 0.5, 1.0)], duration=2.0)
    assert payload['words'] == [word('kept', 0.5, 1.0)]


def test_vendor_full_four_geometry_composite_on_a_two_second_capture():
    raw = [
        vendor_word('ghost', -4.0, -2.0),
        vendor_word('straddle', -0.1, 0.4),
        vendor_word('kept', 0.5, 1.0),
        vendor_word('tail', 2.0, 2.2),
    ]
    payload = run_vendor(raw, duration=2.0)
    assert payload['words'] == [word('straddle', 0.0, 0.4), word('kept', 0.5, 1.0)]


# --- Payload invariants under clamping --------------------------------------------------


def test_vendor_payload_audio_seconds_is_the_admitted_capture_even_when_words_clamp():
    payload = run_vendor([vendor_word('straddle', 0.1, 0.8)], duration=0.5)
    assert payload['audio_seconds'] == 0.5


def test_vendor_payload_words_never_exceed_the_capture_extent():
    payload = run_vendor(
        [vendor_word('a', -0.5, 0.2), vendor_word('b', 0.3, 0.49), vendor_word('c', 0.49, 0.9)], duration=0.5
    )
    assert all(row['timestamp'][0] >= 0.0 and row['timestamp'][1] <= 0.5 for row in payload['words'])


def test_vendor_payload_speech_spans_are_untouched_by_word_clamping():
    payload = run_vendor([vendor_word('straddle', 0.1, 0.8)], duration=0.5)
    assert payload['speech_spans'] == [{'start': 0.0, 'end': 0.5}]


def test_vendor_kept_words_keep_a_speaker_label_key():
    raw = [{'text': 'kept', 'timestamp': [0.1, 0.3], 'speaker': 'SPEAKER_00'}]
    payload = run_vendor(raw, duration=0.5)
    assert payload['words'] == [{'text': 'kept', 'timestamp': [0.1, 0.3], 'word': 'kept', 'speaker': 'SPEAKER_00'}]


def test_vendor_ghosts_between_kept_words_preserve_their_order():
    raw = [
        vendor_word('a', 0.05, 0.1),
        vendor_word('ghost', -1.0, -0.5),
        vendor_word('b', 0.2, 0.3),
        vendor_word('ghost', -2.0, -1.5),
        vendor_word('c', 0.35, 0.45),
    ]
    payload = run_vendor(raw, duration=0.5)
    assert [row['word'] for row in payload['words']] == ['a', 'b', 'c']


# --- Lane parity with the shared ownership function ---------------------------------


def mapped(raw_rows):
    return [{'text': row['text'], 'word': row['text'], 'timestamp': row['timestamp']} for row in raw_rows]


def test_vendor_lane_matches_the_shared_function_on_mixed_geometry():
    raw = [vendor_word('ghost', -3.0, -1.0), vendor_word('straddle', -0.1, 0.3), vendor_word('kept', 0.2, 0.4)]
    payload = run_vendor(raw, duration=0.5)
    assert payload['words'] == bounded_window_words(mapped(raw), 0.5)


def test_vendor_lane_matches_the_shared_function_on_tail_geometry():
    raw = [vendor_word('kept', 0.1, 0.2), vendor_word('tail', 0.5, 0.62)]
    payload = run_vendor(raw, duration=0.5)
    assert payload['words'] == bounded_window_words(mapped(raw), 0.5)


def test_vendor_lane_accepts_the_soniox_service_token():
    payload = run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5, service='soniox')
    assert payload['words_provider'] == 'soniox'


def test_vendor_lane_refuses_an_unknown_service_token():
    with pytest.raises(RecoveryFailure) as raised:
        run_vendor([vendor_word('kept', 0.1, 0.3)], duration=0.5, service='whisper')
    assert raised.value.stage == 'provider' and raised.value.reason == 'provider_failed'


def test_vendor_recovered_payload_words_always_pass_the_strict_validator():
    from utils.batch_pipeline.word_validation import validate_words

    payload = run_vendor([vendor_word('straddle', -0.1, 0.55)], duration=0.5)
    assert validate_words(payload['words'], 0.5) == payload['words']
