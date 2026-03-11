"""Unit tests for pusher private cloud batch upload logic (Phase 2 of #5418).

Tests the batching behavior in process_private_cloud_queue() without importing
the full pusher module. Mirrors the pattern used in test_pusher_private_cloud_data_protection.py.
"""

import time

import pytest

# --- Reimplemented batch logic (mirrors pusher.py process_private_cloud_queue) ---

PRIVATE_CLOUD_CHUNK_DURATION = 60.0
PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0
PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3


def _add_to_batch(pending, chunk_info):
    """Mirrors the _add_to_batch inner function in process_private_cloud_queue."""
    conv_id = chunk_info['conversation_id']
    if conv_id not in pending:
        pending[conv_id] = {
            'data': bytearray(),
            'conversation_id': conv_id,
            'timestamp': chunk_info['timestamp'],
            'queued_at': chunk_info.get('_queued_at', time.monotonic()),
            'retries': 0,
        }
    batch = pending[conv_id]
    batch['data'].extend(chunk_info['data'])


def _get_flush_candidates(pending, sample_rate, now, websocket_active=True):
    """Mirrors the flush decision logic in process_private_cloud_queue."""
    batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION
    conv_ids_to_flush = []
    for conv_id, batch in pending.items():
        batch_age = now - batch['queued_at']
        is_shutdown = not websocket_active
        is_size_ready = len(batch['data']) >= batch_size_threshold
        is_age_ready = batch_age >= PRIVATE_CLOUD_BATCH_MAX_AGE
        if is_shutdown or is_size_ready or is_age_ready:
            conv_ids_to_flush.append(conv_id)
    return conv_ids_to_flush


class TestBatchAccumulation:
    """Tests that chunks for the same conversation accumulate into one batch."""

    def test_multiple_chunks_same_conversation_batched(self):
        """Multiple chunks for the same conversation produce one batch entry."""
        pending = {}
        now = time.monotonic()
        for i in range(12):
            _add_to_batch(
                pending,
                {
                    'data': b'\x00' * 80_000,
                    'conversation_id': 'conv-1',
                    'timestamp': 1000.0 + i * 5.0,
                    '_queued_at': now,
                },
            )
        assert len(pending) == 1
        assert 'conv-1' in pending
        assert len(pending['conv-1']['data']) == 80_000 * 12
        # Oldest timestamp preserved
        assert pending['conv-1']['timestamp'] == 1000.0

    def test_different_conversations_separate_batches(self):
        """Chunks for different conversations go to separate batches."""
        pending = {}
        now = time.monotonic()
        _add_to_batch(
            pending, {'data': b'\x01' * 100, 'conversation_id': 'conv-A', 'timestamp': 1.0, '_queued_at': now}
        )
        _add_to_batch(
            pending, {'data': b'\x02' * 200, 'conversation_id': 'conv-B', 'timestamp': 2.0, '_queued_at': now}
        )
        _add_to_batch(
            pending, {'data': b'\x03' * 150, 'conversation_id': 'conv-A', 'timestamp': 3.0, '_queued_at': now}
        )
        assert len(pending) == 2
        assert len(pending['conv-A']['data']) == 250
        assert len(pending['conv-B']['data']) == 200
        # Oldest timestamps preserved
        assert pending['conv-A']['timestamp'] == 1.0
        assert pending['conv-B']['timestamp'] == 2.0


class TestSizeFlush:
    """Tests that batches flush when they reach 60s of audio data."""

    def test_flush_at_60s_threshold(self):
        """Batch flushes when accumulated data reaches 60s at sample_rate=8000."""
        pending = {}
        sample_rate = 8000
        now = time.monotonic()
        # 60s of PCM16 at 8kHz = 8000 * 2 * 60 = 960,000 bytes
        _add_to_batch(
            pending,
            {
                'data': b'\x00' * 960_000,
                'conversation_id': 'conv-1',
                'timestamp': 100.0,
                '_queued_at': now,
            },
        )
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' in flush

    def test_no_flush_just_below_threshold(self):
        """Batch does NOT flush when 1 byte below the 60s threshold."""
        pending = {}
        sample_rate = 8000
        now = time.monotonic()
        threshold = sample_rate * 2 * int(PRIVATE_CLOUD_CHUNK_DURATION)  # 960,000
        _add_to_batch(
            pending,
            {
                'data': b'\x00' * (threshold - 1),
                'conversation_id': 'conv-1',
                'timestamp': 100.0,
                '_queued_at': now,
            },
        )
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' not in flush

    def test_no_flush_below_threshold(self):
        """Batch does NOT flush when below 60s of data and within max age."""
        pending = {}
        sample_rate = 8000
        now = time.monotonic()
        # 30s of audio = 480,000 bytes, well under 960,000
        _add_to_batch(
            pending,
            {
                'data': b'\x00' * 480_000,
                'conversation_id': 'conv-1',
                'timestamp': 100.0,
                '_queued_at': now,
            },
        )
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' not in flush


