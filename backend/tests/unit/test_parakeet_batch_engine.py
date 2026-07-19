import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")

from testing.import_isolation import load_module_fresh, stub_modules

_PARAKEET_DIR = Path(__file__).resolve().parents[2] / "parakeet"


def _make_torch_stub():
    _torch = MagicMock()
    _torch.cuda.is_available.return_value = False
    _torch.cuda.memory_allocated.return_value = 0
    _torch_props = MagicMock()
    _torch_props.total_memory = 16 * 1024**3
    _torch.cuda.get_device_properties.return_value = _torch_props
    _torch.cuda.empty_cache = MagicMock()
    _torch.inference_mode = lambda: (lambda fn: fn)
    _torch.compile = lambda m: m
    _torch.backends.cudnn = MagicMock()
    return _torch


@pytest.fixture(scope="module", autouse=True)
def _parakeet_modules():
    """Load batch_engine + gpu_worker fresh against stubbed torch/nemo/pyannote deps.

    gpu_worker performs ``import torch`` at module top level, so the torch fake must
    be active before the module is exec'd. Sanctioned Tier-2 "fake must precede
    import" case (see backend/docs/test_isolation.md).
    """
    _nemo_asr = MagicMock()
    _nemo = MagicMock()
    _nemo.collections.asr = _nemo_asr
    fakes = {
        "torch": _make_torch_stub(),
        "nemo": _nemo,
        "nemo.collections": _nemo.collections,
        "nemo.collections.asr": _nemo_asr,
        "pyannote": MagicMock(),
        "pyannote.audio": MagicMock(),
        "pyannote.audio.core": MagicMock(),
        "pyannote.audio.core.model": MagicMock(),
    }
    sys.path.insert(0, str(_PARAKEET_DIR))
    try:
        with stub_modules(fakes):
            gpu_worker = load_module_fresh("gpu_worker", str(_PARAKEET_DIR / "gpu_worker.py"))
            batch_engine = load_module_fresh("batch_engine", str(_PARAKEET_DIR / "batch_engine.py"))
            _g = globals()
            _g["GPUWorker"] = gpu_worker.GPUWorker
            _g["WorkItem"] = gpu_worker.WorkItem
            _g["WorkType"] = gpu_worker.WorkType
            _g["BatchEngine"] = batch_engine.BatchEngine
            _g["QueueFullError"] = batch_engine.QueueFullError
            _g["_unlink_safe"] = batch_engine._unlink_safe
            yield
    finally:
        try:
            sys.path.remove(str(_PARAKEET_DIR))
        except ValueError:
            pass


