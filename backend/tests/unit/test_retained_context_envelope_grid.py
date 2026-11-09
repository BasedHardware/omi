"""The authenticated intake-context envelope and capture-stream identity grid.
Retained materialization seals provenance with with_context and the worker
resolves it with read_context, so every envelope rule (RIFF framing, chunk
bounds, JSON strictness, padding parity, RIFF size rewrite) and every stream
identity rule is pinned here byte-exactly.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import hashlib
import io
import json
import struct
import wave

import pytest

from types import SimpleNamespace

from utils.batch_pipeline.audio import (
    INTAKE_CONTEXT_CHUNK,
    INTAKE_CONTEXT_LIMIT,
    INTAKE_CONTEXT_VERSION,
    audio_unit,
    read_context,
    with_context,
)
from diarizer.batch_pipeline_context import capture_stream
from utils.batch_pipeline.source_audio import batch_timing_store

PCM16 = b"\x00\x02" * 320


def canonical_wav(pcm=PCM16):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm)
    return output.getvalue()


def sealed(wav=None, context=None):
    return with_context(wav if wav is not None else canonical_wav(), context or {'owner_id': 'o'})


def test_with_context_appends_the_chunk_after_the_pcm():
    wav = canonical_wav()
    body = sealed(wav)
    assert body[:4] == wav[:4]
    assert body[12 : len(wav)] == wav[12:]
    assert len(body) > len(wav)


def test_with_context_rewrites_the_riff_size_to_cover_the_chunk():
    wav = canonical_wav()
    body = sealed(wav)
    assert struct.unpack('<I', body[4:8])[0] == len(body) - 8


def test_with_context_keeps_the_wave_form_identifier():
    body = sealed()
    assert body[8:12] == b'WAVE'


def test_with_context_marks_the_custom_chunk_id():
    body = sealed()
    chunk = body[len(canonical_wav()) : len(canonical_wav()) + 4]
    assert chunk == INTAKE_CONTEXT_CHUNK


def test_with_context_stores_the_canonical_version():
    context = read_context(sealed())
    assert context['version'] == INTAKE_CONTEXT_VERSION


def test_with_context_roundtrips_the_frozen_context():
    frozen = {'owner_id': 'o', 'segment_id': 's', 'nested': {'a': 1}}
    assert read_context(sealed(context=frozen)) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_with_context_pads_odd_context_bodies():
    frozen = {'k': 'v'}
    body = sealed(context=frozen)
    chunk_body = len(
        json.dumps({'k': 'v', 'version': INTAKE_CONTEXT_VERSION}, sort_keys=True, separators=(',', ':')).encode()
    )
    declared = struct.unpack('<I', body[len(canonical_wav()) + 4 : len(canonical_wav()) + 8])[0]
    assert declared == chunk_body
    assert len(body) % 2 == 0


def test_with_context_rejects_nan_context_values():
    with pytest.raises(ValueError):
        with_context(canonical_wav(), {'rate': float('nan')})


def test_with_context_rejects_infinite_context_values():
    with pytest.raises(ValueError):
        with_context(canonical_wav(), {'rate': float('inf')})


def test_with_context_rejects_non_riff_bytes():
    with pytest.raises(ValueError):
        with_context(b'\x00' * 64, {'owner_id': 'o'})


def test_with_context_rejects_a_truncated_riff_header():
    with pytest.raises(ValueError):
        with_context(b'RIFF', {'owner_id': 'o'})


def test_with_context_rejects_non_wave_riff():
    junk = b'RIFF\x00\x00\x00\x00JUNK' + b'\x00' * 8
    with pytest.raises(ValueError):
        with_context(junk, {'owner_id': 'o'})


def test_with_context_rejects_oversized_context_bodies():
    huge = {'blob': 'x' * (INTAKE_CONTEXT_LIMIT + 1)}
    with pytest.raises(ValueError):
        with_context(canonical_wav(), huge)


def test_with_context_accepts_a_context_at_the_limit_minus_version():
    payload = 'x' * 64
    body = sealed(context={'blob': payload})
    assert read_context(body)['blob'] == payload


def test_read_context_rejects_missing_riff():
    with pytest.raises(ValueError):
        read_context(b'\x00' * 64)


def test_read_context_rejects_missing_wave():
    junk = b'RIFF' + struct.pack('<I', 56) + b'JUNK' + b'\x00' * 48
    with pytest.raises(ValueError):
        read_context(junk)


def test_read_context_rejects_a_wrong_riff_size():
    wav = canonical_wav()
    broken = wav[:4] + struct.pack('<I', 999) + wav[8:]
    with pytest.raises(ValueError):
        read_context(broken)


def test_read_context_rejects_a_trailing_partial_chunk():
    body = sealed() + b'\x00'
    with pytest.raises(ValueError):
        read_context(body)


def test_read_context_rejects_duplicate_context_chunks():
    body = sealed() + sealed()[len(canonical_wav()) :]
    with pytest.raises(ValueError):
        read_context(body)


def test_read_context_reject_an_oversized_declared_chunk():
    body = bytearray(sealed())
    offset = len(canonical_wav()) + 4
    body[offset : offset + 4] = struct.pack('<I', INTAKE_CONTEXT_LIMIT + 1)
    with pytest.raises(ValueError):
        read_context(bytes(body))


def test_read_context_rejects_a_wrong_version():
    raw = json.dumps({'owner_id': 'o', 'version': 99}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw
    wav = canonical_wav()
    body = wav + chunk
    body = body[:4] + struct.pack('<I', len(body) - 8) + body[8:]
    with pytest.raises(ValueError):
        read_context(body)


def test_read_context_rejects_a_non_dict_context():
    raw = json.dumps([1, 2]).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw
    wav = canonical_wav()
    body = wav + chunk
    body = body[:4] + struct.pack('<I', len(body) - 8) + body[8:]
    with pytest.raises(ValueError):
        read_context(body)


def test_read_context_rejects_corrupt_chunk_json():
    raw = b'{not-json'
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw
    wav = canonical_wav()
    body = wav + chunk
    body = body[:4] + struct.pack('<I', len(body) - 8) + body[8:]
    with pytest.raises(ValueError):
        read_context(body)


def test_read_context_requires_the_context_chunk():
    wav = canonical_wav()
    with pytest.raises(ValueError):
        read_context(wav)


def test_read_context_tolerates_even_padding_after_the_chunk():
    frozen = {'k': 'vv'}
    body = sealed(context=frozen)
    assert read_context(body) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_audio_unit_seals_pcm_into_a_canonical_wav():
    unit = audio_unit(1.0, PCM16)
    assert unit.capture_at == 1.0
    assert unit.duration_seconds == len(PCM16) / 32000.0


def test_audio_unit_wav_is_a_valid_canonical_container():
    unit = audio_unit(1.0, PCM16)
    handle = wave.open(io.BytesIO(unit.wav), 'rb')
    assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, 16000)


def test_audio_unit_duration_matches_the_pcm_frames():
    pcm = b'\x00\x02' * 1600
    unit = audio_unit(2.5, pcm)
    assert unit.duration_seconds == pytest.approx(1600 / 16000.0)


def test_audio_unit_empty_pcm_is_a_zero_length_unit():
    unit = audio_unit(0.0, b'')
    assert unit.duration_seconds == 0.0


def test_audio_unit_provenance_defaults_are_empty():
    unit = audio_unit(1.0, PCM16)
    assert unit.coverage_runs == ()
    assert unit.stored_capture_at is None


def test_conversation_unit_is_its_own_stream():
    it = SimpleNamespace(
        unit_kind='conversation',
        conversation_id='conv-1',
    )
    stream = capture_stream(it, None)
    assert stream.startswith('conversation:conv-1')


def test_conversation_unit_without_id_has_no_stream():
    it = SimpleNamespace(
        unit_kind='conversation',
        conversation_id=None,
    )
    assert capture_stream(it, {'source': 'app'}) is None


def test_capture_unit_without_context_has_no_stream():
    it = SimpleNamespace(
        unit_kind='capture',
        conversation_id='c',
    )
    assert capture_stream(it, None) is None


def test_capture_unit_with_non_string_source_has_no_stream():
    it = SimpleNamespace(
        unit_kind='capture',
        conversation_id='c',
    )
    assert capture_stream(it, {'source': 7}) is None


def test_capture_stream_is_the_capture_prefix():
    it = SimpleNamespace(
        unit_kind='capture',
        conversation_id='ignored',
    )
    stream = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True})
    assert stream.startswith('capture:')


def test_capture_stream_binds_source_device_and_lock():
    it = SimpleNamespace(unit_kind='capture', conversation_id='c')
    one = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True})
    two = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': False})
    three = capture_stream(it, {'source': 'other', 'client_device_id': 'dev', 'should_lock': True})
    four = capture_stream(it, {'source': 'app', 'client_device_id': 'dev2', 'should_lock': True})
    assert len({one, two, three, four}) == 4


def test_capture_stream_is_a_deterministic_sha256():
    it = SimpleNamespace(unit_kind='capture', conversation_id='c')
    stream = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True})
    identity = json.dumps(['app', 'dev', True]).encode()
    assert stream == 'capture:' + hashlib.sha256(identity).hexdigest()


def test_capture_stream_ignores_extra_context_keys():
    it = SimpleNamespace(unit_kind='capture', conversation_id='c')
    one = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True})
    two = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True, 'extra': 'x'})
    assert one == two


def test_capture_stream_missing_device_is_a_distinct_identity():
    it = SimpleNamespace(unit_kind='capture', conversation_id='c')
    one = capture_stream(it, {'source': 'app', 'should_lock': True})
    two = capture_stream(it, {'source': 'app', 'client_device_id': 'dev', 'should_lock': True})
    assert one != two


def test_capture_stream_hash_differs_from_the_conversation_form():
    capture_it = SimpleNamespace(unit_kind='capture', conversation_id='ignored')
    conversation_it = SimpleNamespace(unit_kind='conversation', conversation_id='ignored')
    capture = capture_stream(capture_it, {'source': 'ignored'})
    conversation = capture_stream(conversation_it, None)
    assert capture != conversation


def test_batch_timing_store_empty_references_is_none():
    assert batch_timing_store([]) is None


def test_batch_timing_store_homogeneous_batch_enc_is_batch():
    refs = [{'path': 'raw-live/o/c/a.batch.enc'}, {'path': 'raw-live/o/c/b.batch.enc'}]
    assert batch_timing_store(refs) == 'batch'


def test_batch_timing_store_homogeneous_batch_bin_is_batch():
    refs = [{'path': 'raw-live/o/c/a.batch.bin'}]
    assert batch_timing_store(refs) == 'batch'


def test_batch_timing_store_plain_raw_live_is_none():
    refs = [{'path': 'raw-live/o/c/a.bin'}]
    assert batch_timing_store(refs) is None


def test_batch_timing_store_chunks_are_none():
    refs = [{'path': 'chunks/o/c/a.enc'}]
    assert batch_timing_store(refs) is None


def test_batch_timing_store_mixed_cohort_is_none():
    refs = [{'path': 'raw-live/o/c/a.batch.enc'}, {'path': 'chunks/o/c/b.enc'}]
    assert batch_timing_store(refs) is None


def test_batch_timing_store_missing_path_is_none():
    refs = [{}]
    assert batch_timing_store(refs) is None


def test_batch_timing_store_none_path_is_none():
    refs = [{'path': None}]
    assert batch_timing_store(refs) is None
