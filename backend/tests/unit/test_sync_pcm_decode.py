"""Tests for PCM16 WAL file decode in sync.py."""

import os
import struct
import sys
import tempfile
import wave
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# --- Stubs to isolate from heavy deps ---
# Use MagicMock for modules where specific names are imported (auto-creates attributes).
# Use ModuleType only for modules imported as a whole without specific attribute access at import time.
_stub_modules = [
    'database._client',
    'database.redis_db',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'database.cache',
    'firebase_admin',
    'firebase_admin.messaging',
    'opuslib',
    'models.conversation',
    'models.transcript_segment',
    'utils.conversations.process_conversation',
    'utils.other',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.encryption',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.log_sanitizer',
]
for mod_name in _stub_modules:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Ensure specific attributes exist on key stubs
sys.modules['database.redis_db'].r = MagicMock()
sys.modules['database._client'].db = MagicMock()

from routers.sync import _is_pcm_codec, decode_pcm_file_to_wav, decode_files_to_wav


class TestIsPcmCodec:
    """Test _is_pcm_codec filename detection."""

    def test_pcm16_detected(self):
        assert _is_pcm_codec('audio_phonemic_pcm16_16000_1_fs160_1710000000.bin') is True

    def test_pcm8_detected(self):
        assert _is_pcm_codec('audio_phonemic_pcm8_8000_1_fs160_1710000000.bin') is True

    def test_opus_not_detected(self):
        assert _is_pcm_codec('audio_omi_opus_16000_2_fs160_1710000000.bin') is False

    def test_opus_fs320_not_detected(self):
        assert _is_pcm_codec('audio_omi_opus_fs320_16000_2_fs320_1710000000.bin') is False

    def test_empty_filename(self):
        assert _is_pcm_codec('') is False


