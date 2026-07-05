import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

_PARAKEET_DIR = os.path.join(os.path.dirname(__file__), "../../parakeet")
if _PARAKEET_DIR not in sys.path:
    sys.path.insert(0, _PARAKEET_DIR)

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_STREAM_ENGINE_PATH = os.path.join(_PARAKEET_DIR, "stream_engine.py")


@pytest.fixture(scope="module", autouse=True)
def _stream_engine_module():
    _fake_gpu_worker = AutoMockModule("gpu_worker")
    _fake_gpu_worker.GPUWorker = MagicMock
    with stub_modules({"gpu_worker": _fake_gpu_worker}):
        mod = load_module_fresh("stream_engine", _STREAM_ENGINE_PATH)
        globals()["StreamEngine"] = mod.StreamEngine
        globals()["TooManyStreamsError"] = mod.TooManyStreamsError
        globals()["ChunkTooLargeError"] = mod.ChunkTooLargeError
        yield


def _make_mock_gpu_worker():
    worker = MagicMock()

    async def _stream_open(payload, loop):
        return {"stream_id": payload["stream_id"], "status": "opened"}

    async def _stream_chunk(payload, loop):
        return {
            "stream_id": payload["stream_id"],
            "partial_transcript": "hello",
            "final_transcript": "",
            "is_final": False,
        }

    async def _stream_close(payload, loop):
        return {"stream_id": payload["stream_id"], "final_text": "hello world", "status": "closed"}

    worker.stream_open = AsyncMock(side_effect=_stream_open)
    worker.stream_chunk = AsyncMock(side_effect=_stream_chunk)
    worker.stream_close = AsyncMock(side_effect=_stream_close)
    return worker


def _make_pcm_bytes(n_samples=160):
    samples = np.zeros(n_samples, dtype=np.int16)
    return samples.tobytes()


@pytest.fixture
def gpu_worker():
    return _make_mock_gpu_worker()


@pytest.fixture
def engine(gpu_worker):
    return StreamEngine(
        gpu_worker=gpu_worker,
        max_concurrent_streams=4,
        sample_rate=16000,
        idle_timeout=0,
        max_chunk_bytes=1024,
    )


class TestStreamEngineLifecycle:

    @pytest.mark.asyncio
    async def test_open_process_close(self, engine):
        await engine.start()
        try:
            result = await engine.open_stream()
            assert result["status"] == "opened"
            stream_id = result["stream_id"]
            assert engine.active_streams == 1

            chunk_result = await engine.process_chunk(stream_id, _make_pcm_bytes())
            assert chunk_result["stream_id"] == stream_id
            assert "partial_transcript" in chunk_result

            close_result = await engine.close_stream(stream_id)
            assert close_result["status"] == "closed"
            assert engine.active_streams == 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_multiple_streams(self, engine):
        await engine.start()
        try:
            ids = []
            for _ in range(3):
                r = await engine.open_stream()
                ids.append(r["stream_id"])
            assert engine.active_streams == 3

            for sid in ids:
                await engine.close_stream(sid)
            assert engine.active_streams == 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_all_streams(self, engine):
        await engine.start()
        for _ in range(3):
            await engine.open_stream()
        assert engine.active_streams == 3

        await engine.stop()
        assert engine.active_streams == 0


class TestConcurrencyControl:

    @pytest.mark.asyncio
    async def test_too_many_streams_raises(self, engine):
        await engine.start()
        try:
            for _ in range(4):
                await engine.open_stream()
            assert engine.active_streams == 4

            with pytest.raises(TooManyStreamsError):
                await engine.open_stream()
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_semaphore_released_on_close(self, engine):
        await engine.start()
        try:
            ids = []
            for _ in range(4):
                r = await engine.open_stream()
                ids.append(r["stream_id"])

            with pytest.raises(TooManyStreamsError):
                await engine.open_stream()

            await engine.close_stream(ids[0])
            r = await engine.open_stream()
            assert r["status"] == "opened"
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_semaphore_released_on_gpu_open_failure(self, gpu_worker):
        gpu_worker.stream_open = AsyncMock(side_effect=RuntimeError("GPU error"))
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=2, idle_timeout=0)
        await eng.start()
        try:
            with pytest.raises(RuntimeError, match="GPU error"):
                await eng.open_stream()
            assert eng.active_streams == 0

            gpu_worker.stream_open = AsyncMock(
                side_effect=lambda payload, loop: asyncio.coroutine(
                    lambda: {"stream_id": payload["stream_id"], "status": "opened"}
                )()
            )

            async def _stream_open_ok(payload, loop):
                return {"stream_id": payload["stream_id"], "status": "opened"}

            gpu_worker.stream_open = AsyncMock(side_effect=_stream_open_ok)
            r = await eng.open_stream()
            assert r["status"] == "opened"
        finally:
            await eng.stop()

    @pytest.mark.asyncio
    async def test_semaphore_released_on_close_failure(self, gpu_worker):
        gpu_worker.stream_close = AsyncMock(side_effect=RuntimeError("GPU close error"))
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=2, idle_timeout=0)
        await eng.start()
        try:
            r = await eng.open_stream()
            sid = r["stream_id"]
            close_result = await eng.close_stream(sid)
            assert close_result["status"] == "close_failed"
            assert eng.active_streams == 0

            r2 = await eng.open_stream()
            assert r2["status"] == "opened"
        finally:
            await eng.stop()


