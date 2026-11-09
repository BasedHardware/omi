"""The retained decode_source arm grid: every stored-reference shape routes to
exactly one arm (encrypted, raw-live capture, legacy opus, canonical PCM tail)
and every guard cell carries the typed family token with its exact message.
Routing and guard cells together fence the fetch_decode boundary so a new
deterministic fault cannot silently rejoin the anonymous retry ladder.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import hashlib
import struct

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import utils.batch_pipeline.source_audio as source_audio
import utils.other.audio_opus as opus_module
from utils.batch_pipeline.source_audio import (
    MAX_SOURCE_BYTES,
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    decode_source,
)

KEY = b"\2" * 32
PCM = b"\x00\x02" * 320


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def enc_frame(key, payload):
    nonce = b'\n' * 12
    sealed = AESGCM(key).encrypt(nonce, payload, None)
    return struct.pack('>I', 12 + len(sealed)) + nonce + sealed


def chunk_ref(**extra):
    return {'path': 'chunks/o/c/x.bin', **extra}


def raw_meta(raw, **overrides):
    metadata = {
        'sample_rate': '16000',
        'channels': '1',
        'format': 'pcm16le',
        'sha256': digest(raw),
    }
    return {**metadata, **overrides}


def raw_live_ref(raw, **overrides):
    return {'path': 'raw-live/o/c/x.bin', 'metadata': raw_meta(raw, **overrides)}


def identity_capture(raw, metadata, rate):
    return raw


def identity_opus(raw, sample_rate=16000):
    return PCM


def test_empty_body_is_typed_invalid_size():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'', chunk_ref(), KEY)


def test_oversize_body_is_typed_invalid_size():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'\0' * (MAX_SOURCE_BYTES + 1), chunk_ref(), KEY)


def test_body_at_the_exact_size_bound_reaches_the_arms(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    raw = b'\0' * MAX_SOURCE_BYTES
    out = decode_source(raw, raw_live_ref(raw), KEY)
    assert out == raw


def test_empty_body_is_typed_even_for_the_encrypted_arm():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'', chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_size_guard_precedes_the_checksum():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'', raw_live_ref(b''), KEY)


def test_size_guard_precedes_the_encrypted_arm():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'', chunk_ref(path='raw-live/o/c/x.bin.enc'), KEY)


def test_encrypted_three_byte_header_is_typed_truncated_encrypted():
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(b'\0\0\0', chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_zero_size_frame_is_typed_invalid_encrypted():
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(struct.pack('>I', 0), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_below_minimum_frame_is_typed_invalid_encrypted():
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(struct.pack('>I', 4), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_oversize_frame_is_typed_invalid_encrypted():
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(struct.pack('>I', MAX_SOURCE_BYTES + 1), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_size_past_eof_is_typed_invalid_encrypted():
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(struct.pack('>I', 4096), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_undersized_aes_frame_is_typed_retained_audio():
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(struct.pack('>I', 28) + b'\0' * 28, chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_encrypted_roundtrip_returns_the_exact_plaintext():
    assert decode_source(enc_frame(KEY, PCM), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY) == PCM


def test_wrong_key_ciphertext_is_typed_authentication():
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(enc_frame(b'\x09' * 32, PCM), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_tampered_ciphertext_is_typed_authentication():
    body = enc_frame(KEY, PCM)
    tampered = body[:-1] + bytes([body[-1] ^ 1])
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(tampered, chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_metadata_encrypted_flag_routes_the_decrypt_loop():
    body = enc_frame(KEY, PCM)
    ref = {'path': 'chunks/o/c/x.bin', 'metadata': {'encrypted': 'true'}}
    with pytest.raises(RetainedAudioInvalid):
        decode_source(body, ref, b'\3' * 32)


def test_metadata_encrypted_false_keeps_the_plain_path(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    raw = PCM
    ref = raw_live_ref(raw, encrypted='false')
    assert decode_source(raw, ref, KEY) == raw


def test_encrypted_flag_with_wrong_key_authenticates_loudly():
    body = enc_frame(KEY, PCM)
    ref = {'path': 'chunks/o/c/x.bin', 'metadata': {'encrypted': 'true'}}
    with pytest.raises(RetainedAudioInvalid, match='^retained audio authentication failed$'):
        decode_source(body, ref, b'\4' * 32)


def test_decrypt_then_raw_live_composes_on_one_path(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    ref = {'path': 'raw-live/o/c/x.bin.enc', 'metadata': raw_meta(PCM)}
    assert decode_source(enc_frame(KEY, PCM), ref, KEY) == PCM


def test_decrypt_then_checksum_guards_the_plaintext():
    ref = {'path': 'raw-live/o/c/x.bin.enc', 'metadata': raw_meta(PCM, sha256='0' * 64)}
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(enc_frame(KEY, PCM), ref, KEY)


def test_trailing_garbage_after_one_frame_is_typed():
    body = enc_frame(KEY, PCM) + b'\x00'
    with pytest.raises(RetainedAudioInvalid, match='^truncated encrypted audio length$'):
        decode_source(body, chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_two_concatenated_frames_roundtrip():
    body = enc_frame(KEY, PCM[:64]) + enc_frame(KEY, PCM[64:])
    assert decode_source(body, chunk_ref(path='chunks/o/c/x.bin.enc'), KEY) == PCM


def test_frame_size_bound_rejects_above_the_source_budget():
    body = struct.pack('>I', MAX_SOURCE_BYTES + 1)
    with pytest.raises(RetainedAudioInvalid, match='^invalid encrypted audio frame$'):
        decode_source(body, chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)


def test_decrypt_then_capture_decoder_receives_the_plaintext(monkeypatch):
    seen = []

    def probe(raw, metadata, rate):
        seen.append(raw)
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    ref = {'path': 'raw-live/o/c/x.bin.enc', 'metadata': raw_meta(PCM)}
    decode_source(enc_frame(KEY, PCM), ref, KEY)
    assert seen == [PCM]


def test_checksum_mismatch_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(PCM, raw_live_ref(PCM, sha256='0' * 64), KEY)


def test_missing_checksum_metadata_is_typed():
    raw = PCM
    ref = raw_live_ref(raw)
    del ref['metadata']['sha256']
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(raw, ref, KEY)


def test_non_string_checksum_metadata_is_typed():
    raw = PCM
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(raw, raw_live_ref(raw, sha256=12345), KEY)


def test_uppercase_checksum_metadata_is_typed():
    raw = PCM
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(raw, raw_live_ref(raw, sha256=digest(raw).upper()), KEY)


def test_checksum_matches_only_the_exact_bytes(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    raw = PCM
    assert decode_source(raw + b'\x00', raw_live_ref(raw + b'\x00'), KEY) == raw + b'\x00'


def test_checksum_checks_the_plaintext_not_the_wire(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    ref = {'path': 'raw-live/o/c/x.bin.enc', 'metadata': raw_meta(PCM)}
    assert decode_source(enc_frame(KEY, PCM), ref, KEY) == PCM


def test_format_pcm16le_reaches_the_capture_decoder(monkeypatch):
    seen = {}

    def probe(raw, metadata, rate):
        seen['format'] = metadata.get('format')
        seen['rate'] = rate
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    raw = PCM
    decode_source(raw, raw_live_ref(raw, format='pcm16le'), KEY)
    assert seen == {'format': 'pcm16le', 'rate': 16000}


def test_format_pcm8_u8_reaches_the_capture_decoder(monkeypatch):
    seen = {}

    def probe(raw, metadata, rate):
        seen['format'] = metadata.get('format')
        seen['rate'] = rate
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    raw = PCM
    decode_source(raw, raw_live_ref(raw, format='pcm8-u8'), KEY)
    assert seen == {'format': 'pcm8-u8', 'rate': 16000}


def test_format_wal_reaches_the_capture_decoder(monkeypatch):
    seen = {}

    def probe(raw, metadata, rate):
        seen['format'] = metadata.get('format')
        seen['rate'] = rate
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    raw = PCM
    decode_source(raw, raw_live_ref(raw, format='omi-wal-uint32le-opus-v1'), KEY)
    assert seen == {'format': 'omi-wal-uint32le-opus-v1', 'rate': 16000}


def test_format_flac_marker_reaches_the_capture_decoder(monkeypatch):
    seen = {}

    def probe(raw, metadata, rate):
        seen['format'] = metadata.get('format')
        seen['rate'] = rate
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    raw = PCM
    decode_source(raw, raw_live_ref(raw, format='flac-marker'), KEY)
    assert seen == {'format': 'flac-marker', 'rate': 16000}


def test_format_mystery_reaches_the_capture_decoder(monkeypatch):
    seen = {}

    def probe(raw, metadata, rate):
        seen['format'] = metadata.get('format')
        seen['rate'] = rate
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    raw = PCM
    decode_source(raw, raw_live_ref(raw, format='mystery-format'), KEY)
    assert seen == {'format': 'mystery-format', 'rate': 16000}


def test_raw_live_identity_passthrough_is_byte_exact(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    raw = PCM
    assert decode_source(raw, raw_live_ref(raw), KEY) == raw


def test_raw_live_rate_is_frozen_at_16000(monkeypatch):
    seen = []

    def probe(raw, metadata, rate):
        seen.append(rate)
        return raw

    monkeypatch.setattr(source_audio, 'decode_capture', probe)
    decode_source(PCM, raw_live_ref(PCM), KEY)
    assert seen == [16000]


def test_raw_live_wins_over_the_opus_marker_in_the_path(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    raw = PCM
    ref = {'path': 'raw-live/o/c/x.opus', 'metadata': raw_meta(raw)}
    assert decode_source(raw, ref, KEY) == raw


def test_capture_decoder_output_is_returned_untouched(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', lambda raw, metadata, rate: b'decoded-marker')
    assert decode_source(PCM, raw_live_ref(PCM), KEY) == b'decoded-marker'


def test_opus_path_routes_the_legacy_decoder(monkeypatch):
    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', identity_opus)
    assert decode_source(PCM, {'path': 'chunks/o/c/x.opus'}, KEY) == PCM


def test_prefix_dot_opus_in_path_routes_the_legacy_decoder(monkeypatch):
    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', identity_opus)
    assert decode_source(PCM, {'path': 'chunks/.opus/x.bin'}, KEY) == PCM


def test_middle_dot_opus_in_path_routes_the_legacy_decoder(monkeypatch):
    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', identity_opus)
    assert decode_source(PCM, {'path': 'chunks/o/c/x.opus.bin'}, KEY) == PCM


def test_path_without_dot_opus_stays_on_the_pcm_tail():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, {'path': 'chunks/o/c/opus.bin', 'sample_rate': 7999}, KEY)


def test_double_dot_opus_in_path_routes_the_legacy_decoder(monkeypatch):
    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', identity_opus)
    assert decode_source(PCM, {'path': 'chunks/o/c/x.opus.opus'}, KEY) == PCM


def test_opus_container_too_short_is_typed_with_the_guard_message():
    with pytest.raises(RetainedAudioInvalid, match='^Opus data too short'):
        decode_source(b'123', {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_truncated_packet_table_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^Truncated Opus data'):
        decode_source(struct.pack('<II', 3, 0), {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_one_byte_container_is_typed_too_short():
    with pytest.raises(RetainedAudioInvalid, match='^Opus data too short'):
        decode_source(b'1', {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_packet_count_zero_yields_the_empty_container_bytes(monkeypatch):
    if opus_module.opuslib is None:
        pytest.skip('zero-packet containers still construct the native decoder')
    body = struct.pack('<II', 0, 0)
    assert decode_source(body, {'path': 'chunks/o/c/x.opus'}, KEY) == b''


def test_opus_exactly_eight_bytes_with_no_packets_is_empty(monkeypatch):
    if opus_module.opuslib is None:
        pytest.skip('zero-packet containers still construct the native decoder')
    body = struct.pack('<II', 0, 640)
    assert decode_source(body, {'path': 'chunks/o/c/x.opus'}, KEY) == b''


def test_opus_packet_declared_past_eof_is_typed():
    body = struct.pack('<II', 1, 0) + struct.pack('<H', 64) + b'\x00' * 8
    with pytest.raises(RetainedAudioInvalid, match='^Truncated Opus data'):
        decode_source(body, {'path': 'chunks/o/c/x.opus'}, KEY)


def test_opus_identity_stub_returns_its_marker(monkeypatch):
    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', lambda raw, sample_rate=16000: b'marker')
    assert decode_source(b'12345678', {'path': 'chunks/o/c/x.opus'}, KEY) == b'marker'


def test_opus_guard_message_names_bytes_not_positions():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(b'123', {'path': 'chunks/o/c/x.opus'}, KEY)
    assert '3 bytes' in str(error.value)


def test_rate_16000_passthrough_is_byte_exact():
    assert decode_source(PCM, chunk_ref(sample_rate=16000), KEY) == PCM


def test_missing_rate_defaults_to_passthrough():
    assert decode_source(PCM, chunk_ref(), KEY) == PCM


def test_rate_below_floor_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=7999), KEY)


def test_rate_above_ceiling_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=48001), KEY)


def test_rate_floor_converts_upward():
    out = decode_source(PCM, chunk_ref(sample_rate=8000), KEY)
    assert isinstance(out, bytes) and out
    assert len(out) > len(PCM)


def test_rate_ceiling_converts_downward():
    out = decode_source(PCM, chunk_ref(sample_rate=48000), KEY)
    assert isinstance(out, bytes) and out
    assert len(out) < len(PCM)


def test_odd_pcm_length_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\0' * 33, chunk_ref(), KEY)


def test_rate_metadata_non_numeric_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate='16 kHz'), KEY)


def test_rate_metadata_float_string_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate='16000.0'), KEY)


def test_rate_metadata_empty_string_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=''), KEY)


def test_rate_metadata_none_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=None), KEY)


def test_rate_metadata_bytes_non_numeric_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=b'not-a-rate'), KEY)


def test_rate_metadata_mapping_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate={'rate': 16000}), KEY)


def test_rate_metadata_nan_float_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=float('nan')), KEY)


def test_rate_metadata_infinite_float_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=float('inf')), KEY)


def test_rate_metadata_list_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=[16000]), KEY)


def test_rate_metadata_tuple_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=(16000,)), KEY)


def test_rate_metadata_set_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate={16000}), KEY)


def test_rate_metadata_dict_value_is_typed():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(sample_rate=dict.fromkeys([0])), KEY)


def test_fractional_float_rate_truncates_to_passthrough():
    assert decode_source(PCM, chunk_ref(sample_rate=16000.9), KEY) == PCM


def test_numeric_string_rate_converts_upward():
    out = decode_source(PCM, chunk_ref(sample_rate='8000'), KEY)
    assert isinstance(out, bytes) and len(out) > len(PCM)


def test_digit_bytes_rate_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=b'8000'), KEY)
    assert isinstance(out, bytes) and len(out) > len(PCM)


def test_conversion_fault_never_leaks_the_stored_value():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, chunk_ref(sample_rate='secret-rate-value'), KEY)
    assert 'secret-rate-value' not in str(error.value)
    assert error.value.__suppress_context__


def test_conversion_fault_suppresses_the_cause_context(monkeypatch):
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, chunk_ref(sample_rate='16000.0'), KEY)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


def test_standard_rate_8000_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=8000), KEY)
    assert isinstance(out, bytes) and out


def test_standard_rate_11025_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=11025), KEY)
    assert isinstance(out, bytes) and out


def test_standard_rate_22050_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=22050), KEY)
    assert isinstance(out, bytes) and out


def test_standard_rate_32000_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=32000), KEY)
    assert isinstance(out, bytes) and out


def test_standard_rate_44100_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=44100), KEY)
    assert isinstance(out, bytes) and out


def test_standard_rate_48000_converts():
    out = decode_source(PCM, chunk_ref(sample_rate=48000), KEY)
    assert isinstance(out, bytes) and out


def test_ratecv_tail_receives_the_validated_rate(monkeypatch):
    seen = []

    def probe(raw, width, channels, in_rate, out_rate, state):
        seen.append((in_rate, out_rate))
        return (raw, None)

    monkeypatch.setattr(source_audio.audioop, 'ratecv', probe)
    decode_source(PCM, chunk_ref(sample_rate=8000), KEY)
    assert seen == [(8000, 16000)]


def test_ratecv_tail_output_is_returned_directly(monkeypatch):
    monkeypatch.setattr(source_audio.audioop, 'ratecv', lambda *a: (b'converted', None))
    out = decode_source(PCM, chunk_ref(sample_rate=8000), KEY)
    assert out == b'converted'


def test_rate_16000_never_enters_the_ratecv_tail(monkeypatch):
    calls = []
    monkeypatch.setattr(source_audio.audioop, 'ratecv', lambda *a: calls.append(a))
    decode_source(PCM, chunk_ref(sample_rate=16000), KEY)
    assert calls == []


def test_raw_live_prefix_precedes_the_encrypted_marker(monkeypatch):
    monkeypatch.setattr(source_audio, 'decode_capture', identity_capture)
    ref = {'path': 'raw-live/o/c/x.bin.enc', 'metadata': raw_meta(PCM, encrypted='true')}
    body = enc_frame(KEY, PCM)
    assert decode_source(body, ref, KEY) == PCM


def test_encrypted_metadata_without_enc_path_still_decrypts_first():
    body = enc_frame(KEY, PCM[:32])
    ref = {'path': 'chunks/o/c/x.bin', 'metadata': {'encrypted': 'true'}}
    with pytest.raises(RetainedAudioInvalid):
        decode_source(body, ref, b'\5' * 32)


def test_key_material_never_appears_in_typed_fault_messages():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(enc_frame(b'\6' * 32, PCM), chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)
    assert b'\6' not in str(error.value).encode()
    assert KEY not in str(error.value).encode()


def test_wire_bytes_never_appear_in_typed_fault_messages():
    body = enc_frame(KEY, PCM)
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(body[:-4], chunk_ref(path='chunks/o/c/x.bin.enc'), KEY)
    assert PCM not in str(error.value).encode()


def test_outside_admitted_source_stays_a_distinct_class():
    from utils.batch_pipeline.source_audio import RetainedAudioOutsideAdmittedSource

    assert issubclass(RetainedAudioOutsideAdmittedSource, ValueError)
    assert not issubclass(RetainedAudioOutsideAdmittedSource, RetainedAudioInvalid)


def test_invalid_manifest_is_a_retained_audio_invalid():
    assert issubclass(InvalidRetainedManifest, RetainedAudioInvalid)


def test_retained_audio_invalid_is_a_value_error():
    assert issubclass(RetainedAudioInvalid, ValueError)
