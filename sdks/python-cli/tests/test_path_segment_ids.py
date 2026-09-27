"""IDs from argv must stay inside their own URL path segment."""

from __future__ import annotations

import httpx
import pytest

from omi_cli.client import path_segment
from omi_cli.main import app


@pytest.mark.parametrize(
    ("raw", "encoded"),
    [
        ("abc123", "abc123"),
        ("a/b", "a%2Fb"),
        ("a?x=1", "a%3Fx%3D1"),
        ("a#frag", "a%23frag"),
        ("../x", "..%2Fx"),
        ("a b", "a%20b"),
    ],
)
def test_path_segment_encodes_reserved_characters(raw: str, encoded: str) -> None:
    assert path_segment(raw) == encoded


@pytest.mark.parametrize("raw", ["", ".", ".."])
def test_path_segment_rejects_dot_segments(raw: str) -> None:
    with pytest.raises(Exception) as excinfo:
        path_segment(raw)
    assert excinfo.value.exit_code == 1


def test_goal_delete_traversal_id_cannot_reach_conversations(authed_profile, respx_mock, cli_runner) -> None:
    # Before the fix, httpx resolved the dot-segments and this DELETE landed on
    # /v1/dev/user/conversations/victim — a different resource than the one confirmed.
    conversations = respx_mock.delete("/v1/dev/user/conversations/victim").respond(status_code=204)
    goal = respx_mock.delete("/v1/dev/user/goals/g1%2F..%2F..%2Fconversations%2Fvictim").respond(
        status_code=404, json={"detail": "Goal not found"}
    )
    result = cli_runner.invoke(app, ["--json", "goal", "delete", "g1/../../conversations/victim", "--yes"])
    assert not conversations.called
    assert goal.called
    assert result.exit_code == 5


@pytest.mark.parametrize(
    ("argv", "method", "path"),
    [
        (["memory", "delete", "m?x", "--yes"], "DELETE", "/v1/dev/user/memories/m%3Fx"),
        (["action-item", "complete", "a#b"], "PATCH", "/v1/dev/user/action-items/a%23b"),
        (["conversation", "get", "c/d"], "GET", "/v1/dev/user/conversations/c%2Fd"),
        (["goal", "history", "g/h"], "GET", "/v1/dev/user/goals/g%2Fh/history"),
    ],
)
def test_commands_encode_ids(authed_profile, respx_mock, cli_runner, argv, method, path) -> None:
    seen: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode())
        return httpx.Response(200, json={"id": "x"})

    respx_mock.route(method=method).mock(side_effect=record)
    result = cli_runner.invoke(app, ["--json", *argv])
    assert result.exit_code == 0, result.output
    assert seen and seen[0].split("?")[0] == path


def test_dot_dot_id_is_a_usage_error(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.route().respond(status_code=204)
    result = cli_runner.invoke(app, ["--json", "goal", "delete", "..", "--yes"])
    assert result.exit_code == 1
    assert not route.called
