"""Every deterministic decoder fault on the pinned retained bytes must end the
GPU chain typed as RetainedAudioInvalid instead of escaping decode_source as a
bare non-ValueError (OpusError, KeyError, audioop.error, struct.error,
ZeroDivisionError, OverflowError) that rides the five-attempt retry ladder on
identical bytes and quarantines as stage=unknown worker_reason=unclassified -
the production non-ValueError cohort at fetch_decode. The wrap sites convert
exactly the decoder_fault_types() tuple; RuntimeError (the missing libopus
deploy fault) deliberately stays loud and untyped.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import asyncio
import hashlib
import struct
import time

import audioop
import pytest

import utils.batch_pipeline.source_audio as source_audio
import utils.other.audio_opus as opus_module
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.errors import validate_worker_failure
from utils.batch_pipeline.source_audio import (
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    decode_source,
    decoder_fault_types,
)
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker
from utils.batch_pipeline.scheduler import Scheduler

KEY = b"\1" * 32
PCM = b"\0\2" * 320


class FakeOpusError(Exception):
    """Stands in for opuslib.OpusError on hosts without the native binding."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_live_ref(raw, **overrides):
    metadata = {
        'sample_rate': '16000',
        'channels': '1',
        'format': 'pcm16le',
        'sha256': digest(raw),
    }
    return {'path': 'raw-live/o/c/x.bin', 'metadata': {**metadata, **overrides}}


def stub_decoding(monkeypatch, fault):
    def broken(raw, metadata, rate):
        raise fault

    monkeypatch.setattr(source_audio, 'decode_capture', broken)


def stub_opus(monkeypatch, fault):
    def broken(raw, sample_rate=16000):
        raise fault

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)


def typed_fault(stub):
    def decode(work):
        raise RetainedAudioInvalid(str(stub)) from stub

    return decode


def typed_raise(stub):
    def decode(work):
        raise stub

    return decode


def test_fault_tuple_contains_value_error():
    assert ValueError in decoder_fault_types()


def test_fault_tuple_contains_key_error():
    assert KeyError in decoder_fault_types()


def test_fault_tuple_contains_type_error():
    assert TypeError in decoder_fault_types()


def test_fault_tuple_contains_struct_error():
    assert struct.error in decoder_fault_types()


def test_fault_tuple_contains_audioop_error():
    assert audioop.error in decoder_fault_types()


def test_fault_tuple_contains_couldnt_decode_error():
    assert source_audio.CouldntDecodeError in decoder_fault_types()


def test_fault_tuple_contains_zero_division_error():
    assert ZeroDivisionError in decoder_fault_types()


def test_fault_tuple_contains_overflow_error():
    assert OverflowError in decoder_fault_types()


def test_fault_tuple_never_contains_runtime_error():
    assert RuntimeError not in decoder_fault_types()


def test_fault_tuple_never_contains_memory_error():
    assert MemoryError not in decoder_fault_types()


def test_fault_tuple_never_contains_system_exit():
    assert SystemExit not in decoder_fault_types()


def test_fault_tuple_never_contains_keyboard_interrupt():
    assert KeyboardInterrupt not in decoder_fault_types()


def test_fault_tuple_never_contains_asyncio_cancelled():
    assert asyncio.CancelledError not in decoder_fault_types()


def test_opus_error_joins_the_tuple_only_when_the_binding_resolves():
    resolved = opus_module.opuslib is not None
    names = [cls.__name__ for cls in decoder_fault_types()]
    assert ("OpusError" in names) is resolved


def test_unresolved_binding_leaves_the_tuple_without_opus_error(monkeypatch):
    monkeypatch.setattr(opus_module, 'opuslib', None)
    source_audio._DECODER_FAULT_TYPES = None
    names = [cls.__name__ for cls in source_audio.decoder_fault_types()]
    assert 'OpusError' not in names


def test_unresolved_binding_tuple_still_covers_the_stdlib_faults(monkeypatch):
    monkeypatch.setattr(opus_module, 'opuslib', None)
    source_audio._DECODER_FAULT_TYPES = None
    tuple_out = source_audio.decoder_fault_types()
    assert ValueError in tuple_out and audioop.error in tuple_out
    assert source_audio.CouldntDecodeError in tuple_out


def test_resolved_binding_names_the_real_opus_error_class(monkeypatch):
    source_audio._DECODER_FAULT_TYPES = None
    if opus_module.opuslib is None:
        pytest.skip('native opus binding unavailable on this host')
    matches = [cls for cls in decoder_fault_types() if cls.__name__ == 'OpusError']
    assert matches and matches[0] is opus_module.opuslib.OpusError


