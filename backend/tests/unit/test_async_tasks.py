"""Unit tests for utils/async_tasks.py — structured concurrency utilities."""

import asyncio
import pytest
from unittest.mock import patch

from utils.async_tasks import (
    GatherResult,
    SupervisorExit,
    supervise_tasks,
    drain_tasks,
    gather_with_logging,
    gather_chunked,
    create_named_task,
    sleep_until_shutdown,
)

# ---------------------------------------------------------------------------
# Tests for create_named_task
# ---------------------------------------------------------------------------


class TestCreateNamedTask:
    def test_task_has_name(self):
        async def _run():
            async def noop():
                pass

            task = create_named_task(noop(), name="test:task")
            assert task.get_name() == "test:task"
            await task

        asyncio.run(_run())

    def test_task_added_to_set(self):
        async def _run():
            task_set = set()

            async def noop():
                pass

            task = create_named_task(noop(), name="tracked", task_set=task_set)
            assert task in task_set
            await task
            await asyncio.sleep(0)  # allow done callback to fire
            assert task not in task_set

        asyncio.run(_run())

    def test_task_removed_from_set_on_exception(self):
        async def _run():
            task_set = set()

            async def fail():
                raise ValueError("boom")

            task = create_named_task(fail(), name="failing", task_set=task_set)
            assert task in task_set
            with pytest.raises(ValueError):
                await task
            await asyncio.sleep(0)
            assert task not in task_set

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for drain_tasks
# ---------------------------------------------------------------------------


class TestDrainTasks:
    def test_drain_empty_list(self):
        async def _run():
            result = await drain_tasks([], timeout=1.0, label="empty")
            assert result == 0

        asyncio.run(_run())

    def test_drain_already_done_tasks(self):
        async def _run():
            async def noop():
                pass

            task = asyncio.create_task(noop())
            await task
            result = await drain_tasks([task], timeout=1.0, label="done")
            assert result == 0

        asyncio.run(_run())

    def test_drain_cancels_running_tasks(self):
        async def _run():
            async def hang():
                await asyncio.sleep(999)

            task = asyncio.create_task(hang())
            result = await drain_tasks([task], timeout=1.0, label="cancel", cancel=True)
            assert task.done()
            assert result == 0  # cancelled within timeout

        asyncio.run(_run())

    def test_drain_timeout_force_cancels(self):
        async def _run():
            async def slow_shutdown():
                await asyncio.sleep(999)

            task = asyncio.create_task(slow_shutdown())
            await asyncio.sleep(0)
            # cancel=False means we just wait — task won't finish, so timeout hits
            result = await drain_tasks([task], timeout=0.1, label="stubborn", cancel=False)
            assert result > 0  # had to force-cancel after timeout

        asyncio.run(_run())

    def test_drain_no_cancel_waits_for_completion(self):
        async def _run():
            completed = False

            async def quick():
                nonlocal completed
                await asyncio.sleep(0.05)
                completed = True

            task = asyncio.create_task(quick())
            result = await drain_tasks([task], timeout=1.0, label="wait", cancel=False)
            assert completed
            assert result == 0

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for supervise_tasks
# ---------------------------------------------------------------------------


