#!/usr/bin/env python3
"""Driver for the desktop agent continuity gauntlet (INV-6)."""

from __future__ import annotations

import argparse
import ast
import hashlib
import http.client
import json
import math
import os
import re
import secrets
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
DEFAULT_PORT = int(os.environ.get("OMI_AUTOMATION_PORT", "47777"))
DEFAULT_LOG = Path("/private/tmp/omi-dev.log")
TRACE_LOG = Path.home() / "Library/Logs/Omi/traces.jsonl"
DEFAULT_BUNDLE_SUFFIX = "omi-gauntlet"
GAUNTLET_ROOT = DESKTOP_DIR / ".harness/agent-continuity-gauntlet"
PRUNE_ABORTED_BUNDLE_DAYS = 7
RESILIENCE_DIAGNOSTIC_SCHEMA_VERSION = 1
RESILIENCE_FORBIDDEN_TERMINAL_REASONS = {
    "bridge_launch_error",
    "generic_chat_error",
    "no_assistant_response",
    "no_query_trace",
    "response_already_running",
    "response_stopped",
    "skipped_missing_action",
    "skipped_unimplemented_action",
    "subagent_missing",
    "subagent_status_invisible",
}
RESILIENCE_GENERIC_CHAT_PATTERNS = {
    "AI not available",
    "AI is not running",
    "AI stopped unexpectedly",
    "AI took too long to respond",
    "A response is already running for this chat",
    "Response stopped",
    "requestAlreadyActive",
    "response_already_running",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def bridge_action_timeout_sec(
    name: str,
    params: dict[str, str] | None,
    turn_timeout_ms: int,
) -> float:
    """HTTP client timeout for bridge actions that may block for a full turn."""
    params = params or {}
    turn_sec = max(190.0, (turn_timeout_ms / 1000.0) + 10.0)
    if name == "ptt_test_turn":
        # The controller may redrive the turn once after a mid-turn session swap,
        # so the worst case is two full turn deadlines plus warm-up slack.
        action_sec = float(params.get("timeout", "0"))
        return max(turn_sec, 2.0 * action_sec + 40.0)
    if name == "wait_main_chat_idle":
        wait_ms = int(params.get("timeoutMs", "2000"))
        if wait_ms >= 30_000:
            return max(turn_sec, (wait_ms / 1000.0) + 10.0)
    if name in {"ask_main_chat", "swap_test_owner", "kernel_turn_tail"}:
        return turn_sec
    return 60.0


def automation_token(port: int) -> str | None:
    """Load the per-launch bridge bearer token (same contract as omi-ctl)."""
    token = os.environ.get("OMI_AUTOMATION_TOKEN", "").strip()
    if token:
        return token
    token_file = Path(
        os.environ.get("OMI_AUTOMATION_TOKEN_FILE")
        or os.path.join(os.environ.get("TMPDIR", "/tmp"), f"omi-automation-{port}.token")
    )
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return token or None


def bridge_request(
    port: int,
    method: str,
    route: str,
    body: dict[str, Any] | None = None,
    *,
    timeout_sec: float = 60,
) -> dict[str, Any]:
    payload = None
    headers = {"Accept": "application/json"}
    token = automation_token(port)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{route}",
        data=payload,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": raw}
        parsed["http_status"] = exc.code
        return parsed
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"connection_failed: {exc.reason}"}
    except (TimeoutError, socket.timeout) as exc:
        # Surface as a step failure, never a harness crash.
        return {"ok": False, "error": f"bridge_http_timeout after {timeout_sec:.0f}s: {exc}"}
    except http.client.RemoteDisconnected as exc:
        return {"ok": False, "error": f"bridge_http_disconnected: {exc}"}


def bridge_action(
    port: int,
    name: str,
    params: dict[str, str] | None = None,
    *,
    turn_timeout_ms: int | None = None,
) -> dict[str, Any]:
    timeout_sec = 60.0
    if turn_timeout_ms is not None:
        timeout_sec = bridge_action_timeout_sec(name, params, turn_timeout_ms)
    return bridge_request(
        port,
        "POST",
        "/action",
        {"name": name, "params": params or {}},
        timeout_sec=timeout_sec,
    )


def bridge_state(port: int) -> dict[str, Any]:
    return bridge_request(port, "GET", "/state")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def parse_manifest_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def finalize_evidence_hygiene(run_dir: Path, *, passed: bool, git_sha: str) -> None:
    """Update latest-green pointer, INDEX.md, and prune stale aborted bundles."""
    GAUNTLET_ROOT.mkdir(parents=True, exist_ok=True)
    if passed:
        latest = GAUNTLET_ROOT / "latest-green"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name, target_is_directory=True)
        index_path = GAUNTLET_ROOT / "INDEX.md"
        line = f"- `{run_dir.name}` — `{git_sha[:12]}` — green\n"
        existing = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        if line not in existing:
            with index_path.open("a", encoding="utf-8") as handle:
                if not existing:
                    handle.write("# Agent continuity gauntlet evidence index\n\n")
                handle.write(line)
    prune_aborted_bundles(GAUNTLET_ROOT, keep_dir=run_dir, max_age_days=PRUNE_ABORTED_BUNDLE_DAYS)


def prune_aborted_bundles(root: Path, *, keep_dir: Path, max_age_days: int) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    if not root.is_dir():
        return
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if entry.resolve() == keep_dir.resolve():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if manifest.get("passed") is True:
            continue
        stamp = parse_manifest_timestamp(manifest.get("finished_at")) or parse_manifest_timestamp(
            manifest.get("started_at")
        )
        if stamp is None or stamp >= cutoff:
            continue
        shutil.rmtree(entry, ignore_errors=True)


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(DESKTOP_DIR.parent.parent), "rev-parse", "--short", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def sine_pcm16k(seconds: float = 0.75, frequency: float = 220.0, amplitude: float = 3500.0) -> bytes:
    sample_rate = 16_000
    sample_count = int(sample_rate * seconds)
    chunks: list[bytes] = []
    for index in range(sample_count):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate))
        chunks.append(struct.pack("<h", value))
    return b"".join(chunks)


def trace_line_count() -> int:
    if not TRACE_LOG.exists():
        return 0
    with TRACE_LOG.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def read_new_traces(since_line: int) -> list[dict[str, Any]]:
    if not TRACE_LOG.exists():
        return []
    traces: list[dict[str, Any]] = []
    with TRACE_LOG.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number <= since_line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return traces


def read_all_traces() -> list[dict[str, Any]]:
    if not TRACE_LOG.exists():
        return []
    traces: list[dict[str, Any]] = []
    with TRACE_LOG.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return traces


