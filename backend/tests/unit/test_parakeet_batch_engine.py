import asyncio
import os
import sys
import tempfile
import time
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")

_torch = MagicMock()
_torch.cuda.is_available.return_value = False
_torch.inference_mode = lambda: (lambda fn: fn)
sys.modules.setdefault("torch", _torch)
sys.modules.setdefault("nemo", MagicMock())
sys.modules.setdefault("nemo.collections", MagicMock())
sys.modules.setdefault("nemo.collections.asr", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../parakeet"))

from batch_engine import BatchEngine, QueueFullError, _unlink_safe
from gpu_worker import GPUWorker


def _make_mock_gpu_worker(results_fn=None):
    worker = MagicMock(spec=GPUWorker)
    worker.is_ready = True

    def submit(payload, loop):
        fut = loop.create_future()
        if results_fn:
            res = results_fn(payload)
        else:
            res = [{"text": f"ok:{p}", "timestamp": {}} for p in payload["audio_paths"]]
        loop.call_soon(fut.set_result, res)
        return fut

    worker.submit.side_effect = submit
    return worker


class TestBatchEngineSubmit:

    @pytest.fixture
    def loop(self):
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_single_submit_returns_result(self, loop):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.01)

        async def run():
            await engine.start()
            try:
                result = await engine.submit("/tmp/a.wav", timestamps=True, owns_file=False)
                assert result["text"] == "ok:/tmp/a.wav"
            finally:
                await engine.stop()

        loop.run_until_complete(run())

    def test_batch_flush_at_max_size(self, loop):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=3, max_wait_seconds=1.0)

        async def run():
            await engine.start()
            try:
                futs = [asyncio.ensure_future(engine.submit(f"/tmp/{i}.wav", owns_file=False)) for i in range(3)]
                results = await asyncio.wait_for(asyncio.gather(*futs), timeout=5)
                assert len(results) == 3
                for i, r in enumerate(results):
                    assert r["text"] == f"ok:/tmp/{i}.wav"
            finally:
                await engine.stop()

        loop.run_until_complete(run())

    def test_timer_flush_partial_batch(self, loop):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=100, max_wait_seconds=0.01)

        async def run():
            await engine.start()
            try:
                result = await asyncio.wait_for(engine.submit("/tmp/single.wav", owns_file=False), timeout=5)
                assert result["text"] == "ok:/tmp/single.wav"
            finally:
                await engine.stop()

        loop.run_until_complete(run())


class TestBatchEngineQueueFull:

    def test_queue_full_error(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=100, max_wait_seconds=10.0, max_queue_depth=2)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    engine._pending = [MagicMock() for _ in range(2)]
                    with pytest.raises(QueueFullError):
                        await engine.submit("/tmp/overflow.wav", owns_file=False)
                    assert engine._metrics["rejected_requests"] == 1
                finally:
                    engine._pending = []
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineFileCleanup:

    def test_owns_file_cleaned_after_success(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(b"fake audio")
                        path = f.name

                    await asyncio.wait_for(engine.submit(path, timestamps=True, owns_file=True), timeout=5)
                    assert not os.path.exists(path)
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_not_owns_file_preserved(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(b"fake audio")
                        path = f.name

                    await asyncio.wait_for(engine.submit(path, timestamps=True, owns_file=False), timeout=5)
                    assert os.path.exists(path)
                    os.unlink(path)
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_owns_file_cleaned_on_failed_enqueue(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=100, max_wait_seconds=10.0, max_queue_depth=0)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                        f.write(b"fake audio")
                        path = f.name

                    with pytest.raises(QueueFullError):
                        await engine.submit(path, owns_file=True)
                    assert not os.path.exists(path)
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineErrorPropagation:

    def test_gpu_error_propagates_to_all_futures(self):
        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True

        def submit_error(payload, loop):
            fut = loop.create_future()
            loop.call_soon(fut.set_exception, RuntimeError("GPU exploded"))
            return fut

        gpu.submit.side_effect = submit_error
        engine = BatchEngine(gpu, max_batch_size=3, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/{i}.wav", owns_file=False)) for i in range(3)]
                    for fut in asyncio.as_completed(futs):
                        with pytest.raises(Exception):
                            await fut
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_gpu_queue_full_maps_to_queue_full_error(self):
        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True

        def submit_queue_full(payload, loop):
            fut = loop.create_future()
            loop.call_soon(fut.set_exception, RuntimeError("GPU queue full"))
            return fut

        gpu.submit.side_effect = submit_queue_full
        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with pytest.raises(QueueFullError):
                        await asyncio.wait_for(engine.submit("/tmp/x.wav", owns_file=False), timeout=5)
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineResultMismatch:

    def test_fewer_results_than_requests(self):
        def short_results(payload):
            return [{"text": "only-one", "timestamp": {}}]

        gpu = _make_mock_gpu_worker(results_fn=short_results)
        engine = BatchEngine(gpu, max_batch_size=3, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/{i}.wav", owns_file=False)) for i in range(3)]
                    results = await asyncio.wait_for(asyncio.gather(*futs), timeout=5)
                    assert results[0]["text"] == "only-one"
                    assert results[1]["text"] == ""
                    assert results[2]["text"] == ""
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineMetrics:

    def test_metrics_track_requests_and_batches(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    await asyncio.wait_for(engine.submit("/tmp/a.wav", owns_file=False), timeout=5)
                    m = engine.metrics
                    assert m["total_requests"] >= 1
                    assert m["total_batches"] >= 1
                    assert m["total_files"] >= 1
                    assert m["rejected_requests"] == 0
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineShutdown:

    def test_stop_flushes_pending(self):
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=100, max_wait_seconds=100.0)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                fut = asyncio.ensure_future(engine.submit("/tmp/late.wav", owns_file=False))
                await asyncio.sleep(0.01)
                await engine.stop()
                result = await asyncio.wait_for(fut, timeout=5)
                assert result["text"] == "ok:/tmp/late.wav"

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestUnlinkSafe:

    def test_unlink_existing(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        _unlink_safe(path)
        assert not os.path.exists(path)

    def test_unlink_nonexistent(self):
        _unlink_safe("/tmp/does-not-exist-12345.wav")
