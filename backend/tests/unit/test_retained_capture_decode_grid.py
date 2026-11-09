"""The raw-live capture decode grid: WAL packet framing boundaries, the
capture-format dispatch table, canonical PCM invariants and the provenance
helpers. These are the exact bytes shapes the retained decoder feeds the GPU;
each cell pins one framing or routing rule so malformed stored captures fail
typed at the boundary instead of anonymously on the retry ladder.

Failure-Class: FC-non-value-decoder-fault-burns-retry-ladder
"""

import hashlib
import struct

import audioop
import pytest

from utils.other.raw_audio import (
    WAL_FORMAT,
    decode_capture,
    filename_provenance,
    packet_provenance,
    provenance,
    wal_packets,
)


def test_wal_packets_empty_input_yields_no_packets():
    assert list(wal_packets(b'')) == []


def test_wal_packets_short_header_1_byte_is_typed_truncated():
    with pytest.raises(ValueError, match='^truncated WAL length$'):
        list(wal_packets(b'\x01' * 1))


def test_wal_packets_short_header_2_byte_is_typed_truncated():
    with pytest.raises(ValueError, match='^truncated WAL length$'):
        list(wal_packets(b'\x01' * 2))


def test_wal_packets_short_header_3_byte_is_typed_truncated():
    with pytest.raises(ValueError, match='^truncated WAL length$'):
        list(wal_packets(b'\x01' * 3))


def test_wal_packets_zero_size_is_typed_invalid():
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(struct.pack('<I', 0)))


def test_wal_packets_oversize_is_typed_invalid():
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(struct.pack('<I', 65537)))


def test_wal_packets_max_size_is_in_bounds():
    packet = struct.pack('<I', 65536) + b'\x00' * 65536
    assert list(wal_packets(packet)) == [b'\x00' * 65536]


def test_wal_packets_size_past_eof_is_typed_invalid():
    raw = struct.pack('<I', 16) + b'\x00' * 8
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(raw))


def test_wal_packets_size_one_short_of_eof_is_typed_invalid():
    raw = struct.pack('<I', 16) + b'\x00' * 15
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(raw))


def test_wal_packets_size_exact_at_eof_roundtrips():
    raw = struct.pack('<I', 16) + b'\x00' * 16
    assert list(wal_packets(raw)) == [b'\x00' * 16]


def test_wal_packets_two_packet_chain_roundtrips_in_order():
    raw = struct.pack('<I', 2) + b'ab' + struct.pack('<I', 2) + b'cd'
    assert list(wal_packets(raw)) == [b'ab', b'cd']


def test_wal_packets_empty_packet_size_stays_invalid():
    raw = struct.pack('<I', 0) + struct.pack('<I', 2) + b'ab'
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(raw))


def test_wal_packets_trailing_length_header_short_read_is_typed_invalid():
    raw = struct.pack('<I', 2) + b'ab' + struct.pack('<I', 2) + b'a'
    with pytest.raises(ValueError, match='^invalid WAL packet$'):
        list(wal_packets(raw))


def test_wal_packets_final_header_is_truncated_length():
    raw = struct.pack('<I', 2) + b'ab' + struct.pack('<I', 2)[:1]
    with pytest.raises(ValueError, match='^truncated WAL length$'):
        list(wal_packets(raw))


def test_wal_packets_are_lazy_streams_until_consumed():
    raw = struct.pack('<I', 2) + b'ab'
    stream = wal_packets(raw)
    assert next(stream) == b'ab'
    with pytest.raises(StopIteration):
        next(stream)


def test_pcm16le_mono_16k_passthrough_is_byte_exact():
    raw = b'\x00\x02' * 320
    meta = {'format': 'pcm16le', 'sample_rate': '16000', 'channels': '1'}
    assert decode_capture(raw, meta, 16000) == raw