def wait_for_new_traces(
    since_line: int,
    *,
    min_count: int = 1,
    timeout_sec: float = 8.0,
    poll_sec: float = 0.25,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        traces = read_new_traces(since_line)
        if len(traces) >= min_count:
            return traces
        time.sleep(poll_sec)
    return read_new_traces(since_line)


def traces_for_query(traces: list[dict[str, Any]], query_text: str) -> list[dict[str, Any]]:
    needle = query_text.strip()
    if not needle:
        return traces
    return [trace for trace in traces if str(trace.get("query_text", "")).strip() == needle]


def flatten_trace_text(trace: dict[str, Any]) -> str:
    parts: list[str] = []
    request = trace.get("request") or {}
    if isinstance(request, dict):
        if request.get("system_prompt"):
            parts.append(str(request["system_prompt"]))
        for message in request.get("messages") or []:
            if isinstance(message, dict):
                parts.append(str(message.get("content", "")))
        if request.get("response_text"):
            parts.append(str(request["response_text"]))
    if trace.get("query_text"):
        parts.append(str(trace["query_text"]))
    if trace.get("response_text"):
        parts.append(str(trace["response_text"]))
    for tool in trace.get("tool_executions") or []:
        if isinstance(tool, dict):
            parts.append(str(tool.get("name", "")))
            parts.append(str(tool.get("input", "")))
            parts.append(str(tool.get("output", "")))
    return "\n".join(parts)


def trace_tool_executions(traces: list[dict[str, Any]], names: set[str] | None = None) -> list[dict[str, Any]]:
    return [
        tool
        for trace in traces
        for tool in (trace.get("tool_executions") or [])
        if isinstance(tool, dict) and (names is None or tool.get("name") in names)
    ]


def strip_probe_text(haystack: str, probe_texts: list[str]) -> str:
    """Remove the probe turn's own text from an assertion haystack (R8).

    Traces include the current user message; searching for a marker that the
    probe itself contains would make the assertion self-satisfying.
    """
    for probe in probe_texts:
        if probe:
            haystack = haystack.replace(probe, "")
    return haystack


def latest_assistant_text(snapshot_detail: dict[str, str]) -> str:
    try:
        messages = json.loads(snapshot_detail.get("messages_json", "[]"))
    except json.JSONDecodeError:
        return ""
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("streaming") != "true":
            text = (message.get("text") or "").strip()
            if text:
                return text
    return ""


def current_turn_snapshot_text(snapshot_detail: dict[str, str], query_text: str) -> str:
    try:
        messages = json.loads(snapshot_detail.get("messages_json", "[]"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(messages, list):
        return ""
    query = query_text.strip()
    start_index: int | None = None
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user" and str(message.get("text") or "").strip() == query:
            start_index = index
    if start_index is None:
        return ""
    return json.dumps(messages[start_index:], sort_keys=True)


def current_turn_assistant_text(snapshot_detail: dict[str, str], query_text: str) -> str:
    try:
        messages = json.loads(snapshot_detail.get("messages_json", "[]"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(messages, list):
        return ""
    query = query_text.strip()
    start_index: int | None = None
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user" and str(message.get("text") or "").strip() == query:
            start_index = index
    if start_index is None:
        return ""
    for message in reversed(messages[start_index:]):
        if isinstance(message, dict) and message.get("role") == "assistant" and message.get("streaming") != "true":
            text = (message.get("text") or "").strip()
            if text:
                return text
    return ""


def kernel_surface_identity(database_path: str, owner_id: str) -> dict[str, str] | None:
    """Read kernel-owned main_chat identity from omi-agentd.sqlite3."""
    if not owner_id or not database_path or not Path(database_path).is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT conversation_id, agent_session_id
            FROM surface_conversations
            WHERE owner_id = ?
              AND surface_kind = 'main_chat'
              AND external_ref_kind = 'chat'
              AND external_ref_id = 'default'
            LIMIT 1
            """,
            (owner_id,),
        ).fetchone()
        connection.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "owner_id": owner_id,
        "conversation_id": str(row["conversation_id"] or ""),
        "agent_session_id": str(row["agent_session_id"] or ""),
    }


def identity_keys(detail: dict[str, str], runtime_detail: dict[str, str] | None = None) -> dict[str, str]:
    owner_id = detail.get("owner_id", "")
    database_path = (runtime_detail or {}).get("database_path", "")
    kernel = kernel_surface_identity(database_path, owner_id)
    if kernel:
        return kernel
    return {
        "owner_id": owner_id,
        "conversation_id": "",
        "agent_session_id": "",
    }


def capture_log_excerpt(log_path: Path, offset: int, dest: Path, max_bytes: int = 200_000) -> None:
    if not log_path.exists():
        dest.write_text("(log missing)\n", encoding="utf-8")
        return
    data = log_path.read_bytes()
    excerpt = data[offset : offset + max_bytes]
    dest.write_bytes(excerpt)


def run_agent_swift_screenshot(bundle_id: str, dest: Path) -> dict[str, Any]:
    if shutil.which("agent-swift") is None:
        return {"ok": False, "error": "agent-swift not installed"}
    commands = [
        ["agent-swift", "connect", "--bundle-id", bundle_id],
        ["agent-swift", "screenshot", str(dest)],
    ]
    output: list[str] = []
    for command in commands:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output.append(result.stdout)
        if result.returncode != 0:
            return {"ok": False, "error": result.stdout, "command": command}
    return {"ok": True, "path": str(dest), "output": "\n".join(output)}


class GauntletRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.port = args.port
        self.bundle_id = args.bundle_id
        self.run_id = args.run_id or now_iso()
        self.run_dir = Path(args.run_dir or (DESKTOP_DIR / ".harness/agent-continuity-gauntlet" / self.run_id))
        self.log_path = Path(args.log_path)
        self.log_offset = self.log_path.stat().st_size if self.log_path.exists() else 0
        # Each marker carries its own random nonce (R8): the step-3 blind-recall
        # probe must not be answerable by deriving one marker from another
        # (e.g. reconstructing the PTT marker from the typed marker's run id).
        self.markers = {
            "typed": f"GAUNTLET-{self.run_id}-{secrets.token_hex(4).upper()}-TYPED",
            "ptt": f"GAUNTLET-{self.run_id}-{secrets.token_hex(4).upper()}-PTT",
            "spawn": f"GAUNTLET-{self.run_id}-{secrets.token_hex(4).upper()}-SPAWN",
            "floating_spawn": f"GAUNTLET-{self.run_id}-{secrets.token_hex(4).upper()}-FLOAT",
        }
        self.suites = expand_suites(getattr(args, "suite", "core"))
        self.baseline_identity: dict[str, str] | None = None
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.steps: list[dict[str, Any]] = []
        self.resilience_terminal_reason_counts: dict[str, int] = {}
        self.pcm_path = self.run_dir / "fixtures" / "ptt-voice.pcm"

    def bridge_act(self, name: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        return bridge_action(self.port, name, params, turn_timeout_ms=self.args.turn_timeout_ms)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def record_resilience_diagnostic(
        self,
        scenario: str,
        iteration: int,
        terminal_reason: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "schema_version": RESILIENCE_DIAGNOSTIC_SCHEMA_VERSION,
            "run_id": self.run_id,
            "scenario": scenario,
            "iteration": iteration,
            "terminal_reason": terminal_reason,
            "detail": detail or {},
        }
        append_text(self.run_dir / "resilience-diagnostics.jsonl", json.dumps(record, sort_keys=True) + "\n")
        self.resilience_terminal_reason_counts[terminal_reason] = (
            self.resilience_terminal_reason_counts.get(terminal_reason, 0) + 1
        )
        if terminal_reason in RESILIENCE_FORBIDDEN_TERMINAL_REASONS:
            self.fail(f"{scenario} iteration {iteration}: forbidden terminal reason {terminal_reason}")

    def classify_resilience_turn(
        self,
        *,
        scenario: str,
        iteration: int,
        query: str,
        send: dict[str, Any],
        snapshot: dict[str, str],
        traces: list[dict[str, Any]],
        require_trace: bool = True,
    ) -> str:
        detail = send.get("result", {}).get("detail", {}) if isinstance(send, dict) else {}
        assistant = current_turn_assistant_text(snapshot, query)
        trace_matches = traces_for_query(traces, query)
        evidence = "\n".join(
            [
                json.dumps(send, sort_keys=True, default=str),
                current_turn_snapshot_text(snapshot, query),
                "\n".join(
                    str(value)
                    for key, value in snapshot.items()
                    if "error" in key.lower() and value
                ),
                assistant,
                "\n".join(flatten_trace_text(trace) for trace in trace_matches),
            ]
        )
        lower_evidence = evidence.lower()
        terminal_reason = "passed"
        if send.get("ok") is False or detail.get("error"):
            message = str(detail.get("error", send.get("error", send)))
            if "failed to start agent bridge" in message.lower() or "ai not available" in message.lower():
                terminal_reason = "bridge_launch_error"
            elif "already running" in message.lower() or "already_active" in message.lower():
                terminal_reason = "response_already_running"
            else:
                terminal_reason = "generic_chat_error"
        elif "response_already_running" in lower_evidence or "a response is already running" in lower_evidence:
            terminal_reason = "response_already_running"
        elif "response stopped" in lower_evidence:
            terminal_reason = "response_stopped"
        elif any(pattern.lower() in lower_evidence for pattern in RESILIENCE_GENERIC_CHAT_PATTERNS):
            terminal_reason = "generic_chat_error"
        elif not assistant:
            terminal_reason = "no_assistant_response"
        elif require_trace and not trace_matches:
            terminal_reason = "no_query_trace"

        self.record_resilience_diagnostic(
            scenario,
            iteration,
            terminal_reason,
            {
                "assistant_chars": len(assistant),
                "query_trace_count": len(trace_matches),
                "trace_count": len(traces),
                "send_ok": send.get("ok"),
                "send_detail": detail,
            },
        )
        return terminal_reason

    def ensure_bridge(self) -> None:
        health = bridge_request(self.port, "GET", "/health")
        if not health.get("ok"):
            raise SystemExit(
                f"automation bridge unavailable on port {self.port}: {health.get('error', health)}"
            )

    def navigate_chat(self) -> None:
        navigate = bridge_request(
            self.port,
            "POST",
            "/navigate",
            {"target": "chat", "activateApp": True, "settleMs": 300},
        )
        if navigate.get("ok") is False:
            raise SystemExit(f"navigate chat failed: {navigate.get('error', navigate)}")
        ready = bridge_state(self.port)
        write_json(self.run_dir / "preflight-state.json", ready)

    def record_step(
        self,
        step_id: str,
        name: str,
        *,
        user_text: str,
        action_response: dict[str, Any],
        snapshot_detail: dict[str, str],
        traces: list[dict[str, Any]],
        extra: dict[str, Any] | None = None,
        skip_identity_drift: bool = False,
    ) -> None:
        step_dir = self.run_dir / step_id
        assistant_text = latest_assistant_text(snapshot_detail)
        write_json(step_dir / "action-response.json", action_response)
        write_json(step_dir / "chat-snapshot.json", snapshot_detail)
        write_json(step_dir / "query-traces.json", traces)
        write_json(
            step_dir / "turn-text.json",
            {"user": user_text, "assistant": assistant_text},
        )
        capture_log_excerpt(self.log_path, self.log_offset, step_dir / "app-log-excerpt.txt")
        self.log_offset = self.log_path.stat().st_size if self.log_path.exists() else self.log_offset

        runtime = self.bridge_act( "agent_runtime_evidence")
        runtime_detail = runtime.get("result", {}).get("detail", runtime)
        write_json(step_dir / "runtime-sqlite.json", runtime_detail)

        png_path = step_dir / "main-window.png"
        screenshot = run_agent_swift_screenshot(self.bundle_id, png_path)
        write_json(step_dir / "screenshot-meta.json", screenshot)

        identity = identity_keys(snapshot_detail, runtime_detail)
        write_json(step_dir / "identity.json", identity)
        if not skip_identity_drift and identity.get("conversation_id"):
            if self.baseline_identity is None:
                self.baseline_identity = identity
            elif identity != self.baseline_identity:
                self.fail(
                    f"{name}: conversation identity drifted "
                    f"(baseline={self.baseline_identity}, current={identity})"
                )

        record = {
            "id": step_id,
            "name": name,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "identity": identity,
            "trace_ids": [trace.get("trace_id") for trace in traces],
        }
        if extra:
            record["extra"] = extra
        self.steps.append(record)

    def restore_test_owner(self, context: str) -> None:
        """Undo a swap_test_owner (this run's, or one leaked by a crashed prior run).

        A leaked synthetic owner persists in UserDefaults across relaunches and breaks
        every backend-auth path (realtime mint, kernel persist), so the owner suite must
        always restore, and pre-run hygiene restores defensively.
        """
        restored = self.bridge_act("restore_test_owner")
        detail = restored.get("result", {}).get("detail", {})
        if restored.get("ok") is False or detail.get("error"):
            message = str(detail.get("error", restored.get("error", restored)))
            if "unknown action" in message.lower():
                self.warn(f"{context}: restore_test_owner action unavailable (older app build)")
                return
            self.fail(f"{context}: restore_test_owner failed: {message}")
            return
        if detail.get("restored") == "true":
            self.warn(f"{context}: restored owner {detail.get('owner_id', '?')} after test-owner swap")

    def clear_kernel_hygiene_if_available(self) -> None:
        """Clear kernel main_chat turns on non-prod bundles before continuity assertions."""
        self.restore_test_owner("pre-run hygiene")
        cleared = self.bridge_act("clear_owner_surface_state")
        detail = cleared.get("result", {}).get("detail", {})
        if cleared.get("ok") is False or detail.get("error"):
            message = detail.get("error", cleared.get("error", cleared))
            if "disabled on production" in str(message).lower():
                self.warn(
                    "kernel hygiene skipped on production bundle — repeated runs may pollute "
                    "model-visible history even though R8 nonces protect harness assertions"
                )
                return
            self.fail(f"clear_owner_surface_state failed: {message}")
            return
        write_json(
            self.run_dir / "kernel-hygiene.json",
            {"cleared": True, "detail": detail},
        )

    def ask_floating_and_wait(self, query: str, timeout_ms: int) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
        trace_start = trace_line_count()
        send = self.bridge_act("ask", {"query": query})
        if send.get("ok") is False:
            raise SystemExit(f"ask (floating) failed: {send.get('error', send)}")
        detail = send.get("result", {}).get("detail", {})
        if detail.get("error"):
            raise SystemExit(f"ask (floating) error: {detail['error']}")

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        snapshot_detail: dict[str, str] = {}
        while time.monotonic() < deadline:
            wait = bridge_action(
                self.port,
                "wait_main_chat_idle",
                {"timeoutMs": "2000", "pollMs": "250"},
            )
            snapshot_detail = wait.get("result", {}).get("detail", {})
            if wait.get("ok") and snapshot_detail.get("idle") == "true":
                break
            time.sleep(0.25)
        else:
            self.fail(f"timed out waiting for floating query idle: {query[:120]}")

        snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
        snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
        traces = read_new_traces(trace_start)
        return send, snapshot_detail, traces

    def kernel_turn_tail_blob(self, *, limit: int = 12) -> str:
        tail = self.bridge_act("kernel_turn_tail", {"limit": str(limit)})
        detail = tail.get("result", {}).get("detail", {})
        if tail.get("ok") is False or detail.get("error"):
            self.fail(f"kernel_turn_tail failed: {detail.get('error', tail.get('error', tail))}")
            return ""
        return detail.get("turns_json", "[]")

    def send_and_wait(self, query: str, timeout_ms: int) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
        trace_start = trace_line_count()
        send = self.bridge_act( "ask_main_chat", {"query": query})
        if send.get("ok") is False:
            raise SystemExit(f"ask_main_chat failed: {send.get('error', send)}")
        detail = send.get("result", {}).get("detail", {})
        if detail.get("error"):
            raise SystemExit(f"ask_main_chat error: {detail['error']}")

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        snapshot_detail: dict[str, str] = {}
        while time.monotonic() < deadline:
            wait = bridge_action(
                self.port,
                "wait_main_chat_idle",
                {"timeoutMs": "2000", "pollMs": "250"},
            )
            snapshot_detail = wait.get("result", {}).get("detail", {})
            if wait.get("ok") and snapshot_detail.get("idle") == "true":
                break
            time.sleep(0.25)
        else:
            self.fail(f"timed out waiting for main chat idle after query: {query[:120]}")

        snapshot = self.bridge_act( "main_chat_snapshot", {"limit": "80"})
        snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
        traces = read_new_traces(trace_start)
        return send, snapshot_detail, traces

    def send_and_wait_resilience(
        self,
        query: str,
        timeout_ms: int,
    ) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
        """Main-chat send path for resilience probes; capture failures instead of aborting."""
        trace_start = trace_line_count()
        send = self.bridge_act("ask_main_chat", {"query": query})
        detail = send.get("result", {}).get("detail", {}) if isinstance(send, dict) else {}
        if send.get("ok") is False or detail.get("error"):
            snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
            snapshot_detail = snapshot.get("result", {}).get("detail", {})
            return send, snapshot_detail, read_new_traces(trace_start)

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        snapshot_detail: dict[str, str] = {}
        while time.monotonic() < deadline:
            wait = bridge_action(
                self.port,
                "wait_main_chat_idle",
                {"timeoutMs": "2000", "pollMs": "250"},
            )
            snapshot_detail = wait.get("result", {}).get("detail", {})
            if wait.get("ok") and snapshot_detail.get("idle") == "true":
                break
            time.sleep(0.25)
        else:
            self.fail(f"timed out waiting for resilience main chat idle after query: {query[:120]}")

        snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
        snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
        traces = read_new_traces(trace_start)
        return send, snapshot_detail, traces

    def assert_trace_contains(self, traces: list[dict[str, Any]], needle: str, label: str) -> None:
        haystack = "\n".join(flatten_trace_text(trace) for trace in traces)
        if needle not in haystack:
            self.fail(f"{label}: model-visible trace missing marker {needle}")

    def assert_trace_excludes(self, traces: list[dict[str, Any]], needles: list[str], label: str) -> None:
        haystack = "\n".join(flatten_trace_text(trace) for trace in traces)
        leaked = [needle for needle in needles if needle in haystack]
        if leaked:
            self.fail(f"{label}: owner-B assembled trace leaked owner-A marker(s): {leaked}")

    def assert_assistant_mentions(self, assistant_text: str, needles: list[str], label: str) -> None:
        lowered = assistant_text.lower()
        if not any(needle.lower() in lowered for needle in needles):
            self.fail(f"{label}: assistant response did not reference expected markers: {needles}")

    def assert_step3_blind_recall(
        self,
        assistant_text: str,
        traces: list[dict[str, Any]],
        probe_text: str,
        *,
        label: str = "typed follow-up",
    ) -> dict[str, bool]:
        """Blind-recall continuity assertion (R8).

        The probe deliberately never contains the PTT marker, so the assistant
        can only reproduce it if the voice turn was delivered through kernel
        context (transcript tail, G1 delta, or native history). That behavioral
        check is the hard gate. Trace visibility is a soft signal only:
        QueryTracer captures Swift request.messages, not the kernel-assembled
        prompt, so the marker may legitimately be absent from the trace even
        when delivery works.
        """
        ptt_marker = self.markers["ptt"]
        if ptt_marker in probe_text:
            self.fail(
                f"{label}: probe text contains the PTT marker — the blind-recall "
                "assertion is meaningless when the answer is in the question"
            )
        trace_text = strip_probe_text(
            "\n".join(flatten_trace_text(trace) for trace in traces),
            [probe_text],
        )
        checks = {
            "ptt_marker_in_assistant": ptt_marker in assistant_text,
            "ptt_marker_in_trace_excl_probe": ptt_marker in trace_text,
            "conversation_history_in_trace": (
                "<conversation_history>" in trace_text
                or "# Recent turns from other surfaces" in trace_text
            ),
        }
        if not checks["ptt_marker_in_assistant"]:
            self.fail(
                f"{label}: assistant failed blind recall of PTT marker {ptt_marker} "
                f"(reply={assistant_text[:160]!r}) — voice turn not delivered to typed context"
            )
        if not checks["ptt_marker_in_trace_excl_probe"]:
            self.warn(
                f"{label}: PTT marker not visible in Swift-side trace "
                "(expected when kernel assembles context downstream of QueryTracer)"
            )
        return checks

    def run(self) -> int:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.pcm_path.parent.mkdir(parents=True, exist_ok=True)
        self.pcm_path.write_bytes(sine_pcm16k())

        manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "git": git_sha(),
            "bundle_id": self.bundle_id,
            "port": self.port,
            "markers": self.markers,
            "trace_log": str(TRACE_LOG),
            "app_log": str(self.log_path),
            "ptt_config": {
                "force_transcript_used": True,
                "local_stt_note": (
                    "Gauntlet drives PTT with force_transcript; local_transcript is populated "
                    "only when provider language mismatches user voice languages."
                ),
            },
        }
        manifest["suites"] = sorted(self.suites)
        self.manifest = manifest
        write_json(self.run_dir / "manifest.json", manifest)

        self.ensure_bridge()
        self.navigate_chat()
        self.clear_kernel_hygiene_if_available()

        if "continuity" in self.suites:
            self.run_continuity_suite()
        if "agents" in self.suites:
            self.run_agents_suite()
        if "prompts" in self.suites:
            self.run_prompts_suite()
        if "resilience" in self.suites:
            self.run_resilience_suite()
        if "owner" in self.suites:
            self.run_owner_suite()

        return self.finalize()

    def run_continuity_suite(self) -> None:
        # Step 1 — typed turn
        typed_query = (
            f"Remember this continuity marker exactly: {self.markers['typed']}. "
            "Reply with one short sentence acknowledging the marker."
        )
        send, snapshot, traces = self.send_and_wait(typed_query, self.args.turn_timeout_ms)
        self.record_step("01-typed-turn", "typed turn", user_text=typed_query, action_response=send, snapshot_detail=snapshot, traces=traces)
        self.assert_assistant_mentions(latest_assistant_text(snapshot), [self.markers["typed"]], "typed turn")

        # Step 2 — PTT turn (real hub controller path; transcript forced for determinism)
        ptt_user = (
            f"In our push-to-talk exchange, remember this marker exactly: {self.markers['ptt']}. "
            "Reply briefly acknowledging it."
        )
        trace_start = trace_line_count()
        ptt = self.bridge_act(
            "ptt_test_turn",
            {
                "pcm": str(self.pcm_path),
                "timeout": str(max(30, self.args.turn_timeout_ms // 1000)),
                "force_transcript": ptt_user,
                # No competing fixture audio: the model must answer the forced
                # transcript, not a hallucinated ASR of the sine tone.
                "text_only": "1",
            },
        )
        ptt_detail = ptt.get("result", {}).get("detail", {})
        if ptt.get("ok") is False or ptt_detail.get("error"):
            self.fail(f"PTT turn failed: {ptt_detail.get('error', ptt.get('error', ptt))}")
        else:
            saved_user = ptt_detail.get("saved_user_text") or ptt_detail.get("provider_transcript") or ""
            if self.markers["ptt"] not in saved_user:
                self.fail(f"PTT turn did not persist marker in saved_user_text ({saved_user!r})")

        # Poll for the kernel turn_recorded projection instead of a fixed sleep.
        snapshot_detail: dict[str, str] = {}
        settle_deadline = time.monotonic() + 10.0
        while time.monotonic() < settle_deadline:
            snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
            snapshot_detail = snapshot.get("result", {}).get("detail", {})
            if self.markers["ptt"] in snapshot_detail.get("messages_json", ""):
                break
            time.sleep(0.25)
        traces = read_new_traces(trace_start)
        self.record_step(
            "02-ptt-turn",
            "PTT turn",
            user_text=ptt_user,
            action_response=ptt,
            snapshot_detail=snapshot_detail,
            traces=traces,
            extra={"ptt_diagnostics": ptt_detail},
        )
        messages_blob = snapshot_detail.get("messages_json", "")
        if self.markers["ptt"] not in messages_blob:
            self.fail("PTT turn marker not visible in main chat transcript after voice turn")

        assistant_reply = str(ptt_detail.get("assistant_reply") or "")
        if self.markers["ptt"] not in assistant_reply:
            self.warn(
                f"PTT step 02: assistant reply did not acknowledge marker {self.markers['ptt']} "
                f"(reply={assistant_reply[:120]!r})"
            )
        local_transcript = str(ptt_detail.get("local_transcript") or "").strip()
        provider_transcript = str(ptt_detail.get("provider_transcript") or "").strip()
        if not local_transcript and provider_transcript:
            self.warn(
                "PTT step 02: local_transcript empty while provider_transcript populated "
                "(expected when force_transcript bypasses local STT fallback)"
            )

        # Step 3 — typed follow-up: blind recall of the PTT marker (R8).
        # The probe must NOT contain the marker; the assistant can only answer
        # from delivered kernel context.
        followup_query = (
            "In our earlier push-to-talk voice turn I gave you a continuity marker "
            "starting with GAUNTLET- and ending in -PTT. "
            "Reply with only that exact marker string, nothing else."
        )
        send, snapshot, traces = self.send_and_wait(followup_query, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        continuity_checks = self.assert_step3_blind_recall(assistant, traces, followup_query)
        self.record_step(
            "03-typed-followup",
            "typed follow-up after PTT",
            user_text=followup_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"continuity_checks": continuity_checks},
        )

    def run_agents_suite(self) -> None:
        # Step 4 — background agent spawn
        spawn_query = (
            f"Use spawn_agent now to start a visible background agent. "
            f"Objective: track marker {self.markers['spawn']} and wait silently. "
            "Do not ask follow-up questions."
        )
        trace_start = trace_line_count()
        send, snapshot, traces = self.send_and_wait(spawn_query, self.args.turn_timeout_ms)
        # R8: only a real spawn_agent execution carrying the objective marker
        # counts. list_agent_sessions and coordinator awareness are evidence,
        # never a pass path — a verbal refusal must fail this step.
        # Tool executions often land after main_chat idle; poll traces before asserting.
        spawn_tools: list[dict[str, Any]] = []
        settle_deadline = time.monotonic() + 10.0
        while time.monotonic() < settle_deadline:
            traces = read_new_traces(trace_start)
            spawn_tools = [
                tool
                for trace in traces
                for tool in (trace.get("tool_executions") or [])
                if isinstance(tool, dict)
                and tool.get("name") == "spawn_agent"
                and self.markers["spawn"] in str(tool.get("input", ""))
            ]
            if spawn_tools:
                break
            time.sleep(0.25)
        coordinator = self.bridge_act( "coordinator_awareness_snapshot")
        self.record_step(
            "04-spawn-agent",
            "background agent spawn",
            user_text=spawn_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={
                "spawn_tool_calls": spawn_tools,
                "coordinator_snapshot": coordinator.get("result", {}).get("detail", {}),
            },
        )
        if not spawn_tools:
            assistant = latest_assistant_text(snapshot)
            self.fail(
                "no spawn_agent execution with the objective marker — model refused or "
                f"mis-routed the spawn request (assistant={assistant[:160]!r})"
            )
        else:
            failed_spawns = [
                tool
                for tool in spawn_tools
                if re.search(r"error|failed|denied", str(tool.get("output", "")), re.I)
            ]
            if failed_spawns:
                self.fail(f"spawn_agent execution reported failure: {failed_spawns[0].get('output')!r}")

        # Step 5 — status query about spawned agent
        # R8: marker-free probe — the answer must surface the objective marker
        # from tool output or delivered context, not from this question.
        status_query = (
            "What is the status of the background agent you just started? "
            "Use list_agent_sessions if needed. Answer in one sentence and "
            "include the agent's exact objective marker."
        )
        send, snapshot, traces = self.send_and_wait(status_query, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        list_tools = [
            tool
            for trace in traces
            for tool in (trace.get("tool_executions") or [])
            if isinstance(tool, dict) and tool.get("name") == "list_agent_sessions"
        ]
        self.record_step(
            "05-status-query",
            "status query about spawned agent",
            user_text=status_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"list_agent_sessions_calls": list_tools},
        )
        # R8: assertions run against evidence the probe did not supply — tool
        # outputs and assistant text only, with the probe's own words stripped.
        list_outputs = "\n".join(str(tool.get("output", "")) for tool in list_tools)
        evidence_blob = strip_probe_text(assistant + "\n" + list_outputs, [status_query])
        status_words = re.search(
            r"running|working|in progress|started|completed|queued|active|failed|succeeded",
            evidence_blob,
            re.I,
        )
        if list_tools:
            if self.markers["spawn"] not in list_outputs and self.markers["spawn"] not in assistant:
                self.fail(
                    "list_agent_sessions ran but neither its output nor the answer "
                    f"references spawn marker {self.markers['spawn']}"
                )
        else:
            if self.markers["spawn"] not in evidence_blob or not status_words:
                self.fail(
                    "status query cannot see spawned agent "
                    "(no list_agent_sessions call and answer lacks marker + status language)"
                )
            self.warn(
                "status step passed without list_agent_sessions tool verification "
                "(answer derived from injected context)"
            )

        self.run_floating_spawn_recall_step()

    def run_floating_spawn_recall_step(self) -> None:
        """Floating pill spawn handoff must reach kernel main_chat and PTT seed."""
        spawn_title = f"GAUNTLET Recall Page {self.markers['floating_spawn'][-8:]}"
        casual_query = "yo what's up"
        spawn_query = (
            f"Spawn a background agent titled \"{spawn_title}\" to track marker "
            f"{self.markers['floating_spawn']}. Start it now and do not ask follow-up questions."
        )

        casual_send, casual_snapshot, casual_traces = self.ask_floating_and_wait(
            casual_query, self.args.turn_timeout_ms
        )
        self.record_step(
            "07a-floating-casual",
            "floating pill casual message",
            user_text=casual_query,
            action_response=casual_send,
            snapshot_detail=casual_snapshot,
            traces=casual_traces,
        )

        spawn_send, spawn_snapshot, spawn_traces = self.ask_floating_and_wait(
            spawn_query, self.args.turn_timeout_ms
        )
        kernel_tail = self.kernel_turn_tail_blob(limit=12)
        self.record_step(
            "07b-floating-spawn",
            "floating pill spawn handoff",
            user_text=spawn_query,
            action_response=spawn_send,
            snapshot_detail=spawn_snapshot,
            traces=spawn_traces,
            extra={
                "spawn_title": spawn_title,
                "kernel_turn_tail": kernel_tail,
            },
        )
        if self.markers["floating_spawn"] not in kernel_tail and spawn_title not in kernel_tail:
            self.fail(
                "floating spawn handoff missing from kernel main_chat tail "
                f"(marker={self.markers['floating_spawn']!r}, title={spawn_title!r})"
            )

        recency_probe = "What was the last thing I asked you for?"
        if self.markers["floating_spawn"] in recency_probe or spawn_title in recency_probe:
            self.fail("spawn-recall probe must not contain the spawn marker or title (R8)")

        # Let floating spawn handoff and hub state settle before the voice probe.
        self.bridge_act("wait_main_chat_idle", {"timeoutMs": "30000", "pollMs": "250"})
        time.sleep(1.0)

        # PTT blind recall — seed-first; must not call get_conversations.
        ptt: dict[str, Any] = {}
        ptt_detail: dict[str, Any] = {}
        ptt_traces: list[dict[str, Any]] = []
        ptt_assistant = ""
        ptt_get_convos: list[dict[str, Any]] = []
        for attempt in range(3):
            trace_start = trace_line_count()
            ptt = self.bridge_act(
                "ptt_test_turn",
                {
                    "pcm": str(self.pcm_path),
                    "timeout": str(max(30, self.args.turn_timeout_ms // 1000)),
                    "force_transcript": recency_probe,
                    "text_only": "1",
                },
            )
            ptt_detail = ptt.get("result", {}).get("detail", {})
            if ptt.get("ok") is False or ptt_detail.get("error"):
                self.fail(f"spawn-recall PTT probe failed: {ptt_detail.get('error', ptt.get('error', ptt))}")
            ptt_traces = read_new_traces(trace_start)
            ptt_assistant = str(ptt_detail.get("assistant_reply") or "")
            saved_user = ptt_detail.get("saved_user_text") or ptt_detail.get("provider_transcript") or ""
            if recency_probe.strip() not in str(saved_user):
                self.warn(
                    f"spawn-recall PTT attempt {attempt + 1}: saved transcript mismatch "
                    f"({str(saved_user)[:120]!r})"
                )
            if ptt_assistant and "didn't catch" not in ptt_assistant.lower():
                break
            self.warn(
                f"spawn-recall PTT attempt {attempt + 1}: hub returned empty catch-all "
                f"({ptt_assistant[:120]!r}); retrying after settle"
            )
            time.sleep(2.0)
        ptt_evidence = strip_probe_text(
            ptt_assistant + "\n" + "\n".join(flatten_trace_text(trace) for trace in ptt_traces),
            [recency_probe],
        )
        ptt_get_convos = trace_tool_executions(ptt_traces, {"get_conversations"})
        if ptt_get_convos:
            self.fail("spawn-recall PTT probe called get_conversations while seed should be fresh")
        if (
            self.markers["floating_spawn"] not in ptt_evidence
            and spawn_title not in ptt_evidence
            and spawn_title.lower() not in ptt_evidence.lower()
        ):
            self.fail(
                "spawn-recall PTT probe did not reference floating spawn handoff "
                f"(reply={ptt_assistant[:160]!r})"
            )
        self.record_step(
            "07c-spawn-recall-ptt",
            "PTT blind recall after floating spawn",
            user_text=recency_probe,
            action_response=ptt,
            snapshot_detail={},
            traces=ptt_traces,
            extra={
                "get_conversations_calls": len(ptt_get_convos),
                "assistant_reply": ptt_assistant,
            },
        )

        # Typed main-chat blind recall — same marker-free probe.
        send, snapshot, traces = self.send_and_wait(recency_probe, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        typed_evidence = strip_probe_text(
            assistant + "\n" + "\n".join(flatten_trace_text(trace) for trace in traces),
            [recency_probe],
        )
        if (
            self.markers["floating_spawn"] not in typed_evidence
            and spawn_title not in typed_evidence
            and spawn_title.lower() not in typed_evidence.lower()
        ):
            self.fail(
                "spawn-recall typed probe did not reference floating spawn handoff "
                f"(reply={assistant[:160]!r})"
            )
        self.record_step(
            "07d-spawn-recall-typed",
            "typed blind recall after floating spawn",
            user_text=recency_probe,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
        )

    def run_owner_suite(self) -> None:
        # Step 6 — owner-switch isolation (in-process via swap_test_owner)
        if not self.baseline_identity or not self.baseline_identity.get("conversation_id"):
            # Standalone owner suite: plant an owner-A baseline turn first.
            baseline_query = (
                f"Remember this continuity marker exactly: {self.markers['typed']}. "
                "Reply with one short sentence acknowledging the marker."
            )
            send, snapshot, traces = self.send_and_wait(baseline_query, self.args.turn_timeout_ms)
            self.record_step(
                "00-owner-baseline",
                "owner-A baseline turn",
                user_text=baseline_query,
                action_response=send,
                snapshot_detail=snapshot,
                traces=traces,
            )
        if not self.baseline_identity or not self.baseline_identity.get("conversation_id"):
            self.fail("owner-switch: missing owner-A baseline identity")
            return

        owner_a_identity = dict(self.baseline_identity)
        owner_b_id = f"gauntlet-owner-b-{self.run_id}"
        probe_query = (
            "Reply with the single word PROBE only. "
            "Do not reference any prior GAUNTLET continuity markers."
        )
        trace_start = trace_line_count()
        swap = self.bridge_act(
            "swap_test_owner",
            {"owner_b": owner_b_id, "query": probe_query},
        )
        swap_detail = swap.get("result", {}).get("detail", {})
        if swap.get("ok") is False or swap_detail.get("error"):
            self.fail(f"owner-switch swap_test_owner failed: {swap_detail.get('error', swap.get('error', swap))}")
        # Guard against the ghost-auth regression: swap must keep Firebase
        # auth_userId intact and only set an automation owner override.
        swapped_auth_uid = (swap_detail.get("auth_user_id") or "").strip()
        swapped_override = (swap_detail.get("owner_override") or "").strip()
        swapped_owner_a = (swap_detail.get("owner_a") or "").strip()
        if not swapped_auth_uid or not swapped_override:
            self.fail(
                "owner-switch: swap_test_owner missing auth_user_id/owner_override "
                f"(detail keys={sorted(swap_detail.keys())}); rebuild app with override-based swap"
            )
        if swapped_auth_uid == owner_b_id:
            self.fail(
                "owner-switch: auth_user_id equals synthetic owner_b; "
                "swap must use automation_owner_override instead"
            )
        if swapped_owner_a and swapped_auth_uid != swapped_owner_a:
            self.fail(
                "owner-switch: swap_test_owner rewrote auth_userId "
                f"(owner_a={swapped_owner_a}, auth_user_id={swapped_auth_uid}); "
                "this clears Firebase tokens via getIdToken mismatch"
            )
        if swapped_override != owner_b_id:
            self.fail(
                "owner-switch: owner_override mismatch "
                f"(expected={owner_b_id}, actual={swapped_override})"
            )

        deadline = time.monotonic() + (self.args.turn_timeout_ms / 1000.0)
        snapshot_detail: dict[str, str] = swap_detail
        while time.monotonic() < deadline:
            wait = bridge_action(
                self.port,
                "wait_main_chat_idle",
                {"timeoutMs": "2000", "pollMs": "250"},
            )
            snapshot_detail = wait.get("result", {}).get("detail", snapshot_detail)
            if wait.get("ok") and snapshot_detail.get("idle") == "true":
                break
            time.sleep(0.25)
        else:
            self.fail("owner-switch: timed out waiting for owner-B probe turn to finish")

        snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
        snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
        traces = wait_for_new_traces(trace_start, min_count=1, timeout_sec=10.0)
        if not traces:
            self.fail("owner-switch: owner-B probe produced no QueryTracer evidence")

        runtime = self.bridge_act("agent_runtime_evidence")
        runtime_detail = runtime.get("result", {}).get("detail", runtime)
        owner_b_identity = identity_keys(snapshot_detail, runtime_detail)
        owner_a_kernel = kernel_surface_identity(
            runtime_detail.get("database_path", ""),
            owner_a_identity.get("owner_id", ""),
        )
        owner_b_kernel = kernel_surface_identity(
            runtime_detail.get("database_path", ""),
            owner_b_id,
        )

        isolation_checks = {
            "owner_b_id_matches": owner_b_identity.get("owner_id") == owner_b_id,
            "conversation_id_disjoint": (
                bool(owner_a_kernel and owner_b_kernel)
                and owner_a_kernel.get("conversation_id")
                != owner_b_kernel.get("conversation_id")
            ),
            "trace_count": len(traces),
        }
        self.assert_trace_excludes(
            traces,
            list(self.markers.values()),
            "owner-switch probe",
        )
        if owner_b_identity.get("owner_id") != owner_b_id:
            self.fail(
                f"owner-switch: owner B id mismatch "
                f"(expected={owner_b_id}, actual={owner_b_identity.get('owner_id')})"
            )
        elif not owner_a_kernel or not owner_b_kernel:
            self.fail("owner-switch: could not read kernel surface_conversations for both owners")
        elif owner_a_kernel.get("conversation_id") == owner_b_kernel.get("conversation_id"):
            self.fail(
                "owner-switch: owner B reused owner A conversation_id "
                f"({owner_a_kernel.get('conversation_id')})"
            )

        self.record_step(
            "06-owner-switch-isolation",
            "owner-switch surface isolation (in-process)",
            user_text=probe_query,
            action_response=swap,
            snapshot_detail=snapshot_detail,
            traces=traces,
            extra={
                "owner_a_identity": owner_a_identity,
                "owner_a_kernel": owner_a_kernel,
                "owner_b_identity": owner_b_identity,
                "owner_b_kernel": owner_b_kernel,
                "isolation_checks": isolation_checks,
                "owner_switch_note": (
                    "Kernel owner isolation exercised in-process via swap_test_owner; "
                    "full Firebase auth-UI swap remains manual."
                ),
            },
            skip_identity_drift=True,
        )

        # Always undo the swap — a leaked synthetic owner breaks backend auth for
        # every subsequent turn and survives app relaunch.
        self.restore_test_owner("owner suite")

        self.manifest["owner_switch_note"] = (
            "Step 06 swaps to synthetic owner B in-process, captures owner-B QueryTracer "
            "evidence, and asserts owner-A markers are absent with disjoint conversation_id; "
            "full Firebase auth-UI swap remains manual."
        )

    def run_prompts_suite(self) -> None:
        """Fast typed-only prompt-regression probes (no PTT, no spawns).

        Guards the prompt-tuning loop: models must not over-refuse or mis-route
        tools because of injected policy prose, and register rules must hold.
        Run with --suite prompts for quick iteration after prompt edits.
        """
        # P1 — over-refusal: a direct, benign tool request must execute the tool
        # even with coordinator/context-packet policy prose in the prompt (R9).
        p1_query = "Use execute_sql to count the rows in the memories table and tell me just the number."
        send, snapshot, traces = self.send_and_wait(p1_query, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        sql_calls = trace_tool_executions(traces, {"execute_sql"})
        self.record_step(
            "p1-over-refusal",
            "prompt probe: direct tool request must not be refused",
            user_text=p1_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"execute_sql_calls": len(sql_calls)},
        )
        if not sql_calls:
            self.fail(
                "P1 over-refusal: model did not execute execute_sql for a direct benign request "
                f"(assistant={assistant[:160]!r})"
            )

        # P2 — tool selection: a recap-shaped question should consult a data
        # tool, preferably get_daily_recap.
        p2_query = "What did I do yesterday? One short paragraph."
        send, snapshot, traces = self.send_and_wait(p2_query, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        data_tools = trace_tool_executions(
            traces,
            {"get_daily_recap", "execute_sql", "get_conversations", "search_conversations", "semantic_search"},
        )
        tool_names = [str(tool.get("name")) for tool in data_tools]
        self.record_step(
            "p2-tool-selection",
            "prompt probe: recap question routes to a data tool",
            user_text=p2_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"data_tools": tool_names},
        )
        if not data_tools:
            self.fail(
                "P2 tool selection: recap question answered without consulting any data tool "
                f"(assistant={assistant[:160]!r})"
            )
        elif "get_daily_recap" not in tool_names:
            self.warn(f"P2 tool selection: answered without get_daily_recap (used {tool_names})")

        # P3 — register: unknown-person question must stay short and human,
        # with no robotic data-source phrasing.
        p3_query = "What should I know about my new colleague Zebulon Quarkfinder?"
        send, snapshot, traces = self.send_and_wait(p3_query, self.args.turn_timeout_ms)
        assistant = latest_assistant_text(snapshot)
        robotic = [
            phrase
            for phrase in (
                "in the logs",
                "recorded conversations",
                "captured calls",
                "no data available",
                "based on available memories",
                "in the database",
                "according to the tools",
            )
            if phrase in assistant.lower()
        ]
        self.record_step(
            "p3-register",
            "prompt probe: unknown-person answer stays short and human",
            user_text=p3_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"robotic_phrases": robotic, "reply_chars": len(assistant)},
        )
        if robotic:
            self.fail(f"P3 register: robotic phrasing in reply: {robotic}")
        if len(assistant) > 450:
            self.warn(f"P3 register: unknown-person reply too long ({len(assistant)} chars)")

    def run_resilience_r3_race_policy(self) -> None:
        """Probe concurrent main-chat send rejection via no-wait + busy-state actions."""
        long_query = (
            f"Resilience race hold {self.run_id}. "
            "Take about twenty seconds to reply with exactly: RACE_HOLD_DONE"
        )
        race_query = f"Resilience race probe {self.run_id}. Reply with exactly: RACE_PROBE_REJECTED"

        fire = self.bridge_act("ask_main_chat_no_wait", {"query": long_query})
        fire_detail = fire.get("result", {}).get("detail", {}) if isinstance(fire, dict) else {}
        if fire.get("ok") is False or fire_detail.get("error"):
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                1,
                "generic_chat_error",
                {"phase": "fire", "fire_detail": fire_detail, "fire": fire},
            )
            self.fail(f"R3 race policy: ask_main_chat_no_wait failed: {fire_detail.get('error', fire)}")
            return
        if fire_detail.get("accepted") != "true":
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                1,
                "generic_chat_error",
                {"phase": "fire", "fire_detail": fire_detail},
            )
            self.fail(f"R3 race policy: initial no-wait send was not accepted: {fire_detail}")
            return

        busy_seen = False
        busy_detail: dict[str, Any] = {}
        busy_deadline = time.monotonic() + 5.0
        while time.monotonic() < busy_deadline:
            busy = self.bridge_act("main_chat_busy_state")
            busy_detail = busy.get("result", {}).get("detail", {}) if isinstance(busy, dict) else {}
            if busy.get("ok") is False or busy_detail.get("error"):
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    2,
                    "generic_chat_error",
                    {"phase": "busy_poll", "busy_detail": busy_detail, "busy": busy},
                )
                self.fail(f"R3 race policy: main_chat_busy_state failed: {busy_detail.get('error', busy)}")
                return
            if busy_detail.get("busy") == "true":
                busy_seen = True
                break
            time.sleep(0.05)
        if not busy_seen:
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                2,
                "generic_chat_error",
                {"phase": "busy_poll", "busy_detail": busy_detail, "fire_detail": fire_detail},
            )
            self.fail("R3 race policy: main chat never reported busy after no-wait send")
            return

        race = self.bridge_act("ask_main_chat_no_wait", {"query": race_query})
        race_detail = race.get("result", {}).get("detail", {}) if isinstance(race, dict) else {}
        if race.get("ok") is False or race_detail.get("error"):
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                3,
                "generic_chat_error",
                {"phase": "race", "race_detail": race_detail, "race": race},
            )
            self.fail(f"R3 race policy: concurrent no-wait send errored: {race_detail.get('error', race)}")
            return

        rejected = (
            race_detail.get("accepted") == "false"
            or race_detail.get("busy") == "true"
            or race_detail.get("reason") == "already_sending"
        )
        if not rejected:
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                3,
                "generic_chat_error",
                {
                    "phase": "race",
                    "fire_detail": fire_detail,
                    "busy_detail": busy_detail,
                    "race_detail": race_detail,
                    "rejected": False,
                },
            )
            self.fail(
                "R3 race policy: concurrent ask_main_chat_no_wait was accepted while chat was busy "
                f"(race_detail={race_detail})"
            )
            terminal_reason = "generic_chat_error"
        else:
            terminal_reason = "passed"
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                3,
                terminal_reason,
                {
                    "phase": "race",
                    "fire_detail": fire_detail,
                    "busy_detail": busy_detail,
                    "race_detail": race_detail,
                    "rejected": True,
                },
            )

        # Drain the in-flight hold turn so later resilience probes start idle.
        wait = bridge_action(
            self.port,
            "wait_main_chat_idle",
            {"timeoutMs": str(self.args.turn_timeout_ms), "pollMs": "250"},
        )
        wait_detail = wait.get("result", {}).get("detail", {}) if isinstance(wait, dict) else {}
        self.record_step(
            "r3-already-running-race-policy",
            "resilience: already-running/race policy",
            user_text=long_query,
            action_response=fire,
            snapshot_detail=wait_detail,
            traces=[],
            extra={
                "terminal_reason": terminal_reason,
                "busy_detail": busy_detail,
                "race_query": race_query,
                "race_detail": race_detail,
                "wait_detail": wait_detail,
            },
        )

    def run_resilience_suite(self) -> None:
        """Startup/bad-state probes for bridge, main chat, and subagent launch continuity.

        Run with --suite resilience for release-candidate startup QA; --suite all
        includes this suite alongside the canonical continuity, agents, owner, and
        prompt checks.
        """
        self.manifest["resilience_forbidden_terminal_reasons"] = sorted(
            RESILIENCE_FORBIDDEN_TERMINAL_REASONS
        )

        # R1 — cold/simple bridge launch probe. ask_main_chat goes through the
        # real agent bridge and QueryTracer; it is safe for a named non-prod bundle
        # and avoids process restarts or destructive simulation.
        r1_query = (
            f"Resilience startup probe {self.run_id}. "
            "Reply with exactly: RESILIENCE_BRIDGE_READY"
        )
        send, snapshot, traces = self.send_and_wait_resilience(r1_query, self.args.turn_timeout_ms)
        r1_reason = self.classify_resilience_turn(
            scenario="R1-cold-simple-bridge-launch",
            iteration=1,
            query=r1_query,
            send=send,
            snapshot=snapshot,
            traces=traces,
        )
        self.record_step(
            "r1-cold-bridge-launch",
            "resilience: cold/simple bridge launch probe",
            user_text=r1_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={"terminal_reason": r1_reason},
        )
        self.assert_assistant_mentions(latest_assistant_text(snapshot), ["RESILIENCE_BRIDGE_READY"], "R1 bridge launch")

        # R2 — warm reuse probe. Sequential short prompts must settle cleanly and
        # must not surface already-running or generic stopped-response text.
        for index in range(1, 4):
            query = f"Warm reuse probe {index}. Reply with exactly WARM_REUSE_{index}."
            send, snapshot, traces = self.send_and_wait_resilience(query, self.args.turn_timeout_ms)
            terminal_reason = self.classify_resilience_turn(
                scenario="R2-warm-reuse",
                iteration=index,
                query=query,
                send=send,
                snapshot=snapshot,
                traces=traces,
            )
            self.record_step(
                f"r2-warm-reuse-{index}",
                f"resilience: warm reuse probe {index}",
                user_text=query,
                action_response=send,
                snapshot_detail=snapshot,
                traces=traces,
                extra={"terminal_reason": terminal_reason},
            )
            self.assert_assistant_mentions(
                latest_assistant_text(snapshot),
                [f"WARM_REUSE_{index}"],
                f"R2 warm reuse {index}",
            )

        # R3 — already-running/race policy. Fire a non-waiting main-chat send,
        # confirm busy state, then attempt a concurrent send and assert the bridge
        # rejects it (or reports busy) instead of overlapping turns.
        # Missing actions are a hard fail (skipped_missing_action is forbidden);
        # --self-check also requires these actions so CI catches drift before live.
        bridge_source = (DESKTOP_DIR / "Desktop/Sources/DesktopAutomationBridge.swift").read_text(encoding="utf-8")
        race_actions = {"ask_main_chat_no_wait", "main_chat_busy_state"}
        present = sorted(name for name in race_actions if f'name: "{name}"' in bridge_source)
        missing = sorted(race_actions - set(present))
        if missing:
            # skipped_missing_action is forbidden → record_resilience_diagnostic fails the run.
            self.record_resilience_diagnostic(
                "R3-already-running-race-policy",
                1,
                "skipped_missing_action",
                {
                    "missing_bridge_actions": missing,
                    "note": "need ask_main_chat_no_wait + main_chat_busy_state",
                },
            )
        else:
            self.run_resilience_r3_race_policy()

        # R4 — subagent launch cold/resilience probe. This is stricter than the
        # agents suite because it records terminal reasons and requires runtime,
        # coordinator/pill projection, spawn tool evidence, and status visibility.
        # Prompt mirrors the agents-suite spawn wording (track marker + wait) so
        # the model treats it as a real background-work objective, not a probe.
        marker = f"RESILIENCE-SUBAGENT-{self.run_id}-{secrets.token_hex(3).upper()}"
        spawn_title = f"Resilience Monitor {marker[-8:]}"
        spawn_query = (
            f"Use spawn_agent now to start a visible background agent titled \"{spawn_title}\". "
            f"Objective: track marker {marker} and wait silently. "
            "Do not ask follow-up questions."
        )
        trace_start = trace_line_count()
        send, snapshot, traces = self.send_and_wait_resilience(spawn_query, self.args.turn_timeout_ms)
        spawn_tools: list[dict[str, Any]] = []
        settle_deadline = time.monotonic() + 10.0
        while time.monotonic() < settle_deadline:
            traces = read_new_traces(trace_start)
            spawn_tools = [
                tool
                for tool in trace_tool_executions(traces, {"spawn_agent"})
                if marker in str(tool.get("input", "")) or marker in str(tool.get("output", ""))
            ]
            if spawn_tools:
                break
            time.sleep(0.25)
        coordinator = self.bridge_act("coordinator_awareness_snapshot")
        coordinator_detail = coordinator.get("result", {}).get("detail", {})
        runtime = self.bridge_act("agent_runtime_evidence")
        runtime_detail = runtime.get("result", {}).get("detail", {})
        terminal_reason = self.classify_resilience_turn(
            scenario="R4-subagent-launch",
            iteration=1,
            query=spawn_query,
            send=send,
            snapshot=snapshot,
            traces=traces,
        )
        if not spawn_tools:
            terminal_reason = "subagent_missing"
            self.record_resilience_diagnostic(
                "R4-subagent-launch",
                2,
                terminal_reason,
                {
                    "spawn_tool_calls": 0,
                    "coordinator_snapshot_chars": len(str(coordinator_detail.get("snapshot", ""))),
                    "database_exists": runtime_detail.get("database_exists"),
                },
            )
            self.fail("R4 subagent launch: no spawn_agent execution carrying the resilience marker")
        if runtime.get("ok") is False or runtime_detail.get("error") or runtime_detail.get("database_exists") != "true":
            self.record_resilience_diagnostic(
                "R4-subagent-launch",
                3,
                "runtime_evidence_missing",
                {"runtime_detail": runtime_detail},
            )
            self.fail("R4 subagent launch: runtime sqlite evidence missing")
        if marker not in str(coordinator_detail):
            self.record_resilience_diagnostic(
                "R4-subagent-launch",
                4,
                "pill_runtime_evidence_missing",
                {"coordinator_snapshot_chars": len(str(coordinator_detail.get("snapshot", "")))},
            )
            self.fail("R4 subagent launch: coordinator/pill evidence missing resilience marker")
        self.record_step(
            "r4-subagent-launch",
            "resilience: subagent launch cold probe",
            user_text=spawn_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={
                "terminal_reason": terminal_reason,
                "spawn_tool_calls": spawn_tools,
                "coordinator_snapshot": coordinator_detail,
                "runtime_evidence": runtime_detail,
            },
        )

        status_query = (
            "What is the status of the background agent you just started? "
            "Use list_agent_sessions and include its exact resilience marker."
        )
        send, snapshot, traces = self.send_and_wait_resilience(status_query, self.args.turn_timeout_ms)
        terminal_reason = self.classify_resilience_turn(
            scenario="R4-subagent-status",
            iteration=1,
            query=status_query,
            send=send,
            snapshot=snapshot,
            traces=traces,
        )
        assistant = latest_assistant_text(snapshot)
        list_tools = trace_tool_executions(traces, {"list_agent_sessions"})
        list_outputs = "\n".join(str(tool.get("output", "")) for tool in list_tools)
        if not list_tools or marker not in (assistant + "\n" + list_outputs):
            terminal_reason = "subagent_status_invisible"
            self.record_resilience_diagnostic(
                "R4-subagent-status",
                2,
                terminal_reason,
                {
                    "list_agent_sessions_calls": len(list_tools),
                    "assistant_chars": len(assistant),
                    "marker_in_tool_output": marker in list_outputs,
                },
            )
            self.fail("R4 subagent status: status query could not see the spawned resilience agent")
        self.record_step(
            "r4-subagent-status",
            "resilience: subagent status query",
            user_text=status_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={
                "terminal_reason": terminal_reason,
                "list_agent_sessions_calls": list_tools,
            },
        )

    def finalize(self) -> int:
        manifest = self.manifest
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        if "resilience" in self.suites:
            manifest["resilience_terminal_reason_counts"] = dict(
                sorted(self.resilience_terminal_reason_counts.items())
            )
            manifest["resilience_forbidden_terminal_reasons"] = sorted(
                RESILIENCE_FORBIDDEN_TERMINAL_REASONS
            )
        manifest["steps"] = self.steps
        manifest["failures"] = self.failures
        manifest["warnings"] = self.warnings
        manifest["passed"] = not self.failures
        write_json(self.run_dir / "manifest.json", manifest)
        finalize_evidence_hygiene(self.run_dir, passed=manifest["passed"], git_sha=manifest["git"])

        if self.warnings:
            for warning in self.warnings:
                print(f"GAUNTLET WARN: {warning}", file=sys.stderr)

        if self.failures:
            for failure in self.failures:
                print(f"GAUNTLET FAIL: {failure}", file=sys.stderr)
            print(f"evidence: {self.run_dir}", file=sys.stderr)
            return 1

        print(f"Gauntlet passed. evidence: {self.run_dir}")
        return 0


def run_owner_switch_kernel_check() -> tuple[bool, str]:
    """Kernel-level owner isolation (full auth E2E deferred — see manifest owner_switch_note)."""
    agent_dir = DESKTOP_DIR / "agent"
    if not (agent_dir / "package.json").is_file():
        return False, "agent package missing"
    result = subprocess.run(
        ["npm", "test", "--", "--run", "tests/surface-session.test.ts", "-t", "owner B does not reuse"],
        cwd=agent_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stdout
    return True, "kernel surface_conversations isolates owners per surface"


def self_check() -> int:
    script = SCRIPT_DIR / "agent-continuity-gauntlet.sh"
    bridge_actions = {
        "ask",
        "ask_main_chat",
        "ask_main_chat_no_wait",
        "main_chat_busy_state",
        "main_chat_snapshot",
        "wait_main_chat_idle",
        "agent_runtime_evidence",
        "coordinator_awareness_snapshot",
        "swap_test_owner",
        "restore_test_owner",
        "clear_owner_surface_state",
        "kernel_turn_tail",
    }
    hub_actions = {"ptt_test_turn"}
    bridge_source = (DESKTOP_DIR / "Desktop/Sources/DesktopAutomationBridge.swift").read_text(encoding="utf-8")
    hub_source = (DESKTOP_DIR / "Desktop/Sources/FloatingControlBar/RealtimeHubController.swift").read_text(
        encoding="utf-8"
    )
    missing = sorted(name for name in bridge_actions if f'name: "{name}"' not in bridge_source)
    missing.extend(sorted(name for name in hub_actions if f'name: "{name}"' not in hub_source))
    if missing:
        print(f"self-check failed: missing automation actions: {missing}", file=sys.stderr)
        return 1
    if not script.is_file():
        print("self-check failed: agent-continuity-gauntlet.sh missing", file=sys.stderr)
        return 1
    source = (DESKTOP_DIR / "Desktop/Sources/Providers/ChatProvider.swift").read_text(encoding="utf-8")
    if "clearOwnerState()" not in source:
        print("self-check failed: ChatProvider sign-out must call clearOwnerState()", file=sys.stderr)
        return 1
    driver_source = (SCRIPT_DIR / "agent-continuity-gauntlet-lib.py").read_text(encoding="utf-8")
    missing_auth_checks = bridge_auth_self_check_failures(driver_source)
    if missing_auth_checks:
        print(f"self-check failed: bridge auth wiring missing {missing_auth_checks}", file=sys.stderr)
        return 1
    missing_driver_checks = resilience_driver_self_check_failures(driver_source)
    if missing_driver_checks:
        print(f"self-check failed: resilience suite wiring missing {missing_driver_checks}", file=sys.stderr)
        return 1
    missing_contract_checks = continuity_contract_self_check_failures()
    if missing_contract_checks:
        print(
            f"self-check failed: INV-6 hermetic contract coverage missing {missing_contract_checks}",
            file=sys.stderr,
        )
        return 1
    owner_ok, owner_detail = run_owner_switch_kernel_check()
    if not owner_ok:
        print(f"self-check failed: owner-switch kernel check: {owner_detail}", file=sys.stderr)
        return 1
    print(
        "self-check passed "
        "(R3 race actions + resilience wiring + INV-6 hermetic contract gates + owner-switch)"
    )
    return 0


def continuity_contract_self_check_failures() -> list[str]:
    """Fail if hermetic INV-6 contract tests / harness filter drift out of the DoD gate.

    Live gauntlet suites exercise bridge/LLM continuity; they do NOT replace these
    hermetic behavioral tests. See AGENTS.md → "Live gauntlet vs hermetic INV-6".
    """
    failures: list[str] = []
    tests_dir = DESKTOP_DIR / "Desktop/Tests"
    harness = (SCRIPT_DIR / "agent-logic-harness.sh").read_text(encoding="utf-8")

    required_filter_classes = [
        "KernelTurnRecordedProjectionTests",
        "ChatTimelineContinuityTests",
        "FloatingControlBarStateTests",
        "AgentContinuityGauntletTests",
    ]
    for class_name in required_filter_classes:
        if class_name not in harness:
            failures.append(f"agent-logic-harness filter includes {class_name}")

    projection = (tests_dir / "KernelTurnRecordedProjectionTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testStageOptimisticThenApplyPromotesInPlaceWithoutDuplicate(",
        "func testApplyKernelTurnRecordedDedupesByIdempotencyKey(",
        "func testMainAndFloatingAutomationSnapshotsAliasSameTimeline(",
    ):
        if needle not in projection:
            failures.append(f"KernelTurnRecordedProjectionTests.{needle.split('(')[0].removeprefix('func ')}")

    timeline = (tests_dir / "ChatTimelineContinuityTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testHydratePreferencePrefersRunThenSessionThenPill(",
        "func testFindPillMatchesByHydratePreferenceOrder(",
        "func testAgentCompletionBlockExposesOpenRefAndStaysVisible(",
    ):
        if needle not in timeline:
            failures.append(f"ChatTimelineContinuityTests.{needle.split('(')[0].removeprefix('func ')}")

    floating_state = (tests_dir / "FloatingControlBarStateTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testViewportDerivesCurrentAnswerAndHistoryFromProviderMessages(",
        "func testCanRestoreUsesViewportAnchorsAndActivityWindow(",
        "chatViewport",
    ):
        if needle not in floating_state:
            label = needle.split("(")[0].removeprefix("func ") if needle.startswith("func ") else needle
            failures.append(f"FloatingControlBarStateTests covers {label}")

    return failures



def bridge_auth_self_check_failures(driver_source: str) -> list[str]:
    """Fail if bridge_request no longer sends the automation bearer token."""
    tree = ast.parse(driver_source)
    failures: list[str] = []
    funcs = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    token_fn = funcs.get("automation_token")
    if token_fn is None:
        failures.append("automation_token helper")
    else:
        if not method_contains_string(token_fn, "OMI_AUTOMATION_TOKEN"):
            failures.append("automation_token reads OMI_AUTOMATION_TOKEN")
        if not method_contains_string(token_fn, "omi-automation-"):
            failures.append("automation_token reads omi-automation-{port}.token")
    bridge = funcs.get("bridge_request")
    if bridge is None:
        failures.append("bridge_request function")
        return failures
    if not method_calls(bridge, "automation_token"):
        failures.append("bridge_request calls automation_token")
    if not method_contains_string(bridge, "Authorization"):
        failures.append("bridge_request sets Authorization header")
    # f"Bearer {token}" -> JoinedStr with Constant("Bearer ")
    if not method_contains_string(bridge, "Bearer "):
        failures.append("bridge_request uses Bearer token scheme")
    return failures


def resilience_driver_self_check_failures(driver_source: str) -> list[str]:
    tree = ast.parse(driver_source)
    failures: list[str] = []
    runner = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GauntletRunner"
        ),
        None,
    )
    if runner is None:
        return ["GauntletRunner class"]

    methods = {
        node.name: node
        for node in runner.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method_name in (
        "record_resilience_diagnostic",
        "run_resilience_suite",
        "finalize",
        "run",
    ):
        if method_name not in methods:
            failures.append(f"GauntletRunner.{method_name}")

    if "resilience" not in ast_literal_set(tree, "SUITE_NAMES"):
        failures.append("SUITE_NAMES includes resilience")
    if "resilience" not in ast_literal_set(tree, "SUITE_ALIASES", key="all"):
        failures.append("SUITE_ALIASES['all'] includes resilience")
    if not method_contains_string(methods.get("record_resilience_diagnostic"), "resilience-diagnostics.jsonl"):
        failures.append("record_resilience_diagnostic writes resilience-diagnostics.jsonl")
    if not method_contains_string(methods.get("run_resilience_suite"), "skipped_missing_action"):
        failures.append("run_resilience_suite can record skipped_missing_action")
    if not method_contains_string(methods.get("run_resilience_suite"), "ask_main_chat_no_wait"):
        failures.append("run_resilience_suite references ask_main_chat_no_wait")
    if not method_contains_string(methods.get("run_resilience_suite"), "main_chat_busy_state"):
        failures.append("run_resilience_suite references main_chat_busy_state")
    if "run_resilience_r3_race_policy" not in methods:
        failures.append("GauntletRunner.run_resilience_r3_race_policy")
    elif not method_calls(methods.get("run_resilience_suite"), "run_resilience_r3_race_policy"):
        failures.append("run_resilience_suite calls run_resilience_r3_race_policy")
    if not method_contains_string(methods.get("run_resilience_suite"), '". Objective: track marker '):
        failures.append("run_resilience_suite R4 spawn uses track-marker objective")
    if not method_contains_attr(methods.get("record_resilience_diagnostic"), "resilience_terminal_reason_counts"):
        failures.append("record_resilience_diagnostic updates resilience_terminal_reason_counts")
    if not method_contains_attr(methods.get("finalize"), "resilience_terminal_reason_counts"):
        failures.append("finalize emits resilience_terminal_reason_counts")
    if not method_contains_string(methods.get("finalize"), "resilience_forbidden_terminal_reasons"):
        failures.append("finalize emits resilience_forbidden_terminal_reasons")
    if not method_calls(methods.get("run"), "run_resilience_suite"):
        failures.append("run dispatches run_resilience_suite")
    return failures


def ast_literal_set(tree: ast.Module, name: str, *, key: str | None = None) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                continue
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            value = node.value
            if value is None:
                return set()
        else:
            continue
        if key is not None:
            if not isinstance(value, ast.Dict):
                return set()
            for dict_key, dict_value in zip(value.keys, value.values):
                if isinstance(dict_key, ast.Constant) and dict_key.value == key:
                    value = dict_value
                    break
            else:
                return set()
        if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return {
                item.value
                for item in value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
    return set()


def method_contains_string(node: ast.AST | None, text: str) -> bool:
    return node is not None and any(
        isinstance(child, ast.Constant) and child.value == text
        for child in ast.walk(node)
    )


def method_contains_attr(node: ast.AST | None, name: str) -> bool:
    return node is not None and any(
        isinstance(child, ast.Attribute) and child.attr == name
        for child in ast.walk(node)
    )


def method_calls(node: ast.AST | None, method_name: str) -> bool:
    """True if node calls method_name as attr (obj.foo) or bare name (foo)."""
    if node is None:
        return False
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == method_name:
            return True
        if isinstance(func, ast.Name) and func.id == method_name:
            return True
    return False


SUITE_ALIASES: dict[str, set[str]] = {
    "core": {"continuity", "agents", "owner"},
    "all": {"continuity", "agents", "owner", "prompts", "resilience"},
}
SUITE_NAMES = {"continuity", "agents", "owner", "prompts", "resilience"}


def expand_suites(raw: str) -> set[str]:
    enabled: set[str] = set()
    for token in raw.split(","):
        token = token.strip().lower()
        if not token:
            continue
        if token in SUITE_ALIASES:
            enabled |= SUITE_ALIASES[token]
        elif token in SUITE_NAMES:
            enabled.add(token)
        else:
            raise SystemExit(
                f"unknown suite {token!r}; choose from {sorted(SUITE_NAMES | set(SUITE_ALIASES))}"
            )
    return enabled or SUITE_ALIASES["core"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop agent continuity gauntlet (INV-6)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bundle-id", default=os.environ.get("OMI_GAUNTLET_BUNDLE_ID", f"com.omi.{DEFAULT_BUNDLE_SUFFIX}"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--log-path", default=str(DEFAULT_LOG))
    parser.add_argument("--turn-timeout-ms", type=int, default=180_000)
    parser.add_argument(
        "--suite",
        default="core",
        help=(
            "Comma-separated suites: continuity (steps 1-3, includes PTT), agents (4-5), "
            "owner (6), prompts (fast typed-only prompt-regression probes), "
            "resilience (startup/bad-state bridge + subagent probes), "
            "core (default: continuity+agents+owner), all (core+prompts+resilience). "
            "Example: --suite resilience for release-candidate startup QA."
        ),
    )
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        return self_check()
    return GauntletRunner(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
