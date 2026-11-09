"""Worker-boundary custody parity for every typed retained fault class: each
converted decoder fault ends the GPU chain with ValidationFailureWork and
closed evidence under both safety-net states and for shadow units, while the
deliberately untyped deploy faults keep the legacy retry semantics. Failure
records, callback wiring and sibling semantics are pinned alongside.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import logging
import struct

import audioop
import pytest

import utils.batch_pipeline.source_audio as source_audio
from utils.batch_pipeline.contracts import FailedWork, ValidationFailureWork
from utils.batch_pipeline.source_audio import RetainedAudioInvalid
from tests.unit.test_batch_pipeline_worker import Samples, item, setup_worker

PCM = b"\0\2" * 320


class FakeOpusError(Exception):
    pass


FAULT_CLASSES = {
    'key_error': KeyError('k'),
    'type_error': TypeError('t'),
    'struct_error': struct.error('s'),
    'audioop_error': audioop.error('a'),
    'couldnt_decode_error': source_audio.CouldntDecodeError('c'),
    'zero_division_error': ZeroDivisionError('z'),
    'overflow_error': OverflowError('o'),
}


def test_raw_live_key_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_key_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_type_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_type_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_struct_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_struct_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_audioop_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_audioop_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_couldnt_decode_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_couldnt_decode_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_zero_division_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_zero_division_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_overflow_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_raw_live_overflow_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_key_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_key_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_type_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_type_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_struct_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_struct_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_audioop_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_audioop_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_couldnt_decode_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_couldnt_decode_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_zero_division_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_zero_division_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_overflow_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_opus_overflow_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_key_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_key_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['key_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_type_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_type_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['type_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_struct_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_struct_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['struct_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_audioop_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_audioop_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['audioop_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_couldnt_decode_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_couldnt_decode_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['couldnt_decode_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_zero_division_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_zero_division_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['zero_division_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_overflow_error_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_pcm_tail_overflow_error_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    stub = FAULT_CLASSES['overflow_error']

    def decode(work, _stub=stub):
        raise RetainedAudioInvalid(str(_stub)) from _stub

    worker, words, saved, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]
    assert not words.calls and not saved


def test_stub_opus_error_class_ends_the_chain_with_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    extended = source_audio.decoder_fault_types() + (FakeOpusError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended)

    def decode(work):
        raise RetainedAudioInvalid('x') from FakeOpusError('p')

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_stub_opus_error_class_ends_the_chain_without_safety_net(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    extended = source_audio.decoder_fault_types() + (FakeOpusError,)
    monkeypatch.setattr(source_audio, '_DECODER_FAULT_TYPES', extended)

    def decode(work):
        raise RetainedAudioInvalid('x') from FakeOpusError('p')

    worker, *_ = setup_worker(decode=decode)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_shadow_unit_takes_the_same_terminal_route():
    from dataclasses import replace as _replace

    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('k')

    worker, *_ = setup_worker(decode=decode)
    results = worker.process_batch([_replace(item(), shadow=True)])
    assert results == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_failure_record_books_the_typed_class():
    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('k')

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert worker.counts['failed'] == 1


def test_on_failure_callback_receives_the_typed_class_name():
    seen = []

    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('k')

    worker, *_ = setup_worker(decode=decode, on_failure=lambda work, cls: seen.append(cls))
    worker.process_batch([item()])
    assert seen == ['RetainedAudioInvalid']


def test_raising_on_failure_callback_never_drops_the_failure():
    def boom(work, cls):
        raise RuntimeError('callback')

    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('k')

    worker, *_ = setup_worker(decode=decode, on_failure=boom)
    assert worker.process_batch([item()]) == [ValidationFailureWork('a', 'fetch_decode', 'retained_audio_invalid')]


def test_sibling_survival_with_the_fault_first():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('x') from KeyError('k')
        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item('bad'), item('ok1'), item('ok2')])
    assert [r.segment_id for r in results] == ['bad', 'ok1', 'ok2']
    assert isinstance(results[0], ValidationFailureWork)


def test_sibling_survival_with_the_fault_middle():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('x') from KeyError('k')
        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item('ok1'), item('bad'), item('ok2')])
    assert [r.segment_id for r in results] == ['bad', 'ok1', 'ok2']
    assert isinstance(results[0], ValidationFailureWork)


def test_sibling_survival_with_the_fault_last():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('x') from KeyError('k')
        return Samples(2)

    worker, words, saved, *_ = setup_worker(decode=decode)
    results = worker.process_batch([item('ok1'), item('ok2'), item('bad')])
    assert [r.segment_id for r in results] == ['bad', 'ok1', 'ok2']
    assert isinstance(results[0], ValidationFailureWork)


def test_only_the_faulted_unit_is_counted_failed():
    def decode(work):
        if work.segment_id == 'bad':
            raise RetainedAudioInvalid('x') from KeyError('k')
        return Samples(2)

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item('bad'), item('ok')])
    assert worker.counts['failed'] == 1
    assert worker.counts['items'] == 2


def test_worker_log_leaks_no_cause_text(caplog):
    caplog.set_level(40)

    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('secret-key-text')

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert 'secret-key-text' not in caplog.text


def test_worker_log_names_the_stage_once_per_unit(caplog):
    caplog.set_level(20)

    def decode(work):
        raise RetainedAudioInvalid('x') from KeyError('k')

    worker, *_ = setup_worker(decode=decode)
    worker.process_batch([item()])
    assert caplog.text.count('stage=fetch_decode') >= 1


def test_untyped_fault_log_keeps_the_error_channel(caplog):
    caplog.set_level(40)
    worker, *_ = setup_worker(decode=lambda work: (_ for _ in ()).throw(RuntimeError('binding')))
    worker.process_batch([item()])
    assert 'event=batch_worker_failed' in caplog.text
