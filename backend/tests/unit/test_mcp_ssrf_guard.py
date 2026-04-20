import importlib
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Stub optional/heavy deps before importing target module
sys.modules.setdefault('firebase_admin', MagicMock())
sys.modules.setdefault('firebase_admin.auth', MagicMock())
sys.modules.setdefault('firebase_admin.firestore', MagicMock())
sys.modules.setdefault('firebase_admin.messaging', MagicMock())
sys.modules.setdefault('google.cloud', MagicMock())
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())
sys.modules.setdefault('google.auth', MagicMock())
sys.modules.setdefault('google.auth.transport.requests', MagicMock())

mcp_client = importlib.import_module('utils.mcp_client')


def _addrinfo_for(*ips: str):
    return [
        (
            0,
            0,
            0,
            '',
            (ip, 443),
        )
        for ip in ips
    ]


class TestMcpServerUrlValidation:
    def test_rejects_link_local_metadata_ip(self):
        with patch('utils.mcp_client.socket.getaddrinfo', return_value=_addrinfo_for('169.254.169.254')):
            with pytest.raises(ValueError, match='not allowed'):
                mcp_client.validate_mcp_server_url('http://169.254.169.254/latest/meta-data')

    def test_rejects_loopback(self):
        with patch('utils.mcp_client.socket.getaddrinfo', return_value=_addrinfo_for('127.0.0.1')):
            with pytest.raises(ValueError, match='not allowed'):
                mcp_client.validate_mcp_server_url('http://127.0.0.1:8080/mcp')

    def test_rejects_private_rfc1918(self):
        with patch('utils.mcp_client.socket.getaddrinfo', return_value=_addrinfo_for('10.0.0.5')):
            with pytest.raises(ValueError, match='not allowed'):
                mcp_client.validate_mcp_server_url('http://10.0.0.5/mcp')


class TestOutboundValidation:
    def test_discover_oauth_metadata_blocks_private_target_before_request(self):
        with patch('utils.mcp_client.socket.getaddrinfo', return_value=_addrinfo_for('169.254.169.254')):
            with patch('utils.mcp_client.httpx.AsyncClient') as mock_client_cls:
                import asyncio

                with pytest.raises(ValueError, match='not allowed'):
                    asyncio.run(mcp_client.discover_oauth_metadata('http://169.254.169.254/latest/meta-data'))

        mock_client_cls.assert_not_called()

    def test_discover_mcp_tools_blocks_private_target_before_request(self):
        with patch('utils.mcp_client.socket.getaddrinfo', return_value=_addrinfo_for('169.254.169.254')):
            with patch('utils.mcp_client.httpx.AsyncClient') as mock_client_cls:
                import asyncio

                with pytest.raises(Exception, match='not allowed'):
                    asyncio.run(mcp_client.discover_mcp_tools('http://169.254.169.254/latest/meta-data'))

        mock_client_cls.assert_not_called()


class _FakeStream:
    def __init__(self, chunks):
        self.status_code = 200
        self._request = httpx.Request('GET', 'https://public.example/sse')
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_text(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self):
        return b''


class _FakeClient:
    def __init__(self, chunks):
        self._stream = _FakeStream(chunks)
        self.post = AsyncMock(return_value=httpx.Response(202, request=httpx.Request('POST', 'https://public.example/post')))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return self._stream


class TestSseTransport:
    def test_sse_event_lines_are_processed_inside_chunk_loop(self):
        fake_client = _FakeClient(
            [
                'event: endpoint\ndata: /post\n\n',
                'event: message\ndata: {"id": 1, "result": {"tools": []}}\n\n',
            ]
        )

        @asynccontextmanager
        async def fake_safe_client(url, timeout):
            yield fake_client

        with patch('utils.mcp_client._safe_async_client', fake_safe_client):
            with patch('utils.mcp_client.validate_mcp_server_url'):
                import asyncio

                responses = asyncio.run(
                    mcp_client._sse_send_and_receive_inner('https://public.example/sse', [{'id': 1}], None)
                )

        fake_client.post.assert_awaited_once()
        assert responses == [{'id': 1, 'result': {'tools': []}}]