def _make_mock_gpu_worker(results_fn=None):
    worker = MagicMock(spec=GPUWorker)
    worker.is_ready = True
    worker.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}

    def submit(payload, loop):
        fut = loop.create_future()
        item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
        if results_fn:
            res = results_fn(payload)
        else:
            res = [{"text": f"ok:{p}", "timestamp": {}} for p in payload["audio_paths"]]
        item.inference_seconds = 0.01
        loop.call_soon(fut.set_result, res)
        return fut, item

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
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}

        def submit_error(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            loop.call_soon(fut.set_exception, RuntimeError("GPU exploded"))
            return fut, item

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
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}

        def submit_queue_full(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            loop.call_soon(fut.set_exception, RuntimeError("GPU queue full"))
            return fut, item

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

    def test_cancellation_during_flush_resolves_futures(self):
        """CancelledError in _flush_batch fails futures instead of stranding them."""
        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}

        def submit_hang(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            return fut, item

        gpu.submit.side_effect = submit_hang
        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.01)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                submit_fut = asyncio.ensure_future(engine.submit("/tmp/hang.wav", owns_file=False))
                for _ in range(20):
                    await asyncio.sleep(0.01)
                    if gpu.submit.called:
                        break
                assert gpu.submit.called, "flush_batch never called gpu.submit"
                await engine.stop()
                # Let event loop process future resolution callbacks
                await asyncio.sleep(0)
                assert submit_fut.done()
                with pytest.raises(RuntimeError, match="cancelled during shutdown"):
                    submit_fut.result()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchEngineCallbacks:
    def test_on_batch_complete_called_with_timing(self):
        gpu = _make_mock_gpu_worker()
        callback_data = {}

        def on_complete(queue_durations, inference_seconds, batch_size):
            callback_data["queue_durations"] = queue_durations
            callback_data["inference_seconds"] = inference_seconds
            callback_data["batch_size"] = batch_size

        engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.01, on_batch_complete=on_complete)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/{i}.wav", owns_file=False)) for i in range(2)]
                    await asyncio.wait_for(asyncio.gather(*futs), timeout=5)
                    assert "queue_durations" in callback_data
                    assert len(callback_data["queue_durations"]) == 2
                    assert all(d >= 0 for d in callback_data["queue_durations"])
                    assert callback_data["inference_seconds"] >= 0
                    assert callback_data["batch_size"] == 2
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_on_gpu_oom_called_on_cuda_oom(self):
        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        oom_count = [0]

        def on_oom():
            oom_count[0] += 1

        def submit_oom(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            loop.call_soon(fut.set_exception, RuntimeError("CUDA out of memory"))
            return fut, item

        gpu.submit.side_effect = submit_oom
        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.01, on_gpu_oom=on_oom)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with pytest.raises(RuntimeError, match="CUDA out of memory"):
                        await asyncio.wait_for(engine.submit("/tmp/oom.wav", owns_file=False), timeout=5)
                    assert oom_count[0] == 1
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestConcurrentFlush:
    def test_inflight_semaphore_bounds_concurrent_gpu_calls(self):
        concurrent_count = {"current": 0, "peak": 0}

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            concurrent_count["current"] += 1
            concurrent_count["peak"] = max(concurrent_count["peak"], concurrent_count["current"])

            def resolve():
                concurrent_count["current"] -= 1
                results = [{"text": f"ok_{i}"} for i in range(payload["batch_size"])]
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = 0.01

            loop.call_soon(resolve)
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.005, max_inflight=1, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(8)]
                    results = await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 8
                    assert concurrent_count["peak"] <= 1
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_stop_drains_inflight_batches(self):
        completed = {"count": 0}

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            results = [{"text": "ok"} for _ in range(payload["batch_size"])]

            def resolve():
                completed["count"] += 1
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = 0.01

            loop.call_soon(resolve)
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=2, max_wait_seconds=0.005, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(4)]
                await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

        assert completed["count"] > 0

    def test_flush_loop_fires_without_blocking(self):
        gpu = _make_mock_gpu_worker()
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.005, max_inflight=2, vram_safety_factor=0)

        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(4)]
                    await asyncio.sleep(0.05)
                    results = await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 4
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestMaxInflight2:
    def test_sequential_batching_accumulates_requests(self):
        """With flush_pending gate held during GPU work, requests accumulate
        into larger batches instead of being flushed one-at-a-time."""
        batch_sizes = []

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            batch_sizes.append(payload["batch_size"])

            async def delayed_resolve():
                await asyncio.sleep(0.05)
                results = [{"text": f"ok_{i}"} for i in range(payload["batch_size"])]
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = 0.05

            asyncio.ensure_future(delayed_resolve())
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=8, max_wait_seconds=0.002, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = []
                    for i in range(6):
                        futs.append(asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")))
                        await asyncio.sleep(0.005)
                    results = await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 6
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

        batch1_count = sum(1 for b in batch_sizes if b == 1)
        assert batch1_count <= 1, (
            f"At most 1 batch=1 expected (got {batch1_count}, batches={batch_sizes}). "
            f"flush_pending gate should prevent rapid batch=1 flushes."
        )


class TestFlushGuard:
    def test_no_duplicate_flush_tasks(self):
        gate = asyncio.Event()
        flush_entries = {"count": 0}

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            flush_entries["count"] += 1

            async def wait_and_resolve():
                await gate.wait()
                if not fut.done():
                    fut.set_result([{"text": "ok"} for _ in range(payload["batch_size"])])
                item.inference_seconds = 0.01

            asyncio.ensure_future(wait_and_resolve())
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.005, max_inflight=1, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(8)]
                    await asyncio.sleep(0.1)
                    pending_before = flush_entries["count"]
                    assert pending_before <= 2
                    gate.set()
                    results = await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 8
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestDurationPassthrough:
    def test_payload_includes_durations(self):
        submitted_payloads = []

        def mock_submit(payload, loop):
            submitted_payloads.append(payload)
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            fut.set_result([{"text": "ok"} for _ in range(payload["batch_size"])])
            item.inference_seconds = 0.01
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.01, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(2)]
                    await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

        assert len(submitted_payloads) >= 1
        payload = submitted_payloads[0]
        assert "durations" in payload
        assert len(payload["durations"]) == payload["batch_size"]


class TestLazyVramInit:
    def test_vram_init_deferred_until_worker_ready(self):
        """VRAM info is zero at start() time, populated later — lazy init picks it up."""
        submitted_payloads = []

        def mock_submit(payload, loop):
            submitted_payloads.append(payload)
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            fut.set_result([{"text": "ok"} for _ in range(payload["batch_size"])])
            item.inference_seconds = 0.01
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=32, max_wait_seconds=0.01, vram_safety_factor=0.8)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                assert not engine._vram_enabled, "VRAM should be deferred when total_mb=0"

                gpu.vram_info = {
                    "total_mb": 22563,
                    "baseline_mb": 5709,
                    "attention_mode": "auto",
                    "auto_threshold_sec": 300,
                }

                try:
                    fut = asyncio.ensure_future(engine.submit("/tmp/lazy.wav", owns_file=False))
                    await asyncio.wait_for(fut, timeout=5)
                finally:
                    await engine.stop()

                assert engine._vram_enabled, "VRAM should be enabled after lazy init"
                assert engine._vram_available_mb > 0

            loop.run_until_complete(run())
        finally:
            loop.close()