class TestDecodePcmFileToWav:
    """Test decode_pcm_file_to_wav for length-prefixed PCM16 files."""

    def _make_pcm_bin(self, frames: list, path: str):
        """Create a length-prefixed PCM binary file."""
        with open(path, 'wb') as f:
            for frame in frames:
                f.write(struct.pack('<I', len(frame)))
                f.write(frame)

    def test_single_frame_decode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # 320 bytes of PCM16 = 10ms at 16kHz
            frame = bytes(range(256)) + bytes(range(64))  # 320 bytes
            self._make_pcm_bin([frame], bin_path)

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True
            assert os.path.exists(wav_path)

            # Verify WAV properties
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnchannels() == 1
                assert wf.getframerate() == 16000
                assert wf.getsampwidth() == 2
                assert wf.getnframes() == 160  # 320 bytes / 2 bytes per sample

    def test_multiple_frames_concatenated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # 3 frames of 320 bytes each
            frames = [bytes([i % 256] * 320) for i in range(3)]
            self._make_pcm_bin(frames, bin_path)

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 480  # 960 bytes / 2

    def test_empty_file_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Empty file
            with open(bin_path, 'wb') as f:
                pass

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is False

    def test_truncated_frame_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Write a valid frame followed by a truncated one
            valid_frame = bytes([42] * 320)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(valid_frame)))
                f.write(valid_frame)
                f.write(struct.pack('<I', 320))  # Says 320 bytes
                f.write(bytes([0] * 100))  # But only 100 bytes

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True  # Should still decode the valid frame

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160  # Only the first valid frame

    def test_suspicious_frame_length_stops(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Valid frame then corrupted length header
            valid_frame = bytes([42] * 320)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(valid_frame)))
                f.write(valid_frame)
                f.write(struct.pack('<I', 999999))  # Suspicious length > 65536

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True  # First frame still valid

    def test_frame_length_boundary_65536_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # 65536 bytes is the max accepted frame length
            frame = bytes([42] * 65536)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(frame)))
                f.write(frame)

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 65536 // 2  # 16-bit samples = 2 bytes each

    def test_frame_length_boundary_65537_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Valid frame then 65537 bytes (just over limit)
            valid_frame = bytes([42] * 320)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(valid_frame)))
                f.write(valid_frame)
                f.write(struct.pack('<I', 65537))  # Just over 65536 limit

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True  # First frame still valid

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160  # Only the first valid frame

    def test_zero_length_frame_stops(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Valid frame then zero-length frame
            valid_frame = bytes([42] * 320)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(valid_frame)))
                f.write(valid_frame)
                f.write(struct.pack('<I', 0))  # Zero-length frame

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True  # First frame still valid

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160  # Only the first valid frame

    def test_truncated_length_header_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            # Valid frame then incomplete length header (only 2 bytes instead of 4)
            valid_frame = bytes([42] * 320)
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(valid_frame)))
                f.write(valid_frame)
                f.write(bytes([0x40, 0x01]))  # Truncated length header

            result = decode_pcm_file_to_wav(bin_path, wav_path)
            assert result is True  # First frame still valid

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160  # Only the first valid frame

    def test_nonexistent_file_returns_false(self):
        result = decode_pcm_file_to_wav('/nonexistent/path.bin', '/nonexistent/out.wav')
        assert result is False

    def test_pcm8_sample_rate_and_width(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            frame = bytes([42] * 160)  # 160 bytes for pcm8
            self._make_pcm_bin([frame], bin_path)

            result = decode_pcm_file_to_wav(bin_path, wav_path, sample_rate=8000, sample_width=1)
            assert result is True

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getframerate() == 8000
                assert wf.getsampwidth() == 1  # 8-bit audio
                assert wf.getnframes() == 160  # 160 bytes / 1 byte per sample

    def test_pcm16_sample_width(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'test.bin')
            wav_path = os.path.join(tmpdir, 'test.wav')
            frame = bytes([42] * 320)
            self._make_pcm_bin([frame], bin_path)

            result = decode_pcm_file_to_wav(bin_path, wav_path, sample_rate=16000, sample_width=2)
            assert result is True

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getsampwidth() == 2  # 16-bit audio
                assert wf.getnframes() == 160  # 320 bytes / 2 bytes per sample


class TestDecodeFilesToWavPcmRouting:
    """Test that decode_files_to_wav routes PCM files correctly."""

    def _make_pcm_bin(self, frames: list, path: str):
        with open(path, 'wb') as f:
            for frame in frames:
                f.write(struct.pack('<I', len(frame)))
                f.write(frame)

    def test_pcm16_file_decoded_successfully(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Filename with pcm16 codec marker
            bin_path = os.path.join(tmpdir, 'audio_phonemic_pcm16_16000_1_fs160_1710000000.bin')
            # Write enough data for > 1 second (16000 samples * 2 bytes = 32000 bytes)
            # At 320 bytes per frame, need 100 frames for 1 second
            frames = [bytes([i % 256] * 320) for i in range(100)]
            self._make_pcm_bin(frames, bin_path)

            wav_files = decode_files_to_wav([bin_path])
            assert len(wav_files) == 1
            assert wav_files[0].endswith('.wav')

            with wave.open(wav_files[0], 'rb') as wf:
                assert wf.getframerate() == 16000
                duration = wf.getnframes() / wf.getframerate()
                assert duration >= 1.0

    def test_pcm8_file_uses_filename_sample_rate_and_width(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # pcm8 filename with 16000 sample rate (not default 8000)
            bin_path = os.path.join(tmpdir, 'audio_phonemic_pcm8_16000_1_fs160_1710000000.bin')
            frames = [bytes([i % 256] * 160) for i in range(200)]
            self._make_pcm_bin(frames, bin_path)

            wav_files = decode_files_to_wav([bin_path])
            assert len(wav_files) == 1

            with wave.open(wav_files[0], 'rb') as wf:
                assert wf.getframerate() == 16000  # Should parse from filename, not default to 8000
                assert wf.getsampwidth() == 1  # pcm8 = 8-bit = 1 byte per sample

    def test_pcm16_fallback_sample_rate_when_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Filename with pcm16 but non-standard format (no sample rate token)
            bin_path = os.path.join(tmpdir, 'audio_pcm16_custom_1710000000.bin')
            frames = [bytes([i % 256] * 320) for i in range(100)]
            self._make_pcm_bin(frames, bin_path)

            wav_files = decode_files_to_wav([bin_path])
            assert len(wav_files) == 1

            with wave.open(wav_files[0], 'rb') as wf:
                assert wf.getframerate() == 16000  # Should fallback to pcm16 default

    def test_pcm8_fallback_sample_rate_when_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Filename with pcm8 but no parseable sample rate
            bin_path = os.path.join(tmpdir, 'audio_pcm8_custom_1710000000.bin')
            frames = [bytes([i % 256] * 160) for i in range(200)]
            self._make_pcm_bin(frames, bin_path)

            wav_files = decode_files_to_wav([bin_path])
            assert len(wav_files) == 1

            with wave.open(wav_files[0], 'rb') as wf:
                assert wf.getframerate() == 8000  # Should fallback to pcm8 default

    def test_pcm16_short_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bin_path = os.path.join(tmpdir, 'audio_phonemic_pcm16_16000_1_fs160_1710000000.bin')
            # Only 10 frames = 0.1 seconds, should be skipped (< 1s)
            frames = [bytes([42] * 320) for _ in range(10)]
            self._make_pcm_bin(frames, bin_path)

            wav_files = decode_files_to_wav([bin_path])
            assert len(wav_files) == 0

    def test_opus_filename_not_routed_to_pcm(self):
        """Verify non-PCM filenames don't trigger PCM decode path."""
        assert _is_pcm_codec('audio_omi_opus_16000_1_fs160_1710000000.bin') is False
        assert _is_pcm_codec('audio_omi_opus_fs320_16000_2_fs320_1710000000.bin') is False
        assert _is_pcm_codec('audio_omi_aac_16000_1_fs160_1710000000.bin') is False
        assert _is_pcm_codec('audio_omi_lc3_16000_1_fs160_1710000000.bin') is False
