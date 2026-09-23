"""Tests for conversation list pagination beyond server caps (issue #13950)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from omi_cli.main import app


def _make_conversation(conv_id: str) -> dict[str, Any]:
    return {
        "id": conv_id,
        "structured": {"title": f"Conversation {conv_id}", "category": "test"},
        "started_at": "2026-04-01T00:00:00Z",
        "source": "phone",
    }


def test_conversation_list_pages_up_to_limit_200(authed_profile, respx_mock, cli_runner) -> None:
    """After #13950: server cap raised to 1000, so limit=200 fits in one request."""
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        items = [_make_conversation(f"c_{offset + i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "200"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 200
    # Single request: 200 <= server_page_size (1000 without transcript)
    assert calls == [(200, 0)]


def test_conversation_list_pages_with_include_transcript_chunking(authed_profile, respx_mock, cli_runner) -> None:
    """After #13950: transcript cap raised to 500, so limit=60 fits in one request."""
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        inc_transcript = request.url.params["include_transcript"]
        calls.append((limit, offset, inc_transcript))
        items = [_make_conversation(f"c_{offset + i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--include-transcript", "--limit", "60"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 60
    # Single request: 60 <= server_page_size (500 with transcript)
    assert calls == [(60, 0, "true")]


def test_conversation_list_offset_continuity(authed_profile, respx_mock, cli_runner) -> None:
    """After #13950: limit=150 fits in one request even with offset."""
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        items = [_make_conversation(f"c_{offset + i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--offset", "10", "--limit", "150"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 150
    # Single request: 150 <= 1000
    assert calls == [(150, 10)]


def test_conversation_list_stops_on_empty_page(authed_profile, respx_mock, cli_runner) -> None:
    """After #13950: single request; server returns fewer items than requested."""
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        if offset == 0:
            items = [_make_conversation(f"c_{i}") for i in range(50)]
            return httpx.Response(200, json=items)
        return httpx.Response(200, json=[])

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "200"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 50
    # Single request — no second page needed
    assert len(calls) == 1
    assert calls == [(200, 0)]


def test_conversation_list_returns_what_server_gives(authed_profile, respx_mock, cli_runner) -> None:
    """After #13950: single request; CLI returns whatever the server returns (no auto-pagination for short pages)."""
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        if offset == 0:
            # Server returns fewer items than requested (e.g., filtered/locked conversations)
            items = [_make_conversation(f"c_p1_{i}") for i in range(90)]
            return httpx.Response(200, json=items)
        items = [_make_conversation(f"c_p2_{i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "190"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # After #13950: single request, returns what server gave us (90 items)
    # No automatic second-page fetch since we're within the server page cap
    assert len(payload) == 90
    assert calls == [(190, 0)]


def test_conversation_list_single_request_when_within_cap(authed_profile, respx_mock, cli_runner) -> None:
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        items = [_make_conversation(f"c_{i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    # 1. limit=100 without include_transcript (cap=1000)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "100"])
    assert result.exit_code == 0
    assert calls == [(100, 0)]

    # 2. limit=25 with include_transcript (cap=500)
    calls.clear()
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--include-transcript", "--limit", "25"])
    assert result.exit_code == 0
    assert calls == [(25, 0)]
