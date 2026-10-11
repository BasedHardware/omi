"""``omi app``: build and test an Omi app without a device.

Omi posts events to the endpoint a user configures in Developer Settings.
Seeing one meant the phone app and a publicly reachable URL, and for the day
summary, waiting for the cron tick. These commands replay the same requests
locally and receive them locally.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import typer

from omi_cli import webhook_events as events_mod
from omi_cli import webhook_target
from omi_cli.errors import ServerError, TransportError, UsageError
from omi_cli.json_input import load_json_input

if TYPE_CHECKING:
    from omi_cli.main import AppContext


app = typer.Typer(no_args_is_help=True)

_EVENTS_COLUMNS = ["event", "content_type", "query_params", "body"]
_VERIFY_COLUMNS = ["check", "result", "detail"]

# What the backend's pinned delivery client allows, so a slow connect fails
# here exactly as it would in production.
_DELIVERY_TIMEOUT = httpx.Timeout(webhook_target.READ_TIMEOUT_SECONDS, connect=webhook_target.CONNECT_TIMEOUT_SECONDS)


def _ctx(typer_ctx: typer.Context) -> "AppContext":
    obj = typer_ctx.obj
    if obj is None:  # pragma: no cover
        raise RuntimeError("AppContext not initialized")
    return obj  # type: ignore[no-any-return]


def _resolve_event(name: str) -> events_mod.WebhookEvent:
    event = events_mod.get_event(name)
    if event is None:
        known = ", ".join(events_mod.event_names())
        raise UsageError(f"Unknown event {name!r}", detail=f"Known events: {known}")
    return event


def append_query_params(url: str, params: dict[str, str]) -> str:
    """Append Omi's own query parameters, replacing any the user already set.

    Same rule as the backend: a key Omi owns wins over one already in the URL.
    """
    parts = urlsplit(url)
    kept = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in params]
    kept.extend(params.items())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def _retry_note(status_code: int) -> str:
    if events_mod.is_retried(status_code):
        attempts = len(events_mod.RETRY_DELAYS_SECONDS) + 1
        delays = ", ".join(f"{delay:g}s" for delay in events_mod.RETRY_DELAYS_SECONDS)
        head = f"Omi would retry this delivery: {attempts} attempts, {delays} apart."
    else:
        head = f"Omi does not retry HTTP {status_code}, since a repeat post can only reproduce it."
    return (
        f"{head} A failed delivery goes to the dead-letter queue: "
        f"{events_mod.CIRCUIT_BREAKER_FAILURES} in a row pause this URL for "
        f"{events_mod.CIRCUIT_BREAKER_PAUSE_SECONDS:g}s, {events_mod.AUTO_DISABLE_FAILURES} disable the webhook."
    )


def _sentences(*parts: Optional[str]) -> str:
    kept = [part.rstrip(". ") for part in parts if part]
    return ". ".join(kept) + "." if kept else ""


def _redirect_note(response: httpx.Response) -> str:
    location = response.headers.get("location")
    tail = f" It points at {location}." if location else ""
    return f"Omi never follows redirects, so HTTP {response.status_code} is a failed delivery.{tail}"


def _failure_detail(response: httpx.Response) -> str:
    retry = _retry_note(response.status_code)
    if 300 <= response.status_code < 400:
        return f"{_redirect_note(response)} {retry}"
    return retry


def _notification_note(response: httpx.Response) -> Optional[str]:
    """What Omi would do with a real-time transcript reply."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    message = body.get("message")
    if not isinstance(message, str) or not message:
        return None
    if response.status_code != 200:
        return f"Message ignored: Omi only reads the reply on HTTP 200, not {response.status_code}."
    if len(message) > events_mod.NOTIFICATION_MIN_MESSAGE_LENGTH:
        return f"Omi would notify the user: {message}"
    return (
        f"Message ignored: Omi only notifies when it is longer than "
        f"{events_mod.NOTIFICATION_MIN_MESSAGE_LENGTH} characters."
    )


