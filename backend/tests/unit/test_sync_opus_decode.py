"""Tests for Opus WAL file decoding in sync.py.

Covers the decode_opus_file_to_wav and decode_files_to_wav functions,
focusing on failure modes that cause WALs to become permanently stuck:

  - Corrupt frames (opuslib raises) → must skip frame, not abort entire file
  - Corrupt length prefix → must stop cleanly without reading garbage data
  - Empty / missing files → must return False without leaving stale WAV behind
  - All-corrupt payload → must return False (no partial WAV created)
  - Short decoded audio (< 1 s) → decode_files_to_wav must discard it

Each scenario corresponds to a real-world sticky-pending failure mode.
"""

import os
import struct
import sys
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stubs — isolate from heavy deps before importing sync
# ---------------------------------------------------------------------------

_stub_modules = [
    'database._client',
    'database.redis_db',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'database.cache',
    'database.sync_jobs',
    'firebase_admin',
    'firebase_admin.messaging',
    'opuslib',
    'models.conversation',
    'models.conversation_enums',
    'models.transcript_segment',
    'utils.conversations.process_conversation',
    'utils.conversations.factory',
    'utils.other',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.encryption',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.log_sanitizer',
    'utils.executors',
    'pydub',
    'numpy',
    'httpx',
]
for _mod in _stub_modules:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.modules['database.redis_db'].r = MagicMock()
sys.modules['database._client'].db = MagicMock()
sys.modules['utils.log_sanitizer'].sanitize = lambda x: x
sys.modules['utils.log_sanitizer'].sanitize_pii = lambda x: x

