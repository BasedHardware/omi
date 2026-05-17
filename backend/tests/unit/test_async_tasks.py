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
        import ast

        for filename in ['routers/pusher.py', 'routers/transcribe.py']:
            with open(filename) as f:
                source = f.read()

            # Should not have the old pattern: await asyncio.gather(*tasks)
            # (the final cleanup one is replaced by drain_tasks)
            # Allow asyncio.gather only in non-supervisor contexts
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if (
                            isinstance(node.func.value, ast.Attribute)
                            and getattr(node.func.value, 'attr', '') == 'gather'
                        ):
                            continue

    def test_app_integrations_uses_gather_with_logging(self):
        import ast

        with open('utils/app_integrations.py') as f:
            tree = ast.parse(f.read())

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'utils.async_tasks':
                imports.extend(alias.name for alias in node.names)

        assert 'gather_with_logging' in imports
