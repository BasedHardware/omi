"""The human/JSON contract must hold through both shipped CLI entrypoints."""

from __future__ import annotations

import json
import time
from contextlib import nullcontext
from unittest.mock import Mock

import click
import httpx
import pytest
import respx
import typer

from omi_cli import __version__
from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.client import MAX_RETRY_ATTEMPTS
from omi_cli.main import app

LITERAL = "[/bold] :rocket:"


@pytest.fixture(params=[False, True], ids=["human", "json"])
def json_mode(request):
    return request.param


def arguments(json_mode, *command):
    return [*(["--json"] if json_mode else []), *command]


def assert_error(result, code, json_mode, text):
    assert result.exit_code == code, result
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "\x1b[" not in result.stderr
    if json_mode:
        payload = json.loads(result.stderr)
        assert isinstance(payload["error"], str)
        assert text in payload["error"] + payload.get("detail", "")
    else:
        assert text in result.stderr


def test_api_data_and_created_id_are_literal(public_cli, json_mode, authed_profile, respx_mock):
    payload = {"id": LITERAL, "content": LITERAL}
    route = respx_mock.post("/v1/dev/user/memories").respond(json=payload)

    result = public_cli(arguments(json_mode, "memory", "create", LITERAL))

    assert result.exit_code == 0, result
    assert route.call_count == 1
    if json_mode:
        assert json.loads(result.stdout) == payload
        assert result.stderr == ""
    else:
        assert result.stdout.count(LITERAL) == 2
        assert f"Memory created: {LITERAL}" in result.stderr


@pytest.mark.parametrize("status,code", [(400, 1), (401, 2), (403, 2), (404, 5), (429, 4), (503, 3)])
def test_http_errors_keep_literal_detail_and_exit_code(
    public_cli, json_mode, authed_profile, respx_mock, monkeypatch, status, code
):
    route = respx_mock.get("/v1/dev/user/memories").respond(status, json={"detail": LITERAL})
    monkeypatch.setattr(time, "sleep", lambda _: None)

    result = public_cli(arguments(json_mode, "memory", "list"))

    assert_error(result, code, json_mode, LITERAL)
    assert route.call_count == (MAX_RETRY_ATTEMPTS if status in (429, 503) else 1)


def test_transport_error_is_a_server_error(public_cli, json_mode, authed_profile, respx_mock, monkeypatch):
    route = respx_mock.get("/v1/dev/user/memories").mock(side_effect=httpx.ReadTimeout("test timeout"))
    monkeypatch.setattr(time, "sleep", lambda _: None)

    result = public_cli(arguments(json_mode, "memory", "list"))

    assert_error(result, 3, json_mode, "Request timed out")
    assert route.call_count == MAX_RETRY_ATTEMPTS


@pytest.mark.parametrize(
    "command",
    [
        ["--unknown-option"],
        ["unknown-command"],
        ["memory", "get"],
        ["memory", "list", "--limit", "not-a-number"],
        ["--profile"],
    ],
    ids=["root-option", "command", "missing-argument", "invalid-value", "missing-global-value"],
)
def test_parser_errors_use_the_public_usage_contract(public_cli, json_mode, command):
    result = public_cli(arguments(json_mode, *command))
    assert_error(result, 1, json_mode, "")


@pytest.mark.parametrize("command", [["version"], ["--version"]], ids=["command", "flag"])
def test_version_has_a_machine_result(public_cli, json_mode, command):
    result = public_cli(arguments(json_mode, *command))

    assert result.exit_code == 0, result
    assert result.stderr == ""
    if json_mode:
        assert json.loads(result.stdout) == {"version": __version__}
    else:
        assert result.stdout == f"omi-cli {__version__}\n"


def test_eager_version_respects_json_in_either_order(public_cli):
    result = public_cli(["--version", "--json"])
    assert result.exit_code == 0, result
    assert json.loads(result.stdout) == {"version": __version__}
    assert result.stderr == ""


