"""Tests for resolve_translation_language() — the translation opt-in/out gate.

Covers issue #6837: translation cost optimization via explicit client control.

Uses module stubbing to avoid Firestore/Redis init at import time.
"""

import os
import re
import sys
from unittest.mock import MagicMock

# --- Module-level mocks for heavy dependencies (must happen before any project imports) ---
_mock_redis = MagicMock()
_mock_redis.get.return_value = None
_mock_redis.set.return_value = True
_mock_redis.exists.return_value = 0

if 'database' not in sys.modules:
    sys.modules['database'] = MagicMock()
if 'database.redis_db' not in sys.modules:
    sys.modules['database.redis_db'] = MagicMock(r=_mock_redis)
else:
    sys.modules['database.redis_db'].r = _mock_redis

if 'google' not in sys.modules:
    sys.modules['google'] = MagicMock()
if 'google.cloud' not in sys.modules:
    sys.modules['google.cloud'] = MagicMock()
if 'google.cloud.translate_v3' not in sys.modules:
    sys.modules['google.cloud.translate_v3'] = MagicMock()

from utils.translation import resolve_translation_language


class TestResolveTranslationLanguage:
    """Test the translation language resolution with explicit precedence rules."""

    def test_translate_disabled_overrides_settings(self):
        """Client sending translate=disabled disables translation even when settings would enable it."""
        result = resolve_translation_language(
            translate_param='disabled',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='en',
        )
        assert result is None

    def test_single_language_mode_disables_translation(self):
        """single_language_mode=True disables translation for higher accuracy."""
        result = resolve_translation_language(
            translate_param='enabled',
            single_language_mode=True,
            stt_language='multi',
            language='multi',
            user_language_preference='en',
        )
        assert result is None

    def test_empty_translate_param_uses_settings_default(self):
        """Empty translate param (legacy clients) falls through to settings-based logic."""
        result = resolve_translation_language(
            translate_param='',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='en',
        )
        assert result == 'en'

    def test_translate_enabled_with_multi_language_and_preference(self):
        """translate=enabled with language=multi uses user_language_preference as target."""
        result = resolve_translation_language(
            translate_param='enabled',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='vi',
        )
        assert result == 'vi'

    def test_translate_enabled_with_specific_language(self):
        """translate=enabled with a specific language (not multi) uses that language as target."""
        result = resolve_translation_language(
            translate_param='enabled',
            single_language_mode=False,
            stt_language='multi',
            language='es',
            user_language_preference='en',
        )
        assert result == 'es'

    def test_no_user_language_preference_disables_translation(self):
        """No user language preference means no target language — translation disabled."""
        result = resolve_translation_language(
            translate_param='enabled',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='',
        )
        assert result is None

    def test_non_multi_stt_language_disables_translation(self):
        """Single-language STT (stt_language != 'multi') doesn't need translation."""
        result = resolve_translation_language(
            translate_param='enabled',
            single_language_mode=False,
            stt_language='en',
            language='en',
            user_language_preference='en',
        )
        assert result is None

    def test_precedence_translate_disabled_over_single_language_mode(self):
        """translate=disabled is checked before single_language_mode (both disable, but order matters for logging)."""
        result = resolve_translation_language(
            translate_param='disabled',
            single_language_mode=True,
            stt_language='multi',
            language='multi',
            user_language_preference='en',
        )
        assert result is None

    def test_unknown_translate_value_treated_as_legacy(self):
        """Unknown translate param values (not 'enabled' or 'disabled') fall through like empty."""
        result = resolve_translation_language(
            translate_param='foobar',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='ja',
        )
        assert result == 'ja'

    def test_backward_compat_legacy_client_multi_language(self):
        """Legacy clients (no translate param) with multi-language STT still get translation."""
        result = resolve_translation_language(
            translate_param='',
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='fr',
        )
        assert result == 'fr'

    def test_backward_compat_legacy_client_single_language_mode(self):
        """Legacy clients with single_language_mode still get translation disabled."""
        result = resolve_translation_language(
            translate_param='',
            single_language_mode=True,
            stt_language='multi',
            language='multi',
            user_language_preference='en',
        )
        assert result is None


class TestTranslateParamWiring:
    """Verify the translate param is wired through WebSocket handler signatures."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_listen_handler_has_translate_param(self):
        """listen_handler must accept translate query parameter."""
        source = self._read_transcribe_source()
        match = re.search(r'async def listen_handler\(.*?\):\s*\n', source, re.DOTALL)
        assert match is not None, "Could not find listen_handler"
        assert 'translate' in match.group(), "listen_handler must have translate parameter"

    def test_web_listen_handler_has_translate_param(self):
        """web_listen_handler must accept translate query parameter."""
        source = self._read_transcribe_source()
        match = re.search(r'async def web_listen_handler\(.*?\):\s*\n', source, re.DOTALL)
        assert match is not None, "Could not find web_listen_handler"
        assert 'translate' in match.group(), "web_listen_handler must have translate parameter"

    def test_stream_handler_receives_translate(self):
        """_stream_handler must accept translate and pass it to resolve_translation_language."""
        source = self._read_transcribe_source()
        match = re.search(r'async def _stream_handler\(.*?\):\s*\n', source, re.DOTALL)
        assert match is not None, "Could not find _stream_handler"
        assert 'translate' in match.group(), "_stream_handler must have translate parameter"

    def test_resolve_called_with_translate_param(self):
        """resolve_translation_language must be called with translate_param=translate."""
        source = self._read_transcribe_source()
        assert 'resolve_translation_language(' in source, "resolve_translation_language must be called"
        assert 'translate_param=translate' in source, "Must pass translate_param=translate"
