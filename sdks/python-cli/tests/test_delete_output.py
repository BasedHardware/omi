"""Cloud delete commands share the public human/JSON output contract."""

from __future__ import annotations

import json

import pytest

from omi_cli.main import app


@pytest.fixture(params=["memory", "conversation", "action-item", "goal"])
def delete_command(request):
    command = request.param
    collection = {
        "memory": "memories",
        "conversation": "conversations",
        "action-item": "action-items",
        "goal": "goals",
    }[command]
    return command, f"/v1/dev/user/{collection}/record-1"


@pytest.mark.parametrize("json_mode", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("payload", [None, {"success": True}], ids=["no-content", "json-body"])
def test_delete_success_output(authed_profile, respx_mock, cli_runner, delete_command, json_mode, payload):
    command, path = delete_command
    route = respx_mock.delete(path)
    if payload is None:
        route.respond(204)
    else:
        route.respond(json=payload)

    args = (["--json"] if json_mode else []) + [command, "delete", "record-1", "--yes"]
    result = cli_runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    if json_mode:
        assert json.loads(result.stdout) == payload
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert f"Deleted {command.replace('-', ' ')} record-1." in result.stderr


def test_delete_failure_has_no_success_output(authed_profile, respx_mock, cli_runner, delete_command):
    command, path = delete_command
    respx_mock.delete(path).respond(404, json={"detail": "Record not found"})

    result = cli_runner.invoke(app, ["--json", command, "delete", "record-1", "--yes"])

    assert result.exit_code == 5
    assert result.stdout == ""


def test_delete_declined_confirmation_makes_no_request(authed_profile, respx_mock, cli_runner, delete_command) -> None:
    command, path = delete_command
    route = respx_mock.delete(path).respond(json={"success": True})
    result = cli_runner.invoke(app, [command, "delete", "record-1"], input="n\n")

    assert result.exit_code != 0
    assert not route.called
