"""Regression tests for Rich markup-like resource IDs in success messages.

IDs come straight from ``typer.Argument`` (argv), so a value like
``bad[/bold]id`` used to raise ``MarkupError`` (or silently eat text) when
interpolated into pretty ``[bold]...[/bold]`` success messages. Every
update/delete/complete/progress command must escape user-controlled IDs.
"""

from __future__ import annotations

import pytest

from omi_cli.main import app

MARKUP_ID = "bad[/bold]id"

DELETE_CASES = [
    ("memory", "/v1/dev/user/memories"),
    ("conversation", "/v1/dev/user/conversations"),
    ("action-item", "/v1/dev/user/action-items"),
    ("goal", "/v1/dev/user/goals"),
]

UPDATE_CASES = [
    ("memory", "/v1/dev/user/memories", ["update", "--content", "hello"]),
    ("conversation", "/v1/dev/user/conversations", ["update", "--title", "hello"]),
    ("action-item", "/v1/dev/user/action-items", ["update", "--description", "hello"]),
    ("goal", "/v1/dev/user/goals", ["update", "--title", "hello"]),
    ("goal", "/v1/dev/user/goals", ["progress", "42"]),
    ("action-item", "/v1/dev/user/action-items", ["complete"]),
]


def _update_args(command, subcommand, opts):
    if subcommand == "progress":
        return [command, subcommand, MARKUP_ID, *opts]
    if subcommand == "complete":
        return [command, subcommand, MARKUP_ID]
    return [command, subcommand, MARKUP_ID, *opts]


@pytest.mark.parametrize("command,collection", DELETE_CASES)
def test_delete_markup_id_renders_literally(
    command, collection, authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    # Keep the status line on one line so its literal spelling can be checked.
    monkeypatch.setenv("COLUMNS", "1000")
    route = respx_mock.delete(f"{collection}/{MARKUP_ID}").respond(json={"success": True})
    result = cli_runner.invoke(app, ["--no-color", command, "delete", MARKUP_ID, "--yes"])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr


@pytest.mark.parametrize("command,collection,extra", UPDATE_CASES)
def test_update_markup_id_renders_literally(
    command, collection, extra, authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    monkeypatch.setenv("COLUMNS", "1000")
    subcommand = extra[0]
    if subcommand == "progress":
        route = respx_mock.patch(f"{collection}/{MARKUP_ID}/progress").respond(json={"success": True})
    else:
        route = respx_mock.patch(f"{collection}/{MARKUP_ID}").respond(json={"success": True})
    result = cli_runner.invoke(app, ["--no-color", *_update_args(command, subcommand, extra[1:])])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr


LOCAL_TASK_CASES = [
    ("complete", ["local", "task", "complete", MARKUP_ID]),
    ("delete", ["local", "task", "delete", MARKUP_ID, "--yes"]),
]


@pytest.mark.parametrize("subcommand,args", LOCAL_TASK_CASES)
def test_local_task_markup_id_renders_literally(subcommand, args, cli_runner, respx_mock, monkeypatch) -> None:
    monkeypatch.setenv("COLUMNS", "1000")
    local_url = "http://127.0.0.1:47778"
    route = respx_mock.post(f"{local_url}/v1/local/tool").respond(
        json={"ok": True, "name": "tool", "content_type": "text/plain", "result": '{"ok": true}'}
    )
    result = cli_runner.invoke(
        app,
        ["--no-color", *args],
        env={"OMI_LOCAL_API_URL": local_url, "OMI_LOCAL_TOKEN": "test_token"},
    )

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr


def test_local_screenshot_markup_path_renders_literally(cli_runner, respx_mock, monkeypatch, tmp_path) -> None:
    import base64

    monkeypatch.setenv("COLUMNS", "1000")
    local_url = "http://127.0.0.1:47778"
    markup_filename = "test_[bold]shot.png"
    output_path = tmp_path / markup_filename
    route = respx_mock.post(f"{local_url}/v1/local/tool").respond(
        json={
            "ok": True,
            "name": "get_screenshot",
            "image_base64": base64.b64encode(b"img").decode("ascii"),
            "screenshot_id": "9",
        }
    )
    result = cli_runner.invoke(
        app,
        ["--no-color", "local", "screenshot", "9", "-o", str(output_path)],
        env={"OMI_LOCAL_API_URL": local_url, "OMI_LOCAL_TOKEN": "test_token"},
    )

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert markup_filename in result.stderr


CREATE_CASES = [
    ("memory", "/v1/dev/user/memories", ["create", "hello"]),
    ("conversation", "/v1/dev/user/conversations", ["create", "--text", "hello"]),
    ("action-item", "/v1/dev/user/action-items", ["create", "hello"]),
    ("goal", "/v1/dev/user/goals", ["create", "hello"]),
]


@pytest.mark.parametrize("command,collection,args", CREATE_CASES)
def test_create_markup_id_renders_literally(
    command, collection, args, authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    monkeypatch.setenv("COLUMNS", "1000")
    route = respx_mock.post(collection).respond(json={"id": MARKUP_ID, "status": "processing"})
    result = cli_runner.invoke(app, ["--no-color", command, *args])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr
