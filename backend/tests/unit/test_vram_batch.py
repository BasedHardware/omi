"""Tests for VRAM-aware batch sizing in batch_engine.py."""

import asyncio
import os
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock

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
    must be active in ``sys.modules`` before ``batch_engine`` is exec'd (it binds
    ``torch`` at import). ``stub_modules`` keeps the fakes active for the whole
    module and evicts them (and the freshly-loaded ``batch_engine``) on teardown,
    so nothing leaks to later test files.
    """
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
        g = globals()
        g["BatchEngine"] = be.BatchEngine
        g["PendingRequest"] = be.PendingRequest
        yield be


def _make_wav(duration_sec, sample_rate=16000):
    num_samples = int(duration_sec * sample_rate)
    data_size = num_samples * 2
    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data"
    header += struct.pack("<I", data_size)
    return header + b"\x00" * data_size


def _make_engine(
    vram_total_mb=23034,
    vram_baseline_mb=5709,
    attention_mode="auto",
    auto_threshold_sec=300,
    max_batch_size=32,
    vram_safety_factor=0.8,
    vram_bytes_per_t2=136.6,
    starvation_timeout_sec=5.0,
    max_inflight=1,
):
    gpu = MagicMock()
    gpu.vram_info = {
        "total_mb": vram_total_mb,
        "baseline_mb": vram_baseline_mb,
        "attention_mode": attention_mode,
        "auto_threshold_sec": auto_threshold_sec,
    }
    engine = BatchEngine(
        gpu_worker=gpu,
        max_batch_size=max_batch_size,
        vram_safety_factor=vram_safety_factor,
        vram_bytes_per_t2=vram_bytes_per_t2,
        starvation_timeout_sec=starvation_timeout_sec,
        max_inflight=max_inflight,
    )
    return engine


def _pending(duration_sec=None, age_sec=0.0):
    req = PendingRequest.__new__(PendingRequest)
    req.audio_path = f"test_{duration_sec}s.wav"
    req.timestamps = False
    req.future = MagicMock()
    req.owns_file = False
    req.submitted_at = time.monotonic() - age_sec
    req.duration_sec = duration_sec
    return req


class TestEstimateMaxBatch(unittest.TestCase):
    """Test _estimate_max_batch VRAM formula."""

    def setUp(self):
        self.engine = _make_engine()
        # Budget: 23034 * 0.8 - 5709 = 12718.2 MB
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.engine.start())
        loop.close()

    def test_short_files_allow_full_batch(self):
        # 30s files: T=375, per_file = 136.6 * 375^2 / 1024^2 = 18.3 MB
        # 12718 / 18.3 = 694 → capped at 32
        result = self.engine._estimate_max_batch(30.0)
        self.assertEqual(result, 32)

    def test_medium_files_cap_batch(self):
        # 120s: T=1500, per_file = 136.6 * 1500^2 / 1024^2 = 293 MB
        # 12718 / 293 = 43 → capped at 32
        result = self.engine._estimate_max_batch(120.0)
        self.assertEqual(result, 32)

    def test_long_files_severely_cap(self):
        # 250s: T=3125, per_file = 136.6 * 3125^2 / 1024^2 = 1272 MB
        # 12718 / 1272 = 9
        result = self.engine._estimate_max_batch(250.0)
        self.assertLessEqual(result, 10)
        self.assertGreaterEqual(result, 8)

    def test_near_threshold_files_cap_to_one_or_two(self):
        # 290s: T=3625, per_file = 136.6 * 3625^2 / 1024^2 = 1712 MB
        # 12718 / 1712 = 7
        result = self.engine._estimate_max_batch(290.0)
        self.assertLessEqual(result, 8)
        self.assertGreaterEqual(result, 5)

    def test_very_long_files_skip_limit_in_auto(self):
        # 600s >= 300s threshold, auto mode switches to local attention
        # so VRAM cap is bypassed (linear scaling, no quadratic issue)
        result = self.engine._estimate_max_batch(600.0)
        self.assertEqual(result, 32)

    def test_disabled_returns_max(self):
        engine = _make_engine(vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()
        result = engine._estimate_max_batch(600.0)
        self.assertEqual(result, 32)

    def test_zero_duration_returns_max(self):
        result = self.engine._estimate_max_batch(0.0)
        self.assertEqual(result, 32)

    def test_local_attention_skips_limit(self):
        engine = _make_engine(attention_mode="local")
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()
        result = engine._estimate_max_batch(600.0)
        self.assertEqual(result, 32)

    def test_auto_mode_long_file_skips_limit(self):
        result = self.engine._estimate_max_batch(400.0)
        self.assertEqual(result, 32)

    def test_auto_mode_short_file_applies_limit(self):
        result = self.engine._estimate_max_batch(250.0)
        self.assertLess(result, 32)

    def test_auto_unknown_duration_not_bypassed(self):
        result = self.engine._estimate_max_batch(300.0, duration_known=False)
        self.assertLess(result, 32)

    def test_negative_budget_caps_to_one(self):
        engine = _make_engine(vram_safety_factor=0.1)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()
        engine._vram_available_mb = 0.0
        result = engine._estimate_max_batch(300.0)
        self.assertEqual(result, 1)

    def test_budget_divided_by_max_inflight(self):
        engine_1 = _make_engine(max_inflight=1)
        engine_2 = _make_engine(max_inflight=2)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine_1.start())
        loop.run_until_complete(engine_2.start())
        loop.close()
        self.assertAlmostEqual(engine_1._vram_available_mb, engine_2._vram_available_mb * 2, places=0)
        limit_1 = engine_1._estimate_max_batch(250.0)
        limit_2 = engine_2._estimate_max_batch(250.0)
        self.assertGreater(limit_1, limit_2)


class TestFormVramSafeBatch(unittest.TestCase):
    """Test _form_vram_safe_batch batch formation logic."""

    def setUp(self):
        self.engine = _make_engine()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.engine.start())
        loop.close()

    def test_short_files_batch_fully(self):
        candidates = [_pending(30.0) for _ in range(10)]
        batch = self.engine._form_vram_safe_batch(candidates)
        self.assertEqual(len(batch), 10)

    def test_long_files_capped(self):
        candidates = [_pending(250.0) for _ in range(20)]
        batch = self.engine._form_vram_safe_batch(candidates)
        self.assertLess(len(batch), 20)
        self.assertGreater(len(batch), 0)

    def test_mixed_durations_sorted_short_first(self):
        candidates = [_pending(250.0), _pending(30.0), _pending(60.0)]
        batch = self.engine._form_vram_safe_batch(candidates)
        # Sorted by duration — short files should be first
        self.assertEqual(batch[0].duration_sec, 30.0)

    def test_unknown_duration_treated_conservatively(self):
        candidates = [_pending(None) for _ in range(10)]
        batch = self.engine._form_vram_safe_batch(candidates)
        # Unknown uses auto_threshold_sec (300s) as effective duration
        self.assertLess(len(batch), 10)

    def test_starved_request_gets_priority(self):
        old = _pending(250.0, age_sec=10.0)
        new_items = [_pending(30.0) for _ in range(5)]
        candidates = new_items + [old]
        batch = self.engine._form_vram_safe_batch(candidates)
        # Old request must be in batch
        self.assertIn(old, batch)

    def test_empty_candidates(self):
        batch = self.engine._form_vram_safe_batch([])
        self.assertEqual(len(batch), 0)

    def test_single_candidate(self):
        batch = self.engine._form_vram_safe_batch([_pending(600.0)])
        self.assertEqual(len(batch), 1)

    def test_vram_disabled_returns_max_slice(self):
        engine = _make_engine(vram_safety_factor=0)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()
        candidates = [_pending(600.0) for _ in range(10)]
        batch = engine._form_vram_safe_batch(candidates)
        self.assertEqual(len(batch), 10)


class TestDurationProbe(unittest.TestCase):
    """Test _get_audio_duration for WAV files."""

    def test_wav_duration(self):
        wav = _make_wav(5.0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            path = f.name
        try:
            dur = BatchEngine._get_audio_duration(path)
            self.assertIsNotNone(dur)
            self.assertAlmostEqual(dur, 5.0, places=1)
        finally:
            os.unlink(path)

    def test_invalid_file_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"not a wav file")
            path = f.name
        try:
            dur = BatchEngine._get_audio_duration(path)
            self.assertIsNone(dur)
        finally:
            os.unlink(path)

    def test_missing_file_returns_none(self):
        dur = BatchEngine._get_audio_duration("/nonexistent/file.wav")
        self.assertIsNone(dur)


class TestProdOOMScenario(unittest.TestCase):
    """Validate the VRAM formula against the actual prod OOM data."""

    def test_prod_oom_prevented(self):
        # Prod config: L4 22GB, baseline 5709 MiB, auto mode
        engine = _make_engine(
            vram_total_mb=22563,  # L4 total (from prod log)
            vram_baseline_mb=5709,
            attention_mode="auto",
            auto_threshold_sec=300,
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()

        # The OOM batch was 12 files at ~250s each
        # Formula should cap to < 12
        max_b = engine._estimate_max_batch(250.0)
        self.assertLess(max_b, 12, f"max_batch={max_b} would still OOM (prod had 12)")

        # For 290s files (near threshold), should be even more restrictive
        max_b_290 = engine._estimate_max_batch(290.0)
        self.assertLess(max_b_290, max_b)

    def test_short_files_still_efficient(self):
        engine = _make_engine(
            vram_total_mb=22563,
            vram_baseline_mb=5709,
        )
        loop = asyncio.new_event_loop()
        loop.run_until_complete(engine.start())
        loop.close()

        # 30s files should still allow large batches
        max_b = engine._estimate_max_batch(30.0)
        self.assertEqual(max_b, 32)

        # 77s files (prod average) should allow decent batches
        max_b_77 = engine._estimate_max_batch(77.0)
        self.assertGreaterEqual(max_b_77, 10)


if __name__ == "__main__":
    unittest.main()
