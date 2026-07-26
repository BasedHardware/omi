"""Developer webhook delivery must reject URLs resolving to private/reserved addresses.

Before this fix, utils.webhooks._post_dev_webhook posted straight to a user-supplied
webhook_url with no check that it didn't resolve to an internal service or the cloud
metadata endpoint (e.g. 169.254.169.254). Any user could set their webhook to such an
address and use the delivered payload/response as an SSRF probe/oracle against the
backend's own network. _post_dev_webhook now re-resolves the hostname via
utils.ssrf_guard.hostname_is_public before every delivery attempt (including retries,
so a DNS-rebinding target can't validate once and then repoint).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.webhooks as webhooks_module
from utils.ssrf_guard import is_private_ip


def test_is_private_ip_blocks_known_ranges():
    for ip in ("127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1"):
        assert is_private_ip(ip), f"{ip} must be classified private"


def test_is_private_ip_blocks_ipv4_mapped_ipv6_addresses():
    """Regression: ipaddress.ip_address('::ffff:127.0.0.1') parses as the IPv6 address
    ::ffff:7f00:1, which matches none of PRIVATE_NETWORKS' IPv4 entries and isn't in any
    IPv6 entry either - a real bypass letting an IPv4-mapped IPv6 literal reach loopback/
    internal addresses past the guard. Must unwrap .ipv4_mapped before classifying.
    """
    for ip in ("::ffff:127.0.0.1", "::ffff:10.0.0.5", "::ffff:169.254.169.254"):
        assert is_private_ip(ip), f"{ip} (IPv4-mapped) must be classified private"


def test_is_private_ip_allows_public_addresses():
    for ip in ("8.8.8.8", "1.1.1.1"):
        assert not is_private_ip(ip), f"{ip} must be classified public"


@pytest.mark.asyncio
async def test_post_dev_webhook_blocks_private_target_without_calling_client():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

    with (
        patch.object(webhooks_module, "get_webhook_client", return_value=mock_client),
        patch.object(webhooks_module, "hostname_is_public", AsyncMock(return_value=False)),
    ):
        with pytest.raises(Exception):
            await webhooks_module._post_dev_webhook(
                "test_webhook",
                "http://169.254.169.254/latest/meta-data/",
                retry_delays=(),
                json={"hello": "world"},
            )

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_post_dev_webhook_allows_public_target():
    mock_response = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch.object(webhooks_module, "get_webhook_client", return_value=mock_client),
        patch.object(webhooks_module, "hostname_is_public", AsyncMock(return_value=True)),
    ):
        response = await webhooks_module._post_dev_webhook(
            "test_webhook",
            "https://example.com/webhook",
            retry_delays=(),
            json={"hello": "world"},
        )

    assert response.status_code == 200
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_post_dev_webhook_rejects_non_http_scheme():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

    with patch.object(webhooks_module, "get_webhook_client", return_value=mock_client):
        with pytest.raises(Exception):
            await webhooks_module._post_dev_webhook(
                "test_webhook",
                "file:///etc/passwd",
                retry_delays=(),
                json={"hello": "world"},
            )

    mock_client.post.assert_not_called()
