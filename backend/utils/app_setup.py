"""Shared parsing for developer-hosted app setup checks."""

import httpx


def setup_completed_from_response(response: httpx.Response) -> bool:
    """Treat only an object with a truthy completion flag as completed."""
    try:
        payload: object = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and bool(payload.get('is_setup_completed', False))
