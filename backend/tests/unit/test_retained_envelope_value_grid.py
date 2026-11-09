"""Sealed-envelope value grid: unicode, nested, empty and long-string intake
contexts roundtrip through the seal byte-identically, and the fetch arm
routing table covers the raw-live prefix shapes and encrypted-marker
interactions at the path level.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import io
import json
import struct
import wave

import pytest

from utils.batch_pipeline.audio import INTAKE_CONTEXT_VERSION, read_context, with_context
from utils.batch_pipeline.source_audio import RetainedAudioInvalid, decode_source

PCM = b"\x00\x02" * 320
KEY = b"\x11" * 32


def canonical_wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(PCM)
    return output.getvalue()


def test_context_unicode_value_roundtrips_byte_identically():
    frozen = {'owner': 'caf\\u00e9'}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_nested_value_roundtrips_byte_identically():
    frozen = {'a': {'b': [1, 2, {'c': 3}]}}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_empty_string_value_roundtrips_byte_identically():
    frozen = {'k': ''}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_empty_dict_value_roundtrips_byte_identically():
    frozen = {'d': {}}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_boolean_value_roundtrips_byte_identically():
    frozen = {'flag': True}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_negative_number_roundtrips_byte_identically():
    frozen = {'n': -42}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_float_value_roundtrips_byte_identically():
    frozen = {'f': 0.5}
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_context_long_string_value_roundtrips_byte_identically():
    frozen = {
        's': 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy'
    }
    one = with_context(canonical_wav(), frozen)
    two = with_context(canonical_wav(), frozen)
    assert one == two
    assert read_context(one) == {**frozen, 'version': INTAKE_CONTEXT_VERSION}


def test_empty_context_still_seals_the_version():
    body = with_context(canonical_wav(), {})
    assert read_context(body) == {'version': INTAKE_CONTEXT_VERSION}


def test_context_key_order_does_not_change_the_seal():
    one = with_context(canonical_wav(), {'a': 1, 'b': 2})
    two = with_context(canonical_wav(), {'b': 2, 'a': 1})
    assert one == two


def test_raw_live_prefix_alone_is_not_enough_without_checksum():
    ref = {'path': 'raw-live/o/c/x.bin', 'metadata': {'format': 'pcm16le', 'sample_rate': '16000', 'channels': '1'}}
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(PCM, ref, KEY)


def test_enc_suffix_and_checksum_together_route_the_capture_decoder(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    seen = []

    def probe(raw, metadata, rate):
        seen.append(raw)
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    import hashlib

    raw = PCM
    ref = {
        'path': 'raw-live/o/c/x.bin.enc',
        'metadata': {
            'sha256': hashlib.sha256(raw).hexdigest(),
            'format': 'pcm16le',
            'sample_rate': '16000',
            'channels': '1',
        },
    }
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = b'\n' * 12
    sealed = AESGCM(KEY).encrypt(nonce, raw, None)
    body = struct.pack('>I', 12 + len(sealed)) + nonce + sealed
    assert decode_source(body, ref, KEY) == raw
    assert seen == [raw]


def test_metadata_encrypted_flag_routes_the_opus_body_through_the_decrypt_loop():
    ref = {'path': 'chunks/o/c/x.opus', 'metadata': {'encrypted': 'true'}}
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(PCM, ref, KEY)


def test_chunks_path_without_rate_uses_the_default_passthrough():
    assert decode_source(PCM, {'path': 'chunks/o/c/x.bin'}, KEY) == PCM


def test_deep_path_still_routes_the_pcm_tail():
    out = decode_source(PCM, {'path': 'chunks/o/c/2026/11/deep/x.bin', 'sample_rate': 16000}, KEY)
    assert out == PCM


def test_path_with_query_like_characters_routes_normally():
    out = decode_source(PCM, {'path': 'chunks/o/c/x (1).bin', 'sample_rate': 16000}, KEY)
    assert out == PCM


def test_enc_suffix_decrypts_before_the_raw_live_checksum():
    import hashlib

    raw = PCM
    ref = {
        'path': 'raw-live/o/c/x.bin.enc',
        'metadata': {
            'sha256': hashlib.sha256(raw).hexdigest(),
            'format': 'pcm16le',
            'sample_rate': '16000',
            'channels': '1',
        },
    }
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(raw, ref, KEY)
