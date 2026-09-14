"""Exercise the memory search command against the public developer API contract."""

from __future__ import annotations

import json

import pytest

from omi_cli.main import app

SEARCH_PATH = "/v1/dev/user/memories/vector/search"


def search_response(items: list) -> dict:
    return {
        "items": items,
        "returned_count": len(items),
        "archive_default_visible": False,
        "policy": {
            "consumer": "developer_api",
            "app_has_default_memory_grant": True,
            "archive_capability": False,
            "raw_provenance_capability": False,
        },
    }


@pytest.mark.parametrize("limit", [None, 1, 100])
def test_search_preserves_query_and_response(authed_profile, respx_mock, cli_runner, limit) -> None:
    response = search_response(
        [{"id": "memory-123", "content": "Prefers tea", "category": "core", "relevance_score": 0.91}]
    )
    route = respx_mock.get(SEARCH_PATH).respond(json=response)
    args = ["--json", "memory", "search", "čaj & coffee?"]
    if limit is not None:
        args += ["--limit", str(limit)]
    result = cli_runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == response
    assert dict(route.calls.last.request.url.params) == {"query": "čaj & coffee?", "limit": str(limit or 10)}


def test_search_pretty_keeps_ids_and_literal_content(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get(SEARCH_PATH).respond(
        json=search_response(
            [
                {
                    "id": "memory-id-longer-than-fourteen",
                    "content": "[tea] :coffee:",
                    "category": "core",
                    "relevance_score": 0.91,
                }
            ]
        )
    )
    result = cli_runner.invoke(app, ["--no-color", "memory", "search", "tea"])
    assert result.exit_code == 0, result.output
    assert "memory-id-longer-than-fourteen" in result.stdout
    assert "[tea] :coffee:" in result.stdout
    assert "0.91" in result.stdout


@pytest.mark.parametrize("json_mode", [False, True])
def test_search_empty_results(authed_profile, respx_mock, cli_runner, json_mode) -> None:
    response = search_response([])
    respx_mock.get(SEARCH_PATH).respond(json=response)
    args = ["--json"] if json_mode else ["--no-color"]
    result = cli_runner.invoke(app, [*args, "memory", "search", "tea"])
    assert result.exit_code == 0, result.output
    if json_mode:
        assert json.loads(result.stdout) == response
    else:
        assert "no results" in result.stdout


@pytest.mark.parametrize("args", [[""], ["   "], ["tea", "--limit", "0"], ["tea", "--limit", "101"]])
def test_search_invalid_input_makes_no_request(authed_profile, respx_mock, cli_runner, args) -> None:
    result = cli_runner.invoke(app, ["--json", "memory", "search", *args])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert not respx_mock.calls


def test_search_denied_grant_stays_an_error(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get(SEARCH_PATH).respond(403, json={"detail": {"reason": "default_memory_grant_required"}})
    result = cli_runner.invoke(app, ["--json", "memory", "search", "tea"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Insufficient permissions" in result.stderr
    assert route.call_count == 1
    assert len(respx_mock.calls) == 1
