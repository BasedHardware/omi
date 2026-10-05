"""Cloud chat CLI: shared state, stream framing, and safe reset."""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest

from omi_cli import config as cfg
from omi_cli.auth.store import store_oauth_tokens
from omi_cli.client import OmiClient
from omi_cli.errors import TransportError
from omi_cli.main import app

FAKE_API_BASE = "https://api.test.omi.local"


def _oauth_profile(config_path) -> None:
    store_oauth_tokens(
        "default",
        id_token="firebase-test-token",
        refresh_token="refresh-test-token",
        expires_at=time.time() + 3600,
        api_base=FAKE_API_BASE,
    )


def _done(text: str) -> str:
    encoded = base64.b64encode(json.dumps({"id": "msg-1", "sender": "ai", "text": text}).encode()).decode()
    return f"done: {encoded}\n\n"


def test_chat_requires_browser_oauth(authed_profile, cli_runner, respx_mock) -> None:
    result = cli_runner.invoke(app, ["chat", "Hello"])
    assert result.exit_code != 0
    assert "browser sign-in" in result.output
    assert not respx_mock.calls


def test_chat_streams_and_uses_shared_default_thread(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.post("/v2/messages").mock(
        return_value=httpx.Response(200, text="data: Hello\n\ndata: __CRLF__friend\n\n" + _done("Hello\nfriend"))
    )
    result = cli_runner.invoke(app, ["chat", "Hi"])
    assert result.exit_code == 0, result.output
    assert "Omi: Hello\nfriend" in result.stdout
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer firebase-test-token"
    assert request.headers["X-Omi-Chat-Failure-Protocol"] == "1"
    assert json.loads(request.content) == {"text": "Hi"}
    assert request.url.query == b""


def test_chat_json_is_one_final_document(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(return_value=httpx.Response(200, text=f"data: partial\n\n{_done('final')}"))
    result = cli_runner.invoke(app, ["--json", "chat", "Hi"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["text"] == "final"


def test_verbose_chat_does_not_read_stream_before_rendering(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(return_value=httpx.Response(200, text=_done("Hello")))
    result = cli_runner.invoke(app, ["--verbose", "chat", "Hi"])
    assert result.exit_code == 0, result.output
    assert "Omi: Hello" in result.stdout
    assert "POST /v2/messages" in result.stderr


def test_history_uses_cloud_chat_and_reads_chronologically(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.get("/v2/messages").mock(
        return_value=httpx.Response(200, json=[{"sender": "ai", "text": "Two"}, {"sender": "human", "text": "One"}])
    )
    result = cli_runner.invoke(app, ["chat", "--history", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert result.stdout.index("You: One") < result.stdout.index("Omi: Two")
    assert route.calls.last.request.url.params["limit"] == "2"


def test_clear_requires_explicit_confirmation(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.delete("/v2/messages").mock(return_value=httpx.Response(200, json={"text": "Welcome"}))
    declined = cli_runner.invoke(app, ["chat", "--clear"], input="n\n")
    assert declined.exit_code == 0, declined.output
    assert not route.called
    confirmed = cli_runner.invoke(app, ["chat", "--clear", "--yes"])
    assert confirmed.exit_code == 0, confirmed.output
    assert route.call_count == 1
    assert "across clients" in declined.stdout


def test_declined_clear_keeps_json_stdout_machine_readable(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.delete("/v2/messages").mock(return_value=httpx.Response(200, json={}))
    result = cli_runner.invoke(app, ["--json", "chat", "--clear"], input="n\n")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"cleared": False}
    assert not route.called


def test_confirmed_clear_keeps_json_stdout_machine_readable(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.delete("/v2/messages").mock(return_value=httpx.Response(200, json={}))
    result = cli_runner.invoke(app, ["--json", "chat", "--clear"], input="y\n")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"cleared": True}
    assert route.call_count == 1


def test_repl_task_commands_use_user_routes(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.get("/v1/action-items").mock(
        return_value=httpx.Response(200, json={"action_items": [{"id": "task-1", "description": "Write notes"}]})
    )
    add = respx_mock.post("/v1/action-items").mock(
        return_value=httpx.Response(200, json={"id": "task-2", "description": "Review PR"})
    )
    done = respx_mock.patch("/v1/action-items/task-1/completed").mock(
        return_value=httpx.Response(200, json={"id": "task-1", "description": "Write notes", "completed": True})
    )
    result = cli_runner.invoke(app, ["chat"], input="/tasks\n/task add Review PR\n/task done task-1\n/quit\n")
    assert result.exit_code == 0, result.output
    assert "Write notes" in result.stdout
    assert "Task added" in result.stdout
    assert "Task completed" in result.stdout
    assert json.loads(add.calls.last.request.content) == {"description": "Review PR"}
    assert done.calls.last.request.url.params["completed"] == "true"


def test_stream_error_is_not_reported_as_success(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(
        return_value=httpx.Response(200, text='error: {"error":"quota_exceeded"}\n\n' + _done("Try later"))
    )
    result = cli_runner.invoke(app, ["chat", "Hi"])
    assert result.exit_code != 0
    assert "quota exceeded" in result.output.lower()
    assert "Try later" not in result.output


def test_truncated_stream_requires_history_check(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(return_value=httpx.Response(200, text="data: Hello\n\n"))
    result = cli_runner.invoke(app, ["chat", "Hi"])
    assert result.exit_code != 0
    assert "ended early" in result.output


def test_chat_write_is_not_retried_on_server_error(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    route = respx_mock.post("/v2/messages").mock(return_value=httpx.Response(503, json={"detail": "busy"}))
    result = cli_runner.invoke(app, ["chat", "Hi"])
    assert result.exit_code != 0
    assert route.call_count == 1


def test_malformed_done_frame_fails_cleanly(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(return_value=httpx.Response(200, text="done: not-base64!\n\n"))
    result = cli_runner.invoke(app, ["chat", "Hi"])
    assert result.exit_code != 0
    assert "Invalid chat response" in result.output


def test_malformed_stream_encoding_gets_history_warning(config_path, respx_mock) -> None:
    _oauth_profile(config_path)
    respx_mock.post("/v2/messages").mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(b"not gzip"), headers={"Content-Encoding": "gzip"})
    )
    with OmiClient(cfg.load().get_profile("default")) as client:
        with pytest.raises(TransportError) as error:
            list(client.stream_post_lines("/v2/messages", json_body={"text": "Hi"}))
    assert error.value.message == "Chat connection interrupted"
    assert "--history" in (error.value.detail or "")


def test_json_repl_is_rejected_before_network(config_path, cli_runner, respx_mock) -> None:
    _oauth_profile(config_path)
    result = cli_runner.invoke(app, ["--json", "chat"])
    assert result.exit_code != 0
    assert not respx_mock.calls
