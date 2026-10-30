"""Staging mirror envelope + source codecs (swarm lane 4)."""

import os
import struct

import pytest

from testing.loadgen import mirror_codec as mc
from utils import encryption
from utils.other.raw_audio import filename_provenance
from utils.request_validation import parse_sync_filename_timestamp

STAGING_SECRET = 's' * 48


def test_prod_decrypt_is_byte_compatible_with_utils_encryption():
    uid = 'owner-for-codec-test'
    first, second = os.urandom(333), os.urandom(77)
    sealed = encryption.encrypt_audio_chunk(first, uid) + encryption.encrypt_audio_chunk(second, uid)
    key = mc.derive_prod_user_key(os.environ['ENCRYPTION_SECRET'], uid)
    assert key == encryption.derive_key(uid)
    assert mc.decrypt_prod_audio(sealed, key) == first + second


def test_prod_decrypt_rejects_truncation():
    uid = 'owner-for-codec-test'
    sealed = encryption.encrypt_audio_chunk(b'abc' * 50, uid)
    with pytest.raises(mc.MirrorFormatError):
        mc.decrypt_prod_audio(sealed[:-5], mc.derive_prod_user_key(os.environ['ENCRYPTION_SECRET'], uid))


def test_mirror_envelope_binds_object_name_and_key():
    key = mc.derive_mirror_key(STAGING_SECRET)
    sealed = mc.seal_mirror_object(key, 'mirror/v1/a/g/00000-x.smenc', b'payload')
    assert sealed.startswith(mc.MIRROR_MAGIC)
    assert mc.open_mirror_object(key, 'mirror/v1/a/g/00000-x.smenc', sealed) == b'payload'
    with pytest.raises(Exception):
        mc.open_mirror_object(key, 'mirror/v1/a/g/00001-x.smenc', sealed)
    with pytest.raises(Exception):
        mc.open_mirror_object(mc.derive_mirror_key('t' * 48), 'mirror/v1/a/g/00000-x.smenc', sealed)


def test_mirror_key_differs_from_prod_scheme_and_short_secret_refused():
    assert mc.derive_mirror_key(STAGING_SECRET) != mc.derive_prod_user_key(STAGING_SECRET, 'x')
    assert mc.derive_mirror_key(STAGING_SECRET) != mc.derive_group_key(STAGING_SECRET)
    with pytest.raises(mc.MirrorFormatError):
        mc.derive_mirror_key('short')


def _opus_container(packets, pcm_len):
    return struct.pack('<II', len(packets), pcm_len) + b''.join(struct.pack('<H', len(p)) + p for p in packets)


def test_chunk_opus_container_reframes_to_wal_without_decoding():
    packets = [bytes([i]) * (10 + i) for i in range(50)]
    audio = mc.to_upload_audio(mc.FORMAT_CHUNK_OPUS, _opus_container(packets, 50 * 640))
    assert (audio.codec, audio.sample_rate, audio.frame_size) == ('opus', 16000, 320)
    assert mc.wal_payloads(audio.body) == packets
    assert audio.duration_s == pytest.approx(1.0)


def test_pcm16_chunk_and_silence_padding():
    pcm = b'\x01\x00' * 16000 * 2
    audio = mc.to_upload_audio(mc.FORMAT_CHUNK_PCM16, pcm)
    assert audio.duration_s == pytest.approx(2.0)
    assert b''.join(mc.wal_payloads(audio.body)) == pcm
    padded = mc.pad_with_silence(audio, 1.0, 0.5)
    assert padded.duration_s == pytest.approx(3.5)
    frames = mc.wal_payloads(padded.body)
    assert set(frames[0]) == {0} and set(frames[-1]) == {0}
    assert mc.estimate_wal_duration('pcm16', 16000, audio.frame_size, padded.body) == pytest.approx(3.5)


def test_opus_silence_requires_an_encoded_packet():
    audio = mc.UploadAudio('opus', 16000, 320, b'', 0.0)
    with pytest.raises(mc.MirrorFormatError):
        mc.silence_payloads(audio, 1.0, None)
    assert len(mc.silence_payloads(audio, 1.0, b'\xf8\xff\xfe')) == 50


def test_upload_filename_is_accepted_by_production_parsers():
    audio = mc.UploadAudio('opus', 16000, 320, b'', 0.0)
    name = mc.upload_filename('omi', audio, 1_760_000_000.25)
    assert parse_sync_filename_timestamp(name) == pytest.approx(1_760_000_000.25)
    prov = filename_provenance(name)
    assert (prov['codec'], prov['sample_rate'], prov['frame_size']) == ('opus', 16000, 320)
    fields = mc.parse_upload_filename(name)
    assert fields['capture_start'] == pytest.approx(1_760_000_000.25)


def test_raw_upload_keeps_bytes_and_needs_its_filename():
    body = mc.wal_frame([b'\x00\x01' * 800] * 10)
    name = 'audio_omi_pcm16_16000_1_fs160_1760000000.bin'
    audio = mc.to_upload_audio(mc.FORMAT_RAW_UPLOAD, body, filename=name)
    assert audio.body == body and audio.codec == 'pcm16'
    with pytest.raises(mc.MirrorFormatError):
        mc.to_upload_audio(mc.FORMAT_RAW_UPLOAD, body)


def test_pendant_codec_token_with_frame_suffix_round_trips():
    name = 'audio_abcdef0123456789_opus_fs320_16000_1_fs320_1760000000.123.bin'
    fields = mc.parse_upload_filename(name)
    assert fields['codec'] == 'opus_fs320' and fields['sample_rate'] == 16000 and fields['frame_size'] == 320
    assert fields['capture_start'] == pytest.approx(1_760_000_000.123)
    body = mc.wal_frame([b'\x01' * 40] * 50)
    audio = mc.to_upload_audio(mc.FORMAT_RAW_UPLOAD, body, filename=name)
    assert audio.codec == 'opus_fs320' and audio.duration_s == pytest.approx(1.0)
    renamed = mc.upload_filename('omi', audio, 1_760_000_100.5)
    assert renamed.startswith('audio_omi_opus_fs320_16000_1_fs320_')
    assert mc.parse_upload_filename(renamed)['codec'] == 'opus_fs320'
    assert parse_sync_filename_timestamp(renamed) == pytest.approx(1_760_000_100.5)
    # utils.sync.files decodes with the first _fs<N>: 320 for both names.
    import re

    assert re.search(r'_fs(\d+)', renamed).group(1) == '320'
