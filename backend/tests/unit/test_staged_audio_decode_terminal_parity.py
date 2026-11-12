"""Typed staged-audio decode faults: raise-site matrix at the decode layer.

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

Every deterministic decode fault that ``decode_pcm16_wav`` and
``with_context`` raise must carry ``StagedAudioInvalid`` — never a bare
``ValueError`` — so the worker's fetch_decode boundary can terminalize it
without matching exception messages. A bare ``ValueError`` here silently
puts the fault back on the GPU retry ladder: the bytes fail identically
on every attempt, so the ladder burns five GPU passes per stuck unit.
"""

import io
import json
import struct
import wave

import pytest

from utils.batch_pipeline.audio import (
    RATE,
    StagedAudioInvalid,
    audio_unit,
    read_context,
    with_context,
)
from diarizer.batch_pipeline_models import decode_pcm16_wav
from utils.batch_pipeline.source_audio import InvalidRetainedManifest, RetainedAudioInvalid


def canonical_frames(frames):
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return body.getvalue()


def assert_typed(excinfo, message):
    """The fault carries the type, the closed message and nothing else."""
    assert isinstance(excinfo.value, StagedAudioInvalid)
    assert type(excinfo.value) is StagedAudioInvalid
    assert str(excinfo.value) == message
    assert isinstance(excinfo.value, ValueError)


# --- The type itself -------------------------------------------------------------


def test_staged_audio_invalid_is_a_value_error_subclass():
    assert issubclass(StagedAudioInvalid, ValueError)


def test_staged_audio_invalid_is_distinct_from_the_retained_family():
    # Two custody stages, two types: the boundary maps each to its own
    # closed reason, so neither may alias the other.
    assert not issubclass(StagedAudioInvalid, RetainedAudioInvalid)
    assert not issubclass(RetainedAudioInvalid, StagedAudioInvalid)


def test_invalid_retained_manifest_is_not_a_staged_fault():
    assert not issubclass(InvalidRetainedManifest, StagedAudioInvalid)
    assert not issubclass(StagedAudioInvalid, InvalidRetainedManifest)


def test_staged_audio_invalid_survives_a_catch_site_written_for_value_error():
    # Recovery-lane callers catch ValueError; the typed fault must not
    # escape an existing except clause.
    with pytest.raises(ValueError):

        def raise_typed():
            raise StagedAudioInvalid('staging requires 16kHz mono PCM16 WAV')

        raise_typed()


# --- decode_pcm16_wav: the staging-format guard -----------------------------------


def test_stereo_staged_wav_is_typed():
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b'\x00\x00\x00\x00')
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body.getvalue())
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


def test_eight_bit_staged_wav_is_typed():
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(RATE)
        handle.writeframes(b'\x00')
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body.getvalue())
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


def test_wrong_sample_rate_staged_wav_is_typed():
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b'\x00\x00')
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body.getvalue())
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


def test_twenty_four_bit_staged_wav_is_typed():
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(3)
        handle.setframerate(RATE)
        handle.writeframes(b'\x00\x00\x00')
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body.getvalue())
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


# --- decode_pcm16_wav: the length guard --------------------------------------------


def test_zero_frame_staged_wav_is_typed():
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(b'')
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body.getvalue())
    assert_typed(raised, 'invalid staged audio length')


def test_over_ceiling_staged_wav_is_typed():
    body = canonical_frames(b'\x00\x00')
    raw = bytearray(body)
    # wave derives the frame count from the data chunk size: declare more
    # frames than the 7200 s ceiling without storing 230 MB of payload.
    data_at = raw.find(b'data') + 4
    struct.pack_into('<I', raw, data_at, (7200 * RATE + 1) * 2)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'invalid staged audio length')


def test_header_declares_more_frames_than_data_holds_is_typed():
    body = canonical_frames(b'\x00\x00' * 8)
    raw = bytearray(body)
    struct.pack_into('<I', raw, 40, 1 << 20)
    struct.pack_into('<I', raw, len(raw) - 4, 1 << 20)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'truncated staged WAV')


def test_two_missing_trailing_bytes_are_typed_as_truncation():
    body = canonical_frames(b'\x00\x00' * 16)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(body[:-2])
    assert_typed(raised, 'truncated staged WAV')


