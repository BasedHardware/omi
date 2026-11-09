"""Generated parity grid: the retained rate-conversion cohort at the typed boundary.

Every cell pins one stored-metadata shape through the REAL decode_source (and the
REAL worker boundary / scheduler custody / closed predicates in the sibling grids)
to its exact outcome. A stored rate that was never an integer is deterministic on
the pinned manifest: the fault must end the GPU chain with the family token
instead of walking the bounded retry ladder and booking an anonymous production
error (the sensor's bare ValueError cohort at fetch_decode).

Failure-Class: FC-permanent-retained-decode-failure-burns-retry-ladder
"""

import struct

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.batch_pipeline.source_audio import (
    MAX_SOURCE_BYTES,
    InvalidRetainedManifest,
    RetainedAudioInvalid,
    decode_source,
)

KEY = b'\1' * 32
PCM = b'\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02\x00\x02'


def enc_frame(key, payload):
    nonce = b'\n' * 12
    sealed = AESGCM(key).encrypt(nonce, payload, None)
    return struct.pack('>I', 12 + len(sealed)) + nonce + sealed


def chunk_ref(value_expr):
    return {'path': 'chunks/o/c/x.bin', 'sample_rate': value_expr}


def enc_ref(value_expr):
    return {'path': 'chunks/o/c/x.bin.enc', 'sample_rate': value_expr}


def raw_live_ref(raw, value_expr):
    import hashlib

    metadata = {
        'sample_rate': value_expr,
        'channels': '1',
        'format': 'pcm16le',
        'sha256': hashlib.sha256(raw).hexdigest(),
    }
    return {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}


def raw_live_ref_no_rate(raw):
    import hashlib

    metadata = {'channels': '1', 'format': 'pcm16le', 'sha256': hashlib.sha256(raw).hexdigest()}
    return {'path': 'raw-live/o/c/x.bin', 'metadata': metadata}


def opus_ref(value_expr):
    return {'path': 'chunks/o/c/x.opus', 'sample_rate': value_expr}


def _identity_capture(raw, metadata, rate):
    return raw


def _identity_opus(raw, sample_rate=16000):
    return PCM


def test_chunk_value_error_family_carries_the_closed_token():
    with pytest.raises(ValueError) as error:
        decode_source(PCM, chunk_ref('nope'), KEY)
    assert isinstance(error.value, RetainedAudioInvalid)
    assert str(error.value) == 'invalid retained PCM'


def test_rate_missing_chunk():
    out = decode_source(PCM, {'path': 'chunks/o/c/x.bin'}, KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_missing_enc():
    out = decode_source(enc_frame(KEY, PCM), {'path': 'chunks/o/c/x.bin.enc'}, KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_missing_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref_no_rate(PCM), KEY)
    assert out == PCM


def test_rate_missing_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', {'path': 'chunks/o/c/x.opus'}, KEY)
    assert out == PCM


def test_rate_int_16000_chunk():
    out = decode_source(PCM, chunk_ref(16000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_int_16000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(16000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_int_16000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 16000), KEY)
    assert out == PCM


def test_rate_int_16000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(16000), KEY)
    assert out == PCM


def test_rate_int_8000_chunk():
    out = decode_source(PCM, chunk_ref(8000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_int_8000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(8000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_int_8000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 8000), KEY)
    assert out == PCM


def test_rate_int_8000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(8000), KEY)
    assert out == PCM


def test_rate_int_8001_chunk():
    out = decode_source(PCM, chunk_ref(8001), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1276
    assert out != PCM


def test_rate_int_8001_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(8001), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1276
    assert out != PCM


def test_rate_int_8001_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 8001), KEY)
    assert out == PCM


def test_rate_int_8001_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(8001), KEY)
    assert out == PCM


def test_rate_int_15999_chunk():
    out = decode_source(PCM, chunk_ref(15999), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_int_15999_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(15999), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_int_15999_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 15999), KEY)
    assert out == PCM


def test_rate_int_15999_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(15999), KEY)
    assert out == PCM