@pytest.mark.parametrize("operation", ["set", "use", "delete"])
def test_status_only_config_commands_complete(public_cli, json_mode, operation):
    config = cfg.load()
    config.set_profile(cfg.Profile(name=LITERAL))
    cfg.save(config)
    if operation == "set":
        command = ["--profile", LITERAL, "config", "set", "api_base", "https://example.invalid"]
    else:
        command = ["config", "profile", operation, LITERAL]
        if operation == "delete":
            command.append("--yes")

    result = public_cli(arguments(json_mode, *command))

    assert result.exit_code == 0, result
    if json_mode:
        assert json.loads(result.stdout) is None
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert LITERAL in result.stderr
    saved = cfg.load()
    if operation == "set":
        assert saved.get_profile(LITERAL).api_base == "https://example.invalid"
    elif operation == "use":
        assert saved.active_profile == LITERAL
    else:
        assert LITERAL not in saved.profiles


def test_new_status_only_command_inherits_the_contract(public_cli, json_mode):
    original_commands = list(app.registered_commands)

    @app.command("output-contract-probe")
    def probe(ctx: typer.Context):
        ctx.obj.renderer.success(LITERAL)

    try:
        result = public_cli(arguments(json_mode, "output-contract-probe"))
    finally:
        app.registered_commands[:] = original_commands

    assert result.exit_code == 0, result
    if json_mode:
        assert json.loads(result.stdout) is None
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert LITERAL in result.stderr


@pytest.mark.parametrize("json_mode", [False, True])
def test_empty_delete_response_is_one_result(public_cli, json_mode, authed_profile, respx_mock):
    route = respx_mock.delete("/v1/dev/user/memories/record-1").respond(204)
    result = public_cli(arguments(json_mode, "memory", "delete", "record-1", "--yes"))

    assert result.exit_code == 0, result
    assert route.call_count == 1
    if json_mode:
        assert json.loads(result.stdout) is None
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert "Deleted memory record-1." in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        ["memory", "delete", "record-1"],
        ["conversation", "delete", "record-1"],
        ["action-item", "delete", "record-1"],
        ["goal", "delete", "record-1"],
        ["local", "task", "delete", "record-1"],
        ["config", "profile", "delete", "default"],
    ],
)
def test_json_confirmation_requires_yes_before_side_effects(public_cli, authed_profile, respx_mock, command):
    before = cfg.load().path.read_text()
    result = public_cli(["--json", *command], input_text="y\n")

    assert_error(result, 1, True, "--yes")
    assert respx_mock.calls.call_count == 0
    assert cfg.load().path.read_text() == before


def test_human_confirmation_still_allows_delete(public_cli, authed_profile, respx_mock):
    route = respx_mock.delete("/v1/dev/user/memories/record-1").respond(204)
    result = public_cli(["memory", "delete", "record-1"], input_text="y\n")

    assert result.exit_code == 0, result
    assert route.call_count == 1
    assert "Deleted memory record-1." in result.stderr


def test_json_login_does_not_open_an_interactive_picker(public_cli, respx_mock):
    result = public_cli(["--json", "auth", "login"], tty=True)
    assert_error(result, 1, True, "--api-key")
    assert respx_mock.calls.call_count == 0


def test_browser_progress_does_not_contaminate_json(public_cli, monkeypatch):
    server = Mock(server_address=("127.0.0.1", 12345))
    monkeypatch.setattr(oauth, "_OneShotHTTPServer", lambda *args: nullcontext(server))
    monkeypatch.setattr(oauth.threading, "Thread", lambda **kwargs: Mock())
    monkeypatch.setattr(oauth.threading, "Event", lambda: Mock(wait=Mock(return_value=False)))
    monkeypatch.setattr(oauth.webbrowser, "open", lambda *args, **kwargs: False)

    result = public_cli(["--json", "auth", "login", "--browser"])

    assert_error(result, 2, True, "OAuth flow timed out")


@pytest.mark.parametrize(
    "exception,code,message", [(RuntimeError, 1, "Unexpected error"), (click.Abort, 130, "Aborted")]
)
def test_early_failures_use_the_same_output_boundary(public_cli, json_mode, monkeypatch, exception, code, message):
    def fail_load():
        raise exception("internal test detail")

    monkeypatch.setattr(cfg, "load", fail_load)
    result = public_cli(arguments(json_mode, "config", "show"))

    assert_error(result, code, json_mode, message)
    assert "internal test detail" not in result.stderr


