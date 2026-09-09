"""The four resource DELETE commands preserve the CLI's JSON output contract."""

from __future__ import annotations

import json

import pytest

from omi_cli.main import app


@pytest.fixture(params=["memory", "conversation", "action-item", "goal"])
def resource(request):
    command = request.param
    collection = {
        "memory": "memories",
        "conversation": "conversations",
        "action-item": "action-items",
        "goal": "goals",
    }[command]
    return command, f"/v1/dev/user/{collection}/test-id"


@pytest.mark.parametrize("status_code,payload", [(200, {"success": True}), (204, None)])
def test_delete_json_preserves_success_response(
    resource, status_code, payload, authed_profile, respx_mock, cli_runner
) -> None:
    command, path = resource
    route = respx_mock.delete(path).respond(status_code, json=payload)
    result = cli_runner.invoke(app, ["--json", command, "delete", "test-id", "--yes"])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert json.loads(result.stdout) == payload
    assert result.stderr == ""


def test_delete_pretty_keeps_success_message(resource, authed_profile, respx_mock, cli_runner) -> None:
    command, path = resource
    respx_mock.delete(path).respond(json={"success": True})
    result = cli_runner.invoke(app, ["--no-color", command, "delete", "test-id", "--yes"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "Deleted" in result.stderr
    assert "test-id" in result.stderr


def test_delete_declined_confirmation_makes_no_request(resource, authed_profile, respx_mock, cli_runner) -> None:
    command, path = resource
    route = respx_mock.delete(path).respond(json={"success": True})
    result = cli_runner.invoke(app, ["--json", command, "delete", "test-id"], input="n\n")

    assert result.exit_code != 0
    assert not route.called