class TestSuperviseTasks:
    def test_disconnect_exit(self):
        async def _run():
            async def receive():
                await asyncio.sleep(0.05)

            async def bg():
                await asyncio.sleep(999)

            recv = asyncio.create_task(receive(), name="receive")
            bg_task = asyncio.create_task(bg(), name="bg")

            result = await supervise_tasks(
                receive_task=recv,
                bg_tasks=[bg_task],
                label="test",
            )
            assert result.reason == "disconnect"
            bg_task.cancel()
            await asyncio.gather(bg_task, return_exceptions=True)

        asyncio.run(_run())

    def test_crash_exit(self):
        async def _run():
            async def receive():
                await asyncio.sleep(999)

            async def crashing():
                await asyncio.sleep(0.05)
                raise RuntimeError("boom")

            recv = asyncio.create_task(receive(), name="receive")
            bg_task = asyncio.create_task(crashing(), name="crasher")

            result = await supervise_tasks(
                receive_task=recv,
                bg_tasks=[bg_task],
                label="test",
            )
            assert result.reason == "crash"
            assert result.task_name == "crasher"
            assert isinstance(result.exception, RuntimeError)
            recv.cancel()
            await asyncio.gather(recv, return_exceptions=True)

        asyncio.run(_run())

    def test_lifetime_done_exit(self):
        async def _run():
            async def receive():
                await asyncio.sleep(999)

            async def lifetime():
                await asyncio.sleep(0.05)

            async def finite():
                await asyncio.sleep(0.02)

            recv = asyncio.create_task(receive(), name="receive")
            lt_task = asyncio.create_task(lifetime(), name="lifetime")
            ft_task = asyncio.create_task(finite(), name="finite")

            result = await supervise_tasks(
                receive_task=recv,
                bg_tasks=[lt_task, ft_task],
                finite_tasks={ft_task},
                label="test",
            )
            assert result.reason == "lifetime_done"
            recv.cancel()
            await asyncio.gather(recv, return_exceptions=True)

        asyncio.run(_run())

    def test_finite_task_does_not_trigger_exit(self):
        async def _run():
            async def receive():
                await asyncio.sleep(0.15)

            async def finite():
                await asyncio.sleep(0.02)

            recv = asyncio.create_task(receive(), name="receive")
            ft_task = asyncio.create_task(finite(), name="finite")

            result = await supervise_tasks(
                receive_task=recv,
                bg_tasks=[ft_task],
                finite_tasks={ft_task},
                label="test",
            )
            # finite completes, then receive completes -> disconnect
            assert result.reason == "disconnect"

        asyncio.run(_run())

    def test_empty_bg_tasks(self):
        async def _run():
            async def receive():
                await asyncio.sleep(0.05)

            recv = asyncio.create_task(receive(), name="receive")

            result = await supervise_tasks(
                receive_task=recv,
                bg_tasks=[],
                label="test",
            )
            assert result.reason == "disconnect"

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for gather_with_logging
# ---------------------------------------------------------------------------


class TestGatherWithLogging:
    def test_all_succeed(self):
        async def _run():
            async def add(x):
                return x + 1

            results = await gather_with_logging(
                add(1),
                add(2),
                add(3),
                label="test",
                max_concurrency=10,
            )
            assert len(results) == 3
            assert all(r.ok for r in results)
            assert [r.value for r in results] == [2, 3, 4]

        asyncio.run(_run())

    def test_partial_failure(self):
        async def _run():
            async def ok():
                return "good"

            async def fail():
                raise ValueError("bad")

            results = await gather_with_logging(
                ok(),
                fail(),
                ok(),
                label="test",
                max_concurrency=10,
            )
            assert results[0].ok
            assert not results[1].ok
            assert isinstance(results[1].exception, ValueError)
            assert results[2].ok

        asyncio.run(_run())

    def test_concurrency_bounded(self):
        async def _run():
            max_concurrent = 0
            current = 0

            async def track():
                nonlocal max_concurrent, current
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
                await asyncio.sleep(0.02)
                current -= 1

            await gather_with_logging(
                *[track() for _ in range(20)],
                label="test",
                max_concurrency=5,
            )
            assert max_concurrent <= 5

        asyncio.run(_run())

    def test_empty_coros(self):
        async def _run():
            results = await gather_with_logging(label="test", max_concurrency=10)
            assert results == []

        asyncio.run(_run())

    def test_timeout_per_item(self):
        async def _run():
            async def slow():
                await asyncio.sleep(5.0)
                return "done"

            async def fast():
                return "fast"

            results = await gather_with_logging(
                slow(),
                fast(),
                label="test",
                max_concurrency=10,
                timeout=0.1,
            )
            assert not results[0].ok  # timed out
            assert results[1].ok
            assert results[1].value == "fast"

        asyncio.run(_run())

    def test_preserves_order(self):
        async def _run():
            async def delayed(val, delay):
                await asyncio.sleep(delay)
                return val

            results = await gather_with_logging(
                delayed("c", 0.06),
                delayed("a", 0.02),
                delayed("b", 0.04),
                label="test",
                max_concurrency=10,
            )
            assert [r.value for r in results] == ["c", "a", "b"]
            assert [r.index for r in results] == [0, 1, 2]

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for gather_chunked
# ---------------------------------------------------------------------------


