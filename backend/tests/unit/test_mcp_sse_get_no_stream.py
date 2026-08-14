"""Regression test: GET /v1/mcp/sse must not offer a long-lived SSE stream.

The handler used to return an infinite keepalive-ping SSE stream that carried no
protocol data (the transport is stateless, nothing is ever pushed, and the
deprecated HTTP+SSE transport's required ``endpoint`` event was never sent).
Every connected MCP client parked one such stream for the full Cloud Run request
timeout (3600s). In production (2026-08-14) ~1,100-1,400 hour-long GET streams
per hour saturated the service's entire concurrency budget (maxScale 25 x
containerConcurrency 80, p95 concurrency ~84/80) while CPU sat at ~4%, causing
"no available instance" aborts and minutes-long tool-call tail latency
(measured p90 ~122s, max 300s) for every MCP consumer.

Per the MCP Streamable HTTP transport spec (2025-03-26), a server that does not
offer server-initiated messages MUST return 405 Method Not Allowed for GET on
the endpoint, and clients MUST NOT treat that as an error. External contract:
https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
("listening for messages from the server": the server MUST either return
text/event-stream or HTTP 405 Method Not Allowed).

These tests exercise the real router through FastAPI's TestClient (conftest
sets the fake env vars needed for import).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    from routers import mcp_sse

    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


def test_get_mcp_sse_returns_405_not_a_stream(client):
    """GET must return 405 immediately instead of holding an infinite SSE stream."""
    response = client.get("/v1/mcp/sse")
    assert response.status_code == 405
    assert "text/event-stream" not in response.headers.get("content-type", "")
    # Spec-friendly: advertise the methods the endpoint does serve.
    assert "POST" in response.headers.get("allow", "")


def test_post_mcp_sse_still_routed(client):
    """The 405 is method-scoped: POST (the real transport) must still reach auth, not 405."""
    response = client.post("/v1/mcp/sse", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code != 405
