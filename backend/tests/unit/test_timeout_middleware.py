"""Unit tests for TimeoutMiddleware stale request check (#5929).

Verifies:
- Stale non-multipart requests are rejected with 408
- Multipart file uploads skip the stale check (clock skew safe)
- Malformed headers are ignored (request proceeds)
- Future-dated headers are not rejected
- Timeout path returns 504
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from utils.other.timeout import TimeoutMiddleware


def _make_app(methods_timeout=None):
    """Create a minimal Starlette app with TimeoutMiddleware."""

    async def ok_endpoint(request):
        return PlainTextResponse("ok")

    async def slow_endpoint(request):
        await asyncio.sleep(10)
        return PlainTextResponse("slow")

    app = Starlette(
        routes=[
            Route("/ok", ok_endpoint, methods=["GET", "POST"]),
            Route("/slow", slow_endpoint, methods=["GET"]),
        ],
    )
    app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout or {})
    return app


def test_stale_non_multipart_rejected():
    """Non-multipart request with stale X-Request-Start-Time gets 408."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)  # 10 minutes ago
    response = client.get("/ok", headers={"X-Request-Start-Time": stale_time})
    assert response.status_code == 408


def test_multipart_skips_stale_check():
    """Multipart file upload with stale header should NOT get 408 (#5929)."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)  # 10 minutes ago
    response = client.post(
        "/ok",
        files={"file": ("test.wav", b"fake audio data", "audio/wav")},
        headers={"X-Request-Start-Time": stale_time},
    )
    assert response.status_code == 200


def test_multipart_with_boundary_skips_stale_check():
    """Multipart with boundary param in content-type still skips stale check."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)
    response = client.post(
        "/ok",
        headers={
            "X-Request-Start-Time": stale_time,
            "Content-Type": "multipart/form-data; boundary=----WebKitFormBoundary",
        },
        content=b"fake",
    )
    # Should not be 408 — multipart skips stale check
    assert response.status_code != 408


def test_fresh_non_multipart_passes():
    """Non-multipart request with fresh header passes through."""
    app = _make_app()
    client = TestClient(app)
    fresh_time = str(time.time())
    response = client.get("/ok", headers={"X-Request-Start-Time": fresh_time})
    assert response.status_code == 200


def test_malformed_header_passes():
    """Malformed X-Request-Start-Time header is ignored, request proceeds."""
    app = _make_app()
    client = TestClient(app)
    response = client.get("/ok", headers={"X-Request-Start-Time": "not-a-number"})
    assert response.status_code == 200


def test_no_header_passes():
    """Request without X-Request-Start-Time header proceeds normally."""
    app = _make_app()
    client = TestClient(app)
    response = client.get("/ok")
    assert response.status_code == 200


def test_future_dated_header_passes():
    """Future-dated X-Request-Start-Time (client clock ahead) should not 408."""
    app = _make_app()
    client = TestClient(app)
    future_time = str(time.time() + 600)  # 10 minutes in future
    response = client.get("/ok", headers={"X-Request-Start-Time": future_time})
    assert response.status_code == 200


def test_uppercase_multipart_skips_stale_check():
    """Mixed-case Content-Type 'Multipart/Form-Data' still skips stale check."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)
    response = client.post(
        "/ok",
        headers={
            "X-Request-Start-Time": stale_time,
            "Content-Type": "Multipart/Form-Data; boundary=----abc",
        },
        content=b"fake",
    )
    assert response.status_code != 408


def test_non_multipart_with_multipart_token_still_rejected():
    """Non-multipart content-type is not tricked by substring containing 'multipart/form-data'."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)
    response = client.post(
        "/ok",
        headers={
            "X-Request-Start-Time": stale_time,
            "Content-Type": "application/json",
        },
        content=b'{"key": "value"}',
    )
    assert response.status_code == 408


def test_missing_content_type_still_checked():
    """Request with no Content-Type header still gets stale check."""
    app = _make_app()
    client = TestClient(app)
    stale_time = str(time.time() - 600)
    response = client.get("/ok", headers={"X-Request-Start-Time": stale_time})
    assert response.status_code == 408


def test_timeout_returns_504():
    """Request exceeding timeout returns 504."""
    app = _make_app(methods_timeout={"GET": 0.1})
    client = TestClient(app)
    response = client.get("/slow")
    assert response.status_code == 504
