"""Regression tests for NLLB service metrics instrumentation.

Verifies:
- Queue wait histogram captures executor backlog (not just validation time)
- Model load gauge is set on startup
- Slow-burn alert includes volume gate in PrometheusRule
"""

import os
import sys
import time
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

os.environ.setdefault("NLLB_MODEL_DIR", "/tmp/fake-nllb-model")
os.environ.setdefault("CT2_DEVICE", "cpu")

_saved_modules = {}


def _stub_nllb_deps():
    ct2 = ModuleType("ctranslate2")
    ct2.Translator = MagicMock

    spm = ModuleType("sentencepiece")

    class FakeSPP:
        def Load(self, path):
            pass

        def Encode(self, text, out_type=str):
            return ["▁hello"]

        def Decode(self, tokens):
            return " ".join(tokens)

    spm.SentencePieceProcessor = FakeSPP

    sys.modules["ctranslate2"] = ct2
    sys.modules["sentencepiece"] = spm


def setUpModule():
    global _saved_modules
    _saved_modules = dict(sys.modules)
    _stub_nllb_deps()


def tearDownModule():
    added = set(sys.modules.keys()) - set(_saved_modules.keys())
    for key in added:
        del sys.modules[key]
    sys.modules.update(_saved_modules)


class TestQueueWaitMetric(unittest.TestCase):

    def test_queue_wait_observed_inside_translate_batch(self):
        from nllb_translation.main import _translate_batch, QUEUE_WAIT

        fake_translator = MagicMock()
        fake_result = MagicMock()
        fake_result.hypotheses = [["▁hola", "</s>"]]
        fake_translator.translate_batch.return_value = [fake_result]

        with patch("nllb_translation.main._translator", fake_translator), patch(
            "nllb_translation.main._tokenizer",
            MagicMock(Encode=lambda t, out_type=str: ["▁hello"], Decode=lambda tokens: "hola"),
        ):

            t_before = time.monotonic() - 0.5
            with patch.object(QUEUE_WAIT, "observe") as mock_observe:
                _translate_batch(["hello"], "eng_Latn", "spa_Latn", t_queued=t_before)
                mock_observe.assert_called_once()
                observed_value = mock_observe.call_args[0][0]
                assert observed_value >= 0.4, f"Queue wait {observed_value} should be >= 0.4s (simulated 0.5s delay)"

    def test_queue_wait_skipped_when_no_timestamp(self):
        from nllb_translation.main import _translate_batch, QUEUE_WAIT

        fake_translator = MagicMock()
        fake_result = MagicMock()
        fake_result.hypotheses = [["▁hola", "</s>"]]
        fake_translator.translate_batch.return_value = [fake_result]

        with patch("nllb_translation.main._translator", fake_translator), patch(
            "nllb_translation.main._tokenizer",
            MagicMock(Encode=lambda t, out_type=str: ["▁hello"], Decode=lambda tokens: "hola"),
        ):

            with patch.object(QUEUE_WAIT, "observe") as mock_observe:
                _translate_batch(["hello"], "eng_Latn", "spa_Latn", t_queued=0.0)
                mock_observe.assert_not_called()


class TestModelLoadMetric(unittest.TestCase):

    def test_model_load_sets_duration_gauge(self):
        from nllb_translation.main import MODEL_LOAD_DURATION, MODEL_LOADED

        with patch("nllb_translation.main.ctranslate2") as mock_ct2, patch(
            "nllb_translation.main.spm"
        ) as mock_spm, patch("os.path.exists", return_value=True), patch.object(
            MODEL_LOAD_DURATION, "set"
        ) as mock_duration, patch.object(
            MODEL_LOADED, "set"
        ) as mock_loaded:

            mock_spp = MagicMock()
            mock_spm.SentencePieceProcessor.return_value = mock_spp

            from nllb_translation.main import _load_model

            _load_model()

            mock_loaded.assert_called_with(1)
            mock_duration.assert_called_once()
            assert mock_duration.call_args[0][0] >= 0, "Load duration should be non-negative"


class TestSlowBurnAlertVolumeGate(unittest.TestCase):

    def test_prometheusrule_has_volume_gate(self):
        rule_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'charts', 'nllb-translation', 'templates', 'prometheusrule.yaml'
        )
        with open(rule_path) as f:
            content = f.read()

        assert "NLLBSLOBurnRateSlow" in content, "Slow burn alert should exist"
        slow_burn_start = content.index("NLLBSLOBurnRateSlow")
        slow_burn_section = content[slow_burn_start : slow_burn_start + 500]
        assert (
            "sum(rate(nllb_requests_total[30m])) > 0.1" in slow_burn_section
        ), "Slow burn alert must have volume gate to prevent noisy alerts during low traffic"


if __name__ == "__main__":
    unittest.main()
