"""Dense intake-context chunk-walk cells: benign non-context chunks before and
after the context chunk, odd and even chunk paddings, chunk sizes at the
limit boundary, and a context chunk sitting alone in the envelope all parse
to the exact same frozen dict.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import io
import json
import struct
import wave

import pytest

from utils.batch_pipeline.audio import (
    INTAKE_CONTEXT_CHUNK,
    INTAKE_CONTEXT_LIMIT,
    INTAKE_CONTEXT_VERSION,
    read_context,
    with_context,
)

PCM = b"\x00\x02" * 320


def canonical_wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(PCM)
    return output.getvalue()


def resized(body):
    return body[:4] + struct.pack('<I', len(body) - 8) + body[8:]


def test_benign_chunks_before_the_context_parse():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw + (b'\x00' if len(raw) % 2 else b'')
    benign = b'JUNK' + struct.pack('<I', 4) + b'abcd'
    body = canonical_wav() + benign + chunk
    assert read_context(resized(body)) == {'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}


def test_benign_chunks_after_the_context_parse():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw + (b'\x00' if len(raw) % 2 else b'')
    benign = b'JUNK' + struct.pack('<I', 4) + b'abcd'
    body = canonical_wav() + chunk + benign
    assert read_context(resized(body)) == {'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}


def test_odd_benign_chunks_skip_their_pad_byte():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw + (b'\x00' if len(raw) % 2 else b'')
    benign = b'JUNK' + struct.pack('<I', 3) + b'abc' + b'\x00'
    body = canonical_wav() + benign + chunk
    assert read_context(resized(body)) == {'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}


def test_a_zero_length_benign_chunk_parses():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw + (b'\x00' if len(raw) % 2 else b'')
    benign = b'JUNK' + struct.pack('<I', 0)
    body = canonical_wav() + benign + chunk
    assert read_context(resized(body)) == {'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}


def test_an_unpadded_odd_context_chunk_is_malformed():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw
    body = canonical_wav() + chunk
    with pytest.raises(ValueError, match='^authenticated intake context is required$'):
        read_context(resized(body))


def test_a_benign_chunk_declared_past_the_envelope_is_typed():
    raw = json.dumps({'owner_id': 'o', 'version': INTAKE_CONTEXT_VERSION}).encode()
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(raw)) + raw + (b'\x00' if len(raw) % 2 else b'')
    benign = b'JUNK' + struct.pack('<I', 999)
    body = canonical_wav() + chunk + benign
    with pytest.raises(ValueError, match='^truncated intake WAV chunk$'):
        read_context(resized(body))


def test_the_context_chunk_at_a_single_byte_never_parses():
    raw = b'{'
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', 1) + raw
    body = canonical_wav() + chunk
    with pytest.raises(ValueError):
        read_context(resized(body))


def test_context_at_the_limit_minus_one_byte_parses():
    payload_len = (
        INTAKE_CONTEXT_LIMIT
        - len(json.dumps({'version': INTAKE_CONTEXT_VERSION}, sort_keys=True, separators=(',', ':')).encode())
        - len('{"k":""}')
    )
    frozen = {'k': 'x' * payload_len}
    body = with_context(canonical_wav(), frozen)
    assert read_context(body)['k'] == frozen['k']


def test_sealed_bodies_keep_the_envelope_total_length_even():
    for tail in ('', 'x'):
        body = with_context(canonical_wav(), {'k': tail})
        assert len(body) % 2 == 0


def test_two_seals_of_the_same_context_are_byte_identical():
    frozen = {'owner_id': 'o'}
    assert with_context(canonical_wav(), frozen) == with_context(canonical_wav(), frozen)


def test_different_contexts_seal_differently():
    one = with_context(canonical_wav(), {'owner_id': 'a'})
    two = with_context(canonical_wav(), {'owner_id': 'b'})
    assert one != two


def test_seal_then_read_is_the_identity_for_sorted_contexts():
    frozen = {'a': 1, 'b': ['x', 'y'], 'c': {'d': True}}
    assert read_context(with_context(canonical_wav(), frozen)) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_chunk_id_is_the_documented_custom_marker():
    assert INTAKE_CONTEXT_CHUNK == b'OMIM'


def test_seal_preserves_every_original_wave_byte_after_the_header_size():
    wav = canonical_wav()
    body = with_context(wav, {"owner_id": "o"})
    assert body[:4] == wav[:4]
    assert body[12 : len(wav)] == wav[12:]


def test_seal_output_length_is_wave_plus_chunk_overhead():
    wav = canonical_wav()
    frozen = {"owner_id": "o"}
    body = with_context(wav, frozen)
    raw = json.dumps({**frozen, "version": INTAKE_CONTEXT_VERSION}, sort_keys=True, separators=(",", ":")).encode()
    overhead = 4 + 4 + len(raw) + (len(raw) % 2)
    assert len(body) == len(wav) + overhead


def test_seal_declared_chunk_size_matches_the_body_length():
    frozen = {"owner_id": "o"}
    wav = canonical_wav()
    body = with_context(wav, frozen)
    declared = struct.unpack("<I", body[len(wav) + 4 : len(wav) + 8])[0]
    assert declared == len(
        json.dumps({**frozen, "version": INTAKE_CONTEXT_VERSION}, sort_keys=True, separators=(",", ":")).encode()
    )


def test_read_context_typed_when_data_follows_an_odd_unpadded_last_chunk():
    body = with_context(canonical_wav(), {"owner_id": "o"})
    body = body + b"\x01"
    with pytest.raises(ValueError):
        read_context(body)
