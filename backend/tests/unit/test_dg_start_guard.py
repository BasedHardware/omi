"""Tests for connect_to_deepgram start() guard (#6302).

Verifies that connect_to_deepgram returns None when dg_connection.start()
returns False, preventing dead connections from being passed to callers.
"""

import os
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs — only what streaming.py actually needs at import time
# ---------------------------------------------------------------------------

# Stub database, heavy deps, and deepgram before importing.
# deepgram stubs must match test_streaming_deepgram_backoff.py pattern to avoid
# import-order pollution when pytest collects both files in the same process.
for _mod_name in [
    'database',
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.users',
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.messaging',
    'models',
    'models.other',
    'models.transcript_segment',
    'models.chat',
    'models.conversation',
    'models.notification_message',
    'utils.log_sanitizer',
    'deepgram',
    'deepgram.clients',
    'deepgram.clients.live',
    'deepgram.clients.live.v1',
    'websockets',
    'websockets.exceptions',
]:
    sys.modules.setdefault(_mod_name, MagicMock())


def _fill_existing_stub_attrs(module_name, attrs):
    module = sys.modules.get(module_name)
    if module is None:
        return None

    for attr in attrs:
        if isinstance(module, MagicMock) or not hasattr(module, attr):
            setattr(module, attr, MagicMock())
    return module


os.environ.setdefault('DEEPGRAM_API_KEY', 'fake-for-test')
# NOTE: Do NOT set sys.modules['deepgram'].LiveTranscriptionEvents here.
# MagicMock auto-generates attributes on access, and overwriting would pollute
# shared pytest state for test_streaming_deepgram_backoff.py's close/error handler tests.

_fill_existing_stub_attrs('utils.async_tasks', ['create_named_task'])
_fill_existing_stub_attrs('utils.executors', ['sync_executor', 'run_blocking'])
_fill_existing_stub_attrs('utils.http_client', ['get_stt_client', 'get_stt_semaphore'])

_byok_module = sys.modules.get('utils.byok')
if _byok_module is not None:
    _get_byok_key = getattr(_byok_module, 'get_byok_key', None)
    if isinstance(_byok_module, MagicMock) or isinstance(_get_byok_key, MagicMock) or _get_byok_key is None:
        _byok_module.get_byok_key = MagicMock(return_value=None)

_speaker_embedding = ModuleType('utils.stt.speaker_embedding')
_speaker_embedding.SPEAKER_MATCH_THRESHOLD = 0.45
_speaker_embedding.async_extract_embedding_from_bytes = AsyncMock(return_value=None)
_speaker_embedding.compare_embeddings = MagicMock(return_value=0.0)
sys.modules.setdefault('utils.stt.speaker_embedding', _speaker_embedding)

# Now import the real streaming module
from utils.stt.streaming import connect_to_deepgram


class TestConnectToDeepgramStartGuard:
    """Verify connect_to_deepgram returns None when start() returns False."""

    @patch('utils.stt.streaming.deepgram')
    def test_returns_none_when_start_fails(self, mock_dg):
        """If dg_connection.start() returns False, must return None (#6302)."""
        mock_dg_conn = MagicMock()
        mock_dg_conn.start.return_value = False
        mock_dg.listen.websocket.v.return_value = mock_dg_conn

        result = connect_to_deepgram(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-3',
        )
        assert result is None

    @patch('utils.stt.streaming.deepgram')
    def test_returns_connection_when_start_succeeds(self, mock_dg):
        """If dg_connection.start() returns True, returns the connection."""
        mock_dg_conn = MagicMock()
        mock_dg_conn.start.return_value = True
        mock_dg.listen.websocket.v.return_value = mock_dg_conn

        result = connect_to_deepgram(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-3',
        )
        assert result is mock_dg_conn
