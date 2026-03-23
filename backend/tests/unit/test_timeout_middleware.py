"""Unit tests for TimeoutMiddleware stale request check (#5929).

Verifies:
- Clock skew tolerance: requests within max_age + skew_allowance pass
- Truly stale requests (beyond tolerance) are rejected with 408
- Malformed headers are ignored (request proceeds)
- Future-dated headers are not rejected
- Clock skew allowance is configurable via env var
- Timeout path returns 504
"""

import asyncio
import os
import time

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


def test_fresh_request_passes():
    """Request with fresh timestamp passes through."""
    app = _make_app()
    client = TestClient(app)
    fresh_time = str(time.time())
    response = client.get("/ok", headers={"X-Request-Start-Time": fresh_time})
    assert response.status_code == 200


def test_within_clock_skew_tolerance_passes():
    """Request from phone with ~5min clock skew passes (within tolerance).

    Default: max_age=5min, skew_allowance=5min, effective threshold=10min.
    A 7-minute-old request should pass.
    """
    app = _make_app()
    client = TestClient(app)
    # 7 minutes ago — beyond max_age (5min) but within max_age + skew_allowance (10min)
    skewed_time = str(time.time() - 420)
    response = client.get("/ok", headers={"X-Request-Start-Time": skewed_time})
    assert response.status_code == 200


def test_beyond_tolerance_rejected_with_clock_skew_json():
    """Request beyond max_age + skew_allowance returns 408 with clock skew JSON.

    Default: max_age=5min, skew_allowance=5min, effective threshold=10min.
    A 15-minute-old request should be rejected with diagnostic info.
    """
    app = _make_app()
    client = TestClient(app)
    very_stale_time = str(time.time() - 900)  # 15 minutes ago
    response = client.get("/ok", headers={"X-Request-Start-Time": very_stale_time})
    assert response.status_code == 408
    body = response.json()
    assert body["error"] == "clock_skew"
    assert "server_time" in body
    assert "client_time" in body
    assert "skew_seconds" in body
    assert body["skew_seconds"] >= 900
    assert "hint" in body


def test_at_exact_boundary_rejected():
    """Request exactly at max_age + skew_allowance + 1s is rejected."""
    app = _make_app()
    client = TestClient(app)
    # Default threshold: 5*60 + 5*60 = 600s. Set to 601s ago.
    boundary_time = str(time.time() - 601)
    response = client.get("/ok", headers={"X-Request-Start-Time": boundary_time})
    assert response.status_code == 408


def test_just_within_boundary_passes():
    """Request just within max_age + skew_allowance passes."""
    app = _make_app()
    client = TestClient(app)
    # Default threshold: 600s. Set to 590s ago (10s margin).
    within_time = str(time.time() - 590)
    response = client.get("/ok", headers={"X-Request-Start-Time": within_time})
    assert response.status_code == 200


def test_multipart_upload_with_skew_passes():
    """Multipart file upload with clock skew within tolerance passes (#5929)."""
    app = _make_app()
    client = TestClient(app)
    # 7 minutes ago — simulates phone clock 5min behind + 2min transfer
    skewed_time = str(time.time() - 420)
    response = client.post(
        "/ok",
        files={"file": ("test.wav", b"fake audio data", "audio/wav")},
        headers={"X-Request-Start-Time": skewed_time},
    )
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


def test_custom_skew_allowance_via_env(monkeypatch):
    """HTTP_CLOCK_SKEW_ALLOWANCE env var controls clock skew tolerance."""
    monkeypatch.setenv("HTTP_CLOCK_SKEW_ALLOWANCE", "60")  # only 1 min allowance
    app = _make_app()
    client = TestClient(app)
    # 7 minutes ago — beyond max_age(5min) + skew(1min) = 6min threshold
    skewed_time = str(time.time() - 420)
    response = client.get("/ok", headers={"X-Request-Start-Time": skewed_time})
    assert response.status_code == 408


def test_zero_skew_allowance_original_behavior(monkeypatch):
    """With zero skew allowance, behavior matches original (max_age only)."""
    monkeypatch.setenv("HTTP_CLOCK_SKEW_ALLOWANCE", "0")
    app = _make_app()
    client = TestClient(app)
    # 6 minutes ago — beyond max_age(5min) + skew(0) = 5min threshold
    stale_time = str(time.time() - 360)
    response = client.get("/ok", headers={"X-Request-Start-Time": stale_time})
    assert response.status_code == 408


def test_timeout_returns_504():
    """Request exceeding timeout returns 504."""
    app = _make_app(methods_timeout={"GET": 0.1})
    client = TestClient(app)
    response = client.get("/slow")
    assert response.status_code == 504
