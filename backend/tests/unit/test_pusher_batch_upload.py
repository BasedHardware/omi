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