from routers.sync import decode_opus_file_to_wav, decode_files_to_wav  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: One frame of fake Opus-encoded bytes (content doesn't matter — decoder is mocked).
FAKE_OPUS_FRAME = b'\xAA\xBB\xCC' * 34  # 102 bytes

#: PCM returned by the mocked decoder: 320 bytes = 160 mono samples at 16-bit.
#: 100 such frames = 16 000 samples = 1.0 s at 16 kHz.
FAKE_PCM_FRAME = b'\x00' * 320


def _write_opus_bin(path: str, frames: list[bytes]) -> None:
    """Write a length-prefixed Omi WAL file (the on-device Opus format)."""
    with open(path, 'wb') as f:
        for frame in frames:
            f.write(struct.pack('<I', len(frame)))
            f.write(frame)


def _good_decoder(pcm_per_call: bytes = FAKE_PCM_FRAME):
    """Return a mock Decoder class whose decode() always succeeds."""
    instance = MagicMock()
    instance.decode.return_value = pcm_per_call
    klass = MagicMock(return_value=instance)
    return klass, instance


def _failing_decoder(fail_on: set[int], pcm_per_call: bytes = FAKE_PCM_FRAME):
    """Return a mock Decoder that raises OpusError for specific frame indices."""
    call_count = {'n': 0}

    def _decode(opus_data, frame_size):
        idx = call_count['n']
        call_count['n'] += 1
        if idx in fail_on:
            raise Exception(f'OpusError: frame {idx} is corrupt')
        return pcm_per_call

    instance = MagicMock()
    instance.decode.side_effect = _decode
    klass = MagicMock(return_value=instance)
    return klass, instance


# ---------------------------------------------------------------------------
# decode_opus_file_to_wav
# ---------------------------------------------------------------------------


class TestDecodeOpusFileToWav:
    """Unit tests for decode_opus_file_to_wav."""

    # --- Happy path ---

    def test_valid_file_returns_true_and_creates_wav(self):
        """All frames decode → True, WAV file created."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            assert os.path.exists(wav_path)

    def test_correct_frame_count_in_wav(self):
        """Five decoded frames of 160 samples each → 800 WAV frames."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)
            decode_opus_file_to_wav(bin_path, wav_path)

            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 5 * 160  # 160 samples per frame, 16-bit mono
                assert wf.getframerate() == 16000
                assert wf.getnchannels() == 1

    # --- Single corrupt frame (the bug that was fixed) ---

    def test_one_corrupt_frame_in_middle_is_skipped(self):
        """Frame 2 raises → skipped, rest decoded → True.

        Before the fix (break instead of continue), this returned False
        because decoding stopped at the corrupt frame leaving 0 decoded frames.
        After the fix (continue), frames 0-1 and 3-4 are decoded → True.
        """
        klass, _ = _failing_decoder(fail_on={2})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 4 * 160  # frame 2 skipped

    def test_first_frame_corrupt_rest_valid(self):
        """Frame 0 is corrupt → skipped, frames 1-4 decoded → True."""
        klass, _ = _failing_decoder(fail_on={0})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 4 * 160

    def test_last_frame_corrupt_prior_frames_preserved(self):
        """Frame 4 is corrupt → skipped, frames 0-3 decoded → True."""
        klass, _ = _failing_decoder(fail_on={4})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 4 * 160

    def test_multiple_non_contiguous_corrupt_frames_skipped(self):
        """Frames 1 and 3 corrupt → both skipped, frames 0, 2, 4 decoded → True."""
        klass, _ = _failing_decoder(fail_on={1, 3})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 3 * 160

    # --- All-corrupt payload ---

    def test_all_frames_corrupt_returns_false(self):
        """Every frame raises → frame_count stays 0 → False, no WAV created."""
        klass, _ = _failing_decoder(fail_on={0, 1, 2, 3, 4})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is False
            assert not os.path.exists(wav_path), "Stale WAV must be cleaned up"

    def test_all_corrupt_single_frame_file_returns_false(self):
        """File with one frame that fails → False."""
        klass, _ = _failing_decoder(fail_on={0})
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'test.bin')
            wav_path = os.path.join(d, 'test.wav')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME])

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is False
            assert not os.path.exists(wav_path)

    # --- File-level errors ---

    def test_empty_file_returns_false(self):
        """Zero-byte file → no frames → False."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'empty.bin')
            wav_path = os.path.join(d, 'empty.wav')
            open(bin_path, 'wb').close()  # touch

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is False

    def test_file_not_found_returns_false(self):
        """Non-existent input path → False without exception."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            result = decode_opus_file_to_wav(
                os.path.join(d, 'missing.bin'),
                os.path.join(d, 'missing.wav'),
            )
            assert result is False

    # --- Corrupt / malformed length prefix ---

    def test_truncated_frame_data_stops_cleanly(self):
        """Length prefix says N bytes but file ends early → break, prior frames kept."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'truncated.bin')
            wav_path = os.path.join(d, 'truncated.wav')
            with open(bin_path, 'wb') as f:
                # Write one valid frame
                f.write(struct.pack('<I', len(FAKE_OPUS_FRAME)))
                f.write(FAKE_OPUS_FRAME)
                # Write a length prefix claiming 1000 bytes but only supply 10
                f.write(struct.pack('<I', 1000))
                f.write(b'\xAA' * 10)

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True  # First frame decoded
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160

    def test_truncated_frame_as_first_entry_returns_false(self):
        """Truncated data with no prior valid frames → False."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'trunc_first.bin')
            wav_path = os.path.join(d, 'trunc_first.wav')
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', 500))  # Says 500 bytes
                f.write(b'\xAA' * 10)            # Only 10 bytes follow

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is False
            assert not os.path.exists(wav_path)

    def test_incomplete_length_prefix_at_eof_stops_cleanly(self):
        """Only 2 bytes remain for the 4-byte length prefix → break, prior frames kept."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'partial_prefix.bin')
            wav_path = os.path.join(d, 'partial_prefix.wav')
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(FAKE_OPUS_FRAME)))
                f.write(FAKE_OPUS_FRAME)
                f.write(b'\x00\x01')  # Incomplete length header at EOF

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160

    def test_gigantic_length_prefix_treated_as_truncation(self):
        """0xFFFFFFFF frame length → read returns far fewer bytes → truncation break → prior frames kept."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = os.path.join(d, 'giant_prefix.bin')
            wav_path = os.path.join(d, 'giant_prefix.wav')
            with open(bin_path, 'wb') as f:
                f.write(struct.pack('<I', len(FAKE_OPUS_FRAME)))
                f.write(FAKE_OPUS_FRAME)
                f.write(struct.pack('<I', 0xFFFFFFFF))  # 4 GB claimed
                f.write(b'\xAA' * 20)                   # Only 20 bytes available

            result = decode_opus_file_to_wav(bin_path, wav_path)

            assert result is True
            with wave.open(wav_path, 'rb') as wf:
                assert wf.getnframes() == 160


# ---------------------------------------------------------------------------
# decode_files_to_wav (integration layer on top of decode_opus_file_to_wav)
# ---------------------------------------------------------------------------