class TestBatchesInflight:
    def test_full_batch_uses_second_inflight_slot(self):
        """When a full batch is processing (inflight=1), a second full batch
        should dispatch immediately using the second inflight slot."""
        batch_sizes = []
        gate = asyncio.Event()

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            batch_sizes.append(payload["batch_size"])

            async def resolve():
                if len(batch_sizes) == 1:
                    await gate.wait()
                results = [{"text": f"ok_{i}"} for i in range(payload["batch_size"])]
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = 0.01

            asyncio.ensure_future(resolve())
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=0.002, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = [asyncio.ensure_future(engine.submit(f"/tmp/a{i}.wav")) for i in range(4)]
                    await asyncio.sleep(0.02)
                    assert len(batch_sizes) >= 1, "First batch should have dispatched"
                    more_futs = [asyncio.ensure_future(engine.submit(f"/tmp/b{i}.wav")) for i in range(4)]
                    await asyncio.sleep(0.02)
                    assert len(batch_sizes) >= 2, (
                        f"Second full batch should dispatch while first is inflight "
                        f"(got {len(batch_sizes)} dispatches, batches={batch_sizes})"
                    )
                    gate.set()
                    all_futs = futs + more_futs
                    results = await asyncio.wait_for(asyncio.gather(*all_futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 8
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_batches_inflight_resets_after_gpu_error(self):
        """After a GPU error, _batches_inflight must return to 0 so the
        flush timer can dispatch future batches."""
        call_count = {"n": 0}

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            call_count["n"] += 1
            if call_count["n"] == 1:
                loop.call_soon(fut.set_exception, RuntimeError("GPU exploded"))
            else:
                results = [{"text": "ok"} for _ in range(payload["batch_size"])]
                loop.call_soon(fut.set_result, results)
            item.inference_seconds = 0.01
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=1, max_wait_seconds=0.002, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with pytest.raises(RuntimeError, match="GPU exploded"):
                        await asyncio.wait_for(engine.submit("/tmp/fail.wav"), timeout=5)
                    assert (
                        engine._batches_inflight == 0
                    ), f"_batches_inflight must be 0 after error, got {engine._batches_inflight}"
                    result = await asyncio.wait_for(engine.submit("/tmp/ok.wav"), timeout=5)
                    assert result["text"] == "ok"
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_timer_flush_blocked_during_inflight(self):
        """When _batches_inflight > 0, the 2ms flush timer must NOT create
        new flush tasks — requests accumulate instead."""
        batch_sizes = []

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            batch_sizes.append(payload["batch_size"])

            async def delayed_resolve():
                await asyncio.sleep(0.1)
                results = [{"text": f"ok_{i}"} for i in range(payload["batch_size"])]
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = 0.1

            asyncio.ensure_future(delayed_resolve())
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(gpu, max_batch_size=32, max_wait_seconds=0.002, max_inflight=1, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    futs = []
                    futs.append(asyncio.ensure_future(engine.submit("/tmp/first.wav")))
                    await asyncio.sleep(0.01)
                    for i in range(5):
                        futs.append(asyncio.ensure_future(engine.submit(f"/tmp/later_{i}.wav")))
                        await asyncio.sleep(0.005)
                    results = await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=10)
                    successes = [r for r in results if not isinstance(r, Exception)]
                    assert len(successes) == 6
                    batch1_count = sum(1 for b in batch_sizes if b == 1)
                    assert batch1_count <= 1, (
                        f"At most 1 batch=1 expected (got {batch1_count}, batches={batch_sizes}). "
                        f"Timer should not flush while batches_inflight > 0."
                    )
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_batches_inflight_resets_after_oom(self):
        """After a CUDA OOM, _batches_inflight must return to 0."""
        oom_fired = {"count": 0}

        def on_oom():
            oom_fired["count"] += 1

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            loop.call_soon(fut.set_exception, RuntimeError("CUDA out of memory"))
            item.inference_seconds = 0.01
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(
            gpu, max_batch_size=1, max_wait_seconds=0.002, max_inflight=2, vram_safety_factor=0, on_gpu_oom=on_oom
        )
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    with pytest.raises(RuntimeError, match="CUDA out of memory"):
                        await asyncio.wait_for(engine.submit("/tmp/oom.wav"), timeout=5)
                    assert engine._batches_inflight == 0
                    assert oom_fired["count"] == 1
                finally:
                    await engine.stop()

            loop.run_until_complete(run())
        finally:
            loop.close()

    def test_batches_inflight_resets_on_empty_pending(self):
        """Directly calling _flush_batch with empty _pending must still
        decrement _batches_inflight (exercises the early return branch)."""
        gpu = _make_mock_gpu_worker()
        engine = BatchEngine(gpu, max_batch_size=4, max_wait_seconds=1.0, max_inflight=2, vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        try:

            async def run():
                await engine.start()
                try:
                    assert engine._batches_inflight == 0
                    await engine._flush_batch()
                    assert (
                        engine._batches_inflight == 0
                    ), f"_batches_inflight must be 0 after empty-pending flush, got {engine._batches_inflight}"
                finally:
                    await engine.stop()

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
