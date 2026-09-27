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
    (["local", "task", "complete", MARKUP_ID], "complete_task"),
    (["local", "task", "delete", MARKUP_ID, "--yes"], "delete_task"),
]


@pytest.mark.parametrize("cli_args,tool_name", LOCAL_TASK_CASES)
def test_local_task_markup_id_renders_literally(
    cli_args, tool_name, config_path, respx_mock, cli_runner, monkeypatch
) -> None:
    from omi_cli import config as cfg

    config = cfg.load()
    profile = config.get_profile("default")
    profile.local_api_url = "http://127.0.0.1:47778"
    profile.local_token = "local_test_token"
    config.set_profile(profile)
    cfg.save(config)

    monkeypatch.setenv("COLUMNS", "1000")
    route = respx_mock.post("http://127.0.0.1:47778/v1/local/tool").respond(
        json={"ok": True, "name": tool_name, "content_type": "text/plain", "result": "{}"}
    )
    result = cli_runner.invoke(app, ["--no-color", *cli_args])

    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert "MarkupError" not in result.stderr
    assert MARKUP_ID in result.stderr
