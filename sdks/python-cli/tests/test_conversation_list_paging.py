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
    assert calls == [(100, 0), (100, 100)]


def test_conversation_list_pages_with_include_transcript_chunking(authed_profile, respx_mock, cli_runner) -> None:
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
    assert calls == [(25, 0, "true"), (25, 25, "true"), (10, 50, "true")]


def test_conversation_list_offset_continuity(authed_profile, respx_mock, cli_runner) -> None:
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
    assert calls == [(100, 10), (50, 110)]


def test_conversation_list_stops_on_empty_page(authed_profile, respx_mock, cli_runner) -> None:
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
    assert len(calls) == 2
    assert calls == [(100, 0), (100, 100)]


def test_conversation_list_continues_on_short_page_when_not_empty(authed_profile, respx_mock, cli_runner) -> None:
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        if offset == 0:
            # Simulates 10 locked/filtered conversations in page 1
            items = [_make_conversation(f"c_p1_{i}") for i in range(90)]
            return httpx.Response(200, json=items)
        items = [_make_conversation(f"c_p2_{i}") for i in range(min(limit, 100))]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "190"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 190
    assert calls == [(100, 0), (100, 100)]


def test_conversation_list_single_request_when_within_cap(authed_profile, respx_mock, cli_runner) -> None:
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        items = [_make_conversation(f"c_{i}") for i in range(limit)]
        return httpx.Response(200, json=items)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=handle_request)

    # 1. limit=100 without include_transcript
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "100"])
    assert result.exit_code == 0
    assert calls == [(100, 0)]

    # 2. limit=25 with include_transcript
    calls.clear()
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--include-transcript", "--limit", "25"])
    assert result.exit_code == 0
    assert calls == [(25, 0)]