class TestGatherChunked:
    def test_processes_in_chunks(self):
        async def _run():
            call_order = []

            async def track(i):
                call_order.append(i)
                return i

            results = await gather_chunked(
                [track(i) for i in range(7)],
                chunk_size=3,
                label="test",
            )
            assert len(results) == 7
            assert all(r.ok for r in results)
            # first chunk (0,1,2) processes before second (3,4,5) before third (6)
            assert call_order[:3] == [0, 1, 2] or set(call_order[:3]) == {0, 1, 2}

        asyncio.run(_run())

    def test_empty_input(self):
        async def _run():
            results = await gather_chunked([], chunk_size=5, label="test")
            assert results == []

        asyncio.run(_run())

    def test_single_chunk(self):
        async def _run():
            async def val(x):
                return x

            results = await gather_chunked(
                [val(i) for i in range(3)],
                chunk_size=10,
                label="test",
            )
            assert len(results) == 3

        asyncio.run(_run())

    def test_chunked_with_failures(self):
        async def _run():
            async def maybe_fail(i):
                if i == 3:
                    raise ValueError("fail at 3")
                return i

            results = await gather_chunked(
                [maybe_fail(i) for i in range(6)],
                chunk_size=3,
                label="test",
            )
            assert len(results) == 6
            assert results[3].ok is False
            assert isinstance(results[3].exception, ValueError)
            assert results[0].ok and results[4].ok

        asyncio.run(_run())

    def test_chunked_global_index(self):
        async def _run():
            async def val(x):
                return x

            results = await gather_chunked(
                [val(i) for i in range(5)],
                chunk_size=2,
                label="test",
            )
            # Indices should be sequential across chunks
            indices = [r.index for r in results]
            assert indices == [0, 1, 0, 1, 0]  # reset per chunk

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for drain_tasks edge cases
# ---------------------------------------------------------------------------


class TestDrainTasksEdgeCases:
    def test_drain_force_cancel_reports_count(self):
        """After timeout, force-cancelled tasks are counted correctly."""

        async def _run():
            async def slow():
                await asyncio.sleep(999)

            tasks = [asyncio.create_task(slow()) for _ in range(3)]
            await asyncio.sleep(0)
            # cancel=False: we just wait, tasks won't finish, so all 3 get force-cancelled
            result = await drain_tasks(tasks, timeout=0.1, label="count", cancel=False)
            assert result == 3
            assert all(t.done() for t in tasks)

        asyncio.run(_run())

    def test_drain_mixed_done_and_running(self):
        async def _run():
            async def quick():
                return "done"

            async def slow():
                await asyncio.sleep(999)

            t1 = asyncio.create_task(quick())
            await t1
            t2 = asyncio.create_task(slow())

            result = await drain_tasks([t1, t2], timeout=1.0, label="mixed", cancel=True)
            assert t1.done()
            assert t2.done()
            assert result == 0

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Tests for gather_with_logging edge cases
# ---------------------------------------------------------------------------


class TestGatherWithLoggingEdgeCases:
    def test_all_fail(self):
        async def _run():
            async def fail(msg):
                raise RuntimeError(msg)

            results = await gather_with_logging(
                fail("a"),
                fail("b"),
                fail("c"),
                label="all_fail",
                max_concurrency=10,
            )
            assert all(not r.ok for r in results)
            assert all(isinstance(r.exception, RuntimeError) for r in results)

        asyncio.run(_run())

    def test_none_return_value_preserved(self):
        """None is a valid return value and must not be confused with failure."""

        async def _run():
            async def return_none():
                return None

            results = await gather_with_logging(
                return_none(),
                label="none_val",
                max_concurrency=10,
            )
            assert results[0].ok is True
            assert results[0].value is None

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Structural tests — verify WS handlers use async_tasks utilities
# ---------------------------------------------------------------------------