class TestBoundaryConditions:

    @pytest.mark.asyncio
    async def test_chunk_too_large_raises(self, engine):
        await engine.start()
        try:
            r = await engine.open_stream()
            sid = r["stream_id"]

            big_chunk = b"\x00" * (1025)
            with pytest.raises(ChunkTooLargeError):
                await engine.process_chunk(sid, big_chunk)
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_chunk_at_max_size_succeeds(self, engine):
        await engine.start()
        try:
            r = await engine.open_stream()
            sid = r["stream_id"]

            chunk = _make_pcm_bytes(512)
            assert len(chunk) == 1024
            result = await engine.process_chunk(sid, chunk)
            assert result["stream_id"] == sid
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_process_chunk_unknown_stream_raises(self, engine):
        await engine.start()
        try:
            with pytest.raises(ValueError, match="Unknown stream"):
                await engine.process_chunk("nonexistent-id", _make_pcm_bytes())
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_close_unknown_stream_returns_not_found(self, engine):
        await engine.start()
        try:
            result = await engine.close_stream("nonexistent-id")
            assert result["status"] == "not_found"
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_double_close_returns_not_found(self, engine):
        await engine.start()
        try:
            r = await engine.open_stream()
            sid = r["stream_id"]
            first = await engine.close_stream(sid)
            assert first["status"] == "closed"
            second = await engine.close_stream(sid)
            assert second["status"] == "not_found"
        finally:
            await engine.stop()


class TestMetrics:

    @pytest.mark.asyncio
    async def test_metrics_track_open_close(self, engine):
        await engine.start()
        try:
            m = engine.metrics
            assert m["total_streams_opened"] == 0
            assert m["total_streams_closed"] == 0
            assert m["active_streams"] == 0

            r = await engine.open_stream()
            sid = r["stream_id"]
            m = engine.metrics
            assert m["total_streams_opened"] == 1
            assert m["active_streams"] == 1

            await engine.close_stream(sid)
            m = engine.metrics
            assert m["total_streams_closed"] == 1
            assert m["active_streams"] == 0
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_metrics_track_chunks(self, engine):
        await engine.start()
        try:
            r = await engine.open_stream()
            sid = r["stream_id"]

            await engine.process_chunk(sid, _make_pcm_bytes())
            await engine.process_chunk(sid, _make_pcm_bytes())

            m = engine.metrics
            assert m["total_chunks_processed"] == 2
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_active_streams_property(self, engine):
        await engine.start()
        try:
            assert engine.active_streams == 0
            r1 = await engine.open_stream()
            assert engine.active_streams == 1
            r2 = await engine.open_stream()
            assert engine.active_streams == 2
            await engine.close_stream(r1["stream_id"])
            assert engine.active_streams == 1
            await engine.close_stream(r2["stream_id"])
            assert engine.active_streams == 0
        finally:
            await engine.stop()


class TestAudioProcessing:

    @pytest.mark.asyncio
    async def test_pcm16_conversion(self, gpu_worker):
        captured_payloads = []
        original_chunk = gpu_worker.stream_chunk

        async def _capture_chunk(payload, loop):
            captured_payloads.append(payload)
            return {
                "stream_id": payload["stream_id"],
                "partial_transcript": "",
                "final_transcript": "",
                "is_final": False,
            }

        gpu_worker.stream_chunk = AsyncMock(side_effect=_capture_chunk)

        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=0, max_chunk_bytes=4096)
        await eng.start()
        try:
            r = await eng.open_stream()
            sid = r["stream_id"]

            samples = np.array([0, 16384, -16384, 32767], dtype=np.int16)
            await eng.process_chunk(sid, samples.tobytes())

            assert len(captured_payloads) == 1
            audio_np = captured_payloads[0]["audio_chunk"]
            assert audio_np.dtype == np.float32
            np.testing.assert_allclose(audio_np[0], 0.0, atol=1e-5)
            np.testing.assert_allclose(audio_np[1], 16384.0 / 32768.0, atol=1e-4)
            np.testing.assert_allclose(audio_np[2], -16384.0 / 32768.0, atol=1e-4)
        finally:
            await eng.stop()