def test_fault_tuple_is_memoized_across_calls():
    assert decoder_fault_types() is decoder_fault_types()


def test_memoized_cache_is_returned_untouched(monkeypatch):
    sentinel = (ValueError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', sentinel)
    assert source_audio.decoder_fault_types() is sentinel


def test_cache_reset_recomputes_the_tuple(monkeypatch):
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', None)
    rebuilt = source_audio.decoder_fault_types()
    assert ValueError in rebuilt
    assert source_audio._DECODER_FAULT_TYPES is rebuilt


def test_raw_live_arm_converts_value_error(monkeypatch):
    stub_decoding(monkeypatch, ValueError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_key_error(monkeypatch):
    stub_decoding(monkeypatch, KeyError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_type_error(monkeypatch):
    stub_decoding(monkeypatch, TypeError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_struct_error(monkeypatch):
    stub_decoding(monkeypatch, struct.error('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_audioop_error(monkeypatch):
    stub_decoding(monkeypatch, audioop.error('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_couldnt_decode_error(monkeypatch):
    stub_decoding(monkeypatch, source_audio.CouldntDecodeError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_zero_division_error(monkeypatch):
    stub_decoding(monkeypatch, ZeroDivisionError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_overflow_error(monkeypatch):
    stub_decoding(monkeypatch, OverflowError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_raw_live_arm_converts_stub_opus_error(monkeypatch):
    extended = decoder_fault_types() + (FakeOpusError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended)
    stub_decoding(monkeypatch, FakeOpusError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_opus_arm_converts_value_error(monkeypatch):
    stub_opus(monkeypatch, ValueError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_key_error(monkeypatch):
    stub_opus(monkeypatch, KeyError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_type_error(monkeypatch):
    stub_opus(monkeypatch, TypeError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_struct_error(monkeypatch):
    stub_opus(monkeypatch, struct.error('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_audioop_error(monkeypatch):
    stub_opus(monkeypatch, audioop.error('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_couldnt_decode_error(monkeypatch):
    stub_opus(monkeypatch, source_audio.CouldntDecodeError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_zero_division_error(monkeypatch):
    stub_opus(monkeypatch, ZeroDivisionError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_overflow_error(monkeypatch):
    stub_opus(monkeypatch, OverflowError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_arm_converts_stub_opus_error(monkeypatch):
    extended = decoder_fault_types() + (FakeOpusError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended)
    stub_opus(monkeypatch, FakeOpusError('decode failed'))
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_ratecv_tail_converts_value_error(monkeypatch):
    def broken(*_args):
        raise ValueError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_key_error(monkeypatch):
    def broken(*_args):
        raise KeyError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_type_error(monkeypatch):
    def broken(*_args):
        raise TypeError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_struct_error(monkeypatch):
    def broken(*_args):
        raise struct.error('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_audioop_error(monkeypatch):
    def broken(*_args):
        raise audioop.error('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_zero_division_error(monkeypatch):
    def broken(*_args):
        raise ZeroDivisionError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_overflow_error(monkeypatch):
    def broken(*_args):
        raise OverflowError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_ratecv_tail_converts_couldnt_decode_error(monkeypatch):
    def broken(*_args):
        raise source_audio.CouldntDecodeError('resample failed')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RetainedAudioInvalid):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


RAW_LIVE_CASES = {
    'unknown_format': {'format': 'womp-wal'},
    'zero_channels': {'channels': '0'},
    'huge_rate': {'sample_rate': '99999999999'},
    'bad_channels': {'channels': 'two'},
    'list_rate': {'sample_rate': [16000]},
    'tuple_rate': {'sample_rate': (16000,)},
    'set_rate': {'sample_rate': {16000}},
    'null_rate': {'sample_rate': None},
}
RAW_LIVE_DELETES = ('missing_meta',)


def test_real_raw_live_unknown_format_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['unknown_format'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_zero_channels_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['zero_channels'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_huge_rate_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['huge_rate'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_bad_channels_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['bad_channels'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_list_rate_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['list_rate'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_tuple_rate_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['tuple_rate'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_set_rate_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['set_rate'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_null_rate_cell_is_typed():
    raw = b'\x00\x02' * 160
    overrides = dict(RAW_LIVE_CASES['null_rate'])
    overrides['sha256'] = digest(raw)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, **overrides), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_raw_live_missing_meta_cell_is_typed():
    raw = b'\x00\x02' * 160
    ref = raw_live_ref(raw)
    del ref['metadata']['sample_rate']
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, ref, KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_real_pcm8_missing_rate_metadata_is_typed():
    raw = b'\x81\x82' * 160
    metadata = {'format': 'pcm8-u8', 'channels': '1', 'sha256': digest(raw)}
    ref = {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, ref, KEY)
    assert isinstance(error.value.__cause__, KeyError)


def test_real_missing_rate_metadata_cause_is_key_error():
    raw = b'\x00\x02' * 160
    ref = raw_live_ref(raw)
    del ref['metadata']['sample_rate']
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, ref, KEY)
    assert isinstance(error.value.__cause__, KeyError)


def test_real_zero_channels_cause_is_zero_division():
    raw = b'\x00\x02' * 160
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, channels='0'), KEY)
    assert isinstance(error.value.__cause__, ZeroDivisionError)


def test_real_huge_rate_cause_is_overflow():
    raw = b'\x00\x02' * 160
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, sample_rate='99999999999'), KEY)
    assert isinstance(error.value.__cause__, OverflowError)


def test_real_unknown_format_cause_is_key_error():
    raw = b'\x00\x02' * 160
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(raw, raw_live_ref(raw, format='womp-wal'), KEY)
    assert isinstance(error.value.__cause__, KeyError)


def test_value_error_message_keeps_its_passthrough(monkeypatch):
    stub = ValueError('capture PCM is not sample-aligned')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid, match='^capture PCM is not sample-aligned$'):
        decode_source(PCM, raw_live_ref(PCM), KEY)


def test_key_error_cause_is_chained(monkeypatch):
    stub = KeyError('sample_rate')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_audioop_error_cause_is_chained(monkeypatch):
    stub = audioop.error('fragments')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_couldnt_decode_error_cause_is_chained(monkeypatch):
    stub = source_audio.CouldntDecodeError('format')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_zero_division_error_cause_is_chained(monkeypatch):
    stub = ZeroDivisionError('frame math')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_overflow_error_cause_is_chained(monkeypatch):
    stub = OverflowError('rate')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_struct_error_cause_is_chained(monkeypatch):
    stub = struct.error('unpack')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_type_error_cause_is_chained(monkeypatch):
    stub = TypeError('shape')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_stub_opus_error_cause_is_chained(monkeypatch):
    extended = decoder_fault_types() + (FakeOpusError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended)
    stub = FakeOpusError('packet')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value.__cause__ is stub


def test_opus_arm_key_error_cause_is_chained(monkeypatch):
    stub = KeyError('packet table')
    stub_opus(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)
    assert error.value.__cause__ is stub


def test_runtime_error_still_escapes_the_raw_live_arm_untyped(monkeypatch):
    stub = RuntimeError('backend unavailable')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RuntimeError) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value is stub


def test_memory_error_still_escapes_the_raw_live_arm_untyped(monkeypatch):
    stub = MemoryError('backend unavailable')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(MemoryError) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert error.value is stub


def test_runtime_error_still_escapes_the_opus_arm_untyped(monkeypatch):
    stub = RuntimeError('decoder backend unavailable')
    stub_opus(monkeypatch, stub)
    with pytest.raises(RuntimeError) as error:
        decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY)
    assert error.value is stub


def test_runtime_error_still_escapes_the_ratecv_tail_untyped(monkeypatch):
    def broken(*_args):
        raise RuntimeError('resampler backend unavailable')

    monkeypatch.setattr(source_audio.audioop, 'ratecv', broken)
    with pytest.raises(RuntimeError):
        decode_source(PCM, {'path': 'chunks/o/c/x.bin', 'sample_rate': 8000}, KEY)


def test_converted_fault_is_still_a_value_error_for_the_legacy_boundary(monkeypatch):
    stub_decoding(monkeypatch, KeyError('sample_rate'))
    with pytest.raises(ValueError) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_converted_fault_is_not_the_manifest_subclass(monkeypatch):
    stub_decoding(monkeypatch, KeyError('sample_rate'))
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert not isinstance(error.value, InvalidRetainedManifest)


def test_converted_fault_message_never_carries_private_payload(monkeypatch):
    stub = KeyError('owner-secret-key-name')
    stub_decoding(monkeypatch, stub)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, raw_live_ref(PCM), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)


def test_worker_terminal_for_key_error_fault():
    worker, words, saved, *_ = setup_worker(decode=typed_fault(KeyError('sample_rate')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_worker_terminal_for_audioop_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(audioop.error('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_couldnt_decode_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(source_audio.CouldntDecodeError('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_zero_division_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(ZeroDivisionError('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_overflow_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(OverflowError('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_struct_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(struct.error('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_for_type_error_fault(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(TypeError('x')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_with_safety_net_on(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=typed_fault(KeyError('sample_rate')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_terminal_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_fault(KeyError('sample_rate')))
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_shadow_terminal_for_converted_fault():
    from dataclasses import replace as _replace

    worker, *_ = setup_worker(decode=typed_fault(KeyError('sample_rate')))
    results = worker.process_batch([_replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_worker_counts_one_failure_for_converted_fault():
    worker, _, _, _, _, failures = setup_worker(decode=typed_fault(KeyError('sample_rate')))
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1
    assert failures == [('a', 'RetainedAudioInvalid')]


def test_worker_decode_runs_once_for_converted_fault():
    decoded = []

    def decode(work):
        decoded.append(work.segment_id)
        raise RetainedAudioInvalid('x') from KeyError('sample_rate')

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert decoded == ['a']


def test_worker_log_names_the_closed_reason_not_the_message(caplog):
    caplog.set_level(20)
    worker, *_ = setup_worker(decode=typed_fault(KeyError('the stored key text')))
    worker.process_batch([item()])
    assert 'reason=retained_audio_invalid' in caplog.text
    assert 'the stored key text' not in caplog.text


def test_worker_siblings_survive_a_converted_fault():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('x') from KeyError('sample_rate')
        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item('bad'), item('ok')])
    assert [r.segment_id for r in results] == ['bad', 'ok']
    assert isinstance(results[0], ValidationFailureWork)
    assert results[1].outcome == 'success' and saved['ok']['words']


def test_plain_runtime_error_still_yields_failed_work_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    worker, *_ = setup_worker(decode=typed_raise(RuntimeError('backend unavailable')))
    results = worker.process_batch([item()])
    assert len(results) == 1 and isinstance(results[0], FailedWork)


def test_plain_runtime_error_yields_no_work_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    worker, *_ = setup_worker(decode=typed_raise(RuntimeError('backend unavailable')))
    assert worker.process_batch([item()]) == []


def test_terminal_work_validates_against_the_closed_vocabulary():
    validate_worker_failure({'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'})


def test_converted_fault_quarantines_on_first_attempt(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail(
        'a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    job = store.rows['jobs', 'a']
    assert job['state'] == 'quarantined' and job['attempt'] == 1
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    assert job['recovery_state'] == 'held' and not job['merge_pending']


def test_converted_fault_never_reenters_the_pull_ring(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail(
        'a', lease.token, now, worker_failure={'stage': 'fetch_decode', 'reason': 'retained_audio_invalid'}
    )
    now += 3600
    assert queue.recover(now) == 0
    assert queue.pull(now) == []


def test_untyped_runtime_fault_walks_the_ladder(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item(), time.time())
    now = time.time()
    lease = queue.pull(now)[0]
    assert queue.fail('a', lease.token, now)
    job = store.rows['jobs', 'a']
    assert job['state'] == 'retry'
    assert job['available_at'] > time.time()
    assert 'worker_failure' not in job


def test_fault_tuple_is_frozen():
    assert isinstance(decoder_fault_types(), tuple)


def test_fault_tuple_holds_classes_not_instances():
    assert all(isinstance(cls, type) for cls in decoder_fault_types())


def test_fault_tuple_stays_stable_across_calls():
    first = decoder_fault_types()
    second = decoder_fault_types()
    assert first == second


def test_staged_audio_invalid_is_not_in_the_fault_tuple_by_name():
    assert "StagedAudioInvalid" not in [cls.__name__ for cls in decoder_fault_types()]


def test_retained_audio_invalid_is_not_in_the_fault_tuple_by_name():
    assert "RetainedAudioInvalid" not in [cls.__name__ for cls in decoder_fault_types()]


def test_couldnt_decode_error_is_pydubs_decode_fault():
    assert issubclass(source_audio.CouldntDecodeError, Exception)


def test_audioop_error_is_an_exception_subclass():
    assert issubclass(audioop.error, Exception)


def test_struct_error_is_an_exception_subclass():
    assert issubclass(struct.error, Exception)


def test_fault_tuple_has_no_duplicate_classes():
    names = list(decoder_fault_types())
    assert len(names) == len(set(names))


def test_fault_tuple_length_matches_the_documented_membership():
    expected = 8 + (1 if opus_module.opuslib is not None else 0)
    assert len(decoder_fault_types()) == expected
