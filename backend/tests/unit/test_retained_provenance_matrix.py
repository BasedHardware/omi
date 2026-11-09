"""The capture provenance matrix: every provenance key defaults to unknown,
supplied values override, None values keep the default, the digest and schema
keys always seal the raw bytes, and filename provenance parses its seven
tokens or falls back to the as-captured marker.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import hashlib
import struct

import pytest

from utils.other.raw_audio import WAL_FORMAT, filename_provenance, packet_provenance, provenance, wal_packets

RAW = b"\x00\x02" * 64


def test_supplied_codec_overrides_the_default():
    meta = provenance(RAW, {'codec': 'supplied'})
    assert meta['codec'] == 'supplied'


def test_none_codec_keeps_the_default():
    meta = provenance(RAW, {'codec': None})
    assert meta['codec'] == 'unknown'


def test_supplied_sample_rate_overrides_the_default():
    meta = provenance(RAW, {'sample_rate': 'supplied'})
    assert meta['sample_rate'] == 'supplied'


def test_none_sample_rate_keeps_the_default():
    meta = provenance(RAW, {'sample_rate': None})
    assert meta['sample_rate'] == 'unknown'


def test_supplied_channels_overrides_the_default():
    meta = provenance(RAW, {'channels': 'supplied'})
    assert meta['channels'] == 'supplied'


def test_none_channels_keeps_the_default():
    meta = provenance(RAW, {'channels': None})
    assert meta['channels'] == 'unknown'


def test_supplied_frame_size_overrides_the_default():
    meta = provenance(RAW, {'frame_size': 'supplied'})
    assert meta['frame_size'] == 'supplied'


def test_none_frame_size_keeps_the_default():
    meta = provenance(RAW, {'frame_size': None})
    assert meta['frame_size'] == 'unknown'


def test_supplied_device_model_overrides_the_default():
    meta = provenance(RAW, {'device_model': 'supplied'})
    assert meta['device_model'] == 'supplied'


def test_none_device_model_keeps_the_default():
    meta = provenance(RAW, {'device_model': None})
    assert meta['device_model'] == 'unknown'


def test_supplied_firmware_overrides_the_default():
    meta = provenance(RAW, {'firmware': 'supplied'})
    assert meta['firmware'] == 'supplied'


def test_none_firmware_keeps_the_default():
    meta = provenance(RAW, {'firmware': None})
    assert meta['firmware'] == 'unknown'


def test_supplied_app_version_overrides_the_default():
    meta = provenance(RAW, {'app_version': 'supplied'})
    assert meta['app_version'] == 'supplied'


def test_none_app_version_keeps_the_default():
    meta = provenance(RAW, {'app_version': None})
    assert meta['app_version'] == 'unknown'


def test_supplied_capture_start_overrides_the_default():
    meta = provenance(RAW, {'capture_start': 'supplied'})
    assert meta['capture_start'] == 'supplied'


def test_none_capture_start_keeps_the_default():
    meta = provenance(RAW, {'capture_start': None})
    assert meta['capture_start'] == 'unknown'


def test_supplied_capture_end_overrides_the_default():
    meta = provenance(RAW, {'capture_end': 'supplied'})
    assert meta['capture_end'] == 'supplied'


def test_none_capture_end_keeps_the_default():
    meta = provenance(RAW, {'capture_end': None})
    assert meta['capture_end'] == 'unknown'


def test_supplied_sequence_count_overrides_the_default():
    meta = provenance(RAW, {'sequence_count': 'supplied'})
    assert meta['sequence_count'] == 'supplied'


def test_none_sequence_count_keeps_the_default():
    meta = provenance(RAW, {'sequence_count': None})
    assert meta['sequence_count'] == 'unknown'


def test_supplied_gap_count_overrides_the_default():
    meta = provenance(RAW, {'gap_count': 'supplied'})
    assert meta['gap_count'] == 'supplied'


def test_none_gap_count_keeps_the_default():
    meta = provenance(RAW, {'gap_count': None})
    assert meta['gap_count'] == 'unknown'


def test_supplied_conversation_id_overrides_the_default():
    meta = provenance(RAW, {'conversation_id': 'supplied'})
    assert meta['conversation_id'] == 'supplied'


def test_none_conversation_id_keeps_the_default():
    meta = provenance(RAW, {'conversation_id': None})
    assert meta['conversation_id'] == 'unknown'


def test_supplied_consent_state_overrides_the_default():
    meta = provenance(RAW, {'consent_state': 'supplied'})
    assert meta['consent_state'] == 'supplied'


def test_none_consent_state_keeps_the_default():
    meta = provenance(RAW, {'consent_state': None})
    assert meta['consent_state'] == 'unknown'


def test_supplied_consent_version_overrides_the_default():
    meta = provenance(RAW, {'consent_version': 'supplied'})
    assert meta['consent_version'] == 'supplied'


def test_none_consent_version_keeps_the_default():
    meta = provenance(RAW, {'consent_version': None})
    assert meta['consent_version'] == 'unknown'


def test_provenance_is_total_over_the_documented_keys():
    meta = provenance(RAW, {})
    expected = {
        'codec',
        'sample_rate',
        'channels',
        'frame_size',
        'device_model',
        'firmware',
        'app_version',
        'capture_start',
        'capture_end',
        'sequence_count',
        'gap_count',
        'conversation_id',
        'consent_state',
        'consent_version',
    }
    unknown_only = {key for key, value in meta.items() if value == 'unknown'}
    assert unknown_only == expected


def test_provenance_seals_the_sha256_of_the_exact_bytes():
    meta = provenance(RAW, {})
    assert meta['sha256'] == hashlib.sha256(RAW).hexdigest()


def test_provenance_digest_changes_with_the_bytes():
    one = provenance(RAW, {})
    two = provenance(RAW + b'\x00', {})
    assert one['sha256'] != two['sha256']


def test_provenance_pins_schema_version_one():
    assert provenance(RAW, {})['schema_version'] == '1'


def test_provenance_supplied_booleans_stringify():
    meta = provenance(RAW, {'should_lock': True})
    assert meta['should_lock'] == 'True'


def test_provenance_supplied_numbers_stringify():
    meta = provenance(RAW, {'sample_rate': 16000, 'gap_count': 2})
    assert meta['sample_rate'] == '16000' and meta['gap_count'] == '2'


def test_non_wal_metadata_passes_through_identity():
    meta = {'format': 'pcm16le', 'capture_start': 1.0}
    assert packet_provenance(RAW, meta) is meta


def test_wal_metadata_with_invalid_packets_keeps_the_capture_shape():
    meta = {'format': WAL_FORMAT, 'capture_start': 1.0, 'sample_rate': '16000'}
    raw = struct.pack('<I', 65536) + b'x' * 4
    assert packet_provenance(raw, meta) is meta


def test_wal_metadata_with_an_empty_capture_keeps_the_metadata(monkeypatch):
    """An empty WAL capture contributes zero samples: capture_end stays at start."""
    import utils.other.raw_audio as raw_audio

    class FakeDecoderApi:
        @staticmethod
        def packet_get_nb_frames(packet):
            return 2

        @staticmethod
        def packet_get_samples_per_frame(packet, rate):
            return 320

    class FakeBinding:
        decoder = FakeDecoderApi

    class FakeModule:
        api = FakeBinding

    monkeypatch.setattr(raw_audio, "_get_opuslib", lambda: FakeModule)
    meta = {"format": WAL_FORMAT, "capture_start": 1.0, "sample_rate": "16000"}
    result = packet_provenance(b"", meta)
    assert result["capture_end"] == 1.0
    assert result["sequence_count"] == 0
    assert result["frame_size"] == "variable-opus-packet-header"


def test_filename_seven_tokens_parse():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['device_model'] == 'dev1'
    assert meta['capture_start'] == 1750000000.0


def test_filename_eight_tokens_parse():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x_y.bin')
    assert meta['device_model'] == 'dev1'
    assert meta['capture_start'] == 1750000000.0


def test_filename_six_tokens_fallback():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_wrong_head_token_fallback():
    meta = filename_provenance('voice_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_malformed_frame_prefix_fallback():
    meta = filename_provenance('audio_dev1_opus_16000_1_NOTAFS_1750000000.0_x.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_malformed_epoch_fallback():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_time_x.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_opus_codec_wins_the_wal_format():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['format'] == WAL_FORMAT


def test_filename_pcm_codec_maps_the_pcm_format():
    meta = filename_provenance('audio_dev1_pcm_16000_1_fs320_1750000000.0_x.bin')
    assert meta['format'] == 'omi-wal-uint32le-pcm-v1'


def test_filename_other_codec_maps_the_generic_pcm_format():
    meta = filename_provenance('audio_dev1_flac_16000_1_fs320_1750000000.0_x.bin')
    assert meta['codec'] == 'flac'
    assert meta['format'] == 'omi-wal-uint32le-pcm-v1'


def test_filename_epoch_millis_are_scaled_once():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000123.0_x.bin')
    assert meta['capture_start'] == 1750000000.123


def test_filename_epoch_seconds_are_not_scaled():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['capture_start'] == 1750000000.0


def test_filename_frame_size_strips_the_fs_prefix():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs960_1750000000.0_x.bin')
    assert meta['frame_size'] == 960


def test_filename_channels_and_rate_are_integers():
    meta = filename_provenance('audio_dev1_opus_16000_2_fs320_1750000000.0_x.bin')
    assert meta['sample_rate'] == 16000 and meta['channels'] == 2


def test_filename_ten_tokens_still_parse():
    meta = filename_provenance("audio_dev1_opus_16000_1_fs320_1750000000.0_x_y_z.bin")
    assert meta["device_model"] == "dev1"
    assert meta["format"] == WAL_FORMAT


def test_filename_frame_size_without_fs_prefix_still_parses():
    meta = filename_provenance("audio_dev1_opus_16000_1_320_1750000000.0_x.bin")
    assert meta["frame_size"] == 320
