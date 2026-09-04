"""Regression tests for NLLB service metrics instrumentation.

Verifies:
- Queue wait histogram captures executor backlog (not just validation time)
- Endpoint passes t_queued through to _translate_batch via run_in_executor
- Model load gauge is set on startup
- Slow-burn alert includes volume gate in PrometheusRule
"""

import os
import sys
import time
import unittest
import asyncio
from functools import partial
from types import ModuleType
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

os.environ.setdefault("NLLB_MODEL_DIR", "/tmp/fake-nllb-model")
os.environ.setdefault("CT2_DEVICE", "cpu")

_saved_modules = {}
_nllb_main = None


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
    global _saved_modules, _nllb_main
    _saved_modules = dict(sys.modules)
    _stub_nllb_deps()
    import nllb_translation.main as m

    _nllb_main = m


def tearDownModule():
    added = set(sys.modules.keys()) - set(_saved_modules.keys())
    for key in added:
        del sys.modules[key]
    sys.modules.update(_saved_modules)


class TestQueueWaitMetric(unittest.TestCase):

    def test_queue_wait_observed_inside_translate_batch(self):
        fake_translator = MagicMock()
        fake_result = MagicMock()
        fake_result.hypotheses = [["▁hola", "</s>"]]
        fake_translator.translate_batch.return_value = [fake_result]

        with patch.object(_nllb_main, "_translator", fake_translator), patch.object(
            _nllb_main,
            "_tokenizer",
            MagicMock(Encode=lambda t, out_type=str: ["▁hello"], Decode=lambda tokens: "hola"),
        ):

            t_before = time.monotonic() - 0.5
            with patch.object(_nllb_main.QUEUE_WAIT, "observe") as mock_observe:
                _nllb_main._translate_batch(["hello"], "eng_Latn", "spa_Latn", t_queued=t_before)
                mock_observe.assert_called_once()
                observed_value = mock_observe.call_args[0][0]
                assert observed_value >= 0.4, f"Queue wait {observed_value} should be >= 0.4s (simulated 0.5s delay)"

    def test_queue_wait_skipped_when_no_timestamp(self):
        fake_translator = MagicMock()
        fake_result = MagicMock()
        fake_result.hypotheses = [["▁hola", "</s>"]]
        fake_translator.translate_batch.return_value = [fake_result]

        with patch.object(_nllb_main, "_translator", fake_translator), patch.object(
            _nllb_main,
            "_tokenizer",
            MagicMock(Encode=lambda t, out_type=str: ["▁hello"], Decode=lambda tokens: "hola"),
        ):

            with patch.object(_nllb_main.QUEUE_WAIT, "observe") as mock_observe:
                _nllb_main._translate_batch(["hello"], "eng_Latn", "spa_Latn", t_queued=0.0)
                mock_observe.assert_not_called()


class TestEndpointQueueWaitPassthrough(unittest.TestCase):

    def test_translate_endpoint_passes_t_queued_to_executor(self):
        import asyncio

        captured_partials = []
        original_partial = partial

        def capturing_run_in_executor(pool, func):
            captured_partials.append(func)
            fake_result = MagicMock()
            fake_result.hypotheses = [["▁hola", "</s>"]]
            fake_translator = MagicMock()
            fake_translator.translate_batch.return_value = [fake_result]
            with patch.object(_nllb_main, "_translator", fake_translator), patch.object(
                _nllb_main,
                "_tokenizer",
                MagicMock(Encode=lambda t, out_type=str: ["▁hello"], Decode=lambda tokens: "hola"),
            ):
                result = func()
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(result)
            return fut

        loop = asyncio.new_event_loop()
        try:
            req = _nllb_main.TranslateRequest(contents=["hello"], target_language_code="es")
            mock_loop = MagicMock()
            mock_loop.run_in_executor = MagicMock(side_effect=capturing_run_in_executor)

            with patch("asyncio.get_running_loop", return_value=mock_loop):
                result = loop.run_until_complete(_nllb_main.translate(req))

            assert len(captured_partials) == 1, "Expected one executor call"
            func = captured_partials[0]
            assert isinstance(func, partial), "Executor func should be a partial"
            assert func.keywords.get('t_queued', 0) > 0 or (
                len(func.args) >= 4 and func.args[3] > 0
            ), "t_queued must be passed to _translate_batch via partial()"
        finally:
            loop.close()


class TestModelLoadMetric(unittest.TestCase):

    def test_model_load_sets_duration_gauge(self):
        with patch.object(_nllb_main, "ctranslate2") as mock_ct2, patch.object(_nllb_main, "spm") as mock_spm, patch(
            "os.path.exists", return_value=True
        ), patch.object(_nllb_main.MODEL_LOAD_DURATION, "set") as mock_duration, patch.object(
            _nllb_main.MODEL_LOADED, "set"
        ) as mock_loaded:

            mock_spp = MagicMock()
            mock_spm.SentencePieceProcessor.return_value = mock_spp

            _nllb_main._load_model()

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