class TestMaxAgeFlush:
    """Tests that the 60s max-age timer forces flush of idle conversations."""

    def test_flush_after_max_age(self):
        """Sub-threshold batch flushes when oldest chunk exceeds 60s age."""
        pending = {}
        sample_rate = 8000
        old_time = time.monotonic() - 61.0  # 61 seconds ago
        _add_to_batch(
            pending,
            {
                'data': b'\x00' * 1000,
                'conversation_id': 'conv-1',
                'timestamp': 100.0,
                '_queued_at': old_time,
            },
        )
        now = time.monotonic()
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' in flush

    def test_flush_at_exact_max_age(self):
        """Batch flushes when age equals exactly PRIVATE_CLOUD_BATCH_MAX_AGE (>=)."""
        pending = {}
        sample_rate = 8000
        now = 1000.0
        queued_at = now - PRIVATE_CLOUD_BATCH_MAX_AGE  # exactly 60s ago
        pending['conv-1'] = {
            'data': bytearray(b'\x00' * 1000),
            'conversation_id': 'conv-1',
            'timestamp': 100.0,
            'queued_at': queued_at,
            'retries': 0,
        }
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' in flush

    def test_no_flush_just_before_max_age(self):
        """Batch does NOT flush when 0.1s before max age."""
        pending = {}
        sample_rate = 8000
        now = 1000.0
        queued_at = now - (PRIVATE_CLOUD_BATCH_MAX_AGE - 0.1)  # 59.9s ago
        pending['conv-1'] = {
            'data': bytearray(b'\x00' * 1000),
            'conversation_id': 'conv-1',
            'timestamp': 100.0,
            'queued_at': queued_at,
            'retries': 0,
        }
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' not in flush

    def test_no_flush_before_max_age(self):
        """Batch within max-age window does not flush."""
        pending = {}
        sample_rate = 8000
        recent_time = time.monotonic() - 30.0  # 30 seconds ago
        _add_to_batch(
            pending,
            {
                'data': b'\x00' * 1000,
                'conversation_id': 'conv-1',
                'timestamp': 100.0,
                '_queued_at': recent_time,
            },
        )
        now = time.monotonic()
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=True)
        assert 'conv-1' not in flush


class TestRetryBackoff:
    """Tests that failed uploads reset queued_at for natural backoff."""

    def test_retry_resets_queued_at(self):
        """After upload failure, queued_at is reset so batch won't re-flush for ~60s."""
        pending = {}
        sample_rate = 8000
        now = 1000.0

        # Simulate a batch that failed upload — retry logic resets queued_at
        failed_batch = {
            'data': bytearray(b'\x00' * 1000),
            'conversation_id': 'conv-1',
            'timestamp': 100.0,
            'queued_at': now,  # reset to "now" by retry logic
            'retries': 1,
        }
        pending['conv-1'] = failed_batch

        # 59.9s later — should NOT flush yet (backoff)
        flush = _get_flush_candidates(pending, sample_rate, now + 59.9, websocket_active=True)
        assert 'conv-1' not in flush

        # 60s later — should flush (backoff expired)
        flush = _get_flush_candidates(pending, sample_rate, now + 60.0, websocket_active=True)
        assert 'conv-1' in flush

    def test_retry_preserves_data_and_increments_count(self):
        """Retry preserves chunk data and increments retry count."""
        # Mirrors the retry logic in _flush_batch
        batch = {
            'data': bytearray(b'\xab' * 500),
            'conversation_id': 'conv-1',
            'timestamp': 100.0,
            'queued_at': 900.0,
            'retries': 0,
        }
        # Simulate failed upload — retry path
        retries = batch['retries']
        chunk_data = bytes(batch['data'])
        batch['retries'] = retries + 1
        batch['data'] = bytearray(chunk_data)
        batch['queued_at'] = 1000.0  # reset

        assert batch['retries'] == 1
        assert len(batch['data']) == 500
        assert batch['queued_at'] == 1000.0


