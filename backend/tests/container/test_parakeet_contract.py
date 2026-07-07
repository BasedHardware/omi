"""
Contract tests -- detect when pyannote.audio changes imports that would break stubs.

Run INSIDE the built container:
    docker run --rm parakeet:test \
      python -m pytest tests/container/test_parakeet_contract.py -v

When these fail, pyannote changed its imports and stubs need updating.
"""

import ast
import importlib

import pytest


class TestTorchAudiomentationsContract:
    """Verify pyannote.audio still imports exactly the symbols we stub."""

    EXPECTED_IMPORTS = {
        "torch_audiomentations": ["Identity"],
        "torch_audiomentations.core.transforms_interface": ["BaseWaveformTransform"],
        "torch_audiomentations.augmentations.mix": ["Mix"],
        "torch_audiomentations.utils.config": ["from_dict"],
    }

    def test_all_stubbed_symbols_still_importable(self):
        for module, symbols in self.EXPECTED_IMPORTS.items():
            mod = importlib.import_module(module)
            for sym in symbols:
                assert hasattr(mod, sym), f"{module}.{sym} not found -- stub may need updating"

    def test_no_new_unstubbed_imports(self):
        """Scan pyannote.audio.core.task for new torch_audiomentations imports."""
        try:
            import pyannote.audio.core.task as task_module

            source_file = task_module.__file__
            with open(source_file) as f:
                tree = ast.parse(f.read())
        except Exception:
            pytest.skip("Cannot inspect pyannote source")

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "torch_audiomentations" in node.module:
                    for alias in node.names:
                        imports.add(f"{node.module}.{alias.name}")

        stubbed = set()
        for mod, syms in self.EXPECTED_IMPORTS.items():
            for s in syms:
                stubbed.add(f"{mod}.{s}")

        unstubbed = imports - stubbed
        assert not unstubbed, f"pyannote imports torch_audiomentations symbols we don't stub: {unstubbed}"


class TestTelemetryContract:
    """Verify pyannote.audio still expects exactly these telemetry functions."""

    EXPECTED_FUNCTIONS = [
        "set_opentelemetry_log_level",
        "set_telemetry_metrics",
        "track_model_init",
        "track_pipeline_init",
        "track_pipeline_apply",
    ]

    def test_all_telemetry_functions_present(self):
        from pyannote.audio import telemetry

        for fn_name in self.EXPECTED_FUNCTIONS:
            assert hasattr(telemetry, fn_name), f"Missing telemetry stub: {fn_name}"
            assert callable(getattr(telemetry, fn_name))


class TestTorchaudioBackendContract:
    """Verify our torchaudio patch exports all symbols pyannote.audio needs."""

    REQUIRED_SYMBOLS = [
        "AudioMetaData",
        "info",
        "load",
        "save",
        "list_audio_backends",
        "set_audio_backend",
        "get_audio_backend",
    ]

    def test_all_backend_symbols_exported(self):
        import torchaudio

        for sym in self.REQUIRED_SYMBOLS:
            assert hasattr(torchaudio, sym), f"torchaudio.{sym} missing from patched __init__.py"

    def test_extension_decorator_names(self):
        """All fail_if_no_* decorators must exist and return their argument."""
        from torchaudio import _extension

        decorator_names = [
            "fail_if_no_align",
            "fail_if_no_rir",
            "fail_if_no_sox",
            "fail_if_no_ffmpeg",
            "fail_if_no_soundfile",
            "fail_if_no_kaldi",
        ]
        sentinel = object()
        for name in decorator_names:
            fn = getattr(_extension, name, None)
            assert fn is not None, f"Missing decorator: {name}"
            assert fn(sentinel) is sentinel, f"{name} must return its argument"


class TestPyannoteMetricsContract:
    """Verify pyannote.metrics is installed and compatible with pinned stack."""

    def test_diarization_error_rate_importable(self):
        from pyannote.metrics.diarization import DiarizationErrorRate  # noqa: F401

    def test_der_scoring_on_synthetic(self):
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate

        ref = Annotation()
        ref[Segment(0, 5)] = "A"
        ref[Segment(5, 10)] = "B"

        hyp = Annotation()
        hyp[Segment(0, 5)] = "1"
        hyp[Segment(5, 10)] = "2"

        metric = DiarizationErrorRate(collar=0.25, skip_overlap=True)
        der = metric(ref, hyp)
        assert 0.0 <= der <= 1.0

    def test_der_detailed_components(self):
        """Verify detailed=True returns all component keys the benchmark uses."""
        from pyannote.core import Annotation, Segment
        from pyannote.metrics.diarization import DiarizationErrorRate

        ref = Annotation()
        ref[Segment(0, 5)] = "A"
        ref[Segment(5, 10)] = "B"

        hyp = Annotation()
        hyp[Segment(0, 5)] = "1"
        hyp[Segment(5, 10)] = "2"

        metric = DiarizationErrorRate(collar=0.25, skip_overlap=True)
        detail = metric(ref, hyp, detailed=True)

        assert "diarization error rate" in detail
        assert "missed detection" in detail
        assert "false alarm" in detail
        assert "confusion" in detail
        assert "total" in detail
        assert 0.0 <= detail["diarization error rate"] <= 1.0


class TestPyannoteImportSurfaces:
    """Verify broader pyannote import surfaces that depend on our stubs."""

    def test_pyannote_augmentation_mix(self):
        from pyannote.audio.core.task import Task  # noqa: F401

    def test_torchaudio_compliance_and_functional(self):
        from torchaudio.compliance.kaldi import fbank  # noqa: F401
        from torchaudio.functional import resample  # noqa: F401
