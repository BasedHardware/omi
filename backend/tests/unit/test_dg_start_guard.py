"""Tests for connect_to_deepgram start() guard (#6302).

Verifies that connect_to_deepgram returns None when dg_connection.start()
returns False, preventing dead connections from being passed to callers.

The client is selected lazily per request, so these tests isolate the start
guard by replacing that selector with a deterministic client.
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.stt.streaming import connect_to_deepgram


class TestConnectToDeepgramStartGuard:
    """Verify connect_to_deepgram returns None when start() returns False."""

    @patch('utils.stt.streaming._deepgram_client_for_request')
    def test_returns_none_when_start_fails(self, mock_client_for_request):
        """If dg_connection.start() returns False, must return None (#6302)."""
        mock_dg_conn = MagicMock()
        mock_dg_conn.start.return_value = False
        mock_client_for_request.return_value.listen.websocket.v.return_value = mock_dg_conn

        result = connect_to_deepgram(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-3',
        )
        assert result is None

    @patch('utils.stt.streaming._deepgram_client_for_request')
    def test_returns_connection_when_start_succeeds(self, mock_client_for_request):
        """If dg_connection.start() returns True, returns the connection."""
        mock_dg_conn = MagicMock()
        mock_dg_conn.start.return_value = True
        mock_client_for_request.return_value.listen.websocket.v.return_value = mock_dg_conn

        result = connect_to_deepgram(
            on_message=MagicMock(),
            on_error=MagicMock(),
            language='en',
            sample_rate=16000,
            channels=1,
            model='nova-3',
        )
        assert result is mock_dg_conn