class TestShutdownFlush:
    """Tests that shutdown forces flush of all pending batches regardless of size/age."""

    def test_shutdown_flushes_all_pending(self):
        """All conversations flush on shutdown even if below thresholds."""
        pending = {}
        sample_rate = 8000
        now = time.monotonic()
        _add_to_batch(
            pending, {'data': b'\x00' * 100, 'conversation_id': 'conv-A', 'timestamp': 1.0, '_queued_at': now}
        )
        _add_to_batch(
            pending, {'data': b'\x00' * 200, 'conversation_id': 'conv-B', 'timestamp': 2.0, '_queued_at': now}
        )
        flush = _get_flush_candidates(pending, sample_rate, now, websocket_active=False)
        assert set(flush) == {'conv-A', 'conv-B'}


class TestConversationSwitch:
    """Tests that conversation switch flushes old conversation buffer."""

    def test_conversation_switch_flushes_old_buffer(self):
        """Mirrors the conversation switch flush in receive_tasks (header_type 103)."""
        private_cloud_sync_buffer = bytearray(b'\x00' * 500)
        current_conversation_id = 'conv-old'
        new_conversation_id = 'conv-new'
        private_cloud_chunk_start_time = 100.0
        private_cloud_queue = []

        # Reproduce the flush logic from pusher.py header_type == 103
        if (
            current_conversation_id
            and current_conversation_id != new_conversation_id
            and len(private_cloud_sync_buffer) > 0
        ):
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': current_conversation_id,
                    'timestamp': private_cloud_chunk_start_time or time.time(),
                    'retries': 0,
                }
            )
            private_cloud_sync_buffer = bytearray()
            private_cloud_chunk_start_time = None

        assert len(private_cloud_queue) == 1
        assert private_cloud_queue[0]['conversation_id'] == 'conv-old'
        assert len(private_cloud_queue[0]['data']) == 500
        assert len(private_cloud_sync_buffer) == 0

    def test_no_flush_on_same_conversation_id(self):
        """No flush if conversation_id doesn't change."""
        private_cloud_sync_buffer = bytearray(b'\x00' * 500)
        current_conversation_id = 'conv-1'
        new_conversation_id = 'conv-1'
        private_cloud_queue = []

        if (
            current_conversation_id
            and current_conversation_id != new_conversation_id
            and len(private_cloud_sync_buffer) > 0
        ):
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': current_conversation_id,
                    'timestamp': time.time(),
                    'retries': 0,
                }
            )
            private_cloud_sync_buffer = bytearray()

        assert len(private_cloud_queue) == 0
        assert len(private_cloud_sync_buffer) == 500

    def test_no_flush_on_empty_buffer(self):
        """No flush when buffer is empty even if conversation_id changes."""
        private_cloud_sync_buffer = bytearray()
        current_conversation_id = 'conv-old'
        new_conversation_id = 'conv-new'
        private_cloud_queue = []
        private_cloud_sync_enabled = True

        if (
            private_cloud_sync_enabled
            and current_conversation_id
            and current_conversation_id != new_conversation_id
            and len(private_cloud_sync_buffer) > 0
        ):
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': current_conversation_id,
                    'timestamp': time.time(),
                    'retries': 0,
                }
            )

        assert len(private_cloud_queue) == 0

    def test_no_flush_when_no_current_conversation(self):
        """No flush when current_conversation_id is None."""
        private_cloud_sync_buffer = bytearray(b'\x00' * 500)
        current_conversation_id = None
        new_conversation_id = 'conv-new'
        private_cloud_queue = []
        private_cloud_sync_enabled = True

        if (
            private_cloud_sync_enabled
            and current_conversation_id
            and current_conversation_id != new_conversation_id
            and len(private_cloud_sync_buffer) > 0
        ):
            private_cloud_queue.append(
                {
                    'data': bytes(private_cloud_sync_buffer),
                    'conversation_id': current_conversation_id,
                    'timestamp': time.time(),
                    'retries': 0,
                }
            )

        assert len(private_cloud_queue) == 0


# --- Tests for conversations.py gap threshold and duration logic ---


