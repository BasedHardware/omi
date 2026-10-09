from __future__ import annotations

import json
from typing import Any

import httpx

from omi_integration import OmiIntegrationClient, OmiIntegrationError


def test_bearer_and_app_id_path() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"memories": []})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="https://api.omi.me")
    client = OmiIntegrationClient("test-key", "app-123", client=http)
    body = client.list_memories("user-1", limit=10)
    assert body == {"memories": []}
    assert seen["authorization"] == "Bearer test-key"
    assert "/v2/integrations/app-123/memories" in seen["url"]
    assert "uid=user-1" in seen["url"]
    client.close()


def test_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "nope"})

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.omi.me")
    client = OmiIntegrationClient("test-key", "app-123", client=http)
    try:
        client.list_memories("user-1")
        assert False, "expected error"
    except OmiIntegrationError as exc:
        assert exc.status_code == 401
    finally:
        client.close()
