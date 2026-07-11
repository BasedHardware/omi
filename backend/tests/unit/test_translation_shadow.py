"""Tests for NLLB shadow translation deployment.

Verifies:
- Shadow mode returns Google output unchanged
- Shadow never writes to cache
- Shadow errors don't affect returned text
- BCP-47 to NLLB language mapping
- Shadow scheduling and fire-and-forget behavior
"""

import importlib.util
import os
import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

_saved_modules = {}
_mock_translate_client = None
_mock_redis = None
_TranslationService = None
_translation_module = None


def _ensure_mock_module(name):
    if name not in sys.modules:
        mod = MagicMock()
        mod.__path__ = []
        mod.__name__ = name
        mod.__loader__ = None
        mod.__spec__ = None
        mod.__package__ = name if '.' not in name else name.rsplit('.', 1)[0]
        sys.modules[name] = mod
    return sys.modules[name]


def _restore_package_path(name, path):
    module = sys.modules.get(name)
    if module is not None:
        module.__path__ = [path]


def _restore_real_backend_package(package_name):
    if _BACKEND_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_DIR)
    package = sys.modules.get(package_name)
    if package is None:
        return
    expected_dir = os.path.abspath(os.path.join(_BACKEND_DIR, package_name))
    package_paths = getattr(package, "__path__", None)
    if not package_paths:
        sys.modules.pop(package_name, None)
        return
    try:
        has_real_path = any(os.path.abspath(str(path)) == expected_dir for path in package_paths)
    except TypeError:
        has_real_path = False
    if not has_real_path:
        sys.modules.pop(package_name, None)


def _install_langdetect_stub():
    if 'langdetect' not in sys.modules and importlib.util.find_spec('langdetect') is not None:
        return
    langdetect_mod = sys.modules.get('langdetect') or ModuleType('langdetect')
    exception_mod = sys.modules.get('langdetect.lang_detect_exception') or ModuleType(
        'langdetect.lang_detect_exception'
    )

    class LangDetectException(Exception):
        pass

    class DetectorFactory:
        seed = None

    class _DetectedLang:
        def __init__(self, lang, prob):
            self.lang = lang
            self.prob = prob

    def detect(text):
        return 'en'

    def detect_langs(text):
        return [_DetectedLang('en', 0.99)]

    exception_mod.LangDetectException = LangDetectException
    langdetect_mod.detect = detect
    langdetect_mod.detect_langs = detect_langs
    langdetect_mod.DetectorFactory = DetectorFactory
    langdetect_mod.lang_detect_exception = exception_mod
    sys.modules['langdetect'] = langdetect_mod
    sys.modules['langdetect.lang_detect_exception'] = exception_mod


def setUpModule():
    global _saved_modules, _mock_translate_client, _mock_redis, _TranslationService, _translation_module

    _saved_modules = dict(sys.modules)

    _restore_package_path('utils', os.path.join(_BACKEND_DIR, 'utils'))
    _restore_package_path('models', os.path.join(_BACKEND_DIR, 'models'))
    _install_langdetect_stub()

    _ensure_mock_module("database")
    sys.modules["database"].__path__ = getattr(sys.modules["database"], '__path__', [])
    for sub in ["_client", "redis_db", "auth", "users", "memories", "conversations", "apps", "vector_db"]:
        _ensure_mock_module(f"database.{sub}")

    _mock_redis = MagicMock()
    sys.modules["database.redis_db"].r = _mock_redis

    _ensure_mock_module("google")
    sys.modules["google"].__path__ = []
    _ensure_mock_module("google.cloud")
    sys.modules["google.cloud"].__path__ = []
    _ensure_mock_module("google.cloud.translate_v3")
    sys.modules["google.cloud"].translate_v3 = sys.modules["google.cloud.translate_v3"]

    _mock_translate_client = MagicMock()
    sys.modules["google.cloud.translate_v3"].TranslationServiceClient = MagicMock(return_value=_mock_translate_client)

    _restore_real_backend_package("utils")
    _restore_real_backend_package("models")
    for mod_name in list(sys.modules.keys()):
        if 'translation' in mod_name and 'test' not in mod_name:
            del sys.modules[mod_name]

    from utils.translation import TranslationService
    import utils.translation as tm

    _TranslationService = TranslationService
    _translation_module = tm


