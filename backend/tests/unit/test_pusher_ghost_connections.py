"""Unit tests for ghost connection prevention in the pusher WebSocket handler.

The root cause of the memory leak: when a background task (GCS upload, webhook,
diarizer call) hangs after the WebSocket disconnects, asyncio.gather() for all
5 main tasks blocks forever, preventing cleanup.  The gauge is never decremented
and ~15 MB per ghost connection is leaked.

These tests verify:
1. Receive timeout fires when no data arrives
2. Background tasks are force-cancelled after the drain timeout
3. The gauge is always decremented on exit (no ghost connections)
4. Speaker samples are processed (not silently dropped) on shutdown
"""

import ast
import asyncio
import struct
from pathlib import Path

import pytest

PUSHER_SRC = Path(__file__).resolve().parents[2] / 'routers' / 'pusher.py'


def _parse_constant(name: str) -> float:
    """Extract a module-level constant from pusher.py without importing it."""
    tree = ast.parse(PUSHER_SRC.read_text())
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise ValueError(f'{name} not found in {PUSHER_SRC}')


WS_RECEIVE_TIMEOUT = _parse_constant('WS_RECEIVE_TIMEOUT')
BG_DRAIN_TIMEOUT = _parse_constant('BG_DRAIN_TIMEOUT')
SPEAKER_SAMPLE_MIN_AGE = _parse_constant('SPEAKER_SAMPLE_MIN_AGE')


class TestConstants:
    def test_receive_timeout_is_positive(self):
        assert WS_RECEIVE_TIMEOUT > 0

    def test_receive_timeout_exact_value(self):
        assert WS_RECEIVE_TIMEOUT == 300.0, f"WS_RECEIVE_TIMEOUT should be 300s, got {WS_RECEIVE_TIMEOUT}"

    def test_receive_timeout_longer_than_heartbeat_interval(self):
        assert WS_RECEIVE_TIMEOUT >= 60

    def test_drain_timeout_is_positive(self):
        assert BG_DRAIN_TIMEOUT > 0

    def test_drain_timeout_exact_value(self):
        assert BG_DRAIN_TIMEOUT == 30.0, f"BG_DRAIN_TIMEOUT should be 30s, got {BG_DRAIN_TIMEOUT}"

    def test_drain_timeout_shorter_than_receive_timeout(self):
        assert BG_DRAIN_TIMEOUT < WS_RECEIVE_TIMEOUT

    def test_speaker_sample_min_age_exists(self):
        assert SPEAKER_SAMPLE_MIN_AGE > 0


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