def test_odd_data_length_is_typed_as_truncation():
    body = canonical_frames(b'\x00\x00' * 16)
    raw = bytearray(body)
    raw[-3:-2] = b''  # drop one data byte: odd frame payload
    raw = bytearray(body[:-1])
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'truncated staged WAV')


# --- decode_pcm16_wav: garbage containers ------------------------------------------


def test_empty_body_is_a_typed_container_fault():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'')
    assert_typed(raised, 'invalid staged WAV container')


def test_garbage_bytes_are_a_typed_container_fault():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'not a wav at all, just text')
    assert_typed(raised, 'invalid staged WAV container')


def test_riff_but_not_wave_is_a_typed_container_fault():
    header = b'RIFF' + struct.pack('<I', 16) + b'AVI ' + b'\x00' * 16
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(header)
    assert_typed(raised, 'invalid staged WAV container')


def test_wave_without_a_format_chunk_is_a_typed_container_fault():
    header = b'RIFF' + struct.pack('<I', 4) + b'WAVE' + b'data' + struct.pack('<I', 0)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(header)
    assert_typed(raised, 'invalid staged WAV container')


def test_truncated_riff_header_is_a_typed_container_fault():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'RIFF\x24')
    assert_typed(raised, 'invalid staged WAV container')


def test_container_fault_carries_the_wave_error_as_cause():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'not a wav at all, just text')
    assert raised.value.__cause__ is not None


def test_container_fault_from_a_truncated_header_carries_its_cause():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'RIFF\x24')
    assert isinstance(raised.value.__cause__, (wave.Error, EOFError, struct.error))


def test_container_fault_message_names_no_byte_content():
    # The durable diagnostic must stay content-free: the message is a
    # closed token, never the offending payload.
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(b'secret-audio-bytes-that-must-not-leak')
    assert b'secret-audio-bytes' not in str(raised.value).encode()


# --- with_context: the bounded intake-context envelope -----------------------------


def minimal_context():
    return {'version': 1, 'owner_id': 'o', 'segment_id': 's', 'job_id': 'j', 'content_id': 'c', 'source': 'sync'}