def _finalize_audio_file_group_duration(chunk_group):
    """Mirrors _finalize_audio_file_group duration calculation from conversations.py."""
    from datetime import datetime, timezone

    started_at = datetime.fromtimestamp(chunk_group[0]['timestamp'], tz=timezone.utc)
    last_chunk_start = datetime.fromtimestamp(chunk_group[-1]['timestamp'], tz=timezone.utc)
    last_chunk_size = chunk_group[-1].get('size', 0)
    last_chunk_duration = last_chunk_size / 16000.0 if last_chunk_size > 0 else 5.0
    duration = (last_chunk_start - started_at).total_seconds() + last_chunk_duration
    return duration


def _group_chunks_by_gap(chunks, gap_threshold=90):
    """Mirrors create_audio_files_from_chunks gap grouping from conversations.py."""
    groups = []
    current_group = []
    for chunk in chunks:
        if not current_group:
            current_group.append(chunk)
        else:
            time_gap = chunk['timestamp'] - current_group[-1]['timestamp']
            if time_gap > gap_threshold:
                groups.append(current_group)
                current_group = [chunk]
            else:
                current_group.append(chunk)
    if current_group:
        groups.append(current_group)
    return groups


class TestAudioFileGapThreshold:
    """Tests for the 90s gap threshold in create_audio_files_from_chunks."""

    def test_gap_at_90s_no_split(self):
        """Chunks 90s apart should NOT split (gap <= threshold)."""
        chunks = [
            {'timestamp': 1000.0, 'size': 960_000},
            {'timestamp': 1090.0, 'size': 960_000},
        ]
        groups = _group_chunks_by_gap(chunks, gap_threshold=90)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_gap_at_91s_splits(self):
        """Chunks 91s apart should split (gap > threshold)."""
        chunks = [
            {'timestamp': 1000.0, 'size': 960_000},
            {'timestamp': 1091.0, 'size': 960_000},
        ]
        groups = _group_chunks_by_gap(chunks, gap_threshold=90)
        assert len(groups) == 2
        assert len(groups[0]) == 1
        assert len(groups[1]) == 1

    def test_60s_chunks_stay_grouped(self):
        """Consecutive 60s chunks (normal batching pattern) stay in one group."""
        chunks = [{'timestamp': 1000.0 + i * 60.0, 'size': 960_000} for i in range(5)]
        groups = _group_chunks_by_gap(chunks, gap_threshold=90)
        assert len(groups) == 1
        assert len(groups[0]) == 5

    def test_5s_chunks_stay_grouped(self):
        """Legacy 5s chunks still group correctly."""
        chunks = [{'timestamp': 1000.0 + i * 5.0, 'size': 80_000} for i in range(12)]
        groups = _group_chunks_by_gap(chunks, gap_threshold=90)
        assert len(groups) == 1
        assert len(groups[0]) == 12


class TestAudioFileDurationFromSize:
    """Tests for blob-size-based duration calculation in _finalize_audio_file_group."""

    def test_duration_from_60s_blob(self):
        """60s of PCM16 at 8kHz = 960,000 bytes → duration should be ~60.0s."""
        chunks = [{'timestamp': 1000.0, 'size': 960_000}]
        duration = _finalize_audio_file_group_duration(chunks)
        assert abs(duration - 60.0) < 0.01

    def test_duration_from_5s_blob(self):
        """5s of PCM16 at 8kHz = 80,000 bytes → duration should be ~5.0s."""
        chunks = [{'timestamp': 1000.0, 'size': 80_000}]
        duration = _finalize_audio_file_group_duration(chunks)
        assert abs(duration - 5.0) < 0.01

    def test_duration_fallback_no_size(self):
        """When size is 0 or missing, falls back to 5.0s."""
        chunks = [{'timestamp': 1000.0, 'size': 0}]
        duration = _finalize_audio_file_group_duration(chunks)
        assert abs(duration - 5.0) < 0.01

        chunks_no_key = [{'timestamp': 1000.0}]
        duration2 = _finalize_audio_file_group_duration(chunks_no_key)
        assert abs(duration2 - 5.0) < 0.01

    def test_multi_chunk_duration(self):
        """Duration across multiple 60s chunks: first→last gap + last chunk duration."""
        chunks = [
            {'timestamp': 1000.0, 'size': 960_000},
            {'timestamp': 1060.0, 'size': 960_000},
            {'timestamp': 1120.0, 'size': 960_000},
        ]
        # Expected: (1120 - 1000) + 60.0 = 180.0
        duration = _finalize_audio_file_group_duration(chunks)
        assert abs(duration - 180.0) < 0.01
