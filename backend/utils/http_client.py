"""Shared httpx.AsyncClient instances for outbound HTTP.

Lifecycle: clients are lazily created on first use and should be closed
at application shutdown via ``close_all_clients()``.
"""

import httpx
import logging

logger = logging.getLogger(__name__)

_webhook_client: httpx.AsyncClient | None = None
_maps_client: httpx.AsyncClient | None = None


def get_webhook_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for webhook delivery.

    Uses aggressive connect timeout (2s) and modest read timeout (15s)
    to match existing semantics while avoiding thread pool exhaustion.
    """
    global _webhook_client
    if _webhook_client is None:
        _webhook_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=2.0),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        )
    return _webhook_client


def get_maps_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for Google Maps geocoding."""
    global _maps_client
    if _maps_client is None:
        _maps_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
    return _maps_client


async def close_all_clients():
    """Close all shared HTTP clients. Call at app shutdown."""
    global _webhook_client, _maps_client
    for client in (_webhook_client, _maps_client):
        if client is not None:
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
    _webhook_client = None
    _maps_client = None