def test_rate_int_16001_chunk():
    out = decode_source(PCM, chunk_ref(16001), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 638
    assert out != PCM


def test_rate_int_16001_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(16001), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 638
    assert out != PCM


def test_rate_int_16001_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 16001), KEY)
    assert out == PCM


def test_rate_int_16001_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(16001), KEY)
    assert out == PCM


def test_rate_int_32000_chunk():
    out = decode_source(PCM, chunk_ref(32000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 320
    assert out != PCM


def test_rate_int_32000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(32000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 320
    assert out != PCM


def test_rate_int_32000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 32000), KEY)
    assert out == PCM


def test_rate_int_32000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(32000), KEY)
    assert out == PCM


def test_rate_int_44100_chunk():
    out = decode_source(PCM, chunk_ref(44100), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 232
    assert out != PCM


def test_rate_int_44100_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(44100), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 232
    assert out != PCM


def test_rate_int_44100_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 44100), KEY)
    assert out == PCM


def test_rate_int_44100_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(44100), KEY)
    assert out == PCM


def test_rate_int_48000_chunk():
    out = decode_source(PCM, chunk_ref(48000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_int_48000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(48000), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_int_48000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 48000), KEY)
    assert out == PCM


def test_rate_int_48000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(48000), KEY)
    assert out == PCM


def test_rate_int_47999_chunk():
    out = decode_source(PCM, chunk_ref(47999), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_int_47999_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(47999), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_int_47999_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 47999), KEY)
    assert out == PCM


def test_rate_int_47999_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(47999), KEY)
    assert out == PCM


def test_rate_int_7999_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(7999), KEY)


def test_rate_int_7999_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(7999), KEY)


def test_rate_int_7999_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 7999), KEY)
    assert out == PCM


def test_rate_int_7999_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(7999), KEY)
    assert out == PCM


def test_rate_int_48001_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(48001), KEY)


def test_rate_int_48001_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(48001), KEY)


def test_rate_int_48001_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 48001), KEY)
    assert out == PCM


def test_rate_int_48001_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(48001), KEY)
    assert out == PCM


def test_rate_int_zero_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(0), KEY)


def test_rate_int_zero_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(0), KEY)


def test_rate_int_zero_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 0), KEY)
    assert out == PCM


def test_rate_int_zero_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(0), KEY)
    assert out == PCM


def test_rate_int_negative_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(-16000), KEY)


def test_rate_int_negative_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(-16000), KEY)


def test_rate_int_negative_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, -16000), KEY)
    assert out == PCM


def test_rate_int_negative_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(-16000), KEY)
    assert out == PCM


def test_rate_int_huge_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(999999999), KEY)


def test_rate_int_huge_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(999999999), KEY)


def test_rate_int_huge_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 999999999), KEY)
    assert out == PCM


def test_rate_int_huge_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(999999999), KEY)
    assert out == PCM


def test_rate_bool_true_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(True), KEY)


def test_rate_bool_true_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(True), KEY)


def test_rate_bool_true_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, True), KEY)
    assert out == PCM


def test_rate_bool_true_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(True), KEY)
    assert out == PCM


def test_rate_bool_false_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(False), KEY)


def test_rate_bool_false_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(False), KEY)


def test_rate_bool_false_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, False), KEY)
    assert out == PCM


def test_rate_bool_false_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(False), KEY)
    assert out == PCM


def test_rate_float_16000_0_chunk():
    out = decode_source(PCM, chunk_ref(16000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_float_16000_0_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(16000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_float_16000_0_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 16000.0), KEY)
    assert out == PCM


def test_rate_float_16000_0_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(16000.0), KEY)
    assert out == PCM


def test_rate_float_8000_0_chunk():
    out = decode_source(PCM, chunk_ref(8000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_float_8000_0_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(8000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_float_8000_0_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 8000.0), KEY)
    assert out == PCM


def test_rate_float_8000_0_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(8000.0), KEY)
    assert out == PCM


def test_rate_float_48000_0_chunk():
    out = decode_source(PCM, chunk_ref(48000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_float_48000_0_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(48000.0), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_float_48000_0_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 48000.0), KEY)
    assert out == PCM


def test_rate_float_48000_0_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(48000.0), KEY)
    assert out == PCM