@app.command("events", help="List the webhook events an Omi app can receive.")
def list_events(typer_ctx: typer.Context) -> None:
    ctx = _ctx(typer_ctx)
    rows: list[dict[str, Any]] = []
    for event in events_mod.EVENTS.values():
        rows.append(
            {
                "event": event.name,
                "content_type": event.content_type,
                "query_params": ", ".join(event.query_params),
                "body": event.body,
                "summary": event.summary,
                "response": event.response_note,
            }
        )
    if ctx.renderer.json_mode:
        ctx.renderer.emit(rows)
        return
    ctx.renderer.emit(rows, columns=_EVENTS_COLUMNS, title="Omi app webhook events")
    ctx.renderer.info("Every event is a POST to the configured URL. `omi app payload <event>` prints a sample body.")


@app.command("payload", help="Print the sample body for one event.")
def print_payload(
    typer_ctx: typer.Context,
    event_name: str = typer.Argument(..., metavar="EVENT", help="Event name from `omi app events`."),
    uid: str = typer.Option(events_mod.SAMPLE_UID, "--uid", help="uid to stamp into the sample."),
) -> None:
    ctx = _ctx(typer_ctx)
    event = _resolve_event(event_name)
    payload = event.builder(uid, datetime.now(timezone.utc))
    if isinstance(payload, bytes):
        raise UsageError(
            f"{event.name} sends {event.content_type}, not JSON",
            detail=f"{len(payload)} bytes per request. Use `omi app send {event.name}` to deliver it.",
        )
    ctx.renderer.emit(payload)