class TestDecodeFilesToWavOpus:
    """Tests for decode_files_to_wav focusing on Opus routing and cleanup."""

    # At 16 kHz / frame_size=160, 100 frames = 1.0 s (meets the ≥1 s filter).
    ENOUGH_FRAMES = 101

    def _write_valid_opus_bin(self, path: str, n_frames: int = None) -> None:
        _write_opus_bin(path, [FAKE_OPUS_FRAME] * (n_frames or self.ENOUGH_FRAMES))

    def _opus_filename(self, tmpdir: str, ts: int = 1710000000) -> str:
        """Standard Omi Opus filename used by the device."""
        return os.path.join(tmpdir, f'audio_omi_opus_16000_1_fs160_{ts}.bin')

    # --- File routing ---

    def test_valid_opus_file_included_in_output(self):
        """Valid Opus file with > 1 s of audio → wav path included."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = self._opus_filename(d)
            self._write_valid_opus_bin(bin_path)

            wav_files = decode_files_to_wav([bin_path])

            assert len(wav_files) == 1
            assert wav_files[0].endswith('.wav')
            assert os.path.exists(wav_files[0])

    def test_frame_size_parsed_from_filename(self):
        """_fs320 in filename → frame_size=320 passed to decoder."""
        klass, instance = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            # fs320 filename
            bin_path = os.path.join(d, f'audio_omi_opus_16000_1_fs320_1710000000.bin')
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * self.ENOUGH_FRAMES)

            decode_files_to_wav([bin_path])

            # All decode() calls should use frame_size=320
            for call in instance.decode.call_args_list:
                assert call.kwargs.get('frame_size') == 320

    # --- Failure / cleanup ---

    def test_all_corrupt_frames_file_excluded_from_output(self):
        """Decode returns False → wav not included, bin cleaned up."""
        klass, _ = _failing_decoder(fail_on=set(range(self.ENOUGH_FRAMES)))
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = self._opus_filename(d)
            self._write_valid_opus_bin(bin_path)

            wav_files = decode_files_to_wav([bin_path])

            assert wav_files == []
            assert not os.path.exists(bin_path), ".bin must be cleaned up on failure"

    def test_bin_file_deleted_after_successful_decode(self):
        """Successful decode → .bin removed (not left as an orphan)."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = self._opus_filename(d)
            self._write_valid_opus_bin(bin_path)

            decode_files_to_wav([bin_path])

            assert not os.path.exists(bin_path)

    # --- Duration filter ---

    def test_too_short_audio_excluded(self):
        """< 1 s of decoded audio → excluded from output, wav cleaned up."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = self._opus_filename(d)
            # 5 frames × 160 samples = 800 samples = 0.05 s → below 1 s threshold
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 5)

            wav_files = decode_files_to_wav([bin_path])

            assert wav_files == []
            wav_path = bin_path.replace('.bin', '.wav')
            assert not os.path.exists(wav_path), "Short WAV must be cleaned up"

    def test_exactly_one_second_included(self):
        """Exactly 1.0 s decoded (100 frames × 160 samples at 16 kHz) → included."""
        klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d, patch('routers.sync.Decoder', klass):
            bin_path = self._opus_filename(d)
            # 100 frames × 160 samples / 16000 Hz = 1.0 s
            _write_opus_bin(bin_path, [FAKE_OPUS_FRAME] * 100)

            wav_files = decode_files_to_wav([bin_path])

            # duration == 1.0 → NOT excluded (< 1 check, not <=)
            assert len(wav_files) == 1

    # --- Multiple files ---

    def test_mixed_batch_valid_and_corrupt(self):
        """Valid file + all-corrupt file → only valid included, both bins cleaned up."""
        good_klass, _ = _good_decoder()
        with tempfile.TemporaryDirectory() as d:
            valid_bin = self._opus_filename(d, ts=1710000001)
            corrupt_bin = self._opus_filename(d, ts=1710000002)

            call_count = {'n': 0}
            pcm = FAKE_PCM_FRAME

            def _make_instance(*args, **kwargs):
                call_count['n'] += 1
                inst = MagicMock()
                if call_count['n'] == 1:
                    inst.decode.return_value = pcm
                else:
                    inst.decode.side_effect = Exception("corrupt")
                return inst

            with patch('routers.sync.Decoder', side_effect=_make_instance):
                self._write_valid_opus_bin(valid_bin)
                _write_opus_bin(corrupt_bin, [FAKE_OPUS_FRAME] * 5)

                wav_files = decode_files_to_wav([valid_bin, corrupt_bin])

            assert len(wav_files) == 1
            assert not os.path.exists(valid_bin)
            assert not os.path.exists(corrupt_bin)