@pytest.mark.parametrize("status,code", [(200, 0), (401, 2)])
def test_verbose_json_diagnostics_are_json_lines(public_cli, authed_profile, respx_mock, status, code):
    payload = [] if status == 200 else {"detail": LITERAL}
    respx_mock.get("/v1/dev/user/memories").respond(status, json=payload)

    result = public_cli(["--json", "--verbose", "memory", "list"])

    assert result.exit_code == code, result
    diagnostics = [json.loads(line) for line in result.stderr.splitlines()]
    assert "GET /v1/dev/user/memories" in diagnostics[0]["debug"]
    if code == 0:
        assert json.loads(result.stdout) == []
        assert len(diagnostics) == 1
    else:
        assert result.stdout == ""
        assert diagnostics[-1]["detail"] == LITERAL


def test_json_word_as_data_does_not_enable_json_mode(public_cli, authed_profile, respx_mock):
    respx_mock.post("/v1/dev/user/memories").respond(json={"id": "record-1", "content": "--json"})
    result = public_cli(["memory", "create", "--", "--json"])

    assert result.exit_code == 0, result
    assert "--json" in result.stdout
    assert "Memory created: record-1" in result.stderr


def test_global_option_value_is_not_a_json_flag(public_cli):
    result = public_cli(["--profile", "--json", "--unknown-option"])
    assert_error(result, 1, False, "No such option")
    assert result.stderr.startswith("Usage:")


@pytest.mark.parametrize("command", [[], ["memory"], ["config", "profile"]])
def test_missing_subcommand_is_a_json_usage_error(public_cli, command):
    result = public_cli(["--json", *command])
    assert_error(result, 1, True, "Missing command")


def test_ask_answer_and_sources_are_literal(public_cli, json_mode, authed_profile, respx_mock):
    payload = {"answer": LITERAL, "sources": [{"title": LITERAL, "id": "source-1"}]}
    respx_mock.post("/v1/dev/user/ask").respond(json=payload)
    result = public_cli(arguments(json_mode, "ask", "A test question"))

    assert result.exit_code == 0, result
    assert result.stderr == ""
    if json_mode:
        assert json.loads(result.stdout) == payload
    else:
        assert result.stdout.count(LITERAL) == 2
        assert "[source-1]" in result.stdout


def test_refresh_with_no_response_body_completes(public_cli, json_mode, monkeypatch):
    config = cfg.load()
    config.set_profile(cfg.Profile(name="default", auth_method="oauth", id_token="fake-test-token"))
    cfg.save(config)
    refresh = Mock(return_value="fake-refreshed-test-token")
    monkeypatch.setattr(oauth, "refresh_id_token", refresh)
    result = public_cli(arguments(json_mode, "auth", "refresh"))

    assert result.exit_code == 0, result
    refresh.assert_called_once_with("default")
    if json_mode:
        assert json.loads(result.stdout) is None
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert "Refreshed Firebase ID token" in result.stderr


def test_local_tool_uses_the_same_diagnostic_and_data_boundary(public_cli, json_mode, monkeypatch):
    local_url = "http://127.0.0.1:47778"
    monkeypatch.setenv(cfg.ENV_LOCAL_API_URL, local_url)
    monkeypatch.setenv(cfg.ENV_LOCAL_TOKEN, "fake-local-test-token")
    with respx.mock() as router:
        route = router.post(local_url + "/v1/local/tool").respond(json={"result": LITERAL})
        result = public_cli(arguments(json_mode, "--verbose", "local", "call", LITERAL))

    assert result.exit_code == 0, result
    assert route.call_count == 1
    if json_mode:
        assert json.loads(result.stdout) == LITERAL
        assert LITERAL in json.loads(result.stderr)["debug"]
    else:
        assert LITERAL in result.stdout
        assert LITERAL in result.stderr


def test_help_remains_a_text_interface(public_cli):
    result = public_cli(["--json", "--help"])
    assert result.exit_code == 0, result
    assert "Usage:" in result.stdout
    assert "memory" in result.stdout
    assert result.stderr == ""


def test_human_incomplete_command_still_shows_help(public_cli, cli_runner):
    expected_status = cli_runner.invoke(app, ["memory"]).exit_code
    result = public_cli(["memory"])
    assert result.exit_code == expected_status, result
    assert "Usage:" in result.stdout
    assert "create" in result.stdout
    assert result.stderr == ""


def test_human_declined_confirmation_does_not_delete(public_cli, authed_profile, respx_mock):
    result = public_cli(["memory", "delete", "record-1"], input_text="n\n")
    assert result.exit_code == 1, result
    assert result.stdout.strip() == ""  # Older Click may write the prompt's trailing space here.
    assert "Cancelled" in result.stderr
    assert respx_mock.calls.call_count == 0
