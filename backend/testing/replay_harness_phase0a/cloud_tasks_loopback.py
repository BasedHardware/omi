"""Out-of-process Cloud Tasks loopback scheduler service (feasibility-only).

FEASIBILITY-ONLY: This is a minimal stateful scheduler model, NOT a faithful
Cloud Tasks control-plane. It receives task-creation calls from the admission
process over real loopback HTTP, validates the production task shape, stores
tasks, and delivers them to the worker over loopback HTTP. Named-task dedup
(AlreadyExists) is preserved; duplicate *delivery* is supported via a declared
fault control. Signature/issuer/expiry OIDC verification remains outside scope
(feasibility-only: one exact local token).

This process is deliberately NOT uvicorn/FastAPI — it proves the generic
launcher starts arbitrary declared commands, not just ASGI roles.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

# Install egress guard BEFORE any outbound connection.
from testing.replay_harness_phase0a.egress_guard import guard_from_env

_sink = guard_from_env()

import httpx  # noqa: E402

_WORKER_URL = os.getenv("OMI_REPLAY_WORKER_URL", "")
_OIDC_TOKEN = os.getenv("OMI_REPLAY_OIDC_TOKEN", "")
_OIDC_SA = os.getenv("OMI_REPLAY_OIDC_SA", "")
_OIDC_AUDIENCE = os.getenv("OMI_REPLAY_OIDC_AUDIENCE", "")
_QUEUE_PATH = os.getenv("OMI_REPLAY_QUEUE_PATH", "")
_DISPATCH_DEADLINE = int(os.getenv("OMI_REPLAY_DISPATCH_DEADLINE", "1500"))
_DUPLICATE_DELIVERY = int(os.getenv("OMI_REPLAY_DUPLICATE_DELIVERY", "0"))

_tasks: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_ready = threading.Event()


def _emit(event: dict[str, Any]) -> None:
    if _sink:
        _sink(event)


def _validate_task(payload: dict[str, Any]) -> None:
    """Validate the production tasks_v2.Task shape (feasibility-only: structural check)."""
    parent = payload.get("parent", "")
    if parent != _QUEUE_PATH:
        raise ValueError(f"task parent {parent!r} does not match queue {_QUEUE_PATH!r}")

    task_name = payload.get("task_name", "")
    if not task_name or f"{_QUEUE_PATH}/tasks/" not in task_name:
        raise ValueError("task name must be a child of the queue path")

    body = payload.get("body")
    if not isinstance(body, dict):
        raise ValueError("task body must be a JSON object")
    required_body_keys = {
        "schema_version",
        "job_id",
        "uid",
        "raw_blob_paths",
        "source",
        "should_lock",
        "conversation_id",
        "client_device_id",
    }
    missing = required_body_keys - set(body.keys())
    if missing:
        raise ValueError(f"task body missing keys: {missing}")

    url = payload.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise ValueError(f"task URL must be loopback http, got {url!r}")
    if parsed.path != "/v2/sync-jobs/run":
        raise ValueError(f"task URL path must be /v2/sync-jobs/run, got {parsed.path!r}")

    deadline = payload.get("dispatch_deadline_seconds", 0)
    if deadline != _DISPATCH_DEADLINE:
        raise ValueError(f"dispatch deadline {deadline} != {_DISPATCH_DEADLINE}")

    sa = payload.get("oidc_sa", "")
    audience = payload.get("oidc_audience", "")
    if sa != _OIDC_SA or audience != _OIDC_AUDIENCE:
        raise ValueError("OIDC service account or audience mismatch")


def _deliver(body: dict[str, Any], url: str, *, retry_count: int) -> int:
    """Deliver one task body to the worker over loopback HTTP. Returns HTTP status."""
    headers = {
        "Authorization": f"Bearer {_OIDC_TOKEN}",
        "Content-Type": "application/json",
        "X-CloudTasks-TaskRetryCount": str(retry_count),
    }
    _emit({"event": "task_delivering", "job_id": body.get("job_id", ""), "retry_count": retry_count})
    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            response = client.post(url, json=body, headers=headers)
        _emit(
            {
                "event": "task_delivered",
                "job_id": body.get("job_id", ""),
                "retry_count": retry_count,
                "status_code": response.status_code,
            }
        )
        return response.status_code
    except Exception as exc:
        _emit({"event": "task_delivery_failed", "job_id": body.get("job_id", ""), "error_type": type(exc).__name__})
        return 599


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/__replay/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "role": "cloud-tasks-loopback"}).encode())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/__replay/enqueue":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_error(400, "invalid JSON")
            return

        task_name = payload.get("task_name", "")

        # Validate the production task shape.
        try:
            _validate_task(payload)
        except ValueError as exc:
            _emit({"event": "task_rejected", "task_name": task_name, "reason": str(exc)})
            self.send_error(422, f"task validation failed: {exc}")
            return

        # Named-task dedup (production AlreadyExists semantics).
        with _lock:
            if task_name in _tasks:
                _emit({"event": "named_task_deduplicated", "task_name": task_name})
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "already exists"}).encode())
                return
            _tasks[task_name] = payload

        body = payload["body"]
        url = payload["url"]
        job_id = body.get("job_id", "")
        _emit({"event": "task_captured", "task_name": task_name, "job_id": job_id})

        # Deliver to worker over real loopback HTTP.
        status = _deliver(body, url, retry_count=0)

        # Declared fault: duplicate delivery (at-least-once simulation).
        if _DUPLICATE_DELIVERY > 0 and 200 <= status < 300:
            time.sleep(0.5)  # Let the first delivery settle.
            _deliver(body, url, retry_count=1)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "enqueued", "delivery_status": status}).encode())

    def log_message(self, *_args: Any) -> None:
        pass  # Suppress default stderr logging.


def main() -> int:
    port = int(os.getenv("OMI_REPLAY_PORT", "0"))
    if port == 0:
        raise RuntimeError("OMI_REPLAY_PORT is required")

    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    _ready.set()
    _emit({"event": "loopback_started", "port": port, "duplicate_delivery": _DUPLICATE_DELIVERY})
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