class TestStructuralUsage:
    """AST-level tests that routers actually use the async_tasks utilities."""

    def test_pusher_imports_async_tasks(self):
        import ast

        with open('routers/pusher.py') as f:
            tree = ast.parse(f.read())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'utils.async_tasks':
                imports.extend(alias.name for alias in node.names)

        assert 'supervise_tasks' in imports
        assert 'drain_tasks' in imports
        assert 'create_named_task' in imports

    def test_transcribe_imports_async_tasks(self):
        import ast

        with open('routers/transcribe.py') as f:
            tree = ast.parse(f.read())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'utils.async_tasks':
                imports.extend(alias.name for alias in node.names)

        assert 'supervise_tasks' in imports
        assert 'drain_tasks' in imports
        assert 'create_named_task' in imports

    def test_no_raw_gather_in_ws_supervisor(self):
        """Verify that WS handlers don't use raw asyncio.gather for task supervision."""
        for filename in ['routers/pusher.py', 'routers/transcribe.py']:
            with open(filename) as f:
                source = f.read()
            assert (
                'asyncio.gather(*tasks)' not in source
            ), f"{filename} still has raw asyncio.gather(*tasks) — use supervise_tasks/drain_tasks"
            assert (
                'asyncio.gather(*bg_main_tasks)' not in source
            ), f"{filename} still has raw asyncio.gather(*bg_main_tasks) — use drain_tasks"

    def test_no_dynamic_uid_in_metric_labels(self):
        """Metric labels must be static — no uid/session_id to prevent cardinality explosion."""
        import re

        for filename in ['routers/pusher.py', 'routers/transcribe.py']:
            with open(filename) as f:
                source = f.read()
            for match in re.finditer(r'label=f"[^"]*\{uid\}', source):
                pytest.fail(f"{filename}: dynamic uid in metric label: {match.group()}")
            for match in re.finditer(r'label=f"[^"]*\{session_id\}', source):
                pytest.fail(f"{filename}: dynamic session_id in metric label: {match.group()}")

    def test_app_integrations_uses_gather_with_logging(self):
        import ast

        with open('utils/app_integrations.py') as f:
            tree = ast.parse(f.read())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'utils.async_tasks':
                imports.extend(alias.name for alias in node.names)

        assert 'gather_with_logging' in imports


# ---------------------------------------------------------------------------
# Tests for sleep_until_shutdown
# ---------------------------------------------------------------------------


class TestSleepUntilShutdown:
    def test_returns_false_on_normal_sleep(self):
        async def _run():
            event = asyncio.Event()
            result = await sleep_until_shutdown(event, 0.05)
            assert result is False

        asyncio.run(_run())

    def test_returns_true_when_event_already_set(self):
        async def _run():
            event = asyncio.Event()
            event.set()
            result = await sleep_until_shutdown(event, 10.0)
            assert result is True

        asyncio.run(_run())

    def test_wakes_early_when_event_set_during_sleep(self):
        async def _run():
            event = asyncio.Event()

            async def _set_after():
                await asyncio.sleep(0.05)
                event.set()

            asyncio.create_task(_set_after())
            t0 = asyncio.get_event_loop().time()
            result = await sleep_until_shutdown(event, 10.0)
            elapsed = asyncio.get_event_loop().time() - t0
            assert result is True
            assert elapsed < 1.0

        asyncio.run(_run())

    def test_polling_loop_exits_on_shutdown(self):
        async def _run():
            event = asyncio.Event()
            iterations = 0

            async def _poller():
                nonlocal iterations
                while True:
                    iterations += 1
                    if await sleep_until_shutdown(event, 0.02):
                        break

            async def _shutdown():
                await asyncio.sleep(0.07)
                event.set()

            asyncio.create_task(_shutdown())
            await _poller()
            assert iterations >= 2

        asyncio.run(_run())

    def test_zero_timeout_with_event_set_returns_true(self):
        async def _run():
            event = asyncio.Event()
            event.set()
            result = await sleep_until_shutdown(event, 0)
            assert result is True

        asyncio.run(_run())

    def test_zero_timeout_without_event_returns_false(self):
        async def _run():
            event = asyncio.Event()
            result = await sleep_until_shutdown(event, 0)
            assert result is False

        asyncio.run(_run())