class TestSpeakerSampleShutdownDrain:
    """Verify speaker samples are processed (not silently dropped) on shutdown."""

    @pytest.mark.asyncio
    async def test_pending_samples_processed_on_shutdown(self):
        """When websocket_active goes False, speaker samples younger than
        SPEAKER_SAMPLE_MIN_AGE should still be processed (age check skipped)."""
        import time
        from collections import deque

        websocket_active = True
        processed_ids = []

        speaker_sample_queue = deque(maxlen=100)
        speaker_sample_queue.append(
            {
                'person_id': 'p1',
                'conversation_id': 'c1',
                'segment_ids': ['s1'],
                'queued_at': time.time(),  # just queued — way under 120s age
            }
        )

        async def process_speaker_sample_queue():
            nonlocal websocket_active
            while websocket_active or len(speaker_sample_queue) > 0:
                await asyncio.sleep(0.01)
                if not speaker_sample_queue:
                    continue

                current_time = time.time()
                is_shutdown = not websocket_active
                ready = []
                pending = []
                for req in list(speaker_sample_queue):
                    if is_shutdown or current_time - req['queued_at'] >= SPEAKER_SAMPLE_MIN_AGE:
                        ready.append(req)
                    else:
                        pending.append(req)
                speaker_sample_queue.clear()
                speaker_sample_queue.extend(pending)
                for req in ready:
                    processed_ids.append(req['person_id'])

            return processed_ids

        task = asyncio.create_task(process_speaker_sample_queue())

        # Simulate disconnect after a brief moment
        await asyncio.sleep(0.05)
        websocket_active = False

        result = await asyncio.wait_for(task, timeout=2.0)

        assert 'p1' in processed_ids, "Speaker sample queued < 120s ago should be processed on shutdown, not dropped"


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
        """Supervisor pattern: asyncio.wait(FIRST_COMPLETED) then drain with timeout.
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
                receive_task = asyncio.create_task(asyncio.sleep(0.01))
                bg_tasks = [asyncio.create_task(hung_bg())]

                done, _ = await asyncio.wait(
                    {receive_task, *bg_tasks},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if not receive_task.done():
                    receive_task.cancel()

                remaining = [t for t in bg_tasks if not t.done()]
                if remaining:
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*remaining, return_exceptions=True),
                            timeout=0.1,
                        )
                    except asyncio.TimeoutError:
                        for t in remaining:
                            if not t.done():
                                t.cancel()
                        await asyncio.gather(*remaining, return_exceptions=True)
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


class TestSupervisorBehavior:
    """Verify the supervisor detects bg task crashes during active sessions."""

    @pytest.mark.asyncio
    async def test_bg_crash_detected_immediately(self):
        """If a bg task crashes during an active session, the supervisor
        exits immediately instead of waiting for client disconnect."""
        crash_detected_at = None
        start_time = None

        async def long_receive():
            await asyncio.sleep(999)

        async def crashing_bg():
            await asyncio.sleep(0.05)
            raise RuntimeError("bg task crashed")

        async def supervisor():
            nonlocal crash_detected_at, start_time
            start_time = asyncio.get_event_loop().time()
            receive_task = asyncio.create_task(long_receive())
            bg_tasks = [asyncio.create_task(crashing_bg())]

            done, _ = await asyncio.wait(
                {receive_task, *bg_tasks},
                return_when=asyncio.FIRST_COMPLETED,
            )

            crash_detected_at = asyncio.get_event_loop().time()

            for task in done:
                if task is not receive_task and not task.cancelled():
                    exc = task.exception()
                    if exc is not None:
                        pass  # logged in production

            if not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass

        await asyncio.wait_for(supervisor(), timeout=2.0)

        elapsed = crash_detected_at - start_time
        assert elapsed < 0.5, f"Supervisor should detect bg crash in <0.5s, took {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_normal_disconnect_still_works(self):
        """Normal client disconnect (receive ends) still triggers clean drain."""
        drained = False

        async def short_receive():
            await asyncio.sleep(0.05)

        async def bg_worker():
            nonlocal drained
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                drained = True
                raise

        receive_task = asyncio.create_task(short_receive())
        bg_tasks = [asyncio.create_task(bg_worker())]

        done, _ = await asyncio.wait(
            {receive_task, *bg_tasks},
            return_when=asyncio.FIRST_COMPLETED,
        )

        assert receive_task in done, "Receive task should complete first on normal disconnect"

        remaining = [t for t in bg_tasks if not t.done()]
        for t in remaining:
            t.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)

        assert drained, "BG worker should be cancelled and cleaned up on normal disconnect"

    @pytest.mark.asyncio
    async def test_task_names_assigned(self):
        """Verify tasks get names for production debugging."""
        src = PUSHER_SRC.read_text()
        assert 'name=f"ws:{' in src, "Tasks must have name= with uid for production debugging"


def _parse_handler_ast():
    """Parse _websocket_util_trigger and return key AST info about the try/finally structure."""
    tree = ast.parse(PUSHER_SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == '_websocket_util_trigger':
            return node
    raise ValueError('_websocket_util_trigger not found in pusher.py')


def _find_try_blocks(func_node):
    """Find all Try nodes (direct and nested) within a function."""
    blocks = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Try):
            blocks.append(node)
    return blocks


def _find_calls_in_body(body):
    """Find all function/attribute call names in a list of AST statements."""
    calls = []
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                calls.append(node.func.id)
    return calls


class TestStructuralIntegrity:
    """Verify the pusher source has the expected patterns."""

    def test_source_has_receive_timeout(self):
        src = PUSHER_SRC.read_text()
        assert 'asyncio.wait_for(websocket.receive_bytes()' in src

    def test_source_has_drain_timeout(self):
        src = PUSHER_SRC.read_text()
        assert 'BG_DRAIN_TIMEOUT' in src

    def test_source_uses_supervisor_wait(self):
        """The supervisor uses asyncio.wait(FIRST_COMPLETED) to detect bg crashes."""
        src = PUSHER_SRC.read_text()
        assert 'asyncio.FIRST_COMPLETED' in src
        assert 'asyncio.wait(' in src

    def test_source_does_not_gather_all_five_tasks(self):
        """The old pattern gathered all 5 tasks — verify it's gone."""
        src = PUSHER_SRC.read_text()
        assert 'receive_task,\n' not in src or 'await asyncio.gather(\n            receive_task,' not in src

    def test_source_has_speaker_shutdown_drain(self):
        """Verify the speaker sample queue skips age check on shutdown."""
        src = PUSHER_SRC.read_text()
        assert 'is_shutdown' in src