def test_rate_float_16000_5_chunk():
    out = decode_source(PCM, chunk_ref(16000.5), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_float_16000_5_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(16000.5), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_float_16000_5_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 16000.5), KEY)
    assert out == PCM


def test_rate_float_16000_5_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(16000.5), KEY)
    assert out == PCM


def test_rate_float_7999_9_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(7999.9), KEY)


def test_rate_float_7999_9_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(7999.9), KEY)


def test_rate_float_7999_9_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 7999.9), KEY)
    assert out == PCM


def test_rate_float_7999_9_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(7999.9), KEY)
    assert out == PCM


def test_rate_float_44100_7_chunk():
    out = decode_source(PCM, chunk_ref(44100.7), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 232
    assert out != PCM


def test_rate_float_44100_7_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(44100.7), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 232
    assert out != PCM


def test_rate_float_44100_7_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 44100.7), KEY)
    assert out == PCM


def test_rate_float_44100_7_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(44100.7), KEY)
    assert out == PCM


def test_rate_float_nan_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(float('nan')), KEY)


def test_rate_float_nan_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(float('nan')), KEY)


def test_rate_float_nan_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, float('nan')), KEY)
    assert out == PCM


def test_rate_float_nan_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(float('nan')), KEY)
    assert out == PCM


def test_rate_float_inf_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(float('inf')), KEY)


def test_rate_float_inf_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(float('inf')), KEY)


def test_rate_float_inf_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, float('inf')), KEY)
    assert out == PCM


def test_rate_float_inf_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(float('inf')), KEY)
    assert out == PCM


def test_rate_float_neginf_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(float('-inf')), KEY)


def test_rate_float_neginf_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(float('-inf')), KEY)


def test_rate_float_neginf_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, float('-inf')), KEY)
    assert out == PCM


def test_rate_float_neginf_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(float('-inf')), KEY)
    assert out == PCM


def test_rate_float_1e30_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(1e30), KEY)


def test_rate_float_1e30_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(1e30), KEY)


def test_rate_float_1e30_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, 1e30), KEY)
    assert out == PCM


def test_rate_float_1e30_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(1e30), KEY)
    assert out == PCM


def test_rate_str_16000_chunk():
    out = decode_source(PCM, chunk_ref('16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_16000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref('16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_16000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '16000'), KEY)
    assert out == PCM


def test_rate_str_16000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('16000'), KEY)
    assert out == PCM


def test_rate_str_8000_chunk():
    out = decode_source(PCM, chunk_ref('8000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_str_8000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref('8000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_str_8000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '8000'), KEY)
    assert out == PCM


def test_rate_str_8000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('8000'), KEY)
    assert out == PCM


def test_rate_str_48000_chunk():
    out = decode_source(PCM, chunk_ref('48000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_str_48000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref('48000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 214
    assert out != PCM


def test_rate_str_48000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '48000'), KEY)
    assert out == PCM


def test_rate_str_48000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('48000'), KEY)
    assert out == PCM


def test_rate_str_7999_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('7999'), KEY)


def test_rate_str_7999_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('7999'), KEY)


def test_rate_str_7999_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '7999'), KEY)
    assert out == PCM


def test_rate_str_7999_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('7999'), KEY)
    assert out == PCM


def test_rate_str_48001_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('48001'), KEY)


def test_rate_str_48001_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('48001'), KEY)


def test_rate_str_48001_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '48001'), KEY)
    assert out == PCM


def test_rate_str_48001_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('48001'), KEY)
    assert out == PCM


def test_rate_str_16000_0_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('16000.0'), KEY)


def test_rate_str_16000_0_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('16000.0'), KEY)


def test_rate_str_16000_0_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '16000.0'), KEY)
    assert out == PCM


def test_rate_str_16000_0_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('16000.0'), KEY)
    assert out == PCM


def test_rate_str_16khz_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('16 kHz'), KEY)


def test_rate_str_16khz_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('16 kHz'), KEY)


def test_rate_str_16khz_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '16 kHz'), KEY)
    assert out == PCM


def test_rate_str_16khz_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('16 kHz'), KEY)
    assert out == PCM


