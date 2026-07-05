"""
Regression test for #8664: flush_pending early reset causes batch=1.

Reproduces the exact production failure: when requests arrive one-at-a-time
with realistic GPU latency (seconds, not instant), the early
_flush_pending=False reset inside _flush_batch() lets the 2ms flush timer
fire between each arrival, producing batch=1 instead of accumulating.

RED on main with the early reset (line 273).
GREEN after removing line 273.
"""

import asyncio
import os
import sys
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

from batch_engine import BatchEngine
from gpu_worker import GPUWorker, WorkItem, WorkType

GPU_DELAY_SEC = 0.3
REQUEST_INTERVAL_SEC = 0.02
NUM_REQUESTS = 12
MAX_BATCH_SIZE = 32


class TestFlushPendingBatch1Regression(unittest.TestCase):
    """
    Simulates production traffic: requests arrive every 20ms, GPU takes 300ms
    per batch. With a 2ms flush timer and the early _flush_pending reset,
    the timer fires between arrivals and flushes batch=1 each time.

    Expected healthy behavior: requests accumulate during the ~300ms GPU
    processing window, producing batches of 5-15 files.
    """

    def test_staggered_arrivals_accumulate_not_batch1(self):
        batch_sizes = []

        def mock_submit(payload, loop):
            fut = loop.create_future()
            item = WorkItem(WorkType.BATCH_TRANSCRIBE, payload, future=fut, loop=loop)
            batch_sizes.append(payload["batch_size"])

            async def delayed_resolve():
                await asyncio.sleep(GPU_DELAY_SEC)
                results = [{"text": f"ok_{i}"} for i in range(payload["batch_size"])]
                if not fut.done():
                    fut.set_result(results)
                item.inference_seconds = GPU_DELAY_SEC

            asyncio.ensure_future(delayed_resolve())
            return fut, item

        gpu = MagicMock(spec=GPUWorker)
        gpu.is_ready = True
        gpu.vram_info = {"total_mb": 0, "baseline_mb": 0, "attention_mode": "full", "auto_threshold_sec": 300}
        gpu.submit.side_effect = mock_submit

        engine = BatchEngine(
            gpu,
            max_batch_size=MAX_BATCH_SIZE,
            max_wait_seconds=0.002,
            max_inflight=2,
            vram_safety_factor=0,
        )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())

            async def run():
                futs = []
                for i in range(NUM_REQUESTS):
                    futs.append(asyncio.create_task(engine.submit(f"/tmp/stagger_{i}.wav")))
                    await asyncio.sleep(REQUEST_INTERVAL_SEC)
                return await asyncio.wait_for(asyncio.gather(*futs, return_exceptions=True), timeout=30)

            results = loop.run_until_complete(run())
        finally:
            loop.run_until_complete(engine.stop())
            loop.close()

        successes = [r for r in results if not isinstance(r, Exception)]
        self.assertEqual(len(successes), NUM_REQUESTS, f"All requests must succeed, got {len(successes)}")

        total_batches = len(batch_sizes)
        avg_batch = sum(batch_sizes) / total_batches if total_batches else 0
        batch1_count = sum(1 for b in batch_sizes if b == 1)
        batch1_pct = batch1_count / total_batches * 100 if total_batches else 0

        self.assertGreater(
            avg_batch,
            2.0,
            f"Average batch size must be >2.0 (got {avg_batch:.1f}, "
            f"batches={batch_sizes}, batch=1 rate={batch1_pct:.0f}%)",
        )
        self.assertLessEqual(
            batch1_count,
            1,
            f"At most 1 initial batch=1 is expected (got {batch1_count}, "
            f"batches={batch_sizes}). Multiple batch=1 means flush_pending "
            f"resets too early, preventing accumulation.",
        )


if __name__ == "__main__":
    unittest.main()
