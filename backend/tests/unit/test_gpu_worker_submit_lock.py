"""Tests for GPUWorker._submit_lock: stop()/submit() race prevention."""

import asyncio
import os
import sys
import threading
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")

_torch = MagicMock()
_torch.cuda.is_available.return_value = False
_torch.cuda.memory_allocated.return_value = 0
_torch_props = MagicMock()
_torch_props.total_memory = 16 * 1024**3
_torch.cuda.get_device_properties.return_value = _torch_props
_torch.cuda.empty_cache = MagicMock()
_torch.cuda.mem_get_info.return_value = (10 * 1024**3, 16 * 1024**3)
_torch.inference_mode = lambda: (lambda fn: fn)
_torch.compile = lambda m: m
_torch.backends.cudnn = MagicMock()
sys.modules.setdefault("torch", _torch)

for _mod in ["nemo", "nemo.collections", "nemo.collections.asr"]:
    sys.modules.setdefault(_mod, MagicMock())
for _mod in ["pyannote", "pyannote.audio", "pyannote.audio.core", "pyannote.audio.core.model"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../parakeet"))

from gpu_worker import GPUWorker


class TestSubmitLockRace(unittest.TestCase):

    def _make_started_worker(self):
        worker = GPUWorker()
        worker._running = True
        worker._ready.set()
        return worker

    def test_submit_after_stop_raises_shutting_down(self):
        worker = self._make_started_worker()
        worker.stop()

        loop = asyncio.new_event_loop()
        try:
            fut, item = worker.submit({"audio_paths": ["/tmp/a.wav"]}, loop)
            self.assertIsNone(item)
            self.assertTrue(fut.done())
            with self.assertRaises(RuntimeError) as ctx:
                fut.result()
            self.assertIn("shutting down", str(ctx.exception))
        finally:
            loop.close()

    def test_submit_sync_after_stop_raises_shutting_down(self):
        worker = self._make_started_worker()
        worker.stop()

        with self.assertRaises(RuntimeError) as ctx:
            worker.submit_sync({"audio_paths": ["/tmp/a.wav"]})
        self.assertIn("shutting down", str(ctx.exception))

    def test_submit_embedding_sync_after_stop_raises_shutting_down(self):
        worker = self._make_started_worker()
        worker.stop()

        with self.assertRaises(RuntimeError) as ctx:
            worker.submit_embedding_sync({"waveform": None, "sample_rate": 16000})
        self.assertIn("shutting down", str(ctx.exception))

    def test_concurrent_stop_and_submit_no_enqueue_to_dead_queue(self):
        """Multiple threads calling stop() and submit() concurrently must not
        enqueue work after _running is set to False."""
        worker = self._make_started_worker()
        loop = asyncio.new_event_loop()
        errors = []
        enqueued_after_stop = []

        def submitter():
            for _ in range(50):
                try:
                    fut, item = worker.submit({"audio_paths": ["/tmp/x.wav"]}, loop)
                    if not worker._running and item is not None:
                        enqueued_after_stop.append(True)
                except Exception as e:
                    errors.append(e)

        def stopper():
            worker.stop()

        threads = [threading.Thread(target=submitter) for _ in range(4)]
        threads.append(threading.Thread(target=stopper))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        loop.close()
        self.assertEqual(len(enqueued_after_stop), 0, "No work should be enqueued after _running is set to False")

    def test_concurrent_stop_and_submit_sync_no_enqueue(self):
        """Concurrent stop() + submit_sync() must not enqueue to dead queue."""
        worker = self._make_started_worker()
        errors = []
        enqueued_after_stop = []

        def submitter():
            for _ in range(50):
                try:
                    worker.submit_sync({"audio_paths": ["/tmp/x.wav"]}, timeout=0.01)
                    if not worker._running:
                        enqueued_after_stop.append(True)
                except (RuntimeError, TimeoutError):
                    pass
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=submitter) for _ in range(4)]
        threads.append(threading.Thread(target=worker.stop))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(enqueued_after_stop), 0, "No work should be enqueued after _running is set to False")

    def test_concurrent_stop_and_submit_embedding_sync_no_enqueue(self):
        """Concurrent stop() + submit_embedding_sync() must not enqueue to dead queue."""
        worker = self._make_started_worker()
        errors = []
        enqueued_after_stop = []

        def submitter():
            for _ in range(50):
                try:
                    worker.submit_embedding_sync({"waveform": None, "sample_rate": 16000}, timeout=0.01)
                    if not worker._running:
                        enqueued_after_stop.append(True)
                except (RuntimeError, TimeoutError):
                    pass
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=submitter) for _ in range(4)]
        threads.append(threading.Thread(target=worker.stop))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(enqueued_after_stop), 0, "No work should be enqueued after _running is set to False")

    def test_stop_sets_running_false_atomically(self):
        """stop() must set _running=False under the lock before releasing it."""
        worker = self._make_started_worker()
        self.assertTrue(worker._running)
        worker.stop()
        self.assertFalse(worker._running)


if __name__ == "__main__":
    unittest.main()
