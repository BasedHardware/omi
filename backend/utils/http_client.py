"""Shared httpx.AsyncClient instances for outbound HTTP.

Lifecycle: clients are lazily created on first use and should be closed
at application shutdown via ``close_all_clients()``.
"""

import httpx
import logging

logger = logging.getLogger(__name__)

_webhook_client: httpx.AsyncClient | None = None
_maps_client: httpx.AsyncClient | None = None
_auth_client: httpx.AsyncClient | None = None
_stt_client: httpx.AsyncClient | None = None


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


def get_auth_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for OAuth/auth token exchanges."""
    global _auth_client
    if _auth_client is None:
        _auth_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=8),
        )
    return _auth_client


def get_stt_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for STT/ML services (long timeout)."""
    global _stt_client
    if _stt_client is None:
        _stt_client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=5.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
    return _stt_client


async def close_all_clients():
    """Close all shared HTTP clients. Call at app shutdown."""
    global _webhook_client, _maps_client, _auth_client, _stt_client
    for client in (_webhook_client, _maps_client, _auth_client, _stt_client):
        if client is not None:
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
    _webhook_client = None
    _maps_client = None
    _auth_client = None
    _stt_client = None