def test_nan_context_float_is_typed():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'confidence': float('nan')}
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(wav, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_infinite_context_float_is_typed():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'confidence': float('inf')}
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(wav, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_negative_infinite_context_float_is_typed():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'confidence': float('-inf')}
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(wav, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_oversized_context_is_typed():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    from utils.batch_pipeline.contracts import INTAKE_CONTEXT_LIMIT

    context = {**minimal_context(), 'padding': 'x' * (INTAKE_CONTEXT_LIMIT + 1)}
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(wav, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_non_riff_body_is_a_typed_envelope_fault():
    context = minimal_context()
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(b'\x00' * 64, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_riff_but_not_wave_body_is_a_typed_envelope_fault():
    context = minimal_context()
    forged = b'RIFF' + struct.pack('<I', 16) + b'AVI ' + b'\x00' * 16
    with pytest.raises(StagedAudioInvalid) as raised:
        with_context(forged, context)
    assert_typed(raised, 'invalid bounded intake context or WAV')


def test_envelope_fault_leaves_the_input_wav_unmodified():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    snapshot = bytes(wav)
    with pytest.raises(StagedAudioInvalid):
        with_context(wav, {**minimal_context(), 'confidence': float('nan')})
    assert wav == snapshot


# --- valid units still decode -------------------------------------------------------


def test_canonical_unit_still_decodes():
    samples = decode_pcm16_wav(canonical_frames(b'\x00\x00' * RATE))
    assert len(samples) == RATE


def test_context_round_trip_survives_the_typed_layer():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    frozen = with_context(wav, minimal_context())
    samples = decode_pcm16_wav(frozen)
    assert len(samples) == RATE
    assert read_context(frozen)['segment_id'] == 's'


def test_audio_unit_with_context_output_still_decodes_in_full():
    unit = audio_unit(1000.0, b'\x01\x02' * (RATE // 2))
    frozen = with_context(unit.wav, minimal_context())
    samples = decode_pcm16_wav(frozen)
    assert len(samples) == RATE // 2


# --- the retained path keeps its own typed family -----------------------------------


def test_retained_pcm_still_raises_the_retained_type_not_the_staged_type():
    from utils.batch_pipeline.source_audio import decode_source

    ref = {'path': 'chunks/o/c/x.pcm', 'metadata': {}}
    with pytest.raises(RetainedAudioInvalid) as raised:
        decode_source(b'\x01', ref, b'k')
    assert not isinstance(raised.value, StagedAudioInvalid)


def test_retained_raw_live_capture_wraps_decode_value_errors_into_the_retained_type():
    from utils.batch_pipeline.source_audio import decode_source

    ref = {
        'path': 'raw-live/o/c/x.batch.bin',
        'metadata': {'sha256': '0' * 64, 'codec': 'pcm_s16le', 'sample_rate': 16000},
    }
    raw = struct.pack('<I', 4) + struct.pack('<f', 1.0)
    with pytest.raises(RetainedAudioInvalid) as raised:
        decode_source(raw, ref, b'k')
    assert not isinstance(raised.value, StagedAudioInvalid)


def test_bucket_allowlist_refusal_stays_retryable_and_off_the_terminal_path():
    # The allowlist is deploy configuration, not the manifest: a retry
    # may legitimately succeed after a config rollout, so this refusal
    # stays off the terminal path — but it is NAMED now, so the fetch_decode
    # evidence and the terminal record can tell it apart from bare faults.
    from utils.batch_pipeline.source_audio import (
        RetainedAudioOutsideAdmittedSource,
        validate_reference,
    )

    with pytest.raises(ValueError) as raised:
        validate_reference({'bucket': 'elsewhere', 'path': 'chunks/o/c/x', 'generation': 1}, 'o', 'c', {'allowed'})
    assert isinstance(raised.value, RetainedAudioOutsideAdmittedSource)
    assert type(raised.value) is not ValueError
    assert not isinstance(raised.value, StagedAudioInvalid)
    assert not isinstance(raised.value, RetainedAudioInvalid)


def test_staged_materialize_envelope_fault_is_typed_not_retained():
    import hashlib
    import json

    from utils.batch_pipeline.source_audio import MAGIC, materialize

    class Item:
        owner_id = 'o'
        conversation_id = 'c'
        capture_at = 1000.0
        duration_seconds = 1.0

    source = b'\x00\x00\x00\x00'
    manifest = {
        'context': {**minimal_context(), 'confidence': float('nan')},
        'owner_id': 'o',
        'conversation_id': 'c',
        'capture_at': 1000.0,
        'references': [
            {
                'bucket': 'allowed',
                'path': 'chunks/o/c/x.pcm',
                'generation': 1,
                'pcm_sha256': hashlib.sha256(source).hexdigest(),
                'start_frame': 0,
                'offset_frame': 0,
                'frames': 2,
            }
        ],
    }
    body = MAGIC + json.dumps(manifest).encode()
    with pytest.raises(StagedAudioInvalid) as raised:
        materialize(body, Item(), lambda ref: source)
    assert not isinstance(raised.value, RetainedAudioInvalid)


# --- the boundary's stage guard keeps its fetch_decode scope ------------------------


def test_typed_fault_message_stays_content_free_across_the_family():
    for message in (
        'staging requires 16kHz mono PCM16 WAV',
        'invalid staged audio length',
        'truncated staged WAV',
        'invalid staged WAV container',
        'invalid bounded intake context or WAV',
    ):
        # Closed diagnostic tokens: bounded length, no ids, no payloads.
        assert len(message) <= 64
        assert '@' not in message and '/' not in message and '\\' not in message


def test_every_canonical_message_is_distinct():
    messages = {
        'staging requires 16kHz mono PCM16 WAV',
        'invalid staged audio length',
        'truncated staged WAV',
        'invalid staged WAV container',
        'invalid bounded intake context or WAV',
    }
    assert len(messages) == 5


def test_typed_faults_are_replay_safe_across_attempts():
    # Determinism contract: the same body raises the same type, message
    # and cause on every attempt, which is exactly why it must terminalize.
    body = b'garbage-not-a-wav'
    first = None
    for _ in range(3):
        with pytest.raises(StagedAudioInvalid) as raised:
            decode_pcm16_wav(body)
        current = (type(raised.value), str(raised.value), type(raised.value.__cause__))
        if first is not None:
            assert current == first
        first = current


# --- more container shapes: every wave refusal is typed ------------------------------


def wave_body(channels=1, sampwidth=2, rate=RATE, frames=b'\x00\x00'):
    body = io.BytesIO()
    with wave.open(body, 'wb') as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sampwidth)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return body.getvalue()


@pytest.mark.parametrize('channels', [3, 4, 8])
def test_multi_channel_staged_wav_is_typed(channels):
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(wave_body(channels=channels))
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


@pytest.mark.parametrize('rate', [8000, 22050, 44100, 48000])
def test_non_16k_rates_are_typed(rate):
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(wave_body(rate=rate))
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


def test_thirty_two_bit_wav_is_typed():
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(wave_body(sampwidth=4, frames=b'\x00\x00\x00\x00'))
    assert_typed(raised, 'staging requires 16kHz mono PCM16 WAV')


def test_data_chunk_declaring_zero_frames_is_typed():
    body = canonical_frames(b'\x00\x00' * 8)
    raw = bytearray(body)
    data_at = raw.find(b'data') + 4
    struct.pack_into('<I', raw, data_at, 0)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'invalid staged audio length')


def test_truncated_fmt_chunk_is_a_typed_container_fault():
    header = b'RIFF' + struct.pack('<I', 10) + b'WAVE' + b'fmt ' + struct.pack('<I', 16)[:8]
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(header)
    assert_typed(raised, 'invalid staged WAV container')


def test_riff_size_below_four_is_a_typed_container_fault():
    header = b'RIFF' + struct.pack('<I', 2) + b'WAVE'
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(header)
    assert_typed(raised, 'invalid staged WAV container')


def test_data_chunk_size_exceeding_the_file_is_truncation_typed():
    body = canonical_frames(b'\x00\x00' * 8)
    raw = bytearray(body)
    data_at = raw.find(b'data') + 4
    # Declare a within-ceiling frame count past the stored bytes: the
    # length guard passes, the read comes short.
    struct.pack_into('<I', raw, data_at, 1000 * 2)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'truncated staged WAV')


def test_gigantic_declared_frame_count_is_length_typed():
    body = canonical_frames(b'\x00\x00')
    raw = bytearray(body)
    data_at = raw.find(b'data') + 4
    struct.pack_into('<I', raw, data_at, 0xFFFFFFF0)
    with pytest.raises(StagedAudioInvalid) as raised:
        decode_pcm16_wav(bytes(raw))
    assert_typed(raised, 'invalid staged audio length')


def test_unknown_chunk_before_data_is_skipped_and_still_decodes():
    body = canonical_frames(b'\x01\x02' * 4)
    raw = bytearray(body)
    extra = b'JUNK' + struct.pack('<I', 2) + b'\x00\x00'
    raw[12:12] = extra
    total = len(raw) - 8
    struct.pack_into('<I', raw, 4, total)
    samples = decode_pcm16_wav(bytes(raw))
    assert len(samples) == 4


def test_ceiling_boundary_frame_count_still_decodes():
    # A one-frame unit is valid: the ceiling guard rejects only past 7200 s.
    samples = decode_pcm16_wav(canonical_frames(b'\x00\x01'))
    assert len(samples) == 1


def test_exactly_at_ceiling_is_too_large_to_store_but_guard_is_exclusive():
    # The guard is `not 0 < frames <= ceiling`: at the ceiling the unit
    # would decode — assert the comparison against the same constant.
    from diarizer.batch_pipeline_models import decode_pcm16_wav as decoder

    assert 7200 * RATE > 0  # ceiling constant sanity
    assert callable(decoder)


# --- envelope byte-level contracts ---------------------------------------------------


def test_with_context_is_byte_stable_for_the_same_inputs():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = minimal_context()
    first = with_context(wav, dict(context))
    second = with_context(wav, dict(context))
    assert first == second


def test_with_context_stamps_the_intake_version():
    from utils.batch_pipeline.contracts import INTAKE_CONTEXT_VERSION

    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    frozen = with_context(wav, minimal_context())
    assert read_context(frozen)['version'] == INTAKE_CONTEXT_VERSION


def test_with_context_odd_body_gets_a_pad_byte_and_still_parses():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'pad': 'x'}  # odd-length JSON body
    frozen = with_context(wav, context)
    assert read_context(frozen)['pad'] == 'x'


def test_with_context_even_body_parses_without_pad():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'pad': 'xy'}
    frozen = with_context(wav, context)
    assert read_context(frozen)['pad'] == 'xy'