def test_rate_str_empty_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(''), KEY)


def test_rate_str_empty_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(''), KEY)


def test_rate_str_empty_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, ''), KEY)
    assert out == PCM


def test_rate_str_empty_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(''), KEY)
    assert out == PCM


def test_rate_str_space_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(' '), KEY)


def test_rate_str_space_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(' '), KEY)


def test_rate_str_space_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, ' '), KEY)
    assert out == PCM


def test_rate_str_space_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(' '), KEY)
    assert out == PCM


def test_rate_str_plus_chunk():
    out = decode_source(PCM, chunk_ref('+16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_plus_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref('+16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_plus_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '+16000'), KEY)
    assert out == PCM


def test_rate_str_plus_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('+16000'), KEY)
    assert out == PCM


def test_rate_str_minus_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('-16000'), KEY)


def test_rate_str_minus_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('-16000'), KEY)


def test_rate_str_minus_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '-16000'), KEY)
    assert out == PCM


def test_rate_str_minus_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('-16000'), KEY)
    assert out == PCM


def test_rate_str_superscript_two_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('\u00b2'), KEY)


def test_rate_str_superscript_two_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('\u00b2'), KEY)


def test_rate_str_superscript_two_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '\u00b2'), KEY)
    assert out == PCM


def test_rate_str_superscript_two_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('\u00b2'), KEY)
    assert out == PCM


def test_rate_str_arabic_digits_16000_chunk():
    out = decode_source(PCM, chunk_ref(chr(0x661) + chr(0x666) + chr(0x660) * 3), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_arabic_digits_16000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(chr(0x661) + chr(0x666) + chr(0x660) * 3), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_str_arabic_digits_16000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, chr(0x661) + chr(0x666) + chr(0x660) * 3), KEY)
    assert out == PCM


def test_rate_str_arabic_digits_16000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(chr(0x661) + chr(0x666) + chr(0x660) * 3), KEY)
    assert out == PCM


def test_rate_str_arabic_digits_10000_chunk():
    out = decode_source(PCM, chunk_ref(chr(0x661) + chr(0x660) * 4), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1022
    assert out != PCM


def test_rate_str_arabic_digits_10000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(chr(0x661) + chr(0x660) * 4), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1022
    assert out != PCM


def test_rate_str_arabic_digits_10000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, chr(0x661) + chr(0x660) * 4), KEY)
    assert out == PCM


def test_rate_str_arabic_digits_10000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(chr(0x661) + chr(0x660) * 4), KEY)
    assert out == PCM


def test_rate_str_hex_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref('0x10'), KEY)


def test_rate_str_hex_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('0x10'), KEY)


def test_rate_str_hex_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, '0x10'), KEY)
    assert out == PCM


def test_rate_str_hex_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref('0x10'), KEY)
    assert out == PCM


def test_rate_bytes_16000_chunk():
    out = decode_source(PCM, chunk_ref(b'16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_bytes_16000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(b'16000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 640
    assert out == PCM


def test_rate_bytes_16000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, b'16000'), KEY)
    assert out == PCM


def test_rate_bytes_16000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(b'16000'), KEY)
    assert out == PCM


def test_rate_bytes_8000_chunk():
    out = decode_source(PCM, chunk_ref(b'8000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_bytes_8000_enc():
    out = decode_source(enc_frame(KEY, PCM), enc_ref(b'8000'), KEY)
    assert isinstance(out, bytes)
    assert len(out) == 1278
    assert out != PCM


def test_rate_bytes_8000_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, b'8000'), KEY)
    assert out == PCM


def test_rate_bytes_8000_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(b'8000'), KEY)
    assert out == PCM


def test_rate_bytes_bad_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(b'not-a-rate'), KEY)


def test_rate_bytes_bad_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(b'not-a-rate'), KEY)


def test_rate_bytes_bad_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, b'not-a-rate'), KEY)
    assert out == PCM


def test_rate_bytes_bad_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(b'not-a-rate'), KEY)
    assert out == PCM


def test_rate_none_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(None), KEY)


def test_rate_none_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(None), KEY)


def test_rate_none_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, None), KEY)
    assert out == PCM


