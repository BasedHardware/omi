"""Tests for /v4/web/listen parameter parity with /v4/listen.

Verifies that speaker_auto_assign and vad_gate params are accepted
and passed through to _stream_handler (issue #5393).
"""

import asyncio
import inspect
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

for mod_name in [
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.firestore',
    'firebase_admin.messaging',
    'google.cloud',
    'google.cloud.exceptions',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
    'google.cloud.firestore_v1.query',
    'google.cloud.storage',
    'google.cloud.storage.blob',
    'google.cloud.storage.bucket',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.oauth2',
    'google.oauth2.service_account',
    'pinecone',
    'typesense',
    'openai',
    'langchain_openai',
]:
    sys.modules.setdefault(mod_name, MagicMock())

from routers.transcribe import listen_handler, web_listen_handler, _stream_handler


class TestWebListenParamParity:
    """Ensure /v4/web/listen accepts the same params as /v4/listen."""

    def _get_param_names(self, func):
        """Extract parameter names from a function signature, excluding 'self'."""
        sig = inspect.signature(func)
        return {name for name in sig.parameters if name != 'self'}

    def test_web_listen_has_speaker_auto_assign(self):
        """web_listen_handler must accept speaker_auto_assign param."""
        params = self._get_param_names(web_listen_handler)
        assert 'speaker_auto_assign' in params

    def test_web_listen_has_vad_gate(self):
        """web_listen_handler must accept vad_gate param."""
        params = self._get_param_names(web_listen_handler)
        assert 'vad_gate' in params

    def test_stream_handler_has_speaker_auto_assign_enabled(self):
        """_stream_handler must accept speaker_auto_assign_enabled param."""
        params = self._get_param_names(_stream_handler)
        assert 'speaker_auto_assign_enabled' in params

    def test_stream_handler_has_vad_gate_override(self):
        """_stream_handler must accept vad_gate_override param."""
        params = self._get_param_names(_stream_handler)
        assert 'vad_gate_override' in params

    def test_param_parity_between_listen_and_web_listen(self):
        """All params in /v4/listen should also be in /v4/web/listen (except uid, stt_service)."""
        listen_params = self._get_param_names(listen_handler)
        web_listen_params = self._get_param_names(web_listen_handler)

        # uid is handled via first-message auth in web_listen, not query param
        # stt_service is not exposed to web clients (auto-selected)
        expected_missing = {'uid', 'stt_service'}

        missing = listen_params - web_listen_params - expected_missing
        assert missing == set(), f"web_listen_handler is missing params: {missing}"

    def test_speaker_auto_assign_default(self):
        """speaker_auto_assign should default to 'disabled'."""
        sig = inspect.signature(web_listen_handler)
        default = sig.parameters['speaker_auto_assign'].default
        assert default == 'disabled'

    def test_vad_gate_default(self):
        """vad_gate should default to empty string (auto)."""
        sig = inspect.signature(web_listen_handler)
        default = sig.parameters['vad_gate'].default
        assert default == ''

    def test_stream_handler_accepts_all_needed_kwargs(self):
        """_stream_handler signature must include all kwargs that web_listen passes."""
        stream_params = self._get_param_names(_stream_handler)
        required_kwargs = {
            'websocket',
            'uid',
            'language',
            'sample_rate',
            'codec',
            'channels',
            'include_speech_profile',
            'stt_service',
            'conversation_timeout',
            'source',
            'custom_stt_mode',
            'onboarding_mode',
            'speaker_auto_assign_enabled',
            'vad_gate_override',
        }
        missing = required_kwargs - stream_params
        assert missing == set(), f"_stream_handler is missing params: {missing}"


