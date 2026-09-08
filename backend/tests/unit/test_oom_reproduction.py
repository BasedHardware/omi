"""
E2E OOM reproduction test for VRAM-aware batch sizing.

Reproduces the exact prod OOM scenario: 12 x 290s files in auto mode on L4.
Goes RED without the fix (VRAM_SAFETY_FACTOR=0) and GREEN with it (0.8).

Based on hiro's live reproduction on dev cluster:
  - 12 x 290s files, single batch -> torch.OutOfMemoryError
  - Tried to allocate 2.35 GiB with only 807 MiB free
  - 20.9 GiB PyTorch allocated of 22.03 GiB total
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("PARAKEET_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
os.environ.setdefault("PARAKEET_DEVICE", "cpu")
os.environ.setdefault("PARAKEET_TORCH_COMPILE", "false")
os.environ.setdefault("PARAKEET_CUDA_GRAPHS", "false")

_PARAKEET_DIR = os.path.join(os.path.dirname(__file__), "../../parakeet")
if _PARAKEET_DIR not in sys.path:
    sys.path.insert(0, _PARAKEET_DIR)

from testing.import_isolation import load_module_fresh, stub_modules

_BATCH_ENGINE_PATH = os.path.join(_PARAKEET_DIR, "batch_engine.py")


@pytest.fixture(scope="module", autouse=True)
def _batch_engine_module():
    """Load batch_engine fresh against stubbed torch/nemo/pyannote chains.

    torch/nemo/pyannote are not installed in the test environment, so fake modules
    must be active in ``sys.modules`` before ``batch_engine`` (which imports
    ``gpu_worker``, which imports ``torch``) is exec'd. ``stub_modules`` keeps the
    fakes active for the whole module and evicts them (and the freshly-loaded
    ``batch_engine``/``gpu_worker``) on teardown, so nothing leaks to later test files.
    """
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

    _nemo_asr = MagicMock()
    _nemo = MagicMock()
    _nemo.collections.asr = _nemo_asr

    _pyannote = MagicMock()
    _pyannote_audio = MagicMock()
    _pyannote_audio_core = MagicMock()
    _pyannote_audio_core_model = MagicMock()

    fakes = {
        "torch": _torch,
        "nemo": _nemo,
        "nemo.collections": _nemo.collections,
        "nemo.collections.asr": _nemo_asr,
        "pyannote": _pyannote,
        "pyannote.audio": _pyannote_audio,
        "pyannote.audio.core": _pyannote_audio_core,
        "pyannote.audio.core.model": _pyannote_audio_core_model,
    }
    with stub_modules(fakes):
        be = load_module_fresh("batch_engine", _BATCH_ENGINE_PATH)
        globals()["BatchEngine"] = be.BatchEngine
        yield be


L4_TOTAL_MB = 22563
L4_BASELINE_MB = 5709
VRAM_COEFF = 136.6
AUTO_THRESHOLD_SEC = 300.0
FILE_DURATION_SEC = 290.0
FILE_COUNT = 12


def _per_file_mb(duration_sec):
    T = duration_sec / 0.08
    return VRAM_COEFF * T * T / (1024 * 1024)


def _make_gpu_worker():
    """Mock GPU worker that OOMs when batch VRAM exceeds actual L4 capacity."""
    gpu = MagicMock()
    gpu.vram_info = {
        "total_mb": L4_TOTAL_MB,
        "baseline_mb": L4_BASELINE_MB,
        "attention_mode": "auto",
        "auto_threshold_sec": AUTO_THRESHOLD_SEC,
    }

    available_mb = L4_TOTAL_MB - L4_BASELINE_MB
    per_file = _per_file_mb(FILE_DURATION_SEC)

    def mock_submit(work, loop):
        batch_size = work["batch_size"]
        batch_vram = batch_size * per_file
        future = loop.create_future()
        work_item = MagicMock()
        work_item.inference_seconds = 0.5 * batch_size

        if batch_vram > available_mb:
            needed_gib = per_file / 1024
            free_mb = available_mb - (batch_size - 1) * per_file
            used_gib = (L4_BASELINE_MB + (batch_size - 1) * per_file) / 1024
            loop.call_soon(
                future.set_exception,
                RuntimeError(
                    f"CUDA out of memory. Tried to allocate {needed_gib:.2f} GiB. "
                    f"GPU 0 has a total capacity of {L4_TOTAL_MB / 1024:.2f} GiB of which "
                    f"{free_mb:.0f} MiB is free. {used_gib:.2f} GiB already allocated."
                ),
            )
        else:
            results = [{"text": f"transcription_{i}"} for i in range(batch_size)]
            loop.call_soon(future.set_result, results)

        return future, work_item

    gpu.submit = mock_submit
    return gpu


def _make_engine(vram_safety_factor, batch_wait=0.1):
    gpu = _make_gpu_worker()
    return gpu, BatchEngine(
        gpu_worker=gpu,
        max_batch_size=32,
        max_wait_seconds=batch_wait,
        vram_safety_factor=vram_safety_factor,
        vram_bytes_per_t2=VRAM_COEFF,
        starvation_timeout_sec=5.0,
    )


class TestOOMReproduction(unittest.TestCase):
    """
    Reproduce exact prod OOM: 12 x 290s files on L4 in auto mode.

    RED without fix (vram_safety_factor=0):
      All 12 files land in one batch -> GPU worker raises CUDA OOM
      All 12 requests fail with RuntimeError

    GREEN with fix (vram_safety_factor=0.8):
      VRAM formula caps batches to ~7 files
      12 files processed across 2 batches, all succeed
    """

    @patch('batch_engine.BatchEngine._get_audio_duration', return_value=FILE_DURATION_SEC)
    def test_without_fix_all_oom(self, _mock_dur):
        """Without VRAM cap, 12 x 290s in one batch -> OOM."""
        gpu, engine = _make_engine(vram_safety_factor=0, batch_wait=0.1)
        oom_fired = []
        engine._on_gpu_oom = lambda: oom_fired.append(True)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())

            async def run():
                tasks = []
                for i in range(FILE_COUNT):
                    tasks.append(asyncio.create_task(engine.submit(f"/tmp/repro290/audio_{i:02d}.wav")))
                return await asyncio.gather(*tasks, return_exceptions=True)

            results = loop.run_until_complete(run())
        finally:
            loop.run_until_complete(engine.stop())
            loop.close()

        failures = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(failures), FILE_COUNT, f"Expected all {FILE_COUNT} to fail, got {len(failures)}")
        for f in failures:
            self.assertIn("CUDA out of memory", str(f))
        self.assertTrue(oom_fired, "OOM callback should have fired")

        metrics = engine.metrics
        self.assertEqual(metrics["total_batches"], 1, "Uncapped: exactly 1 batch")
        self.assertEqual(metrics["total_files"], FILE_COUNT)
        self.assertEqual(metrics["vram_limited_batches"], 0, "No VRAM limiting when disabled")

    @patch('batch_engine.BatchEngine._get_audio_duration', return_value=FILE_DURATION_SEC)
    def test_with_fix_all_succeed(self, _mock_dur):
        """With VRAM cap at 0.8, 12 x 290s split into safe batches -> all succeed."""
        gpu, engine = _make_engine(vram_safety_factor=0.8, batch_wait=0.01)
        oom_fired = []
        engine._on_gpu_oom = lambda: oom_fired.append(True)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())

            async def run():
                tasks = []
                for i in range(FILE_COUNT):
                    tasks.append(asyncio.create_task(engine.submit(f"/tmp/repro290/audio_{i:02d}.wav")))
                return await asyncio.gather(*tasks, return_exceptions=True)

            results = loop.run_until_complete(run())
        finally:
            loop.run_until_complete(engine.stop())
            loop.close()

        failures = [r for r in results if isinstance(r, Exception)]
        successes = [r for r in results if not isinstance(r, Exception)]

        self.assertEqual(
            len(successes),
            FILE_COUNT,
            f"Expected all {FILE_COUNT} to succeed, got {len(failures)} failures: {failures}",
        )
        self.assertFalse(oom_fired, "No OOM should occur with VRAM cap")

        metrics = engine.metrics
        self.assertGreater(metrics["total_batches"], 1, "Should split into multiple batches")
        self.assertEqual(metrics["total_files"], FILE_COUNT)
        self.assertGreater(metrics["vram_limited_batches"], 0, "Batches should be VRAM-limited")

    def test_batch_size_matches_formula(self):
        """Verify the formula caps 290s files to the expected batch size on L4."""
        _, engine = _make_engine(vram_safety_factor=0.8)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()

        max_b = engine._estimate_max_batch(FILE_DURATION_SEC)
        per_file = _per_file_mb(FILE_DURATION_SEC)
        per_batch_budget = engine._vram_available_mb

        self.assertLess(max_b, FILE_COUNT, f"B={max_b} must be < {FILE_COUNT} to prevent OOM")
        self.assertGreater(max_b, 0)
        self.assertLessEqual(max_b * per_file, per_batch_budget, "Capped batch must fit in per-batch budget")
        self.assertGreater((max_b + 1) * per_file, per_batch_budget, "B+1 should exceed per-batch budget")

    def test_uncapped_exceeds_l4_vram(self):
        """Verify 12 x 290s uncapped exceeds L4 VRAM -- proving the fix is necessary."""
        per_file = _per_file_mb(FILE_DURATION_SEC)
        total_needed = FILE_COUNT * per_file + L4_BASELINE_MB
        available = L4_TOTAL_MB - L4_BASELINE_MB

        self.assertGreater(
            total_needed, L4_TOTAL_MB, f"12 x 290s should exceed L4: {total_needed:.0f} > {L4_TOTAL_MB} MiB"
        )
        self.assertGreater(
            FILE_COUNT * per_file,
            available,
            f"12 x {per_file:.0f} = {FILE_COUNT * per_file:.0f} > {available:.0f} available",
        )

    @patch('batch_engine.BatchEngine._get_audio_duration', return_value=FILE_DURATION_SEC)
    def test_oom_error_signature_matches_prod(self, _mock_dur):
        """Verify OOM error string matches prod signature."""
        _, engine = _make_engine(vram_safety_factor=0, batch_wait=0.1)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())

            async def run():
                tasks = [asyncio.create_task(engine.submit(f"/tmp/audio_{i}.wav")) for i in range(FILE_COUNT)]
                return await asyncio.gather(*tasks, return_exceptions=True)

            results = loop.run_until_complete(run())
        finally:
            loop.run_until_complete(engine.stop())
            loop.close()

        errors = [r for r in results if isinstance(r, Exception)]
        self.assertTrue(len(errors) > 0)
        err_msg = str(errors[0])
        self.assertIn("CUDA out of memory", err_msg)
        self.assertIn("Tried to allocate", err_msg)
        self.assertIn("GiB", err_msg)


if __name__ == "__main__":
    unittest.main()