def test_rate_none_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(None), KEY)
    assert out == PCM


def test_rate_list_digits_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(['16000']), KEY)


def test_rate_list_digits_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(['16000']), KEY)


def test_rate_list_digits_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, ['16000']), KEY)
    assert out == PCM


def test_rate_list_digits_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(['16000']), KEY)
    assert out == PCM


def test_rate_dict_rate_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref({'rate': 16000}), KEY)


def test_rate_dict_rate_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref({'rate': 16000}), KEY)


def test_rate_dict_rate_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, {'rate': 16000}), KEY)
    assert out == PCM


def test_rate_dict_rate_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref({'rate': 16000}), KEY)
    assert out == PCM


def test_rate_tuple_digits_chunk():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(PCM, chunk_ref(('16000',)), KEY)


def test_rate_tuple_digits_enc():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref(('16000',)), KEY)


def test_rate_tuple_digits_rawlive(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    monkeypatch.setattr(source_audio, 'decode_capture', _identity_capture)
    out = decode_source(PCM, raw_live_ref(PCM, ('16000',)), KEY)
    assert out == PCM


def test_rate_tuple_digits_opus(monkeypatch):
    import utils.other.audio_opus as opus_module

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', _identity_opus)
    out = decode_source(b'12345678', opus_ref(('16000',)), KEY)
    assert out == PCM


def test_oversize_body_typed_before_rate_conversion():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained audio size$'):
        decode_source(b'\0' * (MAX_SOURCE_BYTES + 1), chunk_ref('nope'), KEY)


def test_odd_pcm_typed_after_conversion_with_valid_rate():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\0' * 33, chunk_ref(16000), KEY)


def test_odd_pcm_with_bad_rate_typed_by_conversion_first():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(b'\0' * 33, chunk_ref('nope'), KEY)


def test_encrypted_path_conversion_fault_same_token():
    with pytest.raises(RetainedAudioInvalid, match='^invalid retained PCM$'):
        decode_source(enc_frame(KEY, PCM), enc_ref('nope'), KEY)


def test_conversion_fault_is_not_the_manifest_subclass():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, chunk_ref('nope'), KEY)
    assert not isinstance(error.value, InvalidRetainedManifest)


def test_conversion_fault_suppresses_the_conversion_context():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, chunk_ref('nope'), KEY)
    assert error.value.__suppress_context__ and error.value.__cause__ is None


def test_conversion_fault_message_is_content_free():
    with pytest.raises(RetainedAudioInvalid) as error:
        decode_source(PCM, chunk_ref('classified-rate-value'), KEY)
    assert 'classified-rate-value' not in str(error.value)
    assert str(error.value) == 'invalid retained PCM'


def test_raw_live_checksum_still_precedes_conversion():
    import hashlib

    raw = PCM
    ref = raw_live_ref(raw, 'nope')
    ref['metadata']['sha256'] = '0' * 64
    assert ref['metadata']['sha256'] != hashlib.sha256(raw).hexdigest()
    with pytest.raises(RetainedAudioInvalid, match='^retained capture checksum mismatch$'):
        decode_source(raw, ref, KEY)


def test_raw_live_decode_value_error_is_typed_before_any_rate_logic(monkeypatch):
    import utils.batch_pipeline.source_audio as source_audio

    def broken(raw, metadata, rate):
        raise ValueError('capture PCM is not sample-aligned')

    monkeypatch.setattr(source_audio, 'decode_capture', broken)
    with pytest.raises(RetainedAudioInvalid, match='^capture PCM is not sample-aligned$'):
        decode_source(PCM, raw_live_ref(PCM, 'nope'), KEY)


def test_opus_decode_value_error_is_typed_before_any_rate_logic(monkeypatch):
    import utils.other.audio_opus as opus_module

    def broken(raw, sample_rate=16000):
        raise ValueError('Truncated Opus data: expected packet 0/1 length at offset 8')

    monkeypatch.setattr(opus_module, 'decode_opus_to_pcm', broken)
    with pytest.raises(RetainedAudioInvalid, match='^Truncated Opus data'):
        decode_source(b'12345678', opus_ref('nope'), KEY)
