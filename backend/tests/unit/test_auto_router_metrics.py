"""Tests for the metrics collector + pick history ring buffer."""

import threading
from datetime import datetime

import pytest

from utils.auto_router.metrics import (
    MAX_PICK_HISTORY,
    MetricsCollector,
    PickHistory,
    PickRecord,
)

# ---------------------------------------------------------------------------
# PickHistory ring buffer
# ---------------------------------------------------------------------------


class TestPickHistoryBasics:
    """Ring buffer basics: append, snapshot, len, clear."""

    def test_empty_history_has_len_zero(self):
        h = PickHistory()
        assert len(h) == 0
        assert h.snapshot() == []

    def test_record_appends_and_snapshot_returns_in_order(self):
        h = PickHistory()
        h.record(PickRecord("2026-06-25T10:00:00Z", "ptt_response", "model-a", 0.8, {"quality": 0.4}))
        h.record(PickRecord("2026-06-25T10:01:00Z", "ptt_response", "model-b", 0.7, {"quality": 0.4}))
        snap = h.snapshot()
        assert len(snap) == 2
        assert snap[0].model == "model-a"
        assert snap[1].model == "model-b"

    def test_max_size_must_be_positive(self):
        with pytest.raises(ValueError, match="max_size must be > 0"):
            PickHistory(max_size=0)
        with pytest.raises(ValueError, match="max_size must be > 0"):
            PickHistory(max_size=-1)

    def test_clear_drops_all_records(self):
        h = PickHistory()
        h.record(PickRecord("2026-06-25T10:00:00Z", "t", "m", 0.5, {}))
        h.clear()
        assert len(h) == 0
        assert h.snapshot() == []


class TestPickHistoryEviction:
    """FIFO eviction when capacity is reached."""

    def test_eviction_at_max_size(self):
        h = PickHistory(max_size=3)
        for i in range(5):
            h.record(PickRecord(f"2026-06-25T10:0{i}:00Z", "t", f"model-{i}", 0.5, {}))
        snap = h.snapshot()
        # Only the last 3 should remain (oldest 2 dropped).
        assert len(snap) == 3
        assert [r.model for r in snap] == ["model-2", "model-3", "model-4"]

    def test_default_max_size_is_100(self):
        h = PickHistory()
        # Append MAX_PICK_HISTORY + 5 records.
        for i in range(MAX_PICK_HISTORY + 5):
            h.record(PickRecord(f"2026-06-25T10:00:{i:02d}Z", "t", f"m{i}", 0.5, {}))
        # Should be capped at MAX_PICK_HISTORY.
        assert len(h) == MAX_PICK_HISTORY


class TestPickHistoryThreadSafety:
    """Concurrent record() calls don't corrupt the buffer."""

    def test_concurrent_records_no_loss_at_small_count(self):
        # 10 threads each record 10 records = 100 total. Below the max.
        h = PickHistory(max_size=200)

        def worker(thread_id: int):
            for i in range(10):
                h.record(
                    PickRecord(
                        f"2026-06-25T10:0{thread_id}:{i:02d}Z",
                        "t",
                        f"m{thread_id}-{i}",
                        0.5,
                        {},
                    )
                )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        barrier = threading.Barrier(10)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All 100 records should be present (no loss, no corruption).
        assert len(h) == 100
        models = {r.model for r in h.snapshot()}
        expected = {f"m{t}-{i}" for t in range(10) for i in range(10)}
        assert models == expected

    def test_concurrent_records_at_capacity_does_not_crash(self):
        # 20 threads each record 20 records = 400. Above the max (100).
        h = PickHistory(max_size=100)

        def worker():
            for i in range(20):
                h.record(PickRecord("2026-06-25T10:00:00Z", "t", "m", 0.5, {}))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Capped at 100, no crash.
        assert len(h) == 100


# ---------------------------------------------------------------------------
# PickRecord
# ---------------------------------------------------------------------------


class TestPickRecord:
    """PickRecord is frozen and serializes cleanly."""

    def test_to_dict(self):
        rec = PickRecord(
            "2026-06-25T10:00:00Z",
            "ptt_response",
            "claude-sonnet-4-6",
            0.82,
            {"quality": 0.4, "latency": 0.5, "cost": 0.1},
        )
        d = rec.to_dict()
        assert d == {
            "timestamp": "2026-06-25T10:00:00Z",
            "task": "ptt_response",
            "model": "claude-sonnet-4-6",
            "score": 0.82,
            "weights_used": {"quality": 0.4, "latency": 0.5, "cost": 0.1},
        }

    def test_frozen(self):
        rec = PickRecord("t", "task", "model", 0.5, {})
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            rec.model = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    """MetricsCollector wraps PickHistory + provides current_state()."""

    def test_record_pick_stores_in_history(self):
        h = PickHistory()
        c = MetricsCollector(history=h)
        c.record_pick("ptt_response", "model-a", 0.8, {"quality": 0.4})
        c.record_pick("ptt_response", "model-b", 0.7, {"quality": 0.4})
        assert len(c._history) == 2  # noqa: SLF001

    def test_pick_history_snapshot_returns_dicts(self):
        h = PickHistory()
        c = MetricsCollector(history=h)
        c.record_pick("ptt_response", "model-a", 0.8, {"quality": 0.4})
        snap = c.pick_history_snapshot()
        assert len(snap) == 1
        assert snap[0]["model"] == "model-a"
        assert snap[0]["task"] == "ptt_response"
        assert snap[0]["score"] == 0.8

    def test_current_state_includes_cache_and_tasks(self):
        from utils.auto_router.daily_refresh import DailyRefreshCache
        from utils.auto_router.model_registry import ModelRegistry
        from utils.auto_router.task_registry import TaskRegistry

        cache: DailyRefreshCache = DailyRefreshCache(ttl_seconds=60)
        # Pre-populate the cache with the defaults.
        tasks = TaskRegistry.defaults()
        models = ModelRegistry.empty()  # no models → no winners

        async def loader():
            return tasks, models

        import asyncio

        asyncio.run(cache.get_or_refresh(loader))

        c = MetricsCollector()
        state = c.current_state(tasks, models, cache)
        assert "cache" in state
        assert "tasks" in state
        assert "last_loaded_at" in state["cache"]
        assert "age_seconds" in state["cache"]
        assert "is_fresh" in state["cache"]
        # All 5 task types should appear (even with no models).
        assert set(state["tasks"].keys()) == {
            "ptt_response",
            "screenshot_understanding",
            "screenshot_embedding",
            "general_assistant",
            "transcription",
        }
        # With no models, every task should have candidate_count=0 and current_pick=None.
        for task_name, task_state in state["tasks"].items():
            assert task_state["candidate_count"] == 0
            assert task_state["current_pick"] is None
            assert task_state["current_score"] is None