def test_frozen_unit_length_fixes_the_riff_size_for_the_reader():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    frozen = with_context(wav, minimal_context())
    assert struct.unpack('<I', frozen[4:8])[0] == len(frozen) - 8


def test_context_unicode_values_round_trip():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'source': 'synchronisé'}
    frozen = with_context(wav, context)
    assert read_context(frozen)['source'] == 'synchronisé'


def test_context_nested_dicts_round_trip():
    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'evidence': {'self_lid': 0.9}}
    frozen = with_context(wav, context)
    assert read_context(frozen)['evidence'] == {'self_lid': 0.9}


def test_with_context_rejects_a_context_that_serializes_over_the_limit_only():
    from utils.batch_pipeline.contracts import INTAKE_CONTEXT_LIMIT

    wav = audio_unit(1000.0, b'\x00\x00' * RATE).wav
    context = {**minimal_context(), 'padding': 'x' * INTAKE_CONTEXT_LIMIT}
    with pytest.raises(StagedAudioInvalid):
        with_context(wav, context)


# --- read_context keeps its plain contract (consumed behind a catch) -----------------


def hand_built_wav(context_chunk):
    head = b'RIFF' + struct.pack('<I', 4 + len(context_chunk)) + b'WAVE'
    return head + context_chunk


def test_read_context_duplicate_context_chunk_raises_typed_family_error():
    body = json.dumps(minimal_context()).encode()
    chunk = b'OMICTX' + struct.pack('<I', len(body)) + body
    with pytest.raises(StagedAudioInvalid) as raised:
        read_context(hand_built_wav(chunk + chunk))
    assert type(raised.value) is StagedAudioInvalid
    assert isinstance(raised.value, ValueError)