@app.command("send", help="Send one sample event to a webhook URL.")
def send_event(
    typer_ctx: typer.Context,
    event_name: str = typer.Argument(..., metavar="EVENT", help="Event name from `omi app events`."),
    to: str = typer.Option(..., "--to", help="Webhook URL to POST to."),
    uid: str = typer.Option(events_mod.SAMPLE_UID, "--uid", help="uid Omi would send for the user."),
    payload_file: Optional[str] = typer.Option(
        None, "--payload-file", help="Send this JSON body instead of the sample. '-' reads stdin."
    ),
    idempotency_key: Optional[str] = typer.Option(
        None, "--idempotency-key", help="Reuse one key across sends to exercise your de-duplication."
    ),
    timeout: float = typer.Option(
        webhook_target.READ_TIMEOUT_SECONDS, "--timeout", min=0.1, help="Request timeout in seconds."
    ),
) -> None:
    ctx = _ctx(typer_ctx)
    event = _resolve_event(event_name)
    payload = event.builder(uid, datetime.now(timezone.utc))

    if payload_file is not None:
        raw = _read_payload_file(payload_file)
        if isinstance(payload, bytes):
            payload = raw
        else:
            try:
                parsed = load_json_input(raw)
            except ValueError as exc:
                raise UsageError("Payload file is not valid JSON", detail=str(exc)) from exc
            if not isinstance(parsed, dict):
                raise UsageError("Payload file must contain a JSON object")
            payload = parsed

    url = append_query_params(to, events_mod.request_params(event, uid))
    headers = {"Content-Type": event.content_type}
    # Same precedence as the backend: the key the event carries, else a fresh one.
    headers["Idempotency-Key"] = idempotency_key or events_mod.idempotency_key(event, payload) or str(uuid.uuid4())

    started = time.monotonic()
    try:
        if isinstance(payload, bytes):
            response = httpx.post(url, content=payload, headers=headers, timeout=timeout, follow_redirects=False)
        else:
            response = httpx.post(url, json=payload, headers=headers, timeout=timeout, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise TransportError(f"Could not reach {url}", detail=str(exc)) from exc
    elapsed_ms = int((time.monotonic() - started) * 1000)

    ok = 200 <= response.status_code < 300
    note = _notification_note(response) if event.name == "realtime_transcript" and ok else None

    if ctx.renderer.json_mode:
        ctx.renderer.emit(
            {
                "event": event.name,
                "url": url,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "ok": ok,
                "response": response.text[:2000],
                "note": note or (None if ok else _failure_detail(response)),
            }
        )
    else:
        ctx.renderer.emit(
            {
                "event": event.name,
                "url": url,
                "status": f"{response.status_code} in {elapsed_ms} ms",
                "response": response.text[:500] or "(empty)",
            }
        )
        if note:
            ctx.renderer.info(note)
        if ok:
            ctx.renderer.success("Delivery accepted.")

    if not ok:
        # Exit through the CliError ladder, not typer.Exit: main() runs Click in
        # non-standalone mode, where a raised Exit is returned rather than
        # raised, so the process would report success on a rejected delivery.
        failure = ServerError if response.status_code >= 500 else UsageError
        raise failure(
            f"Receiver answered HTTP {response.status_code}",
            detail=_failure_detail(response),
        )


@app.command("verify", help="Check whether a webhook URL would work in production.")
def verify_receiver(
    typer_ctx: typer.Context,
    to: str = typer.Option(..., "--to", help="Webhook URL to check."),
    event_names: Optional[list[str]] = typer.Option(
        None, "--event", help="Check only these events. Repeatable, defaults to all of them."
    ),
    uid: str = typer.Option(events_mod.SAMPLE_UID, "--uid", help="uid Omi would send for the user."),
) -> None:
    ctx = _ctx(typer_ctx)
    events = [_resolve_event(name) for name in (event_names or events_mod.event_names())]

    target = webhook_target.inspect_target(to)
    rows: list[dict[str, Any]] = [
        {
            "check": "delivery target",
            "result": "pass" if target.ok else "fail",
            "detail": _sentences(target.summary, target.detail),
        }
    ]
    unreachable = False
    latencies: list[int] = []

    for event in events:
        payload = event.builder(uid, datetime.now(timezone.utc))
        url = append_query_params(to, events_mod.request_params(event, uid))
        headers = {"Content-Type": event.content_type}
        headers["Idempotency-Key"] = events_mod.idempotency_key(event, payload) or str(uuid.uuid4())
        started = time.monotonic()
        try:
            if isinstance(payload, bytes):
                response = httpx.post(
                    url, content=payload, headers=headers, timeout=_DELIVERY_TIMEOUT, follow_redirects=False
                )
            else:
                response = httpx.post(
                    url, json=payload, headers=headers, timeout=_DELIVERY_TIMEOUT, follow_redirects=False
                )
        except httpx.HTTPError as exc:
            rows.append({"check": event.name, "result": "fail", "detail": _sentences(f"No usable response: {exc}")})
            unreachable = True
            continue
        elapsed_ms = int((time.monotonic() - started) * 1000)
        latencies.append(elapsed_ms)
        status = f"HTTP {response.status_code} in {elapsed_ms} ms"
        if 200 <= response.status_code < 300:
            note = _notification_note(response) if event.name == "realtime_transcript" else None
            rows.append(
                {
                    "check": event.name,
                    "result": "pass",
                    "detail": _sentences(status, note),
                }
            )
            continue
        rows.append({"check": event.name, "result": "fail", "detail": _sentences(status, _failure_detail(response))})
        if response.status_code >= 500:
            unreachable = True

    if latencies:
        rows.append(
            {
                "check": "response time",
                "result": "pass",
                "detail": _sentences(
                    f"slowest {max(latencies)} ms",
                    f"Omi allows {webhook_target.CONNECT_TIMEOUT_SECONDS:g}s to connect and "
                    f"{webhook_target.READ_TIMEOUT_SECONDS:g}s for the response",
                ),
            }
        )

    if ctx.renderer.json_mode:
        ctx.renderer.emit(rows)
    else:
        ctx.renderer.emit(rows, columns=_VERIFY_COLUMNS, title=f"omi app verify {to}")

    failures = [str(row["check"]) for row in rows if row["result"] == "fail"]
    if failures:
        failure = ServerError if unreachable else UsageError
        raise failure(
            f"{len(failures)} of {len(rows)} checks failed",
            detail=f"Failed: {', '.join(failures)}.",
        )
    if not ctx.renderer.json_mode:
        ctx.renderer.success("This endpoint is ready for Omi.")


def _read_payload_file(payload_file: str) -> bytes:
    if payload_file == "-":
        return sys.stdin.buffer.read()
    path = Path(payload_file)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise UsageError(f"Could not read {payload_file}", detail=str(exc)) from exc


class _WebhookHandler(BaseHTTPRequestHandler):
    """Receiver that prints what arrived and answers however the user asked."""

    # 1.0 closes each connection, so a single-threaded receiver cannot be held
    # open by one client while the next delivery waits.
    protocol_version = "HTTP/1.0"
    reply_status: int = 200
    reply_body: bytes = b"{}"
    on_request: Optional[Any] = None

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's contract
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        parts = urlsplit(self.path)
        record = {
            "path": parts.path,
            "query": dict(parse_qsl(parts.query, keep_blank_values=True)),
            "content_type": self.headers.get("Content-Type", ""),
            "idempotency_key": self.headers.get("Idempotency-Key", ""),
            "bytes": len(body),
            "body": _decode_body(self.headers.get("Content-Type", ""), body),
        }
        self.send_response(self.reply_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.reply_body)))
        self.end_headers()
        self.wfile.write(self.reply_body)
        if callable(self.on_request):
            self.on_request(record)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence the default stderr access log; the handler prints its own."""


def _decode_body(content_type: str, body: bytes) -> Any:
    if "application/json" in content_type:
        try:
            return json.loads(body)
        except ValueError:
            return body.decode("utf-8", "replace")
    if not body:
        return None
    return f"<{len(body)} bytes of {content_type or 'unknown content type'}>"


@app.command("serve", help="Receive webhook deliveries locally and print them.")
def serve(
    typer_ctx: typer.Context,
    port: int = typer.Option(8787, "--port", min=0, max=65535, help="Port to listen on. 0 picks a free one."),
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind."),
    status: int = typer.Option(200, "--status", min=100, max=599, help="Status code to answer with."),
    reply: str = typer.Option("{}", "--reply", help='JSON body to answer with, e.g. {"message": "Got it"}.'),
    requests: int = typer.Option(0, "--requests", min=0, help="Exit after this many deliveries. 0 waits forever."),
) -> None:
    ctx = _ctx(typer_ctx)
    try:
        load_json_input(reply)
    except ValueError as exc:
        raise UsageError("--reply is not valid JSON", detail=str(exc)) from exc

    received: list[dict[str, Any]] = []

    def record(entry: dict[str, Any]) -> None:
        received.append(entry)
        if not ctx.renderer.json_mode:
            ctx.renderer.emit(entry, title=f"delivery {len(received)}")

    handler = type(
        "_BoundWebhookHandler",
        (_WebhookHandler,),
        {"reply_status": status, "reply_body": reply.encode("utf-8"), "on_request": staticmethod(record)},
    )

    with HTTPServer((host, port), handler) as server:
        bound_port = server.server_address[1]
        ctx.renderer.info(f"Listening on http://{host}:{bound_port}, point your webhook at it, or:")
        ctx.renderer.info(f"  omi app send realtime_transcript --to http://{host}:{bound_port}/webhook")
        try:
            while requests == 0 or len(received) < requests:
                server.handle_request()
        except KeyboardInterrupt:  # pragma: no cover - interactive path
            ctx.renderer.info("Stopped.")

    if ctx.renderer.json_mode:
        ctx.renderer.emit(received)
