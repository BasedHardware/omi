"""``omi app`` webhook contracts, sample deliveries, and the local receiver."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from typer.testing import CliRunner

from omi_cli import webhook_events as events_mod
from omi_cli import webhook_target
from omi_cli.commands import app as app_cmd
from omi_cli.errors import EXIT_SERVER, EXIT_USAGE, UsageError
from omi_cli.main import app

_FIXED_NOW = __import__("datetime").datetime(2026, 10, 8, 9, 30, tzinfo=__import__("datetime").timezone.utc)

HOOK_URL = "http://receiver.test.local/hook"


def _run(cli_runner: CliRunner, *args: str, **kwargs: Any) -> Any:
    return cli_runner.invoke(app, list(args), **kwargs)


def test_events_lists_every_webhook_the_backend_sends(cli_runner: CliRunner, config_path: Path) -> None:
    result = _run(cli_runner, "--json", "app", "events")

    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert [row["event"] for row in rows] == [
        "memory_created",
        "realtime_transcript",
        "day_summary",
        "audio_bytes",
        "button_event",
    ]


def test_payload_prints_the_sample_conversation(cli_runner: CliRunner, config_path: Path) -> None:
    result = _run(cli_runner, "--json", "app", "payload", "memory_created")

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["structured"]["title"]
    assert payload["transcript_segments"][0]["speaker_name"]


def test_payload_refuses_the_audio_event(cli_runner: CliRunner, config_path: Path) -> None:
    result = _run(cli_runner, "app", "payload", "audio_bytes")

    assert result.exit_code == 1
    assert "not JSON" in result.stderr


def test_unknown_event_is_a_usage_error(cli_runner: CliRunner, config_path: Path) -> None:
    result = _run(cli_runner, "app", "send", "nope", "--to", HOOK_URL)

    assert result.exit_code == 1
    assert "Unknown event" in result.stderr


def test_unknown_event_detail_names_every_event() -> None:
    with pytest.raises(UsageError) as raised:
        app_cmd._resolve_event("nope")

    detail = raised.value.detail or ""
    for name in events_mod.event_names():
        assert name in detail


def test_send_posts_json_with_uid_and_idempotency_key(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL)

    assert result.exit_code == 0
    request = route.calls[0].request
    assert dict(request.url.params) == {"uid": events_mod.SAMPLE_UID}
    assert request.headers["content-type"] == "application/json"
    assert request.headers["idempotency-key"]
    assert json.loads(request.content)["structured"]["category"]


def test_send_keeps_the_query_the_user_already_had(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "day_summary", "--to", f"{HOOK_URL}?team=design&uid=stale")

    assert result.exit_code == 0
    params = dict(route.calls[0].request.url.params)
    assert params == {"team": "design", "uid": events_mod.SAMPLE_UID}


def test_send_audio_uses_octet_stream_and_sample_rate(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "audio_bytes", "--to", HOOK_URL)

    assert result.exit_code == 0
    request = route.calls[0].request
    assert request.headers["content-type"] == "application/octet-stream"
    assert dict(request.url.params)["sample_rate"] == str(events_mod.AUDIO_SAMPLE_RATE)
    assert len(request.content) == events_mod.AUDIO_SAMPLE_RATE * 2


def test_send_generates_a_fresh_idempotency_key_each_send(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        assert _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL).exit_code == 0
        assert _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL).exit_code == 0

    keys = [call.request.headers["idempotency-key"] for call in route.calls]
    assert keys[0] != keys[1]


def test_send_can_pin_the_idempotency_key(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL, "--idempotency-key", "pinned-key")

    assert result.exit_code == 0
    assert route.calls[0].request.headers["idempotency-key"] == "pinned-key"


def test_send_button_event_keys_idempotency_on_the_event_id(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "button_event", "--to", HOOK_URL)

    assert result.exit_code == 0
    request = route.calls[0].request
    assert request.headers["idempotency-key"] == json.loads(request.content)["event_id"]


def test_send_reports_the_notification_a_reply_would_trigger(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(
            return_value=httpx.Response(200, json={"message": "Noted, I will remind you"})
        )
        result = _run(cli_runner, "app", "send", "realtime_transcript", "--to", HOOK_URL)

    assert result.exit_code == 0
    assert "would notify the user: Noted, I will remind you" in result.stderr


def test_send_says_when_a_reply_is_too_short_to_notify(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={"message": "ok"}))
        result = _run(cli_runner, "app", "send", "realtime_transcript", "--to", HOOK_URL)

    assert result.exit_code == 0
    assert "Message ignored" in result.stderr


def test_send_says_omi_only_reads_a_reply_on_a_200(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(
            return_value=httpx.Response(201, json={"message": "Noted, I will remind you"})
        )
        result = _run(cli_runner, "app", "send", "realtime_transcript", "--to", HOOK_URL)

    assert result.exit_code == 0
    assert "only reads the reply on HTTP 200" in result.stderr


def test_send_fails_with_the_server_exit_code_on_a_5xx(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(500, json={}))
        result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL)

    assert result.exit_code == EXIT_SERVER
    assert "HTTP 500" in result.stderr


def test_send_fails_with_the_usage_exit_code_on_a_4xx(cli_runner: CliRunner, config_path: Path) -> None:
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(404, json={}))
        result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL)

    assert result.exit_code == EXIT_USAGE
    assert "HTTP 404" in result.stderr


def test_failure_detail_names_the_retry_schedule() -> None:
    detail = app_cmd._retry_note(500)

    assert "4 attempts" in detail
    assert "disable the webhook" in detail


def test_failure_detail_does_not_promise_retries_the_backend_skips() -> None:
    """A 4xx other than 408 or 429 is posted once and dropped."""
    assert "does not retry" in app_cmd._retry_note(404)
    assert "4 attempts" in app_cmd._retry_note(429)
    assert "4 attempts" in app_cmd._retry_note(408)


def test_a_rejected_delivery_fails_the_real_process(tmp_path: Path) -> None:
    """The exit code has to survive main(), which runs Click in non-standalone mode."""
    port = _free_port()

    class _Reject(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's contract
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(500)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", port), _Reject)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "omi_cli", "app", "send", "memory_created", "--to", f"http://127.0.0.1:{port}/hook"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "OMI_CONFIG": str(tmp_path / "config.toml"), "NO_COLOR": "1"},
        )
    finally:
        server.server_close()
        thread.join(timeout=5)

    assert completed.returncode == EXIT_SERVER
    assert "HTTP 500" in completed.stderr


def test_send_can_replace_the_sample_body(cli_runner: CliRunner, config_path: Path, tmp_path: Path) -> None:
    body = tmp_path / "payload.json"
    body.write_text(json.dumps({"id": "mine"}), encoding="utf-8")

    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL, "--payload-file", str(body))

    assert result.exit_code == 0
    assert json.loads(route.calls[0].request.content) == {"id": "mine"}


def test_send_rejects_a_payload_file_that_is_not_json(cli_runner: CliRunner, config_path: Path, tmp_path: Path) -> None:
    body = tmp_path / "payload.json"
    body.write_text("{not json", encoding="utf-8")

    result = _run(cli_runner, "app", "send", "memory_created", "--to", HOOK_URL, "--payload-file", str(body))

    assert result.exit_code == 1
    assert "not valid JSON" in result.stderr


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_serve_receives_a_delivery_and_answers_with_the_chosen_reply(cli_runner: CliRunner, config_path: Path) -> None:
    port = _free_port()
    captured: dict[str, Any] = {}

    def deliver() -> None:
        url = f"http://127.0.0.1:{port}/webhook?uid={events_mod.SAMPLE_UID}"
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                response = httpx.post(url, json={"segments": []}, headers={"Idempotency-Key": "key-1"}, timeout=5.0)
            except httpx.HTTPError:
                time.sleep(0.05)
                continue
            captured["status"] = response.status_code
            captured["body"] = response.json()
            return

    sender = threading.Thread(target=deliver, daemon=True)
    sender.start()
    result = _run(
        cli_runner,
        "--json",
        "app",
        "serve",
        "--port",
        str(port),
        "--requests",
        "1",
        "--reply",
        '{"message": "Got it, noted"}',
    )
    sender.join(timeout=10)

    assert result.exit_code == 0
    assert captured["status"] == 200
    assert captured["body"] == {"message": "Got it, noted"}
    received = json.loads(result.stdout)
    assert received[0]["query"] == {"uid": events_mod.SAMPLE_UID}
    assert received[0]["idempotency_key"] == "key-1"


def test_serve_rejects_a_reply_that_is_not_json(cli_runner: CliRunner, config_path: Path) -> None:
    result = _run(cli_runner, "app", "serve", "--port", str(_free_port()), "--reply", "{oops")

    assert result.exit_code == 1
    assert "not valid JSON" in result.stderr


ROOT_DIR = Path(__file__).resolve().parents[3]


def test_conversation_sample_matches_the_published_schema() -> None:
    """The memory_created sample is the integration conversation shape, not a guess."""
    spec = json.loads((ROOT_DIR / "docs" / "api-reference" / "openapi.json").read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    conversation = schemas["DeveloperConversation"]
    structured = schemas["DeveloperConversationStructured"]
    segment = schemas["DeveloperTranscriptSegment"]

    sample = events_mod.EVENTS["memory_created"].builder(events_mod.SAMPLE_UID, _FIXED_NOW)
    assert isinstance(sample, dict)

    # The delivery is the full conversation dump, so a segment carries these two
    # as well; the dev API's trimmed shape does not define them.
    segment_extras = {"speaker", "is_user"}

    assert set(sample) <= set(conversation["properties"])
    assert set(conversation["required"]) <= set(sample)
    # redact_conversation_for_integration drops geolocation before sending.
    assert "geolocation" not in sample
    assert set(sample["structured"]) <= set(structured["properties"])
    assert set(structured["required"]) <= set(sample["structured"])
    for item in sample["transcript_segments"]:
        assert set(item) - segment_extras <= set(segment["properties"])
        assert set(segment["required"]) <= set(item)


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's proxy env out of the loopback receiver test."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)


PUBLIC_ADDRESS = ["93.184.216.34"]


def _public_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook_target, "resolve_addresses", lambda host: list(PUBLIC_ADDRESS))


def test_target_rejects_an_address_omi_will_not_deliver_to() -> None:
    for host, address in (
        ("127.0.0.1", "127.0.0.1"),
        ("intranet.test", "10.0.0.8"),
        ("tailscale.test", "100.100.0.4"),
        ("metadata.test", "169.254.169.254"),
    ):
        report = webhook_target.inspect_target(f"http://{host}/webhook", resolver=lambda _: [address])
        assert not report.ok
        assert address in report.summary
        assert "never receives an event" in (report.detail or "")


def test_target_rejects_a_scheme_and_a_host_omi_cannot_use() -> None:
    assert not webhook_target.inspect_target("ftp://example.com/webhook").ok
    unresolvable = webhook_target.inspect_target(
        "https://nope.test/webhook",
        resolver=lambda _: (_ for _ in ()).throw(socket.gaierror("no such host")),
    )
    assert not unresolvable.ok
    assert "cannot resolve" in unresolvable.summary


def test_target_accepts_a_public_address_and_flags_plain_http() -> None:
    https = webhook_target.inspect_target("https://example.com/webhook", resolver=lambda _: PUBLIC_ADDRESS)
    assert https.ok
    assert https.detail is None

    http = webhook_target.inspect_target("http://example.com/webhook", resolver=lambda _: PUBLIC_ADDRESS)
    assert http.ok
    assert "unencrypted" in (http.detail or "")


def test_verify_passes_a_receiver_that_answers_every_event(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _public_resolver(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "--json", "app", "verify", "--to", HOOK_URL)

    assert result.exit_code == 0
    assert len(route.calls) == len(events_mod.event_names())
    rows = json.loads(result.stdout)
    assert [row["result"] for row in rows] == ["pass"] * len(rows)
    assert rows[0]["check"] == "delivery target"


def test_verify_only_sends_the_events_it_was_asked_for(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _public_resolver(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(204))
        result = _run(cli_runner, "app", "verify", "--to", HOOK_URL, "--event", "day_summary")

    assert result.exit_code == 0
    assert len(route.calls) == 1
    assert json.loads(route.calls[0].request.content)["summary_json"]


def test_verify_reports_a_redirect_as_a_failed_delivery(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _public_resolver(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(
            return_value=httpx.Response(302, headers={"Location": "https://elsewhere.test/hook"})
        )
        result = _run(cli_runner, "app", "verify", "--to", HOOK_URL, "--event", "memory_created")

    assert result.exit_code == EXIT_USAGE
    assert "never follows redirects" in result.stdout
    assert "elsewhere.test" in result.stdout


def test_verify_fails_with_the_server_exit_code_when_the_receiver_breaks(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _public_resolver(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(503))
        result = _run(cli_runner, "app", "verify", "--to", HOOK_URL, "--event", "memory_created")

    assert result.exit_code == EXIT_SERVER


def test_verify_still_checks_the_events_of_a_local_url(cli_runner: CliRunner, config_path: Path) -> None:
    """A loopback receiver answers, and the report still says Omi would never reach it."""
    with respx.mock(assert_all_called=True) as router:
        router.post("http://127.0.0.1:8787/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "verify", "--to", "http://127.0.0.1:8787/hook", "--event", "button_event")

    assert result.exit_code == EXIT_USAGE
    assert "non-public address" in result.stdout
    assert "button_event" in result.stdout


def test_verify_uses_the_delivery_clients_own_timeout_budget(
    cli_runner: CliRunner, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow connect has to fail here for the same reason it fails in production."""
    _public_resolver(monkeypatch)
    with respx.mock(assert_all_called=True) as router:
        route = router.post("http://receiver.test.local/hook").mock(return_value=httpx.Response(200, json={}))
        result = _run(cli_runner, "app", "verify", "--to", HOOK_URL, "--event", "memory_created")

    assert result.exit_code == 0
    timeout = route.calls[0].request.extensions["timeout"]
    assert timeout["connect"] == webhook_target.CONNECT_TIMEOUT_SECONDS
    assert timeout["read"] == webhook_target.READ_TIMEOUT_SECONDS


def test_target_fails_closed_on_an_address_it_cannot_read() -> None:
    report = webhook_target.inspect_target("https://odd.test/hook", resolver=lambda _: ["not-an-address"])

    assert not report.ok
    assert "cannot read" in report.summary