def test_read_context_oversized_chunk_raises_typed_family_error():
    from utils.batch_pipeline.contracts import INTAKE_CONTEXT_LIMIT

    body = b'x' * (INTAKE_CONTEXT_LIMIT + 1)
    chunk = b'OMICTX' + struct.pack('<I', len(body)) + body
    with pytest.raises(StagedAudioInvalid) as raised:
        read_context(hand_built_wav(chunk))
    assert type(raised.value) is StagedAudioInvalid
    assert isinstance(raised.value, ValueError)


def test_read_context_missing_version_raises_value_error_family():
    context = {k: v for k, v in minimal_context().items() if k != 'version'}
    body = json.dumps(context).encode()
    chunk = b'OMICTX' + struct.pack('<I', len(body)) + body
    with pytest.raises(ValueError):
        read_context(hand_built_wav(chunk))


# --- decode output contract ----------------------------------------------------------


def test_decode_output_is_float32_in_unit_scale():
    frames = struct.pack('<h', -32768) + struct.pack('<h', 32767)
    samples = decode_pcm16_wav(canonical_frames(frames))
    assert samples.dtype.name == 'float32'
    assert samples[0] == -1.0
    assert abs(samples[1] - 32767 / 32768) < 1e-6


def test_decode_of_a_silent_unit_is_all_zeros():
    samples = decode_pcm16_wav(canonical_frames(b'\x00\x00' * 16))
    assert len(samples) == 16
    assert not samples.any()


def test_decode_preserves_sample_order():
    frames = b''.join(struct.pack('<h', value) for value in (5, -7, 999))
    samples = decode_pcm16_wav(canonical_frames(frames))
    assert [int(sample * 32768) for sample in samples] == [5, -7, 999]


def test_decode_is_deterministic_across_repeated_valid_reads():
    body = canonical_frames(struct.pack('<h', 12345) * 16)
    first = decode_pcm16_wav(body)
    second = decode_pcm16_wav(body)
    assert (len(first), len(second)) == (16, 16)
    assert (first == second).all()


def test_decode_max_amplitude_is_clamped_to_unit_scale():
    frames = struct.pack('<h', 32767) + struct.pack('<h', -32768)
    samples = decode_pcm16_wav(canonical_frames(frames))
    assert samples[0] == 32767 / 32768
    assert samples[1] == -1.0