def tearDownModule():
    added = set(sys.modules.keys()) - set(_saved_modules.keys())
    for key in added:
        del sys.modules[key]
    sys.modules.update(_saved_modules)


class TestTranslateGoogleBatchHelper(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_google_batch_returns_tuples(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola"
        t1.detected_language_code = "en"
        t2 = MagicMock()
        t2.translated_text = "Mundo"
        t2.detected_language_code = "en"
        mock_response.translations = [t1, t2]
        _mock_translate_client.translate_text.return_value = mock_response

        results = self.service._translate_google_batch(["Hello", "World"], "es")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], ("Hola", "en"))
        self.assertEqual(results[1], ("Mundo", "en"))

    def test_google_batch_passes_correct_args(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola"
        t1.detected_language_code = "en"
        mock_response.translations = [t1]
        _mock_translate_client.translate_text.return_value = mock_response

        self.service._translate_google_batch(["Hello"], "es")
        call_kwargs = _mock_translate_client.translate_text.call_args[1]
        self.assertEqual(call_kwargs["contents"], ["Hello"])
        self.assertEqual(call_kwargs["target_language_code"], "es")
        self.assertIn("parent", call_kwargs)
        self.assertIn("mime_type", call_kwargs)

    def test_google_batch_none_detected_lang(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Test"
        t1.detected_language_code = None
        mock_response.translations = [t1]
        _mock_translate_client.translate_text.return_value = mock_response

        results = self.service._translate_google_batch(["Test"], "en")
        self.assertEqual(results[0], ("Test", ""))


class TestShadowCompareIsolation(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_shadow_not_called_in_google_mode(self):
        original = _translation_module.TRANSLATION_PROVIDER
        _set_translation_provider(_translation_module, "google")
        try:
            with patch.object(self.service, '_run_shadow_compare') as mock_shadow:
                self.service._schedule_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                mock_shadow.assert_not_called()
        finally:
            _translation_module.TRANSLATION_PROVIDER = original
            _translation_module.TRANSLATION_MODE = original.value

    def test_shadow_not_called_without_url(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = ""
        try:
            with patch.object(self.service, '_run_shadow_compare') as mock_shadow:
                self.service._schedule_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                mock_shadow.assert_not_called()
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url

    def test_shadow_error_does_not_propagate(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
        except Exception:
            self.fail("Shadow compare should not propagate exceptions")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowNeverWritesCache(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_translate_text_returns_google_in_shadow_mode(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola mundo"
        t1.detected_language_code = "en"
        mock_response.translations = [t1]
        _mock_translate_client.translate_text.return_value = mock_response
        _mock_redis.get.return_value = None

        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            with patch.object(self.service, '_schedule_shadow_compare') as mock_shadow:
                result = self.service.translate_text("es", "Hello world")
                self.assertEqual(result[0], "Hola mundo")
                self.assertEqual(result[1], "en")
                mock_shadow.assert_called_once()
                call_args = mock_shadow.call_args
                self.assertEqual(call_args[0][0], "translate_text")
                self.assertEqual(call_args[0][1], "es")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowCompareLogging(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_shadow_compare_logs_without_raw_text(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "translations": [{"translated_text": "Hola mundo", "detected_language_code": "en"}],
            "model": "facebook/nllb-200-distilled-600M",
            "latency_ms": 42,
        }
        mock_client.post.return_value = mock_resp

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                with patch("utils.translation.logger") as mock_logger:
                    self.service._shadow_client = None
                    self.service._run_shadow_compare("translate_text", "es", ["Hello world"], [("Hola mundo", "en")])
                    for call in mock_logger.info.call_args_list:
                        call_str = str(call)
                        self.assertNotIn("Hello world", call_str)
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None

    def test_shadow_compare_exact_match_ratio(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "translations": [
                {"translated_text": "Hola", "detected_language_code": "en"},
                {"translated_text": "Mundo", "detected_language_code": "en"},
            ],
            "model": "nllb",
        }
        mock_client.post.return_value = mock_resp

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                with patch("utils.translation.logger") as mock_logger:
                    self.service._shadow_client = None
                    self.service._run_shadow_compare(
                        "test", "es", ["Hello", "World"], [("Hola", "en"), ("Mundo", "en")]
                    )
                    info_calls = mock_logger.info.call_args_list
                    self.assertTrue(len(info_calls) > 0, "Should log comparison")
                    call_args = info_calls[0]
                    self.assertIn("exact_match_ratio", call_args[0][0])
                    self.assertAlmostEqual(call_args[0][5], 1.0)
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None


class TestShadowCallsitesCoverage(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_translate_text_by_sentence_schedules_shadow(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola."
        t1.detected_language_code = "en"
        t2 = MagicMock()
        t2.translated_text = "Mundo."
        t2.detected_language_code = "en"
        mock_response.translations = [t1, t2]
        _mock_translate_client.translate_text.return_value = mock_response
        _mock_redis.get.return_value = None

        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            with patch.object(self.service, '_schedule_shadow_compare') as mock_shadow:
                self.service.translate_text_by_sentence("es", "Hello. World.")
                mock_shadow.assert_called()
                call_args = mock_shadow.call_args
                self.assertEqual(call_args[0][0], "translate_text_by_sentence")
                self.assertEqual(call_args[0][1], "es")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url

    def test_translate_units_batch_schedules_shadow(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola mundo"
        t1.detected_language_code = "en"
        mock_response.translations = [t1]
        _mock_translate_client.translate_text.return_value = mock_response
        _mock_redis.get.return_value = None

        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            with patch.object(self.service, '_schedule_shadow_compare') as mock_shadow:
                units = [("seg1", "Hello world")]
                self.service.translate_units_batch("es", units)
                mock_shadow.assert_called()
                call_args = mock_shadow.call_args
                self.assertEqual(call_args[0][0], "translate_units_batch")
                self.assertEqual(call_args[0][1], "es")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowTimeoutHandling(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_shadow_timeout_does_not_propagate(self):
        import httpx as _httpx

        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_client.post.side_effect = _httpx.TimeoutException("read timeout")

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                self.service._shadow_client = None
                self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
        except Exception:
            self.fail("Shadow timeout should not propagate")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None

    def test_shadow_timeout_logs_warning(self):
        import httpx as _httpx

        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_client.post.side_effect = _httpx.TimeoutException("read timeout")

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                with patch("utils.translation.record_fallback") as mock_fallback:
                    self.service._shadow_client = None
                    self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                    mock_fallback.assert_called_once()
                    call_kwargs = mock_fallback.call_args[1]
                    self.assertEqual(call_kwargs["from_mode"], "shadow")
                    self.assertEqual(call_kwargs["to_mode"], "google")
                    self.assertEqual(call_kwargs["outcome"], "degraded")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None


class TestShadowExecutorScheduling(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_schedule_submits_to_postprocess_executor(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            with patch("utils.translation.submit_with_context") as mock_submit:
                self.service._schedule_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                mock_submit.assert_called_once()
                args = mock_submit.call_args[0]
                from utils.executors import postprocess_executor

                self.assertIs(args[0], postprocess_executor)
                self.assertEqual(args[1], self.service._run_shadow_compare)
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowNon200Fallback(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_non_200_calls_record_fallback(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.post.return_value = mock_resp

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                with patch("utils.translation.record_fallback") as mock_fallback:
                    self.service._shadow_client = None
                    self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                    mock_fallback.assert_called_once()
                    call_kwargs = mock_fallback.call_args[1]
                    self.assertEqual(call_kwargs["from_mode"], "shadow")
                    self.assertEqual(call_kwargs["to_mode"], "google")
                    self.assertEqual(call_kwargs["outcome"], "degraded")
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None


class TestShadowCacheIsolation(unittest.TestCase):

    def setUp(self):
        self.service = _TranslationService()

    def test_shadow_compare_never_writes_cache(self):
        original_provider = _translation_module.TRANSLATION_PROVIDER
        original_url = _translation_module.HOSTED_TRANSLATION_API_URL
        _set_translation_provider(_translation_module, "shadow")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        self.service._shadow_client = None

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "translations": [{"translated_text": "Hola", "detected_language_code": "en"}],
            "model": "nllb",
        }
        mock_client.post.return_value = mock_resp

        try:
            with patch("utils.translation.httpx.Client", return_value=mock_client):
                with patch("utils.translation.cache_translation") as mock_cache:
                    with patch.object(self.service, '_set_memory_cache') as mock_mem:
                        self.service._shadow_client = None
                        self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                        mock_cache.assert_not_called()
                        mock_mem.assert_not_called()
        finally:
            _translation_module.TRANSLATION_PROVIDER = original_provider
            _translation_module.TRANSLATION_MODE = original_provider.value
            _translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None


class TestNLLBLanguageMapping(unittest.TestCase):

    def test_nllb_service_language_mapping(self):
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from nllb_translation.main import BCP47_TO_NLLB

            expected = {
                "en": "eng_Latn",
                "es": "spa_Latn",
                "zh": "zho_Hans",
                "zh-TW": "zho_Hant",
                "hi": "hin_Deva",
                "pt": "por_Latn",
                "ru": "rus_Cyrl",
                "ja": "jpn_Jpan",
                "de": "deu_Latn",
                "ar": "arb_Arab",
                "fr": "fra_Latn",
                "it": "ita_Latn",
                "ko": "kor_Hang",
                "nl": "nld_Latn",
                "th": "tha_Thai",
                "tr": "tur_Latn",
                "uk": "ukr_Cyrl",
                "ur": "urd_Arab",
                "vi": "vie_Latn",
            }
            for bcp47, expected_nllb in expected.items():
                self.assertEqual(BCP47_TO_NLLB[bcp47], expected_nllb)
        except ImportError:
            self.skipTest("nllb_translation dependencies not installed (ctranslate2, sentencepiece)")

    def test_resolve_nllb_code_with_locale(self):
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from nllb_translation.main import _resolve_nllb_code

            self.assertEqual(_resolve_nllb_code("en-US"), "eng_Latn")
            self.assertEqual(_resolve_nllb_code("fr-CA"), "fra_Latn")
            self.assertEqual(_resolve_nllb_code("pt-BR"), "por_Latn")
        except ImportError:
            self.skipTest("nllb_translation dependencies not installed")

    def test_resolve_nllb_code_unsupported(self):
        sys.path.insert(0, _BACKEND_DIR)
        try:
            from nllb_translation.main import _resolve_nllb_code

            self.assertIsNone(_resolve_nllb_code("xx"))
            self.assertIsNone(_resolve_nllb_code(""))
        except ImportError:
            self.skipTest("nllb_translation dependencies not installed")


def _set_translation_provider(module, mode_str: str):
    """Helper: set both TRANSLATION_PROVIDER enum and TRANSLATION_MODE string."""
    module.TRANSLATION_PROVIDER = module.TranslationProvider(mode_str)
    module.TRANSLATION_MODE = mode_str


class TestNllbPrimaryMode(unittest.TestCase):
    """Tests for TRANSLATION_PROVIDER=nllb where NLLB is the primary provider."""

    def setUp(self):
        self.service = _TranslationService()
        self._orig_provider = _translation_module.TRANSLATION_PROVIDER
        self._orig_mode = _translation_module.TRANSLATION_MODE
        self._orig_url = _translation_module.HOSTED_TRANSLATION_API_URL

    def tearDown(self):
        _translation_module.TRANSLATION_PROVIDER = self._orig_provider
        _translation_module.TRANSLATION_MODE = self._orig_mode
        _translation_module.HOSTED_TRANSLATION_API_URL = self._orig_url
        self.service._nllb_client = None

    def test_nllb_batch_returns_translations(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "translations": [
                {"translated_text": "Hola", "detected_language_code": "en"},
                {"translated_text": "Mundo", "detected_language_code": "en"},
            ],
            "model": "nllb-200-distilled-600M",
            "latency_ms": 42,
        }
        mock_client.post.return_value = mock_resp

        with patch("utils.translation.httpx.Client", return_value=mock_client):
            self.service._nllb_client = None
            results = self.service._translate_nllb_batch(["Hello", "World"], "es")
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0], ("Hola", "en"))
            self.assertEqual(results[1], ("Mundo", "en"))

    def test_nllb_batch_sends_source_language_code(self):
        """Regression: NLLB primary must send source_language_code in the payload."""
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "translations": [{"translated_text": "Hola", "detected_language_code": "en"}],
            "latency_ms": 10,
        }
        mock_client.post.return_value = mock_resp

        with patch("utils.translation.httpx.Client", return_value=mock_client):
            self.service._nllb_client = None
            self.service._translate_nllb_batch(["Hello"], "es", source_language="en")
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            self.assertEqual(payload["source_language_code"], "en")
            self.assertEqual(payload["target_language_code"], "es")

    def test_nllb_batch_omits_source_when_empty(self):
        """When source_language is empty, payload should not include source_language_code."""
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "translations": [{"translated_text": "Hola", "detected_language_code": ""}],
            "latency_ms": 10,
        }
        mock_client.post.return_value = mock_resp

        with patch("utils.translation.httpx.Client", return_value=mock_client):
            self.service._nllb_client = None
            self.service._translate_nllb_batch(["Hello"], "es")
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            self.assertNotIn("source_language_code", payload)

    def test_nllb_batch_auto_detects_source_language(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "translations": [
                {"translated_text": "Hello everyone, welcome to today's meeting", "detected_language_code": "es"}
            ],
            "latency_ms": 10,
        }
        mock_client.post.return_value = mock_resp

        with patch("utils.translation.httpx.Client", return_value=mock_client):
            with patch.object(self.service, '_detect_source_language', return_value="es"):
                self.service._nllb_client = None
                self.service._translate_nllb_batch(["Hola a todos, bienvenidos a la reunión de hoy"], "en")
                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                self.assertEqual(payload["source_language_code"], "es")

    def test_detect_source_language_normalizes_zh_cn(self):
        with patch("utils.translation.langdetect_detect", return_value="zh-cn"):
            result = self.service._detect_source_language(["This is long enough text for detection"])
            self.assertEqual(result, "zh-cn")

    def test_detect_source_language_short_text_returns_empty(self):
        result = self.service._detect_source_language(["short"])
        self.assertEqual(result, "")

    def test_detect_source_language_langdetect_exception_returns_empty(self):
        with patch(
            "utils.translation.langdetect_detect",
            side_effect=_translation_module.LangDetectException("fail"),
        ):
            result = self.service._detect_source_language(["This is enough text for language detection attempt"])
            self.assertEqual(result, "")

    def test_detect_source_language_unreliable_lang_returns_empty(self):
        with patch("utils.translation.langdetect_detect", return_value="xx"):
            result = self.service._detect_source_language(["This is enough text for detection but unreliable"])
            self.assertEqual(result, "")

    def test_nllb_batch_malformed_response_returns_empty(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"no_translations_key": []}
        mock_client.post.return_value = mock_resp

        with patch("utils.translation.httpx.Client", return_value=mock_client):
            self.service._nllb_client = None
            results = self.service._translate_nllb_batch(["Hello"], "es")
            self.assertEqual(results, [])

    def test_nllb_fallback_both_fail_raises(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        with patch.object(self.service, '_translate_nllb_batch', side_effect=Exception("nllb down")):
            with patch.object(self.service, '_translate_google_batch', side_effect=Exception("google down")):
                with patch("utils.translation.record_fallback"):
                    with self.assertRaises(Exception) as ctx:
                        self.service._translate_batch(["Hello"], "es")
                    self.assertIn("google down", str(ctx.exception))

    def test_prometheus_idempotent_counter(self):
        counter1 = _translation_module._counter("test_idempotent_counter", "Test counter", ["label1"])
        counter2 = _translation_module._counter("test_idempotent_counter", "Test counter", ["label1"])
        self.assertIs(counter1, counter2)

    def test_prometheus_idempotent_histogram(self):
        h1 = _translation_module._histogram("test_idempotent_histogram", "Test histogram", ["label1"], [0.1, 0.5, 1.0])
        h2 = _translation_module._histogram("test_idempotent_histogram", "Test histogram", ["label1"], [0.1, 0.5, 1.0])
        self.assertIs(h1, h2)

    def test_translate_batch_uses_nllb_when_mode_nllb(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        with patch.object(self.service, '_translate_nllb_batch', return_value=[("Hola", "en")]) as mock_nllb:
            with patch.object(self.service, '_translate_google_batch') as mock_google:
                results = self.service._translate_batch(["Hello"], "es")
                mock_nllb.assert_called_once_with(["Hello"], "es", source_language="")
                mock_google.assert_not_called()
                self.assertEqual(results, [("Hola", "en")])

    def test_translate_batch_passes_source_language_to_nllb(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        with patch.object(self.service, '_translate_nllb_batch', return_value=[("Hola", "en")]) as mock_nllb:
            results = self.service._translate_batch(["Hello"], "es", source_language="en")
            mock_nllb.assert_called_once_with(["Hello"], "es", source_language="en")
            self.assertEqual(results, [("Hola", "en")])

    def test_translate_batch_falls_back_to_google_on_nllb_error(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"

        with patch.object(self.service, '_translate_nllb_batch', side_effect=Exception("connection refused")):
            with patch.object(self.service, '_translate_google_batch', return_value=[("Hola", "en")]) as mock_google:
                with patch("utils.translation.record_fallback") as mock_fallback:
                    results = self.service._translate_batch(["Hello"], "es")
                    mock_google.assert_called_once()
                    mock_fallback.assert_called_once()
                    call_kwargs = mock_fallback.call_args[1]
                    self.assertEqual(call_kwargs["from_mode"], "nllb")
                    self.assertEqual(call_kwargs["to_mode"], "google")
                    self.assertEqual(call_kwargs["outcome"], "recovered")
                    self.assertEqual(results, [("Hola", "en")])

    def test_translate_batch_uses_google_in_google_mode(self):
        _set_translation_provider(_translation_module, "google")
        _translation_module.HOSTED_TRANSLATION_API_URL = ""

        with patch.object(self.service, '_translate_nllb_batch') as mock_nllb:
            with patch.object(self.service, '_translate_google_batch', return_value=[("Hola", "en")]) as mock_google:
                results = self.service._translate_batch(["Hello"], "es")
                mock_google.assert_called_once()
                mock_nllb.assert_not_called()

    def test_translate_text_uses_nllb_in_nllb_mode(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        _mock_redis.get.return_value = None

        with patch.object(self.service, '_translate_batch', return_value=[("Hola mundo", "en")]) as mock_batch:
            result = self.service.translate_text("es", "Hello world")
            self.assertEqual(result[0], "Hola mundo")
            mock_batch.assert_called_once()

    def test_translate_units_batch_uses_nllb_in_nllb_mode(self):
        _set_translation_provider(_translation_module, "nllb")
        _translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        _mock_redis.get.return_value = None

        with patch.object(self.service, '_translate_batch', return_value=[("Hola mundo", "en")]) as mock_batch:
            units = [("seg1", "Hello world")]
            results = self.service.translate_units_batch("es", units)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0], "seg1")
            self.assertEqual(results[0][1], "Hola mundo")
            mock_batch.assert_called()


class TestTranslationModeAutoDetect(unittest.TestCase):
    """Tests for auto-detection of TRANSLATION_MODE based on HOSTED_TRANSLATION_API_URL."""

    def test_auto_detect_nllb_when_url_set(self):
        import importlib

        orig_env_mode = os.environ.get("TRANSLATION_MODE", "")
        orig_env_url = os.environ.get("HOSTED_TRANSLATION_API_URL", "")
        try:
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            import utils.translation as tm_fresh

            self.assertEqual(tm_fresh.TRANSLATION_MODE, "nllb")
        finally:
            if orig_env_mode:
                os.environ["TRANSLATION_MODE"] = orig_env_mode
            else:
                os.environ.pop("TRANSLATION_MODE", None)
            if orig_env_url:
                os.environ["HOSTED_TRANSLATION_API_URL"] = orig_env_url
            else:
                os.environ.pop("HOSTED_TRANSLATION_API_URL", None)
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            from utils.translation import TranslationService
            import utils.translation as tm_restored

            globals()['_TranslationService'] = TranslationService
            globals()['_translation_module'] = tm_restored

    def test_auto_detect_google_when_no_url(self):
        import importlib

        orig_env_mode = os.environ.get("TRANSLATION_MODE", "")
        orig_env_url = os.environ.get("HOSTED_TRANSLATION_API_URL", "")
        try:
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ.pop("HOSTED_TRANSLATION_API_URL", None)
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            import utils.translation as tm_fresh

            self.assertEqual(tm_fresh.TRANSLATION_MODE, "google")
        finally:
            if orig_env_mode:
                os.environ["TRANSLATION_MODE"] = orig_env_mode
            else:
                os.environ.pop("TRANSLATION_MODE", None)
            if orig_env_url:
                os.environ["HOSTED_TRANSLATION_API_URL"] = orig_env_url
            else:
                os.environ.pop("HOSTED_TRANSLATION_API_URL", None)
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            from utils.translation import TranslationService
            import utils.translation as tm_restored

            globals()['_TranslationService'] = TranslationService
            globals()['_translation_module'] = tm_restored

    def test_explicit_mode_overrides_auto_detect(self):
        orig_env_mode = os.environ.get("TRANSLATION_MODE", "")
        orig_env_url = os.environ.get("HOSTED_TRANSLATION_API_URL", "")
        try:
            os.environ["TRANSLATION_MODE"] = "shadow"
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            import utils.translation as tm_fresh

            self.assertEqual(tm_fresh.TRANSLATION_MODE, "shadow")
        finally:
            if orig_env_mode:
                os.environ["TRANSLATION_MODE"] = orig_env_mode
            else:
                os.environ.pop("TRANSLATION_MODE", None)
            if orig_env_url:
                os.environ["HOSTED_TRANSLATION_API_URL"] = orig_env_url
            else:
                os.environ.pop("HOSTED_TRANSLATION_API_URL", None)
            for mod_name in list(sys.modules.keys()):
                if 'translation' in mod_name and 'test' not in mod_name:
                    del sys.modules[mod_name]
            _restore_real_backend_package("utils")
            from utils.translation import TranslationService
            import utils.translation as tm_restored

            globals()['_TranslationService'] = TranslationService
            globals()['_translation_module'] = tm_restored


class TestTranslationServiceModels(unittest.TestCase):
    """Tests for TRANSLATION_SERVICE_MODELS provider selection (STT-style config)."""

    def _reimport(self):
        for mod_name in list(sys.modules.keys()):
            if 'translation' in mod_name and 'test' not in mod_name:
                del sys.modules[mod_name]
        _restore_real_backend_package("utils")
        import utils.translation as tm_fresh

        return tm_fresh

    def _cleanup(self, orig_envs):
        for key, val in orig_envs.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
        for mod_name in list(sys.modules.keys()):
            if 'translation' in mod_name and 'test' not in mod_name:
                del sys.modules[mod_name]
        _restore_real_backend_package("utils")
        from utils.translation import TranslationService
        import utils.translation as tm_restored

        globals()['_TranslationService'] = TranslationService
        globals()['_translation_module'] = tm_restored

    def test_service_models_nllb_with_url(self):
        orig = {
            "TRANSLATION_SERVICE_MODELS": os.environ.get("TRANSLATION_SERVICE_MODELS"),
            "TRANSLATION_MODE": os.environ.get("TRANSLATION_MODE"),
            "HOSTED_TRANSLATION_API_URL": os.environ.get("HOSTED_TRANSLATION_API_URL"),
        }
        try:
            os.environ["TRANSLATION_SERVICE_MODELS"] = "nllb,google"
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            tm = self._reimport()
            self.assertEqual(tm.TRANSLATION_PROVIDER.value, "nllb")
            self.assertEqual(tm.TRANSLATION_MODE, "nllb")
        finally:
            self._cleanup(orig)

    def test_service_models_google_first(self):
        orig = {
            "TRANSLATION_SERVICE_MODELS": os.environ.get("TRANSLATION_SERVICE_MODELS"),
            "TRANSLATION_MODE": os.environ.get("TRANSLATION_MODE"),
            "HOSTED_TRANSLATION_API_URL": os.environ.get("HOSTED_TRANSLATION_API_URL"),
        }
        try:
            os.environ["TRANSLATION_SERVICE_MODELS"] = "google,nllb"
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            tm = self._reimport()
            self.assertEqual(tm.TRANSLATION_PROVIDER.value, "google")
        finally:
            self._cleanup(orig)

    def test_service_models_nllb_skipped_without_url(self):
        orig = {
            "TRANSLATION_SERVICE_MODELS": os.environ.get("TRANSLATION_SERVICE_MODELS"),
            "TRANSLATION_MODE": os.environ.get("TRANSLATION_MODE"),
            "HOSTED_TRANSLATION_API_URL": os.environ.get("HOSTED_TRANSLATION_API_URL"),
        }
        try:
            os.environ["TRANSLATION_SERVICE_MODELS"] = "nllb,google"
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ.pop("HOSTED_TRANSLATION_API_URL", None)
            tm = self._reimport()
            self.assertEqual(tm.TRANSLATION_PROVIDER.value, "google")
        finally:
            self._cleanup(orig)

    def test_service_models_shadow_with_url(self):
        orig = {
            "TRANSLATION_SERVICE_MODELS": os.environ.get("TRANSLATION_SERVICE_MODELS"),
            "TRANSLATION_MODE": os.environ.get("TRANSLATION_MODE"),
            "HOSTED_TRANSLATION_API_URL": os.environ.get("HOSTED_TRANSLATION_API_URL"),
        }
        try:
            os.environ["TRANSLATION_SERVICE_MODELS"] = "shadow"
            os.environ.pop("TRANSLATION_MODE", None)
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            tm = self._reimport()
            self.assertEqual(tm.TRANSLATION_PROVIDER.value, "shadow")
        finally:
            self._cleanup(orig)

    def test_service_models_overrides_legacy_mode(self):
        orig = {
            "TRANSLATION_SERVICE_MODELS": os.environ.get("TRANSLATION_SERVICE_MODELS"),
            "TRANSLATION_MODE": os.environ.get("TRANSLATION_MODE"),
            "HOSTED_TRANSLATION_API_URL": os.environ.get("HOSTED_TRANSLATION_API_URL"),
        }
        try:
            os.environ["TRANSLATION_SERVICE_MODELS"] = "google"
            os.environ["TRANSLATION_MODE"] = "nllb"
            os.environ["HOSTED_TRANSLATION_API_URL"] = "http://nllb:8080"
            tm = self._reimport()
            self.assertEqual(tm.TRANSLATION_PROVIDER.value, "google")
        finally:
            self._cleanup(orig)


if __name__ == "__main__":
    unittest.main()
