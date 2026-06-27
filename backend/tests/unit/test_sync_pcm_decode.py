"""Tests for PCM16 WAL file decode in sync.py."""

import importlib.util
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
    'database.sync_jobs',
    'firebase_admin',
    'firebase_admin.messaging',
    'opuslib',
    'models.conversation',
    'models.conversation_enums',
    'models.transcript_segment',
    'utils.conversations.factory',
    'utils.conversations.process_conversation',
    'utils.other',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.encryption',
    'utils.executors',
    'utils.analytics',
    'utils.byok',
    'utils.cloud_tasks',
    'utils.http_client',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.speaker_assignment',
    'utils.speaker_identification',
    'utils.stt.speaker_embedding',
    'utils.fair_use',
    'utils.subscription',
    'utils.log_sanitizer',
    'pydub',
]
for mod_name in _stub_modules:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


def _ensure_attrs(module_name, attrs):
    module = sys.modules.setdefault(module_name, MagicMock())
    for attr in attrs:
        if not hasattr(module, attr):
            setattr(module, attr, MagicMock())
    return module


class _ConversationSource:
    omi = 'omi'
    limitless = 'limitless'
    unknown = 'unknown'


def _ensure_conversation_source_stub():
    source = getattr(sys.modules.setdefault('models.conversation_enums', MagicMock()), 'ConversationSource', None)
    if source is None or not all(hasattr(source, attr) for attr in ('omi', 'limitless')):
        sys.modules['models.conversation_enums'].ConversationSource = _ConversationSource

    conversation_mod = sys.modules.setdefault('models.conversation', MagicMock())
    if not hasattr(getattr(conversation_mod, 'ConversationSource', None), 'omi'):
        conversation_mod.ConversationSource = sys.modules['models.conversation_enums'].ConversationSource


def _install_python_multipart_stub():
    if 'python_multipart' in sys.modules:
        return False
    if importlib.util.find_spec('python_multipart') is not None:
        return False

    mod = ModuleType('python_multipart')
    mod.__version__ = '0.0.20'
    sys.modules['python_multipart'] = mod
    return True


# Ensure specific attributes exist on key stubs
sys.modules['database.redis_db'].r = MagicMock()
sys.modules['database._client'].db = MagicMock()
_ensure_attrs('opuslib', ['Decoder'])
_ensure_attrs('database.conversations', ['get_closest_conversation_to_timestamps', 'update_conversation_segments'])
_ensure_attrs(
    'database.sync_jobs',
    [
        'TERMINAL_STATUSES',
        'create_sync_job',
        'get_sync_job',
        'update_sync_job',
        'mark_job_processing',
        'mark_job_completed',
        'mark_job_failed',
        'mark_job_queued_for_retry',
        'try_acquire_job_run_lock',
        'release_job_run_lock',
        'add_processed_segment',
        'get_processed_segments',
        'try_mark_once',
    ],
)
_ensure_attrs('models.conversation', ['Conversation', 'CreateConversation'])
_ensure_conversation_source_stub()
_ensure_attrs('models.transcript_segment', ['TranscriptSegment'])
_ensure_attrs('utils.conversations.factory', ['deserialize_conversation'])
_ensure_attrs('utils.conversations.process_conversation', ['process_conversation'])
_ensure_attrs('utils.analytics', ['record_usage'])
_ensure_attrs('utils.other.endpoints', ['get_current_user_uid'])
_ensure_attrs(
    'utils.other.storage',
    [
        'get_syncing_file_temporal_signed_url',
        'delete_syncing_temporal_file',
        'schedule_syncing_temporal_file_deletion',
        'upload_syncing_temporal_file',
        'download_syncing_temporal_file',
        'download_audio_chunks_and_merge',
        'get_or_create_merged_audio',
        'get_merged_audio_signed_url',
        'download_legacy_merged_wav',
        'get_playback_artifact_signed_url',
        'download_playback_artifact',
        'upload_playback_artifact',
        'mark_playback_unavailable',
        'is_playback_unavailable',
        'enqueue_conversation_audio_merge',
        '_PRECACHE_FILE_SEM',
    ],
)
_ensure_attrs('utils.byok', ['get_byok_keys', 'set_byok_keys', 'has_byok_keys'])
_ensure_attrs(
    'utils.cloud_tasks',
    [
        'enqueue_sync_job',
        'get_sync_tasks_max_attempts',
        'is_audio_merge_dispatch_enabled',
        'is_cloud_tasks_dispatch_enabled',
        'verify_cloud_tasks_oidc',
    ],
)
_ensure_attrs('utils.http_client', ['_get_semaphore'])
_ensure_attrs('utils.log_sanitizer', ['sanitize'])
_ensure_attrs(
    'utils.executors',
    [
        'critical_executor',
        'db_executor',
        'postprocess_executor',
        'storage_executor',
        'sync_executor',
        'run_blocking',
        'start_background_task',
        'submit_with_context',
    ],
)
_ensure_attrs('utils.stt.pre_recorded', ['postprocess_words', 'prerecorded'])
_ensure_attrs('utils.stt.vad', ['vad_is_empty'])
_ensure_attrs(
    'utils.fair_use',
    [
        'record_speech_ms',
        'get_rolling_speech_ms',
        'check_soft_caps',
        'is_hard_restricted',
        'trigger_classifier_if_needed',
        'is_dg_budget_exhausted',
        'get_enforcement_stage',
        'record_dg_usage_ms',
        'FAIR_USE_ENABLED',
        'FAIR_USE_RESTRICT_DAILY_DG_MS',
    ],
)
_ensure_attrs('utils.speaker_assignment', ['process_speaker_assigned_segments'])
_ensure_attrs('utils.speaker_identification', ['detect_speaker_from_text'])
_ensure_attrs(
    'utils.stt.speaker_embedding',
    ['extract_embedding_from_bytes', 'compare_embeddings', 'SPEAKER_MATCH_THRESHOLD'],
)
_ensure_attrs('utils.subscription', ['has_transcription_credits'])
_ensure_attrs('pydub', ['AudioSegment'])
if 'google.cloud.tasks_v2' not in sys.modules:
    sys.modules['google.cloud.tasks_v2'] = MagicMock()
if not hasattr(sys.modules.setdefault('google.cloud', MagicMock()), 'tasks_v2'):
    sys.modules['google.cloud'].tasks_v2 = sys.modules['google.cloud.tasks_v2']

_remove_python_multipart_stub = _install_python_multipart_stub()
try:
    from routers.sync import _is_pcm_codec, decode_pcm_file_to_wav, decode_files_to_wav
finally:
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)


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
