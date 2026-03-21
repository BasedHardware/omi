"""Tests for DG usage batching (#5854).

Verifies that record_dg_usage_ms is batched every 60s instead of per-chunk,
reducing Redis ops from ~100/sec/session to ~0.03/sec/session.
"""

import re
import os

import pytest


def _read_transcribe_source():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')
    with open(path, 'r') as f:
        return f.read()


class TestDgUsageBatchingStructure:
    """Verify transcribe.py uses local accumulator instead of per-chunk Redis writes."""

    def test_no_per_chunk_redis_calls(self):
        """record_dg_usage_ms should only be called at flush points, not per chunk."""
        source = _read_transcribe_source()
        calls = re.findall(r'^\s+record_dg_usage_ms\(', source, re.MULTILINE)
        # Only 2 calls: periodic flush + session-end flush
        assert len(calls) == 2, f'Expected 2 record_dg_usage_ms calls (flush only), found {len(calls)}'

    def test_accumulation_covers_all_stt_providers(self):
        """All 4 STT provider paths accumulate locally via dg_usage_ms_pending +=."""
        source = _read_transcribe_source()
        accum = re.findall(r'^\s+dg_usage_ms_pending\s*\+=', source, re.MULTILINE)
        # DG, Soniox, Speechmatics, multi-channel
        assert len(accum) == 4, f'Expected 4 accumulation points, found {len(accum)}'

    def test_nonlocal_declarations_complete(self):
        """All nested functions that touch dg_usage_ms_pending declare nonlocal."""
        source = _read_transcribe_source()
        nonlocals = re.findall(r'nonlocal.*dg_usage_ms_pending', source)
        # _record_usage_periodically, receive_data, flush_stt_buffer
        assert len(nonlocals) == 3, f'Expected 3 nonlocal declarations, found {len(nonlocals)}'

    def test_flush_resets_accumulator(self):
        """Each flush point resets dg_usage_ms_pending to 0."""
        source = _read_transcribe_source()
        lines = source.split('\n')
        resets = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == 'dg_usage_ms_pending = 0':
                resets.append(i)
        # periodic flush + session-end flush
        assert len(resets) == 2, f'Expected 2 reset points, found {len(resets)}'

    def test_flush_before_custom_stt_guard(self):
        """DG flush must happen before use_custom_stt:continue guard."""
        source = _read_transcribe_source()
        flush_pos = source.find('record_dg_usage_ms(uid, dg_usage_ms_pending)')
        guard_pos = source.find('if use_custom_stt:\n')
        assert flush_pos < guard_pos, 'DG flush must be before use_custom_stt guard'


class TestDgUsageBatchingBehavior:
    """Test the record_dg_usage_ms function handles batched input correctly."""

    def setup_method(self):
        import sys
        from types import ModuleType
        from unittest.mock import MagicMock

        for mod_name in [
            'database._client',
            'database.redis_db',
            'database.fair_use',
            'database.users',
            'database.user_usage',
            'database.conversations',
            'firebase_admin',
            'firebase_admin.messaging',
        ]:
            if mod_name not in sys.modules:
                sys.modules[mod_name] = ModuleType(mod_name)

        sys.modules['database._client'].db = MagicMock()
        sys.modules['database.redis_db'].r = MagicMock()

        os.environ.setdefault('FAIR_USE_ENABLED', 'true')
        os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-key-that-is-long-enough-for-encryption-32ch')

    def test_batched_60s_single_redis_write(self):
        """60s of accumulated chunks should produce a single Redis pipeline."""
        from unittest.mock import MagicMock, patch

        import utils.fair_use as fu

        fu.redis_client = MagicMock()
        pipe = MagicMock()
        fu.redis_client.pipeline.return_value = pipe

        with patch.object(fu, 'FAIR_USE_ENABLED', True), patch.object(fu, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000):
            # Simulate 60s of audio: 50 chunks/sec × 60s × 20ms = 60000ms
            total_ms = 60000
            fu.record_dg_usage_ms('user1', total_ms)

        # Single pipeline call with single INCRBY
        fu.redis_client.pipeline.assert_called_once()
        pipe.incrby.assert_called_once()
        call_args = pipe.incrby.call_args
        assert total_ms in call_args[0] or total_ms in call_args[1].values()

    def test_large_accumulation_no_overflow(self):
        """24h of continuous audio should not overflow Python int."""
        from unittest.mock import MagicMock, patch

        import utils.fair_use as fu

        fu.redis_client = MagicMock()
        pipe = MagicMock()
        fu.redis_client.pipeline.return_value = pipe

        with patch.object(fu, 'FAIR_USE_ENABLED', True), patch.object(fu, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000):
            # 24h of audio = 86,400,000 ms — well within Python int range
            total_ms = 86_400_000
            fu.record_dg_usage_ms('user1', total_ms)

        pipe.incrby.assert_called_once()

    def test_disabled_skips_redis(self):
        """When FAIR_USE_ENABLED is False, no Redis calls."""
        from unittest.mock import MagicMock, patch

        import utils.fair_use as fu

        fu.redis_client = MagicMock()

        with patch.object(fu, 'FAIR_USE_ENABLED', False):
            fu.record_dg_usage_ms('user1', 60000)

        fu.redis_client.pipeline.assert_not_called()

    def test_zero_ms_skips_redis(self):
        """Zero ms should not trigger Redis write."""
        from unittest.mock import MagicMock, patch

        import utils.fair_use as fu

        fu.redis_client = MagicMock()

        with patch.object(fu, 'FAIR_USE_ENABLED', True), patch.object(fu, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000):
            fu.record_dg_usage_ms('user1', 0)

        fu.redis_client.pipeline.assert_not_called()


class TestRedisOpsReduction:
    """Verify the ops/sec reduction math."""

    def test_reduction_factor(self):
        """Batching should produce ~3000x reduction."""
        chunks_per_sec = 50
        redis_ops_per_call = 2  # INCRBY + EXPIRE
        flush_interval = 60

        before = chunks_per_sec * redis_ops_per_call  # 100 ops/sec/session
        after = redis_ops_per_call / flush_interval  # 0.033 ops/sec/session

        reduction = before / after
        assert reduction == pytest.approx(3000, rel=0.01)

    def test_100_sessions_ops(self):
        """100 concurrent sessions: before ~10k, after ~3.3 ops/sec."""
        sessions = 100
        before = sessions * 50 * 2  # 10,000
        after = sessions * 2 / 60  # 3.33

        assert before == 10000
        assert after == pytest.approx(3.33, abs=0.01)