class TestWebListenStreamHandlerIntegration:
    """Integration tests: verify web_listen_handler passes correct kwargs to _stream_handler."""

    def _make_mock_ws(self):
        """Create a mock WebSocket with auth message pre-configured."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive = AsyncMock(
            return_value={'type': 'websocket.receive', 'text': json.dumps({"type": "auth", "token": "test-token"})}
        )
        mock_ws.send_json = AsyncMock()
        return mock_ws

    @pytest.mark.asyncio
    async def test_speaker_auto_assign_enabled_passed_to_stream_handler(self):
        """When speaker_auto_assign=enabled, _stream_handler gets speaker_auto_assign_enabled=True."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(
                    websocket=mock_ws,
                    speaker_auto_assign='enabled',
                    vad_gate='enabled',
                )
                mock_stream.assert_called_once()
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is True
                assert kwargs[1]['vad_gate_override'] == 'enabled'

    @pytest.mark.asyncio
    async def test_defaults_passed_to_stream_handler(self):
        """Default params (disabled/empty) produce False/None in _stream_handler call."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws)
                mock_stream.assert_called_once()
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is False
                assert kwargs[1]['vad_gate_override'] is None

    @pytest.mark.asyncio
    async def test_source_desktop_passed_through(self):
        """source=desktop is forwarded to _stream_handler."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, source='desktop')
                kwargs = mock_stream.call_args
                assert kwargs[1]['source'] == 'desktop'

    @pytest.mark.asyncio
    async def test_vad_gate_disabled_passed_to_stream_handler(self):
        """When vad_gate=disabled, _stream_handler gets vad_gate_override='disabled'."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, vad_gate='disabled')
                kwargs = mock_stream.call_args
                assert kwargs[1]['vad_gate_override'] == 'disabled'

    @pytest.mark.asyncio
    async def test_speaker_auto_assign_disabled_explicit(self):
        """Explicit speaker_auto_assign=disabled produces False."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, speaker_auto_assign='disabled')
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is False


class TestWebListenBoundaryInputs:
    """Boundary tests: non-canonical inputs are handled safely by the handler."""

    def _make_mock_ws(self):
        """Create a mock WebSocket with auth message pre-configured."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive = AsyncMock(
            return_value={'type': 'websocket.receive', 'text': json.dumps({"type": "auth", "token": "test-token"})}
        )
        mock_ws.send_json = AsyncMock()
        return mock_ws

    @pytest.mark.asyncio
    async def test_speaker_auto_assign_invalid_string_treated_as_disabled(self):
        """Non-canonical value 'foobar' for speaker_auto_assign should produce False."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, speaker_auto_assign='foobar')
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is False

    @pytest.mark.asyncio
    async def test_speaker_auto_assign_uppercase_treated_as_disabled(self):
        """Uppercase 'ENABLED' should not match — only lowercase 'enabled' is valid."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, speaker_auto_assign='ENABLED')
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is False

    @pytest.mark.asyncio
    async def test_vad_gate_invalid_string_becomes_none(self):
        """Non-canonical value 'foobar' for vad_gate should produce None."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, vad_gate='foobar')
                kwargs = mock_stream.call_args
                assert kwargs[1]['vad_gate_override'] is None

    @pytest.mark.asyncio
    async def test_vad_gate_uppercase_becomes_none(self):
        """Uppercase 'ENABLED' should not match — only lowercase is valid."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, vad_gate='ENABLED')
                kwargs = mock_stream.call_args
                assert kwargs[1]['vad_gate_override'] is None

    @pytest.mark.asyncio
    async def test_vad_gate_whitespace_becomes_none(self):
        """Whitespace-only vad_gate should produce None (not a valid override)."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, vad_gate='  ')
                kwargs = mock_stream.call_args
                assert kwargs[1]['vad_gate_override'] is None

    @pytest.mark.asyncio
    async def test_speaker_auto_assign_empty_treated_as_disabled(self):
        """Empty string for speaker_auto_assign should produce False."""
        mock_ws = self._make_mock_ws()

        with patch('routers.transcribe.auth.get_current_user_uid_from_ws_message', return_value='uid-test'):
            with patch('routers.transcribe._stream_handler', new_callable=AsyncMock) as mock_stream:
                await web_listen_handler(websocket=mock_ws, speaker_auto_assign='')
                kwargs = mock_stream.call_args
                assert kwargs[1]['speaker_auto_assign_enabled'] is False
