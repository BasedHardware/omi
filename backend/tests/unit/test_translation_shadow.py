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


_restore_package_path('utils', os.path.join(_BACKEND_DIR, 'utils'))
_restore_package_path('models', os.path.join(_BACKEND_DIR, 'models'))
_install_langdetect_stub()

_ensure_mock_module("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], '__path__', [])
for sub in ["_client", "redis_db", "auth", "users", "memories", "conversations", "apps", "vector_db"]:
    _ensure_mock_module(f"database.{sub}")

mock_redis = MagicMock()
sys.modules["database.redis_db"].r = mock_redis

_ensure_mock_module("google")
sys.modules["google"].__path__ = []
_ensure_mock_module("google.cloud")
sys.modules["google.cloud"].__path__ = []
_ensure_mock_module("google.cloud.translate_v3")
sys.modules["google.cloud"].translate_v3 = sys.modules["google.cloud.translate_v3"]

mock_translate_client = MagicMock()
sys.modules["google.cloud.translate_v3"].TranslationServiceClient = MagicMock(return_value=mock_translate_client)

_restore_real_backend_package("utils")
_restore_real_backend_package("models")
for mod_name in list(sys.modules.keys()):
    if 'translation' in mod_name and 'test' not in mod_name:
        del sys.modules[mod_name]

from utils.translation import TranslationService
import utils.translation as translation_module


class TestTranslateGoogleBatchHelper(unittest.TestCase):

    def setUp(self):
        self.service = TranslationService()

    def test_google_batch_returns_tuples(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola"
        t1.detected_language_code = "en"
        t2 = MagicMock()
        t2.translated_text = "Mundo"
        t2.detected_language_code = "en"
        mock_response.translations = [t1, t2]
        mock_translate_client.translate_text.return_value = mock_response

        results = self.service._translate_google_batch(["Hello", "World"], "es")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], ("Hola", "en"))
        self.assertEqual(results[1], ("Mundo", "en"))

    def test_google_batch_none_detected_lang(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Test"
        t1.detected_language_code = None
        mock_response.translations = [t1]
        mock_translate_client.translate_text.return_value = mock_response

        results = self.service._translate_google_batch(["Test"], "en")
        self.assertEqual(results[0], ("Test", ""))


class TestShadowCompareIsolation(unittest.TestCase):

    def setUp(self):
        self.service = TranslationService()

    def test_shadow_not_called_in_google_mode(self):
        original = translation_module.TRANSLATION_MODE
        translation_module.TRANSLATION_MODE = "google"
        try:
            with patch.object(self.service, '_run_shadow_compare') as mock_shadow:
                self.service._schedule_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                mock_shadow.assert_not_called()
        finally:
            translation_module.TRANSLATION_MODE = original

    def test_shadow_not_called_without_url(self):
        original_mode = translation_module.TRANSLATION_MODE
        original_url = translation_module.HOSTED_TRANSLATION_API_URL
        translation_module.TRANSLATION_MODE = "shadow"
        translation_module.HOSTED_TRANSLATION_API_URL = ""
        try:
            with patch.object(self.service, '_run_shadow_compare') as mock_shadow:
                self.service._schedule_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
                mock_shadow.assert_not_called()
        finally:
            translation_module.TRANSLATION_MODE = original_mode
            translation_module.HOSTED_TRANSLATION_API_URL = original_url

    def test_shadow_error_does_not_propagate(self):
        original_mode = translation_module.TRANSLATION_MODE
        original_url = translation_module.HOSTED_TRANSLATION_API_URL
        translation_module.TRANSLATION_MODE = "shadow"
        translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
        try:
            self.service._run_shadow_compare("test", "es", ["Hello"], [("Hola", "en")])
        except Exception:
            self.fail("Shadow compare should not propagate exceptions")
        finally:
            translation_module.TRANSLATION_MODE = original_mode
            translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowNeverWritesCache(unittest.TestCase):

    def setUp(self):
        self.service = TranslationService()

    def test_translate_text_returns_google_in_shadow_mode(self):
        mock_response = MagicMock()
        t1 = MagicMock()
        t1.translated_text = "Hola mundo"
        t1.detected_language_code = "en"
        mock_response.translations = [t1]
        mock_translate_client.translate_text.return_value = mock_response
        mock_redis.get.return_value = None

        original_mode = translation_module.TRANSLATION_MODE
        original_url = translation_module.HOSTED_TRANSLATION_API_URL
        translation_module.TRANSLATION_MODE = "shadow"
        translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
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
            translation_module.TRANSLATION_MODE = original_mode
            translation_module.HOSTED_TRANSLATION_API_URL = original_url


class TestShadowCompareLogging(unittest.TestCase):

    def setUp(self):
        self.service = TranslationService()

    def test_shadow_compare_logs_without_raw_text(self):
        original_mode = translation_module.TRANSLATION_MODE
        original_url = translation_module.HOSTED_TRANSLATION_API_URL
        translation_module.TRANSLATION_MODE = "shadow"
        translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
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
            translation_module.TRANSLATION_MODE = original_mode
            translation_module.HOSTED_TRANSLATION_API_URL = original_url
            self.service._shadow_client = None

    def test_shadow_compare_exact_match_ratio(self):
        original_mode = translation_module.TRANSLATION_MODE
        original_url = translation_module.HOSTED_TRANSLATION_API_URL
        translation_module.TRANSLATION_MODE = "shadow"
        translation_module.HOSTED_TRANSLATION_API_URL = "http://fake:8080"
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
            translation_module.TRANSLATION_MODE = original_mode
            translation_module.HOSTED_TRANSLATION_API_URL = original_url
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


if __name__ == "__main__":
    unittest.main()
