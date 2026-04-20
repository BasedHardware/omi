import sys
from unittest.mock import AsyncMock, MagicMock, patch

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
sys.modules.setdefault('httpx', MagicMock())

from utils import mcp_client


class TestMcpServerUrlValidation:
    def test_rejects_link_local_metadata_ip(self):
        with pytest.raises(ValueError, match='not allowed'):
            mcp_client.validate_mcp_server_url('http://169.254.169.254/latest/meta-data')

    def test_rejects_loopback(self):
        with pytest.raises(ValueError, match='not allowed'):
            mcp_client.validate_mcp_server_url('http://127.0.0.1:8080/mcp')

    def test_rejects_private_rfc1918(self):
        with pytest.raises(ValueError, match='not allowed'):
            mcp_client.validate_mcp_server_url('http://10.0.0.5/mcp')


class TestOutboundValidation:
    def test_discover_oauth_metadata_blocks_private_target_before_request(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('utils.mcp_client.httpx.AsyncClient', return_value=mock_client):
            with pytest.raises(ValueError, match='not allowed'):
                import asyncio
                asyncio.run(mcp_client.discover_oauth_metadata('http://169.254.169.254/latest/meta-data'))

        mock_client.get.assert_not_called()

    def test_discover_mcp_tools_blocks_private_target_before_request(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('utils.mcp_client.httpx.AsyncClient', return_value=mock_client):
            with pytest.raises(Exception, match='not allowed'):
                import asyncio
                asyncio.run(mcp_client.discover_mcp_tools('http://169.254.169.254/latest/meta-data'))

        mock_client.post.assert_not_called()