class TestStartStop:

    @pytest.mark.asyncio
    async def test_start_sets_loop(self, engine):
        await engine.start()
        assert engine._loop is not None
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_reaper(self, gpu_worker):
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=60)
        await eng.start()
        assert eng._reaper_task is not None
        await eng.stop()
        assert eng._reaper_task.cancelled()

    @pytest.mark.asyncio
    async def test_no_reaper_when_timeout_zero(self, engine):
        await engine.start()
        assert engine._reaper_task is None
        await engine.stop()


class TestIdleReaping:

    @pytest.mark.asyncio
    async def test_idle_stream_is_reaped(self, gpu_worker):
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=0.01)
        await eng.start()
        try:
            r = await eng.open_stream()
            assert eng.active_streams == 1
            await asyncio.sleep(0.05)
            # Cancel the background reaper and run a single-pass reap manually
            eng._reaper_task.cancel()
            try:
                await eng._reaper_task
            except asyncio.CancelledError:
                pass
            # Directly invoke the reaping logic by running the coroutine with
            # asyncio.sleep patched to break after one iteration
            call_count = 0
            original_sleep = asyncio.sleep

            async def _break_after_one(*a, **kw):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise asyncio.CancelledError
                # Don't actually sleep — sessions are already idle

            import unittest.mock

            with unittest.mock.patch('asyncio.sleep', side_effect=_break_after_one):
                try:
                    await eng._reap_idle_streams()
                except asyncio.CancelledError:
                    pass
            assert eng.active_streams == 0
            assert eng.metrics["total_streams_reaped"] >= 1
        finally:
            await eng.stop()

    @pytest.mark.asyncio
    async def test_active_stream_not_reaped(self, gpu_worker):
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=60)
        await eng.start()
        try:
            r = await eng.open_stream()
            assert eng.active_streams == 1
            # Cancel the background reaper and do a single-pass reap
            eng._reaper_task.cancel()
            try:
                await eng._reaper_task
            except asyncio.CancelledError:
                pass

            call_count = 0

            async def _break_after_one(*a, **kw):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise asyncio.CancelledError

            import unittest.mock

            with unittest.mock.patch('asyncio.sleep', side_effect=_break_after_one):
                try:
                    await eng._reap_idle_streams()
                except asyncio.CancelledError:
                    pass
            assert eng.active_streams == 1
            assert eng.metrics["total_streams_reaped"] == 0
        finally:
            await eng.stop()

    @pytest.mark.asyncio
    async def test_reaper_task_is_running(self, gpu_worker):
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=10)
        await eng.start()
        try:
            assert eng._reaper_task is not None
            assert not eng._reaper_task.done()
        finally:
            await eng.stop()
            assert eng._reaper_task.done()


class TestConcurrentStress:

    @pytest.mark.asyncio
    async def test_concurrent_opens_respect_limit(self, gpu_worker):
        max_streams = 8
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=max_streams, idle_timeout=0)
        await eng.start()
        try:
            results = await asyncio.gather(*[eng.open_stream() for _ in range(max_streams)], return_exceptions=True)
            opened = [r for r in results if not isinstance(r, Exception)]
            assert len(opened) == max_streams
            assert eng.active_streams == max_streams

            overflow_results = await asyncio.gather(*[eng.open_stream() for _ in range(4)], return_exceptions=True)
            errors = [r for r in overflow_results if isinstance(r, TooManyStreamsError)]
            assert len(errors) == 4

            for r in opened:
                await eng.close_stream(r["stream_id"])
            assert eng.active_streams == 0

            r = await eng.open_stream()
            assert r["status"] == "opened"
            assert eng.active_streams == 1
        finally:
            await eng.stop()

    @pytest.mark.asyncio
    async def test_concurrent_open_close_cycle(self, gpu_worker):
        eng = StreamEngine(gpu_worker=gpu_worker, max_concurrent_streams=4, idle_timeout=0)
        await eng.start()
        try:
            for cycle in range(5):
                ids = []
                for _ in range(4):
                    r = await eng.open_stream()
                    ids.append(r["stream_id"])
                assert eng.active_streams == 4

                for sid in ids:
                    await eng.close_stream(sid)
                assert eng.active_streams == 0
        finally:
            await eng.stop()