class TestProductionFlowStructure:
    """AST-based verification of the actual production code flow in _websocket_util_trigger.

    These tests parse the real pusher.py source and verify structural invariants
    that prevent ghost connections — not reimplementations, but proofs about the
    actual code paths.
    """

    def test_handler_exists(self):
        handler = _parse_handler_ast()
        assert handler.name == '_websocket_util_trigger'

    def test_gauge_inc_in_try_dec_in_finally(self):
        """PUSHER_ACTIVE_WS_CONNECTIONS.inc() must be in try body,
        .dec() must be in finally — this is the core gauge-leak prevention."""
        handler = _parse_handler_ast()
        try_blocks = _find_try_blocks(handler)

        found_inc_in_try = False
        found_dec_in_finally = False

        for tb in try_blocks:
            try_calls = _find_calls_in_body(tb.body)
            finally_calls = _find_calls_in_body(tb.finalbody) if tb.finalbody else []

            if 'inc' in try_calls:
                found_inc_in_try = True
            if 'dec' in finally_calls:
                found_dec_in_finally = True

        assert found_inc_in_try, "PUSHER_ACTIVE_WS_CONNECTIONS.inc() must be in try body"
        assert found_dec_in_finally, "PUSHER_ACTIVE_WS_CONNECTIONS.dec() must be in finally block"

    def test_supervisor_before_bg_drain(self):
        """asyncio.wait(FIRST_COMPLETED) supervisor must appear before BG_DRAIN_TIMEOUT —
        proving we detect disconnect/crash first, then drain."""
        src = PUSHER_SRC.read_text()
        wait_pos = src.find('asyncio.FIRST_COMPLETED')
        drain_pos = src.find('timeout=BG_DRAIN_TIMEOUT')

        assert wait_pos != -1, "'asyncio.FIRST_COMPLETED' not found in source"
        assert drain_pos != -1, "'timeout=BG_DRAIN_TIMEOUT' not found in source"
        assert wait_pos < drain_pos, (
            f"'asyncio.FIRST_COMPLETED' (pos {wait_pos}) must appear before "
            f"'timeout=BG_DRAIN_TIMEOUT' (pos {drain_pos}) — supervisor-then-drain ordering"
        )

    def test_receive_task_not_in_gather_with_bg_tasks(self):
        """receive_task must NOT appear in the same gather() as bg_main_tasks.
        This was the root cause of ghost connections."""
        src = PUSHER_SRC.read_text()
        lines = src.split('\n')

        for i, line in enumerate(lines):
            if 'asyncio.gather(' in line:
                gather_block = '\n'.join(lines[i : i + 6])
                assert not (
                    'receive_task' in gather_block and 'bg_main_tasks' in gather_block
                ), f"receive_task must not be gathered with bg_main_tasks (line {i + 1})"

    def test_force_cancel_in_timeout_except(self):
        """After BG_DRAIN_TIMEOUT fires, tasks must be cancelled — verify
        cancel() appears in the TimeoutError handler that follows BG_DRAIN_TIMEOUT."""
        src = PUSHER_SRC.read_text()

        drain_pos = src.find('timeout=BG_DRAIN_TIMEOUT')
        assert drain_pos != -1, "timeout=BG_DRAIN_TIMEOUT not found"

        after_drain = src[drain_pos:]
        timeout_pos = after_drain.find('except asyncio.TimeoutError:')
        assert timeout_pos != -1, "except asyncio.TimeoutError not found after BG_DRAIN_TIMEOUT"

        after_timeout = after_drain[timeout_pos:]
        lines = after_timeout.split('\n')[1:]

        found_cancel = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('except ') or stripped.startswith('finally:') or stripped.startswith('else:'):
                break
            if '.cancel()' in stripped:
                found_cancel = True
                break

        assert found_cancel, "task.cancel() must follow asyncio.TimeoutError in drain path"

    def test_finally_cancels_remaining_tasks(self):
        """The finally block must cancel any remaining un-done tasks (bg_tasks + bg_main_tasks)."""
        handler = _parse_handler_ast()
        try_blocks = _find_try_blocks(handler)

        found_cancel_in_finally = False
        for tb in try_blocks:
            if tb.finalbody:
                finally_calls = _find_calls_in_body(tb.finalbody)
                if 'cancel' in finally_calls:
                    found_cancel_in_finally = True

        assert found_cancel_in_finally, "finally block must cancel remaining tasks"

    def test_bg_main_tasks_has_four_tasks(self):
        """bg_main_tasks list literal should have exactly 4 tasks (not 5 — receive is separate)."""
        src = PUSHER_SRC.read_text()
        lines = src.split('\n')

        in_bg_list = False
        task_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('bg_main_tasks = [') and stripped != 'bg_main_tasks = []':
                in_bg_list = True
                continue
            if in_bg_list:
                if 'create_task(' in stripped:
                    task_count += 1
                if ']' in stripped:
                    break

        assert task_count == 4, f"bg_main_tasks should have 4 tasks (receive separate), found {task_count}"

    def test_is_shutdown_guards_speaker_sample_age_check(self):
        """In process_speaker_sample_queue, is_shutdown must be checked
        in the same conditional as SPEAKER_SAMPLE_MIN_AGE."""
        src = PUSHER_SRC.read_text()
        lines = src.split('\n')

        for line in lines:
            if 'is_shutdown' in line and 'SPEAKER_SAMPLE_MIN_AGE' in line:
                return
        pytest.fail("is_shutdown must guard the SPEAKER_SAMPLE_MIN_AGE check in process_speaker_sample_queue")

    def test_dropped_counts_logged_on_drain_timeout(self):
        """When drain timeout fires, per-queue drop counts must be logged."""
        src = PUSHER_SRC.read_text()
        assert 'dropped_speaker' in src, "Must log dropped speaker sample count"
        assert 'dropped_transcript' in src, "Must log dropped transcript count"
        assert 'dropped_audio' in src, "Must log dropped audio count"
        assert 'dropped_cloud' in src, "Must log dropped cloud count"