class TestAdmissionControl(unittest.TestCase):
    """503-at-cap admission (SCA-439): reject immediately instead of queueing forever."""

    def _request(self):
        return _nllb_main.TranslateRequest(contents=["hello"], target_language_code="es")

    def test_max_in_flight_at_least_worker_count(self):
        assert _nllb_main.MAX_IN_FLIGHT >= _nllb_main.INFERENCE_WORKERS
        assert _nllb_main.MAX_IN_FLIGHT == _nllb_main.INFERENCE_WORKERS * 2  # default cap

    def test_translate_rejects_503_at_cap_without_executor(self):
        drained = asyncio.Semaphore(0)  # locked(): admission full
        mock_loop = MagicMock()
        with patch.object(_nllb_main, "_admission", drained), patch.object(
            _nllb_main, "_translate_batch", MagicMock()
        ) as mock_batch, patch("asyncio.get_running_loop", return_value=mock_loop):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_nllb_main.translate(self._request()))
        assert ctx.exception.status_code == 503
        assert ctx.exception.detail == "admission_full"
        mock_batch.assert_not_called()
        mock_loop.run_in_executor.assert_not_called()

    def test_active_requests_gauge_not_incremented_on_reject(self):
        drained = asyncio.Semaphore(0)
        with patch.object(_nllb_main, "_admission", drained), patch.object(
            _nllb_main.ACTIVE_REQUESTS, "inc"
        ) as mock_inc, patch.object(_nllb_main.ACTIVE_REQUESTS, "dec") as mock_dec:
            with self.assertRaises(HTTPException):
                asyncio.run(_nllb_main.translate(self._request()))
        mock_inc.assert_not_called()
        mock_dec.assert_not_called()


class TestReadinessShed(unittest.TestCase):
    """/ready sheds load when saturated so kube drops the pod from Endpoints."""

    def test_ready_503_when_model_not_loaded(self):
        with patch.object(_nllb_main, "_translator", None), patch.object(_nllb_main, "_tokenizer", None):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_nllb_main.ready())
        assert ctx.exception.status_code == 503

    def test_ready_503_when_in_flight_at_cap(self):
        model = MagicMock()
        with patch.object(_nllb_main, "_translator", model), patch.object(
            _nllb_main, "_tokenizer", model
        ), patch.object(_nllb_main, "_in_flight", _nllb_main.MAX_IN_FLIGHT):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_nllb_main.ready())
        assert ctx.exception.status_code == 503
        assert ctx.exception.detail == "saturated"

    def test_ready_200_when_model_loaded_and_below_cap(self):
        model = MagicMock()
        with patch.object(_nllb_main, "_translator", model), patch.object(
            _nllb_main, "_tokenizer", model
        ), patch.object(_nllb_main, "_in_flight", _nllb_main.MAX_IN_FLIGHT - 1):
            assert asyncio.run(_nllb_main.ready()) == {"status": "ready"}


class TestLivenessSaturation(unittest.TestCase):
    """/live kills the pod only when saturation is continuous past the window."""

    def test_live_200_on_short_saturation_burst(self):
        with patch.object(_nllb_main, "_saturation_since", time.monotonic()):
            assert asyncio.run(_nllb_main.live()) == {"status": "alive"}

    def test_live_200_when_not_saturated(self):
        with patch.object(_nllb_main, "_saturation_since", None):
            assert asyncio.run(_nllb_main.live()) == {"status": "alive"}

    def test_live_503_after_continuous_saturation_window(self):
        started = time.monotonic() - (_nllb_main.SATURATED_LIVE_SECONDS + 1)
        with patch.object(_nllb_main, "_saturation_since", started):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_nllb_main.live())
        assert ctx.exception.status_code == 503
        assert ctx.exception.detail == "saturated"

    def test_live_503_immediately_when_threshold_is_zero(self):
        with patch.object(_nllb_main, "_saturation_since", time.monotonic()), patch.object(
            _nllb_main, "SATURATED_LIVE_SECONDS", 0
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(_nllb_main.live())
        assert ctx.exception.status_code == 503

    def test_saturation_tracker_stamps_on_crossing_and_clears_below_cap(self):
        with patch.object(_nllb_main, "_in_flight", _nllb_main.MAX_IN_FLIGHT), patch.object(
            _nllb_main, "_saturation_since", None
        ):
            _nllb_main._update_saturation()
            self.assertIsNotNone(_nllb_main._saturation_since)
        with patch.object(_nllb_main, "_in_flight", _nllb_main.MAX_IN_FLIGHT - 1):
            _nllb_main._update_saturation()
            self.assertIsNone(_nllb_main._saturation_since)


class TestHealthUnaffectedBySaturation(unittest.TestCase):
    """/health must stay 200 while saturated — the startup probe cannot die."""

    def test_health_200_while_saturated(self):
        with patch.object(_nllb_main, "_in_flight", _nllb_main.MAX_IN_FLIGHT), patch.object(
            _nllb_main, "_saturation_since", time.monotonic() - 3600
        ):
            result = asyncio.run(_nllb_main.health())
        assert result["status"] == "ok"


if __name__ == "__main__":
    unittest.main()
