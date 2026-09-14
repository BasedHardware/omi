"""``omi conversation list`` must honour ``--limit`` above the API's per-request cap.

``GET /v1/dev/user/conversations`` clamps ``limit`` server-side to 100 (25 when
``include_transcript`` is set) and does not report the effective value, so a single
request for ``--limit 200`` came back with at most 100 rows under a table titled
``limit=200``. The CLI now issues offset-preserving page requests until the requested
window is covered, which is exactly what one honoured request would have returned.
"""

from __future__ import annotations

import json

import httpx

from omi_cli.main import app


def _paged_api(respx_mock, total: int):
    """Serve ``total`` conversations honouring offset/limit, clamped like the real API."""
    calls: list[tuple[int, int]] = []

    def respond(request):
        params = request.url.params
        limit = int(params["limit"])
        offset = int(params["offset"])
        cap = 25 if params.get("include_transcript") == "true" else 100
        calls.append((limit, offset))
        page = [
            {"id": f"c{i}", "structured": {"title": f"t{i}"}}
            for i in range(offset, min(offset + min(limit, cap), total))
        ]
        return httpx.Response(200, json=page)

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=respond)
    return calls


def test_list_limit_above_server_cap_is_fetched_in_pages(authed_profile, respx_mock, cli_runner) -> None:
    calls = _paged_api(respx_mock, total=500)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "200"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [c["id"] for c in payload] == [f"c{i}" for i in range(200)]
    assert calls == [(100, 0), (100, 100)]


def test_list_with_transcript_uses_the_tighter_server_cap(authed_profile, respx_mock, cli_runner) -> None:
    calls = _paged_api(respx_mock, total=500)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "60", "--include-transcript"])
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)) == 60
    assert calls == [(25, 0), (25, 25), (10, 50)]


def test_list_pages_preserve_the_requested_offset(authed_profile, respx_mock, cli_runner) -> None:
    calls = _paged_api(respx_mock, total=500)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "150", "--offset", "10"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [c["id"] for c in payload] == [f"c{i}" for i in range(10, 160)]
    assert calls == [(100, 10), (50, 110)]


def test_list_covers_the_window_past_an_empty_page(authed_profile, respx_mock, cli_runner) -> None:
    # A page can come back empty when every row in it was locked, so emptiness is not
    # exhaustion either: the requested window is always covered.
    calls: list[tuple[int, int]] = []

    def respond(request):
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        if offset == 100:
            return httpx.Response(200, json=[])  # an all-locked page
        return httpx.Response(200, json=[{"id": f"c{i}"} for i in range(offset, offset + limit)])

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=respond)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "200", "--offset", "100"])
    assert result.exit_code == 0, result.stderr
    assert [c["id"] for c in json.loads(result.stdout)] == [f"c{i}" for i in range(200, 300)]
    assert calls == [(100, 100), (100, 200)]


def test_list_continues_past_a_short_page(authed_profile, respx_mock, cli_runner) -> None:
    # The API filters locked conversations after paging, so a short page is not exhaustion
    # (same contract as action-item paging, #13214). The window still advances by the
    # requested page size so offsets line up with what one honoured request would cover.
    calls: list[tuple[int, int]] = []

    def respond(request):
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        calls.append((limit, offset))
        if offset == 0:
            return httpx.Response(200, json=[{"id": f"c{i}"} for i in range(90)])  # 10 locked rows dropped
        return httpx.Response(200, json=[{"id": f"c{i}"} for i in range(offset, offset + limit)])

    respx_mock.get("/v1/dev/user/conversations").mock(side_effect=respond)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "200"])
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)) == 190
    assert calls == [(100, 0), (100, 100)]


def test_list_within_server_cap_is_a_single_request(authed_profile, respx_mock, cli_runner) -> None:
    calls = _paged_api(respx_mock, total=500)
    result = cli_runner.invoke(app, ["--json", "conversation", "list", "--limit", "100", "--offset", "5"])
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)) == 100
    assert calls == [(100, 5)]


def test_list_table_reports_rows_returned(authed_profile, respx_mock, cli_runner) -> None:
    _paged_api(respx_mock, total=500)
    result = cli_runner.invoke(app, ["conversation", "list", "--limit", "120"])
    assert result.exit_code == 0, result.stderr
    assert "c119" in result.stdout
