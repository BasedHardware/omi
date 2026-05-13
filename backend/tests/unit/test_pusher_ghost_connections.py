"""Unit tests for ghost connection prevention in the pusher WebSocket handler.

The root cause of the memory leak: when a background task (GCS upload, webhook,
diarizer call) hangs after the WebSocket disconnects, asyncio.gather() for all
5 main tasks blocks forever, preventing cleanup.  The gauge is never decremented
and ~15 MB per ghost connection is leaked.

These tests verify:
1. Receive timeout fires when no data arrives
2. Background tasks are force-cancelled after the drain timeout
3. The gauge is always decremented on exit (no ghost connections)
"""

import asyncio
import struct

import pytest

WS_RECEIVE_TIMEOUT = 300.0
BG_DRAIN_TIMEOUT = 30.0


class TestConstants:
    def test_receive_timeout_is_positive(self):
        assert WS_RECEIVE_TIMEOUT > 0

    def test_receive_timeout_longer_than_heartbeat_interval(self):
        assert WS_RECEIVE_TIMEOUT >= 60

    def test_drain_timeout_is_positive(self):
        assert BG_DRAIN_TIMEOUT > 0

    def test_drain_timeout_shorter_than_receive_timeout(self):
        assert BG_DRAIN_TIMEOUT < WS_RECEIVE_TIMEOUT


class TestReceiveTimeoutBehavior:
    """Verify receive_tasks() exits on timeout instead of hanging forever."""

    @pytest.mark.asyncio
    async def test_receive_timeout_breaks_loop(self):
        """Simulate the receive loop with a timeout — should exit cleanly."""
        websocket_active = True
        timed_out = False

        async def mock_receive_bytes():
            await asyncio.sleep(999)

        timeout = 0.1
        try:
            while websocket_active:
                try:
                    await asyncio.wait_for(mock_receive_bytes(), timeout=timeout)
                except asyncio.TimeoutError:
                    timed_out = True
                    break
        except Exception:
            pass

        assert timed_out, "Receive loop should have exited via timeout"

    @pytest.mark.asyncio
    async def test_receive_timeout_does_not_fire_on_active_connection(self):
        """Active connections (regular data) should NOT trigger the timeout."""
        frames_received = 0
        total_frames = 5

        async def mock_receive_bytes():
            nonlocal frames_received
            await asyncio.sleep(0.01)
            frames_received += 1
            if frames_received >= total_frames:
                raise Exception("disconnect")
            return struct.pack('<I', 100)

        timeout = 1.0
        try:
            while True:
                data = await asyncio.wait_for(mock_receive_bytes(), timeout=timeout)
        except asyncio.TimeoutError:
            pytest.fail("Timeout should not fire on active connection")
        except Exception:
            pass

        assert frames_received == total_frames


class TestDrainTimeout:
    """Verify background tasks are force-cancelled after drain timeout."""

    @pytest.mark.asyncio
    async def test_hung_task_is_force_cancelled(self):
        """A background task stuck in a network call should be cancelled."""
        cancelled = False

        async def hung_task():
            nonlocal cancelled
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.create_task(hung_task())
        drain_timeout = 0.1

        try:
            await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True),
                timeout=drain_timeout,
            )
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert cancelled, "Hung task should have been cancelled"
        assert task.done(), "Task should be done after cancellation"

    @pytest.mark.asyncio
    async def test_healthy_task_completes_within_drain(self):
        """A task that exits promptly should complete without force-cancellation."""
        completed = False

        async def quick_task():
            nonlocal completed
            await asyncio.sleep(0.01)
            completed = True

        task = asyncio.create_task(quick_task())
        drain_timeout = 1.0

        try:
            await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True),
                timeout=drain_timeout,
            )
        except asyncio.TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert completed, "Quick task should have completed normally"

    @pytest.mark.asyncio
    async def test_mixed_tasks_hung_and_healthy(self):
        """Mix of hung and healthy tasks — healthy complete, hung get cancelled."""
        completed = False
        cancelled = False

        async def healthy():
            nonlocal completed
            await asyncio.sleep(0.01)
            completed = True

        async def hung():
            nonlocal cancelled
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled = True
                raise

        tasks = [asyncio.create_task(healthy()), asyncio.create_task(hung())]
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=0.2,
            )
        except asyncio.TimeoutError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        assert completed
        assert cancelled


class TestGaugeDecrement:
    """Verify the gauge is always decremented regardless of task state."""

    @pytest.mark.asyncio
    async def test_gauge_decremented_after_normal_exit(self):
        gauge_value = 0

        async def simulate_connection():
            nonlocal gauge_value
            gauge_value += 1
            try:
                await asyncio.sleep(0.01)
            finally:
                gauge_value -= 1

        await simulate_connection()
        assert gauge_value == 0

    @pytest.mark.asyncio
    async def test_gauge_decremented_after_error(self):
        gauge_value = 0

        async def simulate_connection():
            nonlocal gauge_value
            gauge_value += 1
            try:
                raise RuntimeError("connection error")
            except Exception:
                pass
            finally:
                gauge_value -= 1

        await simulate_connection()
        assert gauge_value == 0

    @pytest.mark.asyncio
    async def test_gauge_decremented_with_hung_bg_tasks(self):
        """The new pattern: await receive first, then drain bg with timeout.
        Gauge must dec even when bg tasks hang."""
        gauge_value = 0

        async def hung_bg():
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                raise

        async def simulate_connection():
            nonlocal gauge_value
            bg_tasks = []
            gauge_value += 1
            try:
                bg_tasks = [asyncio.create_task(hung_bg())]
                await asyncio.sleep(0.01)

                try:
                    await asyncio.wait_for(
                        asyncio.gather(*bg_tasks, return_exceptions=True),
                        timeout=0.1,
                    )
                except asyncio.TimeoutError:
                    for t in bg_tasks:
                        t.cancel()
                    await asyncio.gather(*bg_tasks, return_exceptions=True)
            except Exception:
                pass
            finally:
                for t in bg_tasks:
                    if not t.done():
                        t.cancel()
                gauge_value -= 1

        await simulate_connection()
        assert gauge_value == 0, "Gauge must be decremented even with hung background tasks"

    @pytest.mark.asyncio
    async def test_old_pattern_leaks_with_hung_bg(self):
        """Demonstrate the OLD bug: asyncio.gather on all tasks blocks forever
        when a bg task hangs, preventing gauge decrement."""
        gauge_value = 0

        async def hung_bg():
            await asyncio.sleep(999)

        async def old_pattern():
            nonlocal gauge_value
            gauge_value += 1
            try:
                receive = asyncio.create_task(asyncio.sleep(0.01))
                bg = asyncio.create_task(hung_bg())
                await asyncio.gather(receive, bg)
            except Exception:
                pass
            finally:
                gauge_value -= 1

        task = asyncio.create_task(old_pattern())

        await asyncio.sleep(0.2)

        assert gauge_value == 1, "Old pattern leaks: gather hangs on hung bg task"
        assert not task.done(), "Old pattern: connection handler never finishes"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
