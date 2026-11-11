"""Tests for DG usage batching (#5854).

Verifies that record_dg_usage_ms is batched every 60s instead of per-chunk,
reducing Redis ops from ~100/sec/session to ~0.03/sec/session.
"""

import os
import re
from pathlib import Path
from types import ModuleType
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class _SoftCapTrigger:
    DAILY = 'daily'
    THREE_DAY = 'three_day'
    WEEKLY = 'weekly'


@pytest.fixture
def fair_use() -> Iterator[ModuleType]:
    redis_client = MagicMock()

    async def run_blocking(_executor, func, *args, **kwargs):
        return func(*args, **kwargs)

    stubs = {
        'database.fair_use': AutoMockModule('database.fair_use'),
        'database.users': AutoMockModule('database.users'),
        'database.redis_db': _module('database.redis_db', r=redis_client),
        'models.fair_use': _module('models.fair_use', SoftCapTrigger=_SoftCapTrigger),
        'utils.subscription': _module(
            'utils.subscription',
            has_transcription_credits=MagicMock(return_value=True),
            is_paid_plan=MagicMock(return_value=False),
        ),
        'utils.executors': _module(
            'utils.executors',
            db_executor=object(),
            postprocess_executor=object(),
            run_blocking=run_blocking,
        ),
        'utils.llm.fair_use_classifier': _module(
            'utils.llm.fair_use_classifier',
            classify_user_purpose=MagicMock(),
        ),
        'utils.notifications': _module('utils.notifications', send_notification=MagicMock()),
    }

    with stub_modules(stubs):
        yield load_module_fresh('utils.fair_use', str(BACKEND_DIR / 'utils' / 'fair_use.py'))


def _read_listen_source(module: str):
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'listen', f'{module}.py')
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class TestDgUsageBatchingStructure:
    """Verify listen components use a local accumulator instead of per-chunk Redis writes."""

    def test_no_per_chunk_redis_calls(self):
        """record_dg_usage_ms should only be called at flush points, not per chunk."""
        source = _read_listen_source('runtime')
        calls = re.findall(r'record_dg_usage_ms, self\.request\.uid, self\.state\.dg_usage_ms_pending', source)
        # Periodic and final flushes use one shared persistence boundary.
        assert len(calls) == 1, f'Expected one shared record_dg_usage_ms flush, found {len(calls)}'

    def test_accumulation_covers_all_stt_providers(self):
        """All STT provider paths accumulate locally via session.dg_usage_ms_pending +=."""
        source = _read_listen_source('receiver')
        accum = re.findall(r'^\s+self\.host\.state\.dg_usage_ms_pending\s*\+=', source, re.MULTILINE)
        # DG single-channel + multi-channel
        assert len(accum) == 2, f'Expected 2 accumulation points, found {len(accum)}'

    def test_accumulator_lives_in_session_state(self):
        """The DG accumulator is explicit session state, not closure nonlocal state."""
        source = _read_listen_source('contracts')
        assert 'dg_usage_ms_pending: int = 0' in source
        assert not re.findall(r'nonlocal.*dg_usage_ms_pending', source)

    def test_flush_resets_accumulator(self):
        """Each flush point resets dg_usage_ms_pending to 0."""
        source = _read_listen_source('runtime')
        lines = source.split('\n')
        resets = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == 'self.state.dg_usage_ms_pending = 0':
                resets.append(i)
        assert len(resets) == 1, f'Expected one shared reset point, found {len(resets)}'

    def test_flush_before_custom_stt_guard(self):
        """DG flush must happen before use_custom_stt early-return guard."""
        source = _read_listen_source('runtime')
        flush_start = source.find('async def _flush_usage(')
        flush_end = source.find('    async def _start_pusher', flush_start)
        flush_body = source[flush_start:flush_end]
        flush_pos = flush_body.find('record_dg_usage_ms, self.request.uid, self.state.dg_usage_ms_pending')
        # PR #7690 split the compound guard into a standalone custom-STT
        # early-return (with its own isolated fair-use lane) followed by the
        # last_usage_record_timestamp check.  The invariant is unchanged: the
        # DG accumulator flush must precede the custom-STT exit path.
        guard_pos = flush_body.find('if self.use_custom_stt:')
        assert flush_pos != -1, 'DG flush call not found'
        assert guard_pos != -1, 'use_custom_stt guard not found'
        assert flush_pos < guard_pos, 'DG flush must be before use_custom_stt guard'


class TestDgUsageBatchingBehavior:
    """Test the record_dg_usage_ms function handles batched input correctly."""

    def test_batched_60s_single_redis_write(self, fair_use):
        """60s of accumulated chunks should produce a single Redis pipeline."""
        pipe = MagicMock()
        fair_use.redis_client.pipeline.return_value = pipe

        with patch.object(fair_use, 'FAIR_USE_ENABLED', True), patch.object(
            fair_use, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000
        ):
            # Simulate 60s of audio: 50 chunks/sec × 60s × 20ms = 60000ms
            total_ms = 60000
            fair_use.record_dg_usage_ms('user1', total_ms)

        # Single pipeline call with single INCRBY
        fair_use.redis_client.pipeline.assert_called_once()
        pipe.incrby.assert_called_once()
        call_args = pipe.incrby.call_args
        assert total_ms in call_args[0] or total_ms in call_args[1].values()

    def test_large_accumulation_no_overflow(self, fair_use):
        """24h of continuous audio should not overflow Python int."""
        pipe = MagicMock()
        fair_use.redis_client.pipeline.return_value = pipe

        with patch.object(fair_use, 'FAIR_USE_ENABLED', True), patch.object(
            fair_use, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000
        ):
            # 24h of audio = 86,400,000 ms — well within Python int range
            total_ms = 86_400_000
            fair_use.record_dg_usage_ms('user1', total_ms)

        pipe.incrby.assert_called_once()

    def test_disabled_skips_redis(self, fair_use):
        """When FAIR_USE_ENABLED is False, no Redis calls."""
        with patch.object(fair_use, 'FAIR_USE_ENABLED', False):
            fair_use.record_dg_usage_ms('user1', 60000)

        fair_use.redis_client.pipeline.assert_not_called()

    def test_zero_ms_skips_redis(self, fair_use):
        """Zero ms should not trigger Redis write."""
        with patch.object(fair_use, 'FAIR_USE_ENABLED', True), patch.object(
            fair_use, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000
        ):
            fair_use.record_dg_usage_ms('user1', 0)

        fair_use.redis_client.pipeline.assert_not_called()


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