def test_pcm16le_non_target_rate_resamples():
    raw = b'\x00\x02' * 320
    meta = {'format': 'pcm16le', 'sample_rate': '8000', 'channels': '1'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out
    assert len(out) > len(raw)


def test_pcm16le_stereo_downmix_halves_the_samples():
    raw = b'\x00\x02' * 320
    meta = {'format': 'pcm16le', 'sample_rate': '16000', 'channels': '2'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out
    assert len(out) == len(raw) // 2


def test_pcm16le_unaligned_stereo_is_typed():
    raw = b'\x00\x02' * 321
    meta = {'format': 'pcm16le', 'sample_rate': '16000', 'channels': '2'}
    with pytest.raises(ValueError, match='^capture PCM is not sample-aligned$'):
        decode_capture(raw, meta, 16000)


def test_pcm16le_unaligned_mono_still_decodes():
    raw = b'\x00\x02' * 321
    meta = {'format': 'pcm16le', 'sample_rate': '16000', 'channels': '1'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out


def test_pcm8_u8_width_doubles():
    raw = b'\x81' * 320
    meta = {'format': 'pcm8-u8', 'sample_rate': '16000', 'channels': '1'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out
    assert len(out) == 2 * len(raw)


def test_unknown_format_without_codec_key_is_typed_key_error():
    raw = b'\x00' * 64
    meta = {'format': 'womp-wal', 'sample_rate': '16000', 'channels': '1'}
    with pytest.raises(KeyError):
        decode_capture(raw, meta, 16000)


def test_unknown_format_with_non_flac_codec_is_typed_value_error():
    raw = b'\x00' * 64
    meta = {'format': 'womp-wal', 'sample_rate': '16000', 'channels': '1', 'codec': 'womp'}
    with pytest.raises(ValueError, match='^capture format cannot serve playback$'):
        decode_capture(raw, meta, 16000)


def test_wal_format_decodes_every_packet(monkeypatch):
    def fake_get():
        class FakeDecoder:
            def __init__(self, rate, channels):
                pass

            def decode(self, packet, frame_bytes):
                return b'\x00\x02' * 320

        class FakeBinding:
            Decoder = FakeDecoder

        return FakeBinding()

    import utils.other.raw_audio as raw_audio

    monkeypatch.setattr(raw_audio, '_get_opuslib', fake_get)
    raw = struct.pack('<I', 2) + b'ab' + struct.pack('<I', 2) + b'cd'
    meta = {'format': WAL_FORMAT, 'sample_rate': '16000', 'channels': '1'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out


def test_wal_format_empty_packet_list_fails_in_the_decoder(monkeypatch):
    import utils.other.raw_audio as raw_audio

    def failing_get():
        raise RuntimeError('no native binding')

    monkeypatch.setattr(raw_audio, '_get_opuslib', failing_get)
    raw = b'\x00' * 8
    meta = {'format': WAL_FORMAT, 'sample_rate': '16000', 'channels': '1'}
    with pytest.raises(RuntimeError):
        decode_capture(raw, meta, 16000)


def test_flac_format_routes_through_the_audio_segment(monkeypatch):
    import utils.other.raw_audio as raw_audio

    class FakeSegment:
        def __init__(self, marker):
            self.marker = marker

        def set_frame_rate(self, rate):
            return self

        def set_channels(self, channels):
            return self

        def set_sample_width(self, width):
            return self

    fake = FakeSegment(b'flac-marker')
    fake.raw_data = b'flac-marker'

    class FakeAudioSegment:
        @staticmethod
        def from_file(handle, format=None):
            return fake

    monkeypatch.setattr(raw_audio, 'AudioSegment', FakeAudioSegment)
    raw = b'\x00' * 64
    meta = {'format': 'anything-else', 'sample_rate': '16000', 'channels': '1'}
    import io

    orig_from_file = FakeAudioSegment.from_file
    codec = {'format': 'flac-marker', 'sample_rate': '16000', 'channels': '1'}
    codec['codec'] = 'flac'
    out = decode_capture(raw, codec, 16000)
    assert out == b'flac-marker'


def test_capture_without_format_key_is_typed():
    raw = b'\x00' * 64
    with pytest.raises(KeyError):
        decode_capture(raw, {'sample_rate': '16000', 'channels': '1'}, 16000)


def test_capture_with_zero_rate_metadata_is_typed():
    raw = b'\x00\x02' * 320
    meta = {'format': 'pcm16le', 'sample_rate': '0', 'channels': '1'}
    with pytest.raises(audioop.error):
        decode_capture(raw, meta, 16000)


def test_capture_output_rate_is_always_reached():
    raw = b'\x00\x02' * 320
    meta = {'format': 'pcm16le', 'sample_rate': '48000', 'channels': '1'}
    out = decode_capture(raw, meta, 16000)
    assert isinstance(out, bytes) and out


def test_provenance_defaults_codec_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['codec'] == 'unknown'


def test_provenance_defaults_sample_rate_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['sample_rate'] == 'unknown'


def test_provenance_defaults_channels_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['channels'] == 'unknown'


def test_provenance_defaults_frame_size_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['frame_size'] == 'unknown'


def test_provenance_defaults_device_model_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['device_model'] == 'unknown'


def test_provenance_defaults_firmware_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['firmware'] == 'unknown'


def test_provenance_defaults_app_version_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['app_version'] == 'unknown'


def test_provenance_defaults_capture_start_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['capture_start'] == 'unknown'


def test_provenance_defaults_capture_end_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['capture_end'] == 'unknown'


def test_provenance_defaults_sequence_count_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['sequence_count'] == 'unknown'


def test_provenance_defaults_gap_count_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['gap_count'] == 'unknown'


def test_provenance_defaults_conversation_id_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['conversation_id'] == 'unknown'


def test_provenance_defaults_consent_state_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['consent_state'] == 'unknown'


def test_provenance_defaults_consent_version_to_unknown():
    meta = provenance(b'\x00\x02', {})
    assert meta['consent_version'] == 'unknown'


def test_provenance_always_sets_the_schema_version():
    meta = provenance(b'\x00\x02', {})
    assert meta['schema_version'] == '1'


def test_provenance_always_pins_the_sha256():
    raw = b'\x00\x02' * 320
    meta = provenance(raw, {})
    assert meta['sha256'] == hashlib.sha256(raw).hexdigest()


def test_provenance_supplied_values_override_unknown():
    meta = provenance(b'\x00', {'codec': 'opus', 'channels': 1})
    assert meta['codec'] == 'opus'
    assert meta['channels'] == '1'


def test_provenance_none_supplied_values_stay_unknown():
    meta = provenance(b'\x00', {'codec': None, 'channels': 1})
    assert meta['codec'] == 'unknown'
    assert meta['channels'] == '1'


def test_provenance_unknown_keys_are_stringified():
    meta = provenance(b'\x00', {'sequence_count': 12, 'gap_count': 3.5})
    assert meta['sequence_count'] == '12'
    assert meta['gap_count'] == '3.5'


def test_packet_provenance_non_wal_metadata_passthrough_identity():
    meta = {'format': 'pcm16le', 'capture_start': 5.0}
    assert packet_provenance(b'\x00', meta) is meta


def test_packet_provenance_wal_invalid_packets_keep_the_metadata():
    meta = {'format': WAL_FORMAT, 'capture_start': 5.0, 'sample_rate': '16000'}
    raw = struct.pack('<I', 99999) + b'\x00' * 4
    assert packet_provenance(raw, meta) is meta


def test_packet_provenance_wal_truncated_header_keeps_the_metadata():
    meta = {'format': WAL_FORMAT, 'capture_start': 5.0, 'sample_rate': '16000'}
    assert packet_provenance(b'\x01', meta) is meta


def test_packet_provenance_wal_computes_capture_end(monkeypatch):
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

    monkeypatch.setattr(raw_audio, '_get_opuslib', lambda: FakeModule)
    raw = struct.pack('<I', 2) + b'ab'
    meta = {'format': WAL_FORMAT, 'capture_start': 10.0, 'sample_rate': '16000'}
    result = packet_provenance(raw, meta)
    assert result['capture_end'] == 10.0 + (2 * 320) / 16000
    assert result['sequence_count'] == 1
    assert result['frame_size'] == 'variable-opus-packet-header'


def test_filename_provenance_non_audio_prefix_is_as_captured():
    meta = filename_provenance('voice_2026.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_provenance_short_token_list_is_as_captured():
    meta = filename_provenance('audio_1_2_3_4.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_provenance_opus_codec_maps_to_the_wal_format():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['format'] == WAL_FORMAT


def test_filename_provenance_pcm_codec_maps_to_the_pcm_format():
    meta = filename_provenance('audio_dev1_pcm_16000_1_fs320_1750000000.0_x.bin')
    assert meta['format'] == 'omi-wal-uint32le-pcm-v1'


def test_filename_provenance_reads_the_device_model():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['device_model'] == 'dev1'


def test_filename_provenance_reads_sample_rate_channels_and_frame():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['sample_rate'] == 16000
    assert meta['channels'] == 1
    assert meta['frame_size'] == 320


def test_filename_provenance_epoch_seconds_pass_through():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000.0_x.bin')
    assert meta['capture_start'] == 1750000000.0


def test_filename_provenance_epoch_millis_scale_to_seconds():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_1750000000000.0_x.bin')
    assert meta['capture_start'] == 1750000000.0


def test_filename_provenance_malformed_float_is_as_captured():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs320_notatime_x.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_provenance_malformed_frame_size_is_as_captured():
    meta = filename_provenance('audio_dev1_opus_16000_1_fsbad_1750000000.0_x.bin')
    assert meta == {'format': 'as-captured-file-v1'}


def test_filename_provenance_frame_prefix_is_stripped():
    meta = filename_provenance('audio_dev1_opus_16000_1_fs480_1750000000.0_x.bin')
    assert meta['frame_size'] == 480
