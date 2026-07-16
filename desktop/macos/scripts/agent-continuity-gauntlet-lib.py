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
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
DEFAULT_PORT = int(os.environ.get("OMI_AUTOMATION_PORT", "47777"))
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
EXACT_VOICE_AGENT_MEMORY_REQUEST = (
    "Have an agent look through my memories today and surface one surprising insight."
)
EXACT_VOICE_AGENT_MEMORY_FOLLOWUP = (
    "Continue in this same agent session. Call get_memories again for today, then "
    "return one additional surprising insight. Do not spawn another agent."
)
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled", "orphaned"}
AGENT_CHILD_SURFACES = {
    "background_agent",
    "delegated_agent",
    "floating_bar",
    "floating_pill",
}
CONVERGENCE_FORBIDDEN_EVIDENCE_PATTERNS = {
    "unrouted_tool_call",
    "malformed jsonl",
    "malformed_jsonl",
    "invalid json:",
    "malformed_external_surface",
    "malformed_authorized_execution",
    "legacy_tool_authorization",
    "legacy_path_invoked",
    "legacy-path invoked",
    "legacy path invoked",
    "agentdelegationresolver",
    "agentpillsmanager.classify",
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
    if name in {
        "ask_main_chat",
        "coordinator_continue_agent",
        "coordinator_inspect_run",
        "quit_and_reopen",
        "swap_test_owner",
        "kernel_turn_tail",
    }:
        return turn_sec
    return 60.0


class AutomationTokenError(RuntimeError):
    """Token file exists but cannot be read (permissions/encoding). Fail closed."""


def automation_token(port: int) -> str | None:
    """Load the per-launch bridge bearer token (same contract as omi-ctl).

    Missing token file → None (caller may proceed unauthenticated or fail later).
    Unreadable/corrupt token file → AutomationTokenError (fail closed; do not
    silently omit Authorization).
    """
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
    except (OSError, UnicodeError) as exc:
        raise AutomationTokenError(
            f"automation token file unreadable at {token_file}: {exc}"
        ) from exc
    return token or None


def bridge_request(
    port: int,
    method: str,
    route: str,
    body: dict[str, Any] | None = None,
    *,
    timeout_sec: float = 60,
    authenticate: bool = True,
) -> dict[str, Any]:
    payload = None
    headers = {"Accept": "application/json"}
    if authenticate:
        try:
            token = automation_token(port)
        except AutomationTokenError as exc:
            # Fail closed: never send an unauthenticated request when the token
            # contract is broken. Still return a structured failure (no crash).
            return {"ok": False, "error": f"automation_token_unreadable: {exc}"}
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


def health_log_path(health: dict[str, Any]) -> str | None:
    """Read the log path from the bridge's standard success envelope."""
    if health.get("ok") is not True:
        return None
    result = health.get("result")
    raw_path = result.get("logFilePath") if isinstance(result, dict) else health.get("logFilePath")
    return raw_path if isinstance(raw_path, str) else None


def resolve_active_log_path(port: int, explicit_path: str | None) -> str:
    if explicit_path:
        return explicit_path
    # /health deliberately serves immutable launch diagnostics only to callers
    # without credentials; an authenticated request returns the state envelope.
    health = bridge_request(port, "GET", "/health", authenticate=False)
    raw_path = health_log_path(health)
    if not isinstance(raw_path, str) or not raw_path or not Path(raw_path).is_absolute():
        raise SystemExit(
            "automation health did not provide an absolute logFilePath; use a current named bundle "
            "or pass --log-path explicitly"
        )
    return raw_path


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


def automation_listener_pid(port: int) -> str:
    try:
        result = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        return ""
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")


def sine_pcm16k(seconds: float = 0.75, frequency: float = 220.0, amplitude: float = 3500.0) -> bytes:
    sample_rate = 16_000
    sample_count = int(sample_rate * seconds)
    chunks: list[bytes] = []
    for index in range(sample_count):
        value = int(amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate))
        chunks.append(struct.pack("<h", value))
    return b"".join(chunks)


@dataclass(frozen=True)
class TraceCursor:
    device: int | None
    inode: int | None
    offset: int
    line_count: int
    prefix_digest: str


@dataclass(frozen=True)
class TraceLogLine:
    source: str
    line_number: int
    text: str


def capture_trace_cursor(trace_log: Path = TRACE_LOG) -> TraceCursor:
    try:
        with trace_log.open("rb") as handle:
            stat = os.fstat(handle.fileno())
            contents = handle.read(stat.st_size)
            final_newline = contents.rfind(b"\n")
            last_complete_offset = final_newline + 1 if final_newline >= 0 else 0
            complete_prefix = contents[:last_complete_offset]
            return TraceCursor(
                stat.st_dev,
                stat.st_ino,
                last_complete_offset,
                complete_prefix.count(b"\n"),
                hashlib.sha256(complete_prefix).hexdigest(),
            )
    except FileNotFoundError:
        return TraceCursor(None, None, 0, 0, hashlib.sha256(b"").hexdigest())


def _opened_trace_file(path: Path):
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return None
    stat = os.fstat(handle.fileno())
    return handle, (stat.st_dev, stat.st_ino), stat.st_size


def _read_trace_file_lines(
    opened: tuple[Any, tuple[int, int], int],
    *,
    offset: int,
    first_line_number: int,
    source: str,
) -> list[TraceLogLine]:
    handle, _, size = opened
    effective_offset = offset if 0 <= offset <= size else 0
    handle.seek(effective_offset)
    text = handle.read().decode("utf-8", errors="replace")
    return [
        TraceLogLine(source=source, line_number=first_line_number + index, text=line)
        for index, line in enumerate(text.splitlines())
    ]


def _trace_cursor_prefix_matches(
    opened: tuple[Any, tuple[int, int], int],
    cursor: TraceCursor,
) -> bool:
    handle, _, size = opened
    if size < cursor.offset:
        return False
    handle.seek(0)
    prefix = handle.read(cursor.offset)
    return hashlib.sha256(prefix).hexdigest() == cursor.prefix_digest


def _new_trace_lines(cursor: TraceCursor, trace_log: Path = TRACE_LOG) -> list[TraceLogLine]:
    backup_log = trace_log.with_name("traces.1.jsonl")
    active = _opened_trace_file(trace_log)
    backup = _opened_trace_file(backup_log)
    cursor_identity = (cursor.device, cursor.inode)
    try:
        if active is not None and active[1] == cursor_identity:
            if _trace_cursor_prefix_matches(active, cursor):
                return _read_trace_file_lines(
                    active,
                    offset=cursor.offset,
                    first_line_number=cursor.line_count + 1,
                    source=trace_log.name,
                )
            return _read_trace_file_lines(
                active,
                offset=0,
                first_line_number=1,
                source=trace_log.name,
            )

        lines: list[TraceLogLine] = []
        if backup is not None and backup[1] == cursor_identity:
            backup_offset = cursor.offset if _trace_cursor_prefix_matches(backup, cursor) else 0
            lines.extend(_read_trace_file_lines(
                backup,
                offset=backup_offset,
                first_line_number=cursor.line_count + 1 if backup_offset else 1,
                source=backup_log.name,
            ))
        if active is not None:
            lines.extend(_read_trace_file_lines(
                active,
                offset=0,
                first_line_number=1,
                source=trace_log.name,
            ))
        return lines
    finally:
        if active is not None:
            active[0].close()
        if backup is not None:
            backup[0].close()


def read_new_traces(cursor: TraceCursor, trace_log: Path = TRACE_LOG) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for line in _new_trace_lines(cursor, trace_log):
        raw = line.text.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            traces.append(parsed)
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


def read_new_trace_diagnostics(
    cursor: TraceCursor,
    trace_log: Path = TRACE_LOG,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return new QueryTracer rows plus any malformed JSONL evidence.

    The general-purpose trace reader intentionally tolerates a damaged historical
    line. The convergence acceptance step cannot: malformed frames are one of its
    explicit zero-count gates, so it records line numbers and a bounded preview.
    """
    traces: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    for line in _new_trace_lines(cursor, trace_log):
        raw = line.text.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            malformed.append(
                {
                    "source": line.source,
                    "line": line.line_number,
                    "error": exc.msg,
                    "preview": raw[:400],
                }
            )
            continue
        if not isinstance(parsed, dict):
            malformed.append(
                {
                    "source": line.source,
                    "line": line.line_number,
                    "error": "top-level JSONL value is not an object",
                    "preview": raw[:400],
                }
            )
            continue
        traces.append(parsed)
    return traces, malformed


def embedded_coordinator_payload(
    action_response: dict[str, Any],
    detail_key: str,
) -> dict[str, Any]:
    """Decode a runtime-control JSON string returned through the Swift bridge."""
    if action_response.get("ok") is False:
        raise ValueError(str(action_response.get("error") or action_response))
    detail = action_response.get("result", {}).get("detail", {})
    if not isinstance(detail, dict):
        raise ValueError("automation action detail is not an object")
    raw = detail.get(detail_key)
    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{detail_key} contains malformed coordinator JSON: {exc.msg}"
            ) from exc
    else:
        raise ValueError(f"automation action omitted {detail_key}")
    if not isinstance(payload, dict):
        raise ValueError(f"{detail_key} coordinator payload is not an object")
    if payload.get("ok") is False:
        raise ValueError(str(payload.get("error") or payload))
    return payload


def coordinator_awareness_payload(action_response: dict[str, Any]) -> dict[str, Any]:
    payload = embedded_coordinator_payload(action_response, "snapshot")
    snapshot = payload.get("snapshot", payload)
    if not isinstance(snapshot, dict):
        raise ValueError("coordinator awareness snapshot is not an object")
    if not isinstance(snapshot.get("ownerId"), str) or not snapshot.get("ownerId"):
        raise ValueError("coordinator awareness snapshot omitted ownerId")
    if not isinstance(snapshot.get("sessions"), list):
        raise ValueError("coordinator awareness snapshot omitted sessions")
    if not isinstance(snapshot.get("runs"), list):
        raise ValueError("coordinator awareness snapshot omitted runs")
    return snapshot


def coordinator_run_payload(action_response: dict[str, Any]) -> dict[str, Any]:
    payload = embedded_coordinator_payload(action_response, "run")
    if not isinstance(payload.get("session"), dict):
        raise ValueError("run inspection omitted session")
    if not isinstance(payload.get("run"), dict):
        raise ValueError("run inspection omitted run")
    if not isinstance(payload.get("attempts"), list):
        raise ValueError("run inspection omitted attempts")
    if not isinstance(payload.get("toolInvocations"), list):
        raise ValueError("run inspection omitted toolInvocations")
    return payload


def agent_lifecycle_convergence_payload(action_response: dict[str, Any]) -> dict[str, Any]:
    payload = embedded_coordinator_payload(action_response, "snapshot")
    entries = payload.get("entries")
    missing = payload.get("missingRequestedRunIds")
    if not isinstance(entries, list) or not isinstance(missing, list):
        raise ValueError("agent lifecycle convergence snapshot omitted entries or requested-run coverage")
    return payload


def awareness_session_parts(
    summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    session = summary.get("session")
    if not isinstance(session, dict):
        return {}, {}
    active_run = summary.get("activeRun")
    latest_run = summary.get("latestRun")
    selected_run = active_run if isinstance(active_run, dict) else latest_run
    return session, selected_run if isinstance(selected_run, dict) else {}


def awareness_session_ids(snapshot: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for summary in snapshot.get("sessions", []):
        if not isinstance(summary, dict):
            continue
        session, _ = awareness_session_parts(summary)
        session_id = session.get("sessionId")
        if isinstance(session_id, str) and session_id:
            result.add(session_id)
    return result


def awareness_run_ids(snapshot: dict[str, Any]) -> set[str]:
    return {
        run.get("runId")
        for run in snapshot.get("runs", [])
        if isinstance(run, dict) and isinstance(run.get("runId"), str) and run.get("runId")
    }


def new_leaf_session_summaries(
    snapshot: dict[str, Any],
    baseline_session_ids: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for summary in snapshot.get("sessions", []):
        if not isinstance(summary, dict):
            continue
        session, _ = awareness_session_parts(summary)
        session_id = session.get("sessionId")
        surface_kind = session.get("surfaceKind")
        execution_role = session.get("executionRole")
        if not isinstance(session_id, str) or not session_id or session_id in baseline_session_ids:
            continue
        if execution_role == "leaf" or surface_kind in AGENT_CHILD_SURFACES:
            result.append(summary)
    return result


def exact_external_parent_run_ids(snapshot: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for run in snapshot.get("runs", []):
        if not isinstance(run, dict):
            continue
        run_input = run.get("input")
        if not isinstance(run_input, dict) or run_input.get("prompt") != EXACT_VOICE_AGENT_MEMORY_REQUEST:
            continue
        metadata = run_input.get("metadata")
        external = metadata.get("externalSurface") if isinstance(metadata, dict) else None
        if not isinstance(external, dict) or external.get("authority") != "swift_realtime":
            continue
        run_id = run.get("runId")
        if isinstance(run_id, str) and run_id:
            result.append(run_id)
    return sorted(set(result))


def tool_invocation_contract_errors(
    payload: dict[str, Any],
    expected_run_id: str,
) -> list[str]:
    """Validate the bounded get_agent_run invocation summaries (no raw inputs/results)."""
    required_fields = {
        "invocationId",
        "runId",
        "attemptId",
        "toolName",
        "status",
        "errorCode",
        "preparedAtMs",
        "dispatchedAtMs",
        "completedAtMs",
        "updatedAtMs",
    }
    forbidden_fields = {
        "arguments",
        "argumentsJSON",
        "input",
        "inputHash",
        "output",
        "result",
        "toolInput",
    }
    allowed_statuses = {"prepared", "dispatched", "succeeded", "failed", "outcome_unknown"}
    attempt_ids = {
        attempt.get("attemptId")
        for attempt in payload.get("attempts", [])
        if isinstance(attempt, dict) and isinstance(attempt.get("attemptId"), str)
    }
    errors: list[str] = []
    for index, invocation in enumerate(payload.get("toolInvocations", [])):
        if not isinstance(invocation, dict):
            errors.append(f"toolInvocations[{index}] is not an object")
            continue
        missing = sorted(required_fields - set(invocation))
        leaked = sorted(forbidden_fields & set(invocation))
        if missing:
            errors.append(f"toolInvocations[{index}] missing {missing}")
        if leaked:
            errors.append(f"toolInvocations[{index}] leaked unbounded fields {leaked}")
        if invocation.get("runId") != expected_run_id:
            errors.append(f"toolInvocations[{index}] runId does not match inspected run")
        if invocation.get("attemptId") not in attempt_ids:
            errors.append(f"toolInvocations[{index}] attemptId is not an inspected attempt")
        if invocation.get("status") not in allowed_statuses:
            errors.append(f"toolInvocations[{index}] has invalid status {invocation.get('status')!r}")
        for field in ("preparedAtMs", "updatedAtMs"):
            if not isinstance(invocation.get(field), int):
                errors.append(f"toolInvocations[{index}] {field} is not an integer")
        for field in ("dispatchedAtMs", "completedAtMs"):
            if invocation.get(field) is not None and not isinstance(invocation.get(field), int):
                errors.append(f"toolInvocations[{index}] {field} is not integer/null")
    return errors


def tool_invocations_named(payload: dict[str, Any], tool_name: str) -> list[dict[str, Any]]:
    return [
        invocation
        for invocation in payload.get("toolInvocations", [])
        if isinstance(invocation, dict) and invocation.get("toolName") == tool_name
    ]


def run_terminal_event_count(payload: dict[str, Any], run_id: str, status: str) -> int:
    return sum(
        1
        for event in payload.get("events", [])
        if isinstance(event, dict)
        and event.get("runId") == run_id
        and event.get("type") == f"run.{status}"
    )


def wait_for_new_traces(
    cursor: TraceCursor,
    *,
    min_count: int = 1,
    timeout_sec: float = 8.0,
    poll_sec: float = 0.25,
    query_text: str | None = None,
    trace_log: Path = TRACE_LOG,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        traces = read_new_traces(cursor, trace_log)
        if query_text is not None:
            traces = traces_for_query(traces, query_text)
        if len(traces) >= min_count:
            return traces
        time.sleep(poll_sec)
    traces = read_new_traces(cursor, trace_log)
    return traces_for_query(traces, query_text) if query_text is not None else traces


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


def spawn_tool_acceptance_error(output: Any) -> str | None:
    """Validate the spawn admission result, not incidental words in its JSON.

    spawn_agent is asynchronous: a successful tool response returns an admitted
    child whose run is normally queued (or may already be running/succeeded).
    Nested fields such as errorCode=null must never turn that accepted response
    into a failure merely because their key contains the word "error".
    """
    payload = output
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return "spawn_agent output is not valid JSON"
    if not isinstance(payload, dict):
        return "spawn_agent output is not a JSON object"
    if payload.get("ok") is not True:
        error = payload.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("code")
            if detail:
                return f"spawn_agent rejected the request: {detail}"
        return "spawn_agent response did not report ok=true"
    agents = payload.get("agents")
    if not isinstance(agents, list) or not agents:
        return "spawn_agent ok=true response has no admitted agents"
    requested = payload.get("requestedAgentCount")
    if isinstance(requested, int) and requested > 0 and len(agents) != requested:
        return f"spawn_agent admitted {len(agents)} agents, expected {requested}"
    # Admission happens before adapter execution. `starting` is a valid
    # transient receipt; lifecycle convergence separately requires the child
    # to reach a canonical terminal state.
    accepted_statuses = {"queued", "starting", "running", "succeeded"}
    for index, agent in enumerate(agents):
        run = agent.get("run") if isinstance(agent, dict) else None
        status = run.get("status") if isinstance(run, dict) else None
        if status not in accepted_statuses:
            return f"spawn_agent agent {index} has non-accepted run status {status!r}"
    return None


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


def terminal_assistant_for_exact_turn(
    snapshot_detail: dict[str, str], query_text: str
) -> dict[str, Any] | None:
    """Return only this query's terminal assistant, never a neighboring turn's."""
    try:
        messages = json.loads(snapshot_detail.get("messages_json", "[]"))
    except json.JSONDecodeError:
        return None
    if not isinstance(messages, list):
        return None
    query = query_text.strip()
    start_index: int | None = None
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user" and str(message.get("text") or "").strip() == query:
            start_index = index
    if start_index is None:
        return None
    for message in messages[start_index + 1 :]:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            # A later user turn owns any following assistant rows.
            return None
        if message.get("role") == "assistant" and message.get("streaming") != "true":
            return message
    return None


def current_turn_assistant_text(snapshot_detail: dict[str, str], query_text: str) -> str:
    if message := terminal_assistant_for_exact_turn(snapshot_detail, query_text):
        return str(message.get("text") or "").strip()
    return ""


def current_turn_has_terminal_assistant(snapshot_detail: dict[str, str], query_text: str) -> bool:
    """Return whether the exact query has its own terminal assistant projection.

    Main-chat idle is a transport/lifecycle signal, not proof that this send
    produced a terminal row. Keying the wait to the exact user text prevents a
    failed empty turn from inheriting the previous turn's assistant response.
    """
    return terminal_assistant_for_exact_turn(snapshot_detail, query_text) is not None


def exact_voice_agent_turn_signature(
    snapshot_detail: dict[str, Any],
    *,
    child_session_id: str,
    child_run_id: str,
    expected_assistant_text: str | None = None,
) -> dict[str, Any]:
    """Validate the initial canonical run on the exact #9515 producing turn.

    A continuation reuses the child session but creates a distinct canonical run.
    Its terminal block belongs on the same producing receipt, so this verifier
    pins exactly one spawn and completion for *the initial run* while requiring
    each later completion to have a distinct terminal run identity.
    """
    try:
        messages = json.loads(str(snapshot_detail.get("messages_json", "[]")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"main chat snapshot contains malformed messages JSON: {exc.msg}") from exc
    if not isinstance(messages, list):
        raise ValueError("main chat snapshot messages are not an array")

    producing_assistants: list[tuple[int, dict[str, Any], list[Any]]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        try:
            candidate_blocks = json.loads(str(message.get("content_blocks_json", "[]")))
        except json.JSONDecodeError:
            continue
        if not isinstance(candidate_blocks, list):
            continue
        if any(
            isinstance(block, dict)
            and block.get("type") in {"agentSpawn", "agentCompletion"}
            and block.get("sessionId") == child_session_id
            and block.get("runId") == child_run_id
            for block in candidate_blocks
        ):
            producing_assistants.append((index, message, candidate_blocks))
    if len(producing_assistants) != 1:
        raise ValueError(
            "expected one producing assistant for the accepted child, "
            f"found {len(producing_assistants)}"
        )
    assistant_index, assistant, blocks = producing_assistants[0]
    adjacent_users = [
        message
        for message in messages[max(0, assistant_index - 1) : assistant_index]
        if isinstance(message, dict)
        and message.get("role") == "user"
        and str(message.get("raw_text") or message.get("text") or "").strip()
        == EXACT_VOICE_AGENT_MEMORY_REQUEST
    ]
    if len(adjacent_users) != 1:
        raise ValueError(
            "accepted child producing assistant does not have exactly one adjacent exact voice user turn"
        )
    assistant_raw_text = str(assistant.get("raw_text") or assistant.get("text") or "").strip()
    if not assistant_raw_text:
        raise ValueError("producing assistant omitted its canonical spawn acknowledgement")
    # The kernel owns this acknowledgement after it accepts the spawn. Its
    # wording may include the accepted agent title, so a fixed English sentence
    # would reject a healthy receipt. What matters is that the exact receipt
    # shown to the PTT caller is the text persisted on its producing journal
    # turn—not speculative provider narration or a second assistant row.
    if expected_assistant_text is not None and assistant_raw_text != expected_assistant_text.strip():
        raise ValueError(
            "producing assistant acknowledgement disagrees with the canonical PTT receipt: "
            f"{assistant_raw_text!r} != {expected_assistant_text!r}"
        )

    try:
        resources = json.loads(str(assistant.get("resources_json", "[]")))
    except json.JSONDecodeError as exc:
        raise ValueError(f"producing turn structured payload is malformed: {exc.msg}") from exc
    if not isinstance(blocks, list) or not isinstance(resources, list):
        raise ValueError("producing turn blocks/resources are not arrays")
    spawns = [block for block in blocks if isinstance(block, dict) and block.get("type") == "agentSpawn"]
    completions = [
        block for block in blocks if isinstance(block, dict) and block.get("type") == "agentCompletion"
    ]
    matching_spawns = [
        block
        for block in spawns
        if block.get("sessionId") == child_session_id and block.get("runId") == child_run_id
    ]
    matching_completions = [
        block
        for block in completions
        if block.get("sessionId") == child_session_id and block.get("runId") == child_run_id
    ]
    if len(spawns) != 1 or len(matching_spawns) != 1 or len(matching_completions) != 1:
        raise ValueError(
            "expected one initial-run agentSpawn and one matching agentCompletion on the producing turn "
            f"(spawn={len(spawns)}, initial_spawn={len(matching_spawns)}, "
            f"initial_completion={len(matching_completions)}, completions={len(completions)})"
        )
    spawn = matching_spawns[0]
    completion = matching_completions[0]
    for label, block in (("spawn", spawn), ("completion", completion)):
        if block.get("sessionId") != child_session_id or block.get("runId") != child_run_id:
            raise ValueError(
                f"{label} block identity does not match accepted child "
                f"(session={block.get('sessionId')!r}, run={block.get('runId')!r})"
            )
    if spawn.get("pillId") != completion.get("pillId"):
        raise ValueError("spawn/completion pill identity changed")
    if completion.get("status") != "completed":
        raise ValueError(f"agentCompletion is not terminal-success: {completion.get('status')!r}")
    completion_run_ids: set[str] = set()
    for continuation_completion in completions:
        continuation_session_id = str(continuation_completion.get("sessionId") or "")
        continuation_pill_id = continuation_completion.get("pillId")
        continuation_run_id = str(continuation_completion.get("runId") or "")
        if continuation_session_id != child_session_id or continuation_pill_id != spawn.get("pillId"):
            raise ValueError("producing turn contains a completion for another child identity")
        if not continuation_run_id:
            raise ValueError("producing turn contains a completion without a run identity")
        if continuation_run_id in completion_run_ids:
            raise ValueError(f"producing turn contains duplicate completion for run {continuation_run_id!r}")
        completion_run_ids.add(continuation_run_id)
    for resource in resources:
        if not isinstance(resource, dict):
            raise ValueError("producing turn resource is not an object")
        resource_run = resource.get("runId")
        if resource_run not in {None, "", *completion_run_ids}:
            raise ValueError(f"producing turn contains an orphan resource for run {resource_run!r}")
    return {
        "messageId": assistant.get("id"),
        "spawnBlockId": spawn.get("id"),
        "completionBlockId": completion.get("id"),
        "pillId": spawn.get("pillId"),
        "sessionId": spawn.get("sessionId"),
        "runId": spawn.get("runId"),
        "resourceIds": sorted(
            str(resource.get("id"))
            for resource in resources
            if isinstance(resource, dict) and resource.get("id")
        ),
    }


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


def classify_restarted_bundle_state(
    state: dict[str, Any],
    expected_bundle: str,
    expected_port: int,
) -> tuple[str, str]:
    """Classify a replacement process snapshot without treating auth restore as terminal."""
    if state.get("ok") is not True:
        return "wait", f"automation state is not ready ({state.get('error', 'missing ok=true')})"
    result = state.get("result")
    if not isinstance(result, dict):
        return "wait", "automation state has no result"

    current_bundle = str(result.get("bundleIdentifier") or "")
    if not current_bundle:
        return "wait", "replacement bundle identity is not ready"
    if current_bundle != expected_bundle:
        return "fail", "automation state belongs to an unexpected bundle identifier"

    current_port = str(result.get("bridgePort") or "")
    if not current_port:
        return "wait", "replacement automation port is not ready"
    if current_port != str(expected_port):
        return "fail", "automation state reports an unexpected bridge port"

    # The replacement listener can bind before Firebase restores the local
    # session. Signed-out/onboarding snapshots from that window are retryable.
    if result.get("isSignedIn") is not True or result.get("hasCompletedOnboarding") is not True:
        return "wait", "replacement process is still restoring signed-in/onboarded state"
    return "ready", "replacement process restored signed-in/onboarded state"


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
        state = bridge_state(self.port)
        classification, detail = classify_restarted_bundle_state(state, self.bundle_id, self.port)
        if classification != "ready":
            raise SystemExit(
                f"automation bridge on port {self.port} does not match ready bundle "
                f"{self.bundle_id}: {detail}"
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
        classification, detail = classify_restarted_bundle_state(ready, self.bundle_id, self.port)
        if classification != "ready":
            raise SystemExit(f"navigate chat did not retain expected bridge identity/readiness: {detail}")

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
        assistant_text = current_turn_assistant_text(snapshot_detail, user_text)
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
        trace_start = capture_trace_cursor()
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

    def coordinator_awareness(
        self,
        *,
        label: str,
        record_failure: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        action = self.bridge_act("coordinator_awareness_snapshot", {"limit": "200"})
        try:
            return action, coordinator_awareness_payload(action)
        except ValueError as exc:
            if record_failure:
                self.fail(f"{label}: owner-scoped coordinator awareness failed: {exc}")
            return action, None

    def wait_for_exact_voice_producing_turn(
        self,
        *,
        child_session_id: str,
        child_run_id: str,
        step_dir: Path,
        artifact_stem: str,
        expected_assistant_text: str | None = None,
        timeout_sec: float = 45,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        deadline = time.monotonic() + timeout_sec
        poll_path = step_dir / f"{artifact_stem}-journal-polls.jsonl"
        last_error = "journal projection unavailable"
        while time.monotonic() < deadline:
            action = self.bridge_act("main_chat_snapshot", {"limit": "100"})
            detail = action.get("result", {}).get("detail", {})
            if not isinstance(detail, dict):
                detail = {}
            try:
                signature = exact_voice_agent_turn_signature(
                    detail,
                    child_session_id=child_session_id,
                    child_run_id=child_run_id,
                    expected_assistant_text=expected_assistant_text,
                )
            except ValueError as exc:
                last_error = str(exc)
                append_text(
                    poll_path,
                    json.dumps({"action": action, "error": last_error}, sort_keys=True, default=str) + "\n",
                )
                time.sleep(0.25)
                continue
            write_json(step_dir / f"{artifact_stem}-journal-action.json", action)
            write_json(step_dir / f"{artifact_stem}-journal-signature.json", signature)
            return action, signature
        self.fail(f"exact voice producing journal turn never converged: {last_error}")
        return None

    def wait_for_agent_lifecycle_convergence(
        self,
        *,
        run_id: str,
        step_dir: Path,
        artifact_stem: str,
        timeout_sec: float = 30,
    ) -> dict[str, Any] | None:
        """Wait for one terminal child to converge into its visible pill + journal block."""
        deadline = time.monotonic() + timeout_sec
        poll_path = step_dir / f"{artifact_stem}-lifecycle-convergence-polls.jsonl"
        last_error = "lifecycle projection unavailable"
        final_action: dict[str, Any] = {}
        while time.monotonic() < deadline:
            action = self.bridge_act(
                "agent_lifecycle_convergence_snapshot",
                {"runIds": run_id},
            )
            final_action = action
            try:
                payload = agent_lifecycle_convergence_payload(action)
                if payload.get("canonicalReadError"):
                    raise ValueError(f"canonical read failed: {payload['canonicalReadError']}")
                if payload.get("missingRequestedRunIds"):
                    raise ValueError(f"requested run missing: {payload['missingRequestedRunIds']}")
                matching = [
                    entry
                    for entry in payload["entries"]
                    if isinstance(entry, dict) and entry.get("runId") == run_id
                ]
                if len(matching) != 1:
                    raise ValueError(f"expected one lifecycle entry for run, found {len(matching)}")
                entry = matching[0]
                if entry.get("canonicalStatus") != "succeeded":
                    raise ValueError(f"canonical child is not succeeded: {entry.get('canonicalStatus')!r}")
                if entry.get("projectedStatus") != "done":
                    raise ValueError(f"visible pill has not converged: {entry.get('projectedStatus')!r}")
                if entry.get("completionMaterialized") is not True:
                    raise ValueError("producing journal turn has no terminal agent completion")
                if entry.get("converged") is not True:
                    raise ValueError("lifecycle entry reports non-converged terminal state")
                write_json(step_dir / f"{artifact_stem}-lifecycle-convergence-action.json", action)
                write_json(step_dir / f"{artifact_stem}-lifecycle-convergence.json", payload)
                return entry
            except ValueError as exc:
                last_error = str(exc)
                append_text(
                    poll_path,
                    json.dumps({"action": action, "error": last_error}, sort_keys=True, default=str) + "\n",
                )
                time.sleep(0.25)
        write_json(step_dir / f"{artifact_stem}-lifecycle-convergence-action.json", final_action)
        self.fail(f"terminal child did not converge into pill and journal: {last_error}")
        return None

    def restart_named_bundle_and_wait(self, step_dir: Path) -> bool:
        before_pid = automation_listener_pid(self.port)
        before_state = bridge_state(self.port)
        write_json(step_dir / "pre-restart-state.json", before_state)
        before_result = before_state.get("result", {})
        if not before_pid or not isinstance(before_result, dict):
            self.fail("cannot prove named-bundle restart without the original listener/state")
            return False
        before_classification, before_detail = classify_restarted_bundle_state(
            before_state, self.bundle_id, self.port
        )
        if before_classification != "ready":
            self.fail(f"cannot prove named-bundle restart from the expected ready bundle: {before_detail}")
            return False
        restart = self.bridge_act("quit_and_reopen")
        write_json(step_dir / "quit-and-reopen-action.json", restart)
        detail = restart.get("result", {}).get("detail", {})
        if restart.get("ok") is False or not isinstance(detail, dict) or detail.get("error"):
            self.fail(f"named-bundle quit-and-reopen failed: {detail.get('error', restart)}")
            return False
        deadline = time.monotonic() + 90
        saw_replacement = False
        last_restart_detail = "replacement process not observed"
        last_restart_state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            current_pid = automation_listener_pid(self.port)
            if current_pid and current_pid != before_pid:
                saw_replacement = True
                state = bridge_state(self.port)
                last_restart_state = state
                classification, last_restart_detail = classify_restarted_bundle_state(
                    state, self.bundle_id, self.port
                )
                if classification == "fail":
                    self.fail(last_restart_detail)
                    return False
                if classification == "ready":
                    write_json(
                        step_dir / "post-restart-state.json",
                        {"beforeListenerPID": before_pid, "afterListenerPID": current_pid, "state": state},
                    )
                    return True
            time.sleep(0.5)
        if saw_replacement:
            write_json(
                step_dir / "restart-wait-timeout.json",
                {
                    "beforeListenerPID": before_pid,
                    "currentListenerPID": automation_listener_pid(self.port),
                    "detail": last_restart_detail,
                    "state": last_restart_state,
                },
            )
            self.fail(
                "quit-and-reopen replacement did not finish auth/onboarding restore "
                f"({last_restart_detail})"
            )
            return False
        self.fail(
            "named bundle did not replace its automation listener after quit-and-reopen "
            f"(before={before_pid!r}, current={automation_listener_pid(self.port)!r})"
        )
        return False

    def wait_for_exact_voice_spawn(
        self,
        baseline: dict[str, Any],
        step_dir: Path,
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]] | None:
        """Wait for one new leaf session and the exact realtime parent run.

        A provider reconnect may redrive a transport turn before any tool effect.
        Parent run cardinality can therefore exceed one, but the later ledger gate
        still requires exactly one successful spawn invocation across those runs.
        """
        baseline_session_ids = awareness_session_ids(baseline)
        baseline_run_ids = awareness_run_ids(baseline)
        baseline_owner_id = str(baseline.get("ownerId") or "")
        deadline = time.monotonic() + (self.args.turn_timeout_ms / 1000.0)
        stable_signature: tuple[tuple[str, ...], tuple[str, ...]] | None = None
        stable_polls = 0
        latest_action: dict[str, Any] = {}
        latest_snapshot: dict[str, Any] | None = None
        latest_children: list[dict[str, Any]] = []
        latest_parent_ids: list[str] = []
        poll_path = step_dir / "post-voice-awareness-polls.jsonl"

        while time.monotonic() < deadline:
            latest_action, snapshot = self.coordinator_awareness(
                label="exact voice spawn poll",
                record_failure=False,
            )
            if snapshot is None:
                append_text(
                    poll_path,
                    json.dumps(
                        {
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": latest_action.get("error", latest_action),
                        },
                        sort_keys=True,
                        default=str,
                    )
                    + "\n",
                )
                time.sleep(0.5)
                continue

            latest_snapshot = snapshot
            if snapshot.get("ownerId") != baseline_owner_id:
                self.fail(
                    "exact voice spawn: coordinator awareness owner changed "
                    f"(baseline={baseline_owner_id!r}, current={snapshot.get('ownerId')!r})"
                )
                break
            latest_children = new_leaf_session_summaries(snapshot, baseline_session_ids)
            latest_parent_ids = sorted(
                set(exact_external_parent_run_ids(snapshot)) - baseline_run_ids
            )
            child_ids = sorted(
                str(awareness_session_parts(summary)[0].get("sessionId") or "")
                for summary in latest_children
            )
            signature = (tuple(child_ids), tuple(latest_parent_ids))
            stable_polls = stable_polls + 1 if signature == stable_signature else 1
            stable_signature = signature
            append_text(
                poll_path,
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "ownerId": snapshot.get("ownerId"),
                        "newLeafSessionIds": child_ids,
                        "exactExternalParentRunIds": latest_parent_ids,
                        "stablePolls": stable_polls,
                    },
                    sort_keys=True,
                )
                + "\n",
            )

            if len(latest_children) > 1:
                self.fail(
                    "exact voice spawn created more than one new leaf session "
                    f"({child_ids})"
                )
                break
            if len(latest_children) == 1 and latest_parent_ids and stable_polls >= 4:
                break
            time.sleep(0.5)

        write_json(step_dir / "post-voice-awareness-action.json", latest_action)
        if latest_snapshot is not None:
            write_json(step_dir / "post-voice-awareness.json", latest_snapshot)
        if latest_snapshot is None:
            self.fail("exact voice spawn: coordinator awareness never returned valid JSON")
            return None
        if len(latest_children) != 1:
            self.fail(
                "exact voice spawn did not produce exactly one new owner-scoped leaf session "
                f"(count={len(latest_children)})"
            )
            return None
        if not latest_parent_ids:
            self.fail("exact voice spawn did not expose an exact-prompt realtime parent run")
            return None

        child_summary = latest_children[0]
        child_session, child_run = awareness_session_parts(child_summary)
        if not child_session.get("sessionId") or not child_run.get("runId"):
            self.fail("exact voice spawn child omitted canonical sessionId/runId")
            return None
        return child_session, child_run, latest_parent_ids

    def wait_for_run_success(
        self,
        *,
        run_id: str,
        expected_session_id: str,
        expected_owner_id: str,
        required_tool: str,
        label: str,
        artifact_stem: str,
        step_dir: Path,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + (self.args.turn_timeout_ms / 1000.0)
        poll_path = step_dir / f"{artifact_stem}-inspection-polls.jsonl"
        final_action: dict[str, Any] = {}
        final_payload: dict[str, Any] = {}
        last_error = "no inspection response"

        while time.monotonic() < deadline:
            action = self.bridge_act("coordinator_inspect_run", {"runId": run_id})
            final_action = action
            try:
                payload = coordinator_run_payload(action)
            except ValueError as exc:
                last_error = str(exc)
                append_text(
                    poll_path,
                    json.dumps(
                        {
                            "at": datetime.now(timezone.utc).isoformat(),
                            "error": last_error,
                        },
                        sort_keys=True,
                    )
                    + "\n",
                )
                time.sleep(0.5)
                continue

            final_payload = payload
            run = payload.get("run", {})
            session = payload.get("session", {})
            status = str(run.get("status") or "unknown")
            invocations = payload.get("toolInvocations", [])
            append_text(
                poll_path,
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "status": status,
                        "attemptCount": len(payload.get("attempts", [])),
                        "toolInvocations": [
                            {
                                "invocationId": invocation.get("invocationId"),
                                "toolName": invocation.get("toolName"),
                                "status": invocation.get("status"),
                                "errorCode": invocation.get("errorCode"),
                            }
                            for invocation in invocations
                            if isinstance(invocation, dict)
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
            )

            identity_errors: list[str] = []
            if run.get("runId") != run_id:
                identity_errors.append(f"runId={run.get('runId')!r}")
            if run.get("sessionId") != expected_session_id:
                identity_errors.append(f"run.sessionId={run.get('sessionId')!r}")
            if session.get("sessionId") != expected_session_id:
                identity_errors.append(f"session.sessionId={session.get('sessionId')!r}")
            if session.get("ownerId") != expected_owner_id:
                identity_errors.append(f"session.ownerId={session.get('ownerId')!r}")
            if identity_errors:
                self.fail(f"{label}: owner/run identity mismatch ({', '.join(identity_errors)})")
                break

            if status not in TERMINAL_RUN_STATUSES:
                time.sleep(0.5)
                continue
            if status != "succeeded":
                self.fail(
                    f"{label}: run terminated as {status} "
                    f"({run.get('errorCode') or run.get('errorMessage') or 'no error detail'})"
                )
                break

            contract_errors = tool_invocation_contract_errors(payload, run_id)
            if contract_errors:
                self.fail(f"{label}: invalid bounded tool ledger: {contract_errors}")
            attempts = [
                attempt
                for attempt in payload.get("attempts", [])
                if isinstance(attempt, dict)
            ]
            if not attempts or attempts[-1].get("status") != "succeeded":
                self.fail(f"{label}: latest attempt is not terminal succeeded")
            pending = [
                invocation
                for invocation in invocations
                if isinstance(invocation, dict)
                and invocation.get("status") in {"prepared", "dispatched"}
            ]
            if pending:
                self.fail(f"{label}: terminal run retained pending tool invocations")
            required = tool_invocations_named(payload, required_tool)
            if not required:
                self.fail(f"{label}: terminal run never invoked {required_tool}")
            rejected = [
                invocation
                for invocation in required
                if invocation.get("status") != "succeeded"
                or invocation.get("errorCode") not in {None, ""}
                or not isinstance(invocation.get("completedAtMs"), int)
            ]
            if rejected:
                self.fail(
                    f"{label}: {required_tool} did not complete successfully: {rejected}"
                )
            completion_count = run_terminal_event_count(payload, run_id, "succeeded")
            if completion_count != 1:
                self.fail(
                    f"{label}: expected one canonical run.succeeded completion event, "
                    f"found {completion_count}"
                )
            break
        else:
            self.fail(f"{label}: timed out waiting for terminal success ({last_error})")

        write_json(step_dir / f"{artifact_stem}-inspection-action.json", final_action)
        write_json(step_dir / f"{artifact_stem}-run.json", final_payload)
        return final_payload

    def wait_for_single_parent_spawn_invocation(
        self,
        *,
        parent_run_ids: list[str],
        expected_owner_id: str,
        step_dir: Path,
    ) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
        """Prove one (and only one) spawn effect across provider redrives."""
        deadline = time.monotonic() + min(30.0, self.args.turn_timeout_ms / 1000.0)
        poll_path = step_dir / "voice-parent-inspection-polls.jsonl"
        final_actions: dict[str, Any] = {}
        final_payloads: dict[str, Any] = {}
        selected: tuple[str, dict[str, Any], dict[str, Any]] | None = None

        while time.monotonic() < deadline:
            spawn_rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
            statuses: dict[str, str] = {}
            for run_id in parent_run_ids:
                action = self.bridge_act("coordinator_inspect_run", {"runId": run_id})
                final_actions[run_id] = action
                try:
                    payload = coordinator_run_payload(action)
                except ValueError as exc:
                    statuses[run_id] = f"inspection_error:{exc}"
                    continue
                final_payloads[run_id] = payload
                run = payload.get("run", {})
                session = payload.get("session", {})
                statuses[run_id] = str(run.get("status") or "unknown")
                if session.get("ownerId") != expected_owner_id:
                    self.fail(
                        "exact voice parent inspection escaped the baseline owner "
                        f"(run={run_id}, owner={session.get('ownerId')!r})"
                    )
                    return None
                contract_errors = tool_invocation_contract_errors(payload, run_id)
                if contract_errors:
                    self.fail(
                        f"exact voice parent {run_id} has invalid bounded tool ledger: "
                        f"{contract_errors}"
                    )
                    return None
                for invocation in tool_invocations_named(payload, "spawn_agent"):
                    spawn_rows.append((run_id, payload, invocation))

            append_text(
                poll_path,
                json.dumps(
                    {
                        "at": datetime.now(timezone.utc).isoformat(),
                        "parentStatuses": statuses,
                        "spawnInvocations": [
                            {
                                "runId": run_id,
                                "invocationId": invocation.get("invocationId"),
                                "status": invocation.get("status"),
                                "errorCode": invocation.get("errorCode"),
                            }
                            for run_id, _, invocation in spawn_rows
                        ],
                    },
                    sort_keys=True,
                )
                + "\n",
            )
            if len(spawn_rows) > 1:
                self.fail(
                    "exact voice request authorized more than one spawn_agent invocation "
                    f"({[(row[0], row[2].get('invocationId')) for row in spawn_rows]})"
                )
                break
            if len(spawn_rows) == 1:
                run_id, payload, invocation = spawn_rows[0]
                run = payload.get("run", {})
                if run.get("status") == "succeeded" and invocation.get("status") == "succeeded":
                    selected = (run_id, payload, invocation)
                    break
                if run.get("status") in TERMINAL_RUN_STATUSES:
                    self.fail(
                        "exact voice spawn authority terminated unsuccessfully "
                        f"(run={run.get('status')}, invocation={invocation.get('status')}, "
                        f"error={invocation.get('errorCode')})"
                    )
                    break
            time.sleep(0.5)

        write_json(step_dir / "voice-parent-inspection-actions.json", final_actions)
        write_json(step_dir / "voice-parent-runs.json", final_payloads)
        if selected is None:
            self.fail("exact voice request did not yield one successful spawn_agent ledger row")
            return None

        run_id, payload, invocation = selected
        if invocation.get("errorCode") not in {None, ""}:
            self.fail(
                f"exact voice spawn invocation retained errorCode={invocation.get('errorCode')!r}"
            )
        if not isinstance(invocation.get("completedAtMs"), int):
            self.fail("exact voice spawn invocation omitted completedAtMs")
        completion_count = run_terminal_event_count(payload, run_id, "succeeded")
        if completion_count != 1:
            self.fail(
                "exact voice parent expected one canonical run.succeeded event, "
                f"found {completion_count}"
            )
        return selected

    def send_and_wait(self, query: str, timeout_ms: int) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
        trace_start = capture_trace_cursor()
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
                snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
                snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
                if current_turn_has_terminal_assistant(snapshot_detail, query):
                    break
            time.sleep(0.25)
        else:
            self.fail(
                "timed out waiting for query-specific terminal assistant row after query: "
                f"{query[:120]}"
            )

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
        trace_start = capture_trace_cursor()
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
                snapshot = self.bridge_act("main_chat_snapshot", {"limit": "80"})
                snapshot_detail = snapshot.get("result", {}).get("detail", snapshot_detail)
                if current_turn_has_terminal_assistant(snapshot_detail, query):
                    break
            time.sleep(0.25)
        else:
            self.fail(
                "timed out waiting for resilience query-specific terminal assistant row after query: "
                f"{query[:120]}"
            )

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
        self.assert_assistant_mentions(
            current_turn_assistant_text(snapshot, typed_query),
            [self.markers["typed"]],
            "typed turn",
        )

        # Step 2 — PTT turn (real hub controller path; transcript forced for determinism).
        # Its request deliberately omits the typed marker, so the PTT provider can
        # satisfy the first clause only from the canonical kernel context.
        ptt_user = (
            "First reply with the exact continuity marker I gave you in typed chat; "
            "it starts with GAUNTLET- and ends in -TYPED. Then remember this new "
            f"push-to-talk marker exactly: {self.markers['ptt']}."
        )
        trace_start = capture_trace_cursor()
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
        if self.markers["typed"] not in assistant_reply:
            self.fail(
                "PTT step 02 failed blind recall of the prior typed marker "
                f"{self.markers['typed']} (reply={assistant_reply[:160]!r})"
            )
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

        # Step 2b — second PTT turn: the marker is absent from the probe, so this
        # proves that the previous PTT input reached the next PTT provider session.
        ptt_recall_query = (
            "In the earlier push-to-talk voice turn I gave you a continuity marker "
            "starting with GAUNTLET- and ending in -PTT. Reply with only that exact marker."
        )
        trace_start = capture_trace_cursor()
        ptt_recall = self.bridge_act(
            "ptt_test_turn",
            {
                "pcm": str(self.pcm_path),
                "timeout": str(max(30, self.args.turn_timeout_ms // 1000)),
                "force_transcript": ptt_recall_query,
                "text_only": "1",
            },
        )
        ptt_recall_detail = ptt_recall.get("result", {}).get("detail", {})
        if ptt_recall.get("ok") is False or ptt_recall_detail.get("error"):
            self.fail(
                "PTT-to-PTT blind recall failed: "
                f"{ptt_recall_detail.get('error', ptt_recall.get('error', ptt_recall))}"
            )
        ptt_recall_reply = str(ptt_recall_detail.get("assistant_reply") or "")
        if self.markers["ptt"] not in ptt_recall_reply:
            self.fail(
                "PTT step 02b failed blind recall of the prior PTT marker "
                f"{self.markers['ptt']} (reply={ptt_recall_reply[:160]!r})"
            )
        self.record_step(
            "02b-ptt-followup",
            "PTT blind recall after PTT",
            user_text=ptt_recall_query,
            action_response=ptt_recall,
            snapshot_detail={},
            traces=read_new_traces(trace_start),
            extra={"assistant_reply": ptt_recall_reply},
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
        assistant = current_turn_assistant_text(snapshot, followup_query)
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

    def run_exact_voice_memory_agent_step(self) -> None:
        """Live regression for #9515: realtime spawn + run-scoped memory tools.

        This intentionally starts at the provider PTT seam rather than invoking
        spawn_agent directly. The durable run ledger, not assistant wording or a
        trace heuristic, proves one spawn and two authorized get_memories effects.
        """
        step_id = "04-exact-voice-memory-agent"
        step_dir = self.run_dir / step_id
        step_dir.mkdir(parents=True, exist_ok=True)

        baseline_action, baseline = self.coordinator_awareness(
            label="exact voice baseline",
        )
        write_json(step_dir / "baseline-awareness-action.json", baseline_action)
        if baseline is None:
            return
        write_json(step_dir / "baseline-awareness.json", baseline)
        baseline_owner_id = str(baseline.get("ownerId") or "")
        baseline_session_ids = awareness_session_ids(baseline)

        step_log_offset = self.log_path.stat().st_size if self.log_path.exists() else 0
        trace_start = capture_trace_cursor()
        ptt = self.bridge_act(
            "ptt_test_turn",
            {
                "pcm": str(self.pcm_path),
                "timeout": str(max(30, self.args.turn_timeout_ms // 1000)),
                "force_transcript": EXACT_VOICE_AGENT_MEMORY_REQUEST,
                "text_only": "1",
            },
        )
        write_json(step_dir / "ptt-action-response.json", ptt)
        ptt_detail = ptt.get("result", {}).get("detail", {})
        if not isinstance(ptt_detail, dict):
            ptt_detail = {}
        write_json(step_dir / "ptt-diagnostics.json", ptt_detail)
        if ptt.get("ok") is False or ptt_detail.get("error"):
            self.fail(
                "exact voice PTT provider path failed: "
                f"{ptt_detail.get('error', ptt.get('error', ptt))}"
            )
            return
        saved_user_text = str(
            ptt_detail.get("saved_user_text")
            or ptt_detail.get("provider_transcript")
            or ""
        ).strip()
        if saved_user_text != EXACT_VOICE_AGENT_MEMORY_REQUEST:
            self.fail(
                "exact voice PTT did not persist the exact acceptance request "
                f"(saved={saved_user_text!r})"
            )
        if not str(ptt_detail.get("provider") or "").strip():
            self.fail("exact voice PTT diagnostics omitted the realtime provider")
        if not str(ptt_detail.get("assistant_reply") or "").strip():
            self.fail("exact voice PTT provider returned no acknowledgement")

        spawned = self.wait_for_exact_voice_spawn(baseline, step_dir)
        if spawned is None:
            return
        child_session, child_run, parent_run_ids = spawned
        child_session_id = str(child_session["sessionId"])
        initial_child_run_id = str(child_run["runId"])

        parent_authority = self.wait_for_single_parent_spawn_invocation(
            parent_run_ids=parent_run_ids,
            expected_owner_id=baseline_owner_id,
            step_dir=step_dir,
        )
        initial_child = self.wait_for_run_success(
            run_id=initial_child_run_id,
            expected_session_id=child_session_id,
            expected_owner_id=baseline_owner_id,
            required_tool="get_memories",
            label="exact voice child",
            artifact_stem="initial-child",
            step_dir=step_dir,
        )
        initial_memory_calls = tool_invocations_named(initial_child, "get_memories")
        producing_before_restart = self.wait_for_exact_voice_producing_turn(
            child_session_id=child_session_id,
            child_run_id=initial_child_run_id,
            step_dir=step_dir,
            artifact_stem="before-restart",
            expected_assistant_text=str(ptt_detail.get("assistant_reply") or "").strip(),
        )
        lifecycle_convergence = self.wait_for_agent_lifecycle_convergence(
            run_id=initial_child_run_id,
            step_dir=step_dir,
            artifact_stem="initial-child",
        )

        continuation = self.bridge_act(
            "coordinator_continue_agent",
            {
                "sessionId": child_session_id,
                "prompt": EXACT_VOICE_AGENT_MEMORY_FOLLOWUP,
                "surfaceKind": "realtime",
            },
        )
        write_json(step_dir / "continuation-action-response.json", continuation)
        continuation_detail = continuation.get("result", {}).get("detail", {})
        if not isinstance(continuation_detail, dict):
            continuation_detail = {}
        continuation_error = str(
            continuation_detail.get("error") or continuation.get("error") or ""
        ).strip()
        continuation_session_id = str(continuation_detail.get("session_id") or "")
        continuation_run_id = str(continuation_detail.get("run_id") or "")
        if continuation.get("ok") is False or continuation_error:
            self.fail(f"same-child continuation failed: {continuation_error or continuation}")
        if continuation_session_id != child_session_id:
            self.fail(
                "same-child continuation changed canonical session "
                f"(expected={child_session_id}, actual={continuation_session_id!r})"
            )
        if not continuation_run_id or continuation_run_id == initial_child_run_id:
            self.fail(
                "same-child continuation did not create one distinct follow-up run "
                f"(initial={initial_child_run_id}, followup={continuation_run_id!r})"
            )

        followup_child: dict[str, Any] = {}
        if continuation_run_id:
            followup_child = self.wait_for_run_success(
                run_id=continuation_run_id,
                expected_session_id=child_session_id,
                expected_owner_id=baseline_owner_id,
                required_tool="get_memories",
                label="same-child memory follow-up",
                artifact_stem="followup-child",
                step_dir=step_dir,
            )
        followup_memory_calls = tool_invocations_named(followup_child, "get_memories")
        successful_memory_invocation_ids = {
            str(invocation.get("invocationId"))
            for invocation in initial_memory_calls + followup_memory_calls
            if invocation.get("status") == "succeeded"
            and invocation.get("errorCode") in {None, ""}
            and invocation.get("invocationId")
        }
        if len(successful_memory_invocation_ids) < 2:
            self.fail(
                "exact voice child authority produced fewer than two distinct successful "
                f"get_memories invocations ({sorted(successful_memory_invocation_ids)})"
            )

        producing_after_restart: tuple[dict[str, Any], dict[str, Any]] | None = None
        if producing_before_restart is not None and self.restart_named_bundle_and_wait(step_dir):
            producing_after_restart = self.wait_for_exact_voice_producing_turn(
                child_session_id=child_session_id,
                child_run_id=initial_child_run_id,
                step_dir=step_dir,
                artifact_stem="after-restart",
                expected_assistant_text=str(ptt_detail.get("assistant_reply") or "").strip(),
                timeout_sec=60,
            )
            if (
                producing_after_restart is not None
                and producing_after_restart[1] != producing_before_restart[1]
            ):
                self.fail(
                    "exact voice producing turn identity/blocks/resources changed across restart "
                    f"(before={producing_before_restart[1]}, after={producing_after_restart[1]})"
                )

        final_awareness_action, final_awareness = self.coordinator_awareness(
            label="exact voice final awareness",
        )
        write_json(step_dir / "final-awareness-action.json", final_awareness_action)
        if final_awareness is not None:
            write_json(step_dir / "final-awareness.json", final_awareness)
            final_leaf_summaries = new_leaf_session_summaries(
                final_awareness,
                baseline_session_ids,
            )
            final_leaf_ids = {
                str(awareness_session_parts(summary)[0].get("sessionId") or "")
                for summary in final_leaf_summaries
            }
            if final_leaf_ids != {child_session_id}:
                self.fail(
                    "exact voice flow did not preserve exactly one new child session "
                    f"(expected={child_session_id}, actual={sorted(final_leaf_ids)})"
                )

        traces, malformed_traces = read_new_trace_diagnostics(trace_start)
        write_json(step_dir / "query-traces.json", traces)
        write_json(step_dir / "malformed-query-trace-jsonl.json", malformed_traces)
        if malformed_traces:
            self.fail(
                "exact voice flow emitted malformed QueryTracer JSONL rows "
                f"({len(malformed_traces)})"
            )

        log_text = ""
        if self.log_path.exists():
            log_text = self.log_path.read_bytes()[step_log_offset:].decode(
                "utf-8",
                errors="replace",
            )
        (step_dir / "acceptance-app-log-excerpt.txt").write_text(log_text, encoding="utf-8")
        structured_evidence = json.dumps(
            {
                "ptt": ptt,
                "parentAuthority": parent_authority,
                "initialChild": initial_child,
                "lifecycleConvergence": lifecycle_convergence,
                "continuation": continuation,
                "followupChild": followup_child,
                "finalAwareness": final_awareness,
                "producingTurnBeforeRestart": (
                    producing_before_restart[1] if producing_before_restart is not None else None
                ),
                "producingTurnAfterRestart": (
                    producing_after_restart[1] if producing_after_restart is not None else None
                ),
            },
            sort_keys=True,
            default=str,
        )
        searchable_evidence = f"{log_text}\n{structured_evidence}".lower()
        forbidden_hits: dict[str, list[str]] = {}
        for pattern in sorted(CONVERGENCE_FORBIDDEN_EVIDENCE_PATTERNS):
            snippets: list[str] = []
            for match in re.finditer(re.escape(pattern), searchable_evidence):
                start = max(0, match.start() - 120)
                end = min(len(searchable_evidence), match.end() + 240)
                snippets.append(searchable_evidence[start:end].replace("\n", " "))
                if len(snippets) >= 5:
                    break
            if snippets:
                forbidden_hits[pattern] = snippets
        write_json(
            step_dir / "zero-legacy-jsonl-tool-routing-evidence.json",
            {
                "forbiddenPatterns": sorted(CONVERGENCE_FORBIDDEN_EVIDENCE_PATTERNS),
                "hits": forbidden_hits,
                "malformedQueryTraceRows": malformed_traces,
                "appLogBytesInspected": len(log_text.encode("utf-8")),
                "coordinatorPayloadsDecoded": 5 + len(parent_run_ids),
            },
        )
        if forbidden_hits:
            self.fail(
                "exact voice convergence evidence contains forbidden legacy/routing/JSONL "
                f"signals: {sorted(forbidden_hits)}"
            )

        parent_run_id = parent_authority[0] if parent_authority is not None else ""
        parent_invocation_id = (
            str(parent_authority[2].get("invocationId") or "")
            if parent_authority is not None
            else ""
        )
        summary = {
            "ownerId": baseline_owner_id,
            "exactVoiceRequest": EXACT_VOICE_AGENT_MEMORY_REQUEST,
            "parentRunIdsObserved": parent_run_ids,
            "authoritativeParentRunId": parent_run_id,
            "spawnInvocationId": parent_invocation_id,
            "newChildSessionCount": 1,
            "childSessionId": child_session_id,
            "initialChildRunId": initial_child_run_id,
            "followupChildRunId": continuation_run_id,
            "followupReusedChildSession": continuation_session_id == child_session_id,
            "initialCompletionEvents": run_terminal_event_count(
                initial_child,
                initial_child_run_id,
                "succeeded",
            ),
            "initialPillConverged": lifecycle_convergence is not None,
            "followupCompletionEvents": run_terminal_event_count(
                followup_child,
                continuation_run_id,
                "succeeded",
            ),
            "successfulGetMemoriesInvocationIds": sorted(successful_memory_invocation_ids),
            "producingTurnBeforeRestart": (
                producing_before_restart[1] if producing_before_restart is not None else None
            ),
            "producingTurnAfterRestart": (
                producing_after_restart[1] if producing_after_restart is not None else None
            ),
            "producingTurnSurvivedRestart": (
                producing_before_restart is not None
                and producing_after_restart is not None
                and producing_before_restart[1] == producing_after_restart[1]
            ),
            "forbiddenEvidenceHits": forbidden_hits,
            "malformedQueryTraceRows": len(malformed_traces),
        }
        write_json(step_dir / "acceptance-summary.json", summary)

        snapshot_action = self.bridge_act("main_chat_snapshot", {"limit": "80"})
        snapshot_detail = snapshot_action.get("result", {}).get("detail", {})
        if not isinstance(snapshot_detail, dict):
            snapshot_detail = {}
        self.record_step(
            step_id,
            "exact PTT agent memory authority and same-child follow-up",
            user_text=EXACT_VOICE_AGENT_MEMORY_REQUEST,
            action_response=ptt,
            snapshot_detail=snapshot_detail,
            traces=traces,
            extra={"acceptance_summary": summary},
        )

    def run_agents_suite(self) -> None:
        self.run_exact_voice_memory_agent_step()

        # Step 4 — background agent spawn
        spawn_query = (
            f"Use spawn_agent now to start a visible background agent. "
            f"Objective: track marker {self.markers['spawn']} and wait silently. "
            "Do not ask follow-up questions."
        )
        trace_start = capture_trace_cursor()
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
            assistant = current_turn_assistant_text(snapshot, spawn_query)
            self.fail(
                "no spawn_agent execution with the objective marker — model refused or "
                f"mis-routed the spawn request (assistant={assistant[:160]!r})"
            )
        else:
            failed_spawns = [
                (tool, error)
                for tool in spawn_tools
                if (error := spawn_tool_acceptance_error(tool.get("output"))) is not None
            ]
            if failed_spawns:
                failed_tool, failure = failed_spawns[0]
                self.fail(
                    f"spawn_agent execution reported failure: {failure}; "
                    f"output={failed_tool.get('output')!r}"
                )

        # Step 5 — status query about spawned agent
        # R8: marker-free probe — the answer must surface the objective marker
        # from tool output or delivered context, not from this question.
        status_query = (
            "What is the status of the background agent you just started? "
            "Use list_agent_sessions if needed. Answer in one sentence and "
            "include the agent's exact objective marker."
        )
        send, snapshot, traces = self.send_and_wait(status_query, self.args.turn_timeout_ms)
        assistant = current_turn_assistant_text(snapshot, status_query)
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
            r"starting|running|working|in progress|started|completed|queued|active|failed|succeeded",
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
            trace_start = capture_trace_cursor()
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
        assistant = current_turn_assistant_text(snapshot, recency_probe)
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
        trace_start = capture_trace_cursor()
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
        traces = wait_for_new_traces(
            trace_start,
            min_count=1,
            timeout_sec=10.0,
            query_text=probe_query,
        )
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
        assistant = current_turn_assistant_text(snapshot, p1_query)
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
        assistant = current_turn_assistant_text(snapshot, p2_query)
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
        assistant = current_turn_assistant_text(snapshot, p3_query)
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

        # P4 — public web: this is deliberately a live contract probe. The
        # Anthropic server-side tool is invisible to the desktop query trace,
        # so require the terminal product outcome (a source URL) and fail on
        # the provider's direct-tool-choice error. This catches a deployed
        # gateway that has an incompatible web_search payload even when the
        # local Rust translation unit test is green.
        p4_query = (
            "Search the public web for the current National Weather Service forecast page "
            "for New York City. Use public web search before answering, then reply with "
            "exactly one full https source URL."
        )
        send, snapshot, traces = self.send_and_wait(
            p4_query,
            min(self.args.turn_timeout_ms, 90_000),
        )
        assistant = current_turn_assistant_text(snapshot, p4_query)
        p4_evidence = "\n".join(
            (
                assistant,
                current_turn_snapshot_text(snapshot, p4_query),
                json.dumps(send, sort_keys=True, default=str),
                "\n".join(flatten_trace_text(trace) for trace in traces_for_query(traces, p4_query)),
            )
        ).lower()
        provider_errors = (
            "tool_choice.name",
            "invalid_request_error",
            "this tool only allows calls from",
            "required public web search is unavailable",
        )
        has_source_url = re.search(r"https://[^\s)]+", assistant, flags=re.IGNORECASE) is not None
        self.record_step(
            "p4-public-web",
            "prompt probe: public-web lookup completes with source evidence",
            user_text=p4_query,
            action_response=send,
            snapshot_detail=snapshot,
            traces=traces,
            extra={
                "provider_error_markers": [
                    marker for marker in provider_errors if marker in p4_evidence
                ],
                "has_source_url": has_source_url,
            },
        )
        matched_errors = [marker for marker in provider_errors if marker in p4_evidence]
        if matched_errors:
            self.fail(
                "P4 public web: gateway rejected the server-side lookup contract "
                f"({matched_errors})"
            )
        elif not assistant:
            self.fail("P4 public web: lookup produced no terminal assistant response")
        elif not has_source_url:
            self.fail(
                "P4 public web: lookup completed without the requested https source URL "
                f"(assistant={assistant[:160]!r})"
            )

    def run_resilience_r3_race_policy(self) -> None:
        """Probe concurrent main-chat send rejection via no-wait + busy-state actions."""
        long_query = (
            f"Resilience race hold {self.run_id}. "
            "Take about twenty seconds to reply with exactly: RACE_HOLD_DONE"
        )
        race_query = f"Resilience race probe {self.run_id}. Reply with exactly: RACE_PROBE_REJECTED"
        # Deterministic busy window (bridge latch) so R3 does not depend on LLM latency.
        hold_busy_ms = "15000"

        fire = self.bridge_act(
            "ask_main_chat_no_wait",
            {"query": long_query, "hold_busy_ms": hold_busy_ms},
        )
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

        # Hold was accepted — always drain before returning so R4 starts idle.
        busy_detail: dict[str, Any] = {}
        race_detail: dict[str, Any] = {}
        wait_detail: dict[str, Any] = {}
        terminal_reason = "generic_chat_error"
        provider_busy_seen = False
        try:
            busy_seen = False
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
                    self.fail(
                        f"R3 race policy: main_chat_busy_state failed: {busy_detail.get('error', busy)}"
                    )
                    return
                if (
                    busy_detail.get("is_sending") == "true"
                    or busy_detail.get("is_streaming") == "true"
                ):
                    provider_busy_seen = True
                if busy_detail.get("busy") == "true":
                    busy_seen = True
                    break
                time.sleep(0.05)
            if not busy_seen:
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    2,
                    "generic_chat_error",
                    {
                        "phase": "busy_poll",
                        "busy_detail": busy_detail,
                        "fire_detail": fire_detail,
                        "note": "hold never became busy (or finished before poll)",
                    },
                )
                self.fail("R3 race policy: main chat never reported busy after no-wait send")
                return
            # Latch alone is not enough — require ChatProvider isSending/isStreaming
            # at least once so R3 is not a pure harness-gate self-test.
            if not provider_busy_seen:
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    2,
                    "generic_chat_error",
                    {
                        "phase": "provider_busy_missing",
                        "busy_detail": busy_detail,
                        "fire_detail": fire_detail,
                        "note": "busy was latch-only; never observed is_sending/is_streaming",
                    },
                )
                self.fail(
                    "R3 race policy: never observed ChatProvider is_sending/is_streaming "
                    "(latch-only busy is insufficient)"
                )
                return

            # Re-check immediately before the race send — models often finish the
            # hold prompt early; accepting a second send while idle is not a race bug.
            # Latch may keep busy=true after provider idle; that is OK for the race
            # window only after provider_busy_seen above.
            pre_race = self.bridge_act("main_chat_busy_state")
            pre_race_detail = (
                pre_race.get("result", {}).get("detail", {}) if isinstance(pre_race, dict) else {}
            )
            if pre_race.get("ok") is False or pre_race_detail.get("error"):
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    3,
                    "generic_chat_error",
                    {"phase": "pre_race_busy", "busy_detail": pre_race_detail},
                )
                self.fail(
                    "R3 race policy: main_chat_busy_state failed before race: "
                    f"{pre_race_detail.get('error', pre_race)}"
                )
                return
            if pre_race_detail.get("busy") != "true":
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    3,
                    "generic_chat_error",
                    {
                        "phase": "hold_completed_early",
                        "busy_detail": busy_detail,
                        "pre_race_detail": pre_race_detail,
                        "fire_detail": fire_detail,
                        "note": "hold turn went idle before concurrent send; race inconclusive",
                    },
                )
                self.fail(
                    "R3 race policy: hold turn completed before concurrent send "
                    "(busy cleared; race inconclusive — retry or lengthen hold)"
                )
                return
            busy_detail = pre_race_detail

            race = self.bridge_act("ask_main_chat_no_wait", {"query": race_query})
            race_detail = race.get("result", {}).get("detail", {}) if isinstance(race, dict) else {}
            if race.get("ok") is False or race_detail.get("error"):
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    4,
                    "generic_chat_error",
                    {"phase": "race", "race_detail": race_detail, "race": race},
                )
                self.fail(
                    f"R3 race policy: concurrent no-wait send errored: {race_detail.get('error', race)}"
                )
                return

            rejected = (
                race_detail.get("accepted") == "false"
                or race_detail.get("busy") == "true"
                or race_detail.get("reason") == "already_sending"
            )
            if not rejected:
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    4,
                    "generic_chat_error",
                    {
                        "phase": "race",
                        "fire_detail": fire_detail,
                        "busy_detail": busy_detail,
                        "race_detail": race_detail,
                        "rejected": False,
                        "provider_busy_seen": provider_busy_seen,
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
                    4,
                    terminal_reason,
                    {
                        "phase": "race",
                        "fire_detail": fire_detail,
                        "busy_detail": busy_detail,
                        "race_detail": race_detail,
                        "rejected": True,
                        "provider_busy_seen": provider_busy_seen,
                    },
                )
        finally:
            # Must use bridge_act so HTTP client timeout tracks turn_timeout_ms
            # (bare bridge_action defaults to 60s and can abort a longer drain).
            wait = self.bridge_act(
                "wait_main_chat_idle",
                {"timeoutMs": str(self.args.turn_timeout_ms), "pollMs": "250"},
            )
            wait_detail = wait.get("result", {}).get("detail", {}) if isinstance(wait, dict) else {}
            drain_ok = (
                wait.get("ok") is not False
                and not wait_detail.get("error")
                and wait_detail.get("idle") == "true"
            )
            if not drain_ok:
                self.record_resilience_diagnostic(
                    "R3-already-running-race-policy",
                    5,
                    "generic_chat_error",
                    {
                        "phase": "drain",
                        "wait_detail": wait_detail,
                        "wait": wait if isinstance(wait, dict) else {"raw": str(wait)},
                        "prior_terminal_reason": terminal_reason,
                    },
                )
                self.fail(
                    "R3 race policy: wait_main_chat_idle did not reach idle before R4 "
                    f"(wait_detail={wait_detail})"
                )
                terminal_reason = "generic_chat_error"
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
                    "provider_busy_seen": provider_busy_seen,
                    "drain_ok": drain_ok,
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
        self.assert_assistant_mentions(
            current_turn_assistant_text(snapshot, r1_query),
            ["RESILIENCE_BRIDGE_READY"],
            "R1 bridge launch",
        )

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
                current_turn_assistant_text(snapshot, query),
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
        trace_start = capture_trace_cursor()
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
        spawn_failures = [
            error
            for tool in spawn_tools
            if (error := spawn_tool_acceptance_error(tool.get("output"))) is not None
        ]
        if spawn_failures:
            self.record_resilience_diagnostic(
                "R4-subagent-launch",
                2,
                "subagent_spawn_rejected",
                {"error": spawn_failures[0]},
            )
            self.fail(f"R4 subagent launch: {spawn_failures[0]}")
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
        assistant = current_turn_assistant_text(snapshot, status_query)
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


def trace_cursor_self_check_failures() -> list[str]:
    """Exercise append, rotation, truncation, and replacement cursor semantics."""
    failures: list[str] = []

    def trace_row(trace_id: str, *, padding: str = "", query_text: str = "") -> str:
        return json.dumps(
            {"trace_id": trace_id, "padding": padding, "query_text": query_text}
        ) + "\n"

    def trace_ids(traces: list[dict[str, Any]]) -> list[str]:
        return [str(trace.get("trace_id", "")) for trace in traces]

    with tempfile.TemporaryDirectory(prefix="omi-trace-cursor-") as temporary_directory:
        active = Path(temporary_directory) / "traces.jsonl"
        backup = active.with_name("traces.1.jsonl")

        active.write_text(trace_row("append-base"), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        with active.open("a", encoding="utf-8") as handle:
            handle.write(trace_row("append-new"))
        append_ids = trace_ids(read_new_traces(cursor, active))
        if append_ids != ["append-new"]:
            failures.append(f"append expected ['append-new'], got {append_ids}")

        complete_prefix = trace_row("partial-base")
        active.write_text(complete_prefix + '{"trace_id":"partial', encoding="utf-8")
        cursor = capture_trace_cursor(active)
        if cursor.offset != len(complete_prefix.encode("utf-8")):
            failures.append("partial append cursor did not stop at the last complete newline")
        with active.open("a", encoding="utf-8") as handle:
            handle.write('","padding":"","query_text":""}\n')
        partial_ids = trace_ids(read_new_traces(cursor, active))
        if partial_ids != ["partial"]:
            failures.append(f"partial append expected ['partial'], got {partial_ids}")

        active.write_text(trace_row("rotate-base"), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        with active.open("a", encoding="utf-8") as handle:
            handle.write(trace_row("before-rotate"))
        active.replace(backup)
        active.write_text(trace_row("after-rotate") + "{malformed\n", encoding="utf-8")
        rotated_traces, malformed = read_new_trace_diagnostics(cursor, active)
        rotated_ids = trace_ids(rotated_traces)
        if rotated_ids != ["before-rotate", "after-rotate"]:
            failures.append(
                "rotation expected ['before-rotate', 'after-rotate'], "
                f"got {rotated_ids}"
            )
        if len(malformed) != 1 or malformed[0].get("source") != active.name:
            failures.append(f"rotation malformed diagnostics lost source identity: {malformed}")

        backup.unlink()
        active.write_text(trace_row("truncate-base", padding="x" * 512), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        with active.open("r+b") as handle:
            handle.seek(0)
            handle.truncate()
            handle.write(trace_row("after-truncate").encode("utf-8"))
        truncated_ids = trace_ids(read_new_traces(cursor, active))
        if truncated_ids != ["after-truncate"]:
            failures.append(f"truncation expected ['after-truncate'], got {truncated_ids}")

        active.write_text(trace_row("regrow-base", padding="x" * 512), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        original_inode = active.stat().st_ino
        regrown_rows = "".join(
            trace_row(f"after-regrow-{index}", padding="y" * 256)
            for index in range(1, 4)
        )
        with active.open("r+b") as handle:
            handle.seek(0)
            handle.truncate()
            handle.write(regrown_rows.encode("utf-8"))
        if active.stat().st_ino != original_inode or active.stat().st_size <= cursor.offset:
            failures.append("truncate-regrow fixture did not preserve inode and exceed old offset")
        regrown_ids = trace_ids(read_new_traces(cursor, active))
        expected_regrown_ids = ["after-regrow-1", "after-regrow-2", "after-regrow-3"]
        if regrown_ids != expected_regrown_ids:
            failures.append(
                f"truncate-regrow expected {expected_regrown_ids}, got {regrown_ids}"
            )

        active.write_text(trace_row("identity-base"), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        replacement = active.with_name("replacement.jsonl")
        replacement.write_text(trace_row("after-identity-change"), encoding="utf-8")
        os.replace(replacement, active)
        replacement_ids = trace_ids(read_new_traces(cursor, active))
        if replacement_ids != ["after-identity-change"]:
            failures.append(
                "identity change expected ['after-identity-change'], "
                f"got {replacement_ids}"
            )

        active.write_text(trace_row("query-base"), encoding="utf-8")
        cursor = capture_trace_cursor(active)
        with active.open("a", encoding="utf-8") as handle:
            handle.write(trace_row("unrelated", query_text="other query"))
            handle.write(trace_row("exact", query_text="owner probe"))
        exact_ids = trace_ids(
            wait_for_new_traces(
                cursor,
                timeout_sec=0,
                query_text="owner probe",
                trace_log=active,
            )
        )
        if exact_ids != ["exact"]:
            failures.append(f"exact-query wait expected ['exact'], got {exact_ids}")

    return failures


def owner_trace_gate_self_check_failures(driver_source: str) -> list[str]:
    tree = ast.parse(driver_source)
    runner = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GauntletRunner"),
        None,
    )
    owner_suite = next(
        (
            node
            for node in (runner.body if runner is not None else [])
            if isinstance(node, ast.FunctionDef) and node.name == "run_owner_suite"
        ),
        None,
    )
    if owner_suite is None:
        return ["run_owner_suite missing"]
    waits = [
        node
        for node in ast.walk(owner_suite)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "wait_for_new_traces"
    ]
    has_exact_query_gate = any(
        any(
            keyword.arg == "query_text"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "probe_query"
            for keyword in call.keywords
        )
        for call in waits
    )
    return [] if has_exact_query_gate else ["owner probe does not wait on query_text=probe_query"]


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
        "agent_lifecycle_convergence_snapshot",
        "coordinator_continue_agent",
        "coordinator_inspect_run",
        "quit_and_reopen",
        "swap_test_owner",
        "restore_test_owner",
        "clear_owner_surface_state",
        "kernel_turn_tail",
        "ptt_turn_snapshot",
        "ptt_manager_turn",
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
    enveloped_health = {"ok": True, "result": {"logFilePath": "/private/tmp/omi-gauntlet.log"}}
    if health_log_path(enveloped_health) != "/private/tmp/omi-gauntlet.log":
        print("self-check failed: health log path must read the standard result envelope", file=sys.stderr)
        return 1
    legacy_health = {"ok": True, "logFilePath": "/private/tmp/omi-gauntlet.log"}
    if health_log_path(legacy_health) != "/private/tmp/omi-gauntlet.log":
        print("self-check failed: health log path must preserve legacy top-level compatibility", file=sys.stderr)
        return 1
    trace_cursor_failures = trace_cursor_self_check_failures()
    if trace_cursor_failures:
        print(
            f"self-check failed: rotation-aware trace cursor {trace_cursor_failures}",
            file=sys.stderr,
        )
        return 1
    source = (DESKTOP_DIR / "Desktop/Sources/Providers/ChatProvider.swift").read_text(encoding="utf-8")
    if "resetSessionStateForAuthChange()" not in source:
        print(
            "self-check failed: ChatProvider must reset projected session state on auth change",
            file=sys.stderr,
        )
        return 1
    if "clearOwnerState()" in source:
        print(
            "self-check failed: RuntimeOwnerIdentity must remain the exclusive owner revoker",
            file=sys.stderr,
        )
        return 1
    driver_source = (SCRIPT_DIR / "agent-continuity-gauntlet-lib.py").read_text(encoding="utf-8")
    owner_trace_gate_failures = owner_trace_gate_self_check_failures(driver_source)
    if owner_trace_gate_failures:
        print(
            f"self-check failed: owner trace acceptance {owner_trace_gate_failures}",
            file=sys.stderr,
        )
        return 1
    missing_auth_checks = bridge_auth_self_check_failures(driver_source)
    if missing_auth_checks:
        print(f"self-check failed: bridge auth wiring missing {missing_auth_checks}", file=sys.stderr)
        return 1
    missing_driver_checks = resilience_driver_self_check_failures(driver_source)
    if missing_driver_checks:
        print(f"self-check failed: resilience suite wiring missing {missing_driver_checks}", file=sys.stderr)
        return 1
    missing_exact_voice_checks = exact_voice_acceptance_self_check_failures(driver_source)
    if missing_exact_voice_checks:
        print(
            "self-check failed: exact voice acceptance wiring missing "
            f"{missing_exact_voice_checks}",
            file=sys.stderr,
        )
        return 1
    restart_bundle = "com.omi.omi-gauntlet"
    restart_transitional = {
        "ok": True,
        "result": {
            "bundleIdentifier": "com.omi.omi-gauntlet",
            "bridgePort": 47777,
            "isSignedIn": False,
            "hasCompletedOnboarding": True,
        },
    }
    restart_ready = {
        "ok": True,
        "result": {
            "bundleIdentifier": "com.omi.omi-gauntlet",
            "bridgePort": 47777,
            "isSignedIn": True,
            "hasCompletedOnboarding": True,
        },
    }
    if classify_restarted_bundle_state(restart_transitional, restart_bundle, 47777)[0] != "wait":
        print("self-check failed: transitional restart auth state must remain retryable", file=sys.stderr)
        return 1
    if classify_restarted_bundle_state(restart_ready, restart_bundle, 47777)[0] != "ready":
        print("self-check failed: restored restart auth state must become ready", file=sys.stderr)
        return 1
    restart_wrong_bundle = {"ok": True, "result": {**restart_ready["result"], "bundleIdentifier": "com.omi.other"}}
    if classify_restarted_bundle_state(restart_wrong_bundle, restart_bundle, 47777)[0] != "fail":
        print("self-check failed: replacement bundle mismatch must remain terminal", file=sys.stderr)
        return 1
    restart_wrong_port = {"ok": True, "result": {**restart_ready["result"], "bridgePort": 47778}}
    if classify_restarted_bundle_state(restart_wrong_port, restart_bundle, 47777)[0] != "fail":
        print("self-check failed: replacement automation port mismatch must remain terminal", file=sys.stderr)
        return 1
    restart_missing_ok = {"result": restart_ready["result"]}
    if classify_restarted_bundle_state(restart_missing_ok, restart_bundle, 47777)[0] != "wait":
        print("self-check failed: replacement state without ok=true must remain retryable", file=sys.stderr)
        return 1
    spawn_acceptance_failures = spawn_acceptance_self_check_failures(driver_source)
    if spawn_acceptance_failures:
        print(
            f"self-check failed: spawn acceptance classification {spawn_acceptance_failures}",
            file=sys.stderr,
        )
        return 1
    stale_turn_messages = [
        {"role": "user", "text": "old query", "streaming": "false"},
        {"role": "assistant", "text": "old answer", "streaming": "false"},
        {"role": "user", "text": "new query", "streaming": "false"},
    ]
    stale_turn_snapshot = {"messages_json": json.dumps(stale_turn_messages)}
    if (
        current_turn_assistant_text(stale_turn_snapshot, "new query")
        or current_turn_has_terminal_assistant(stale_turn_snapshot, "new query")
    ):
        print(
            "self-check failed: query-specific evidence inherited a prior assistant turn",
            file=sys.stderr,
        )
        return 1
    stale_turn_messages.append(
        {"role": "assistant", "text": "", "streaming": "false", "status": "failed"}
    )
    terminal_failure_snapshot = {"messages_json": json.dumps(stale_turn_messages)}
    if not current_turn_has_terminal_assistant(terminal_failure_snapshot, "new query"):
        print(
            "self-check failed: query-specific wait did not recognize an empty terminal row",
            file=sys.stderr,
        )
        return 1
    interleaved_turn_snapshot = {
        "messages_json": json.dumps(
            [
                {"role": "user", "text": "first query", "streaming": "false"},
                {"role": "user", "text": "second query", "streaming": "false"},
                {"role": "assistant", "text": "second answer", "streaming": "false"},
            ]
        )
    }
    if current_turn_has_terminal_assistant(interleaved_turn_snapshot, "first query"):
        print(
            "self-check failed: query-specific wait inherited a later user's assistant turn",
            file=sys.stderr,
        )
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
        "(R3 race actions + resilience wiring + exact voice authority + "
        "query-specific terminal evidence + rotation-aware trace cursor + "
        "INV-6 hermetic contract gates + owner-switch)"
    )
    return 0


def spawn_acceptance_self_check_failures(driver_source: str) -> list[str]:
    failures: list[str] = []
    tree = ast.parse(driver_source)
    runner = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GauntletRunner"),
        None,
    )
    methods = {
        node.name: node
        for node in (runner.body if runner is not None else [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method_name in ("run_agents_suite", "run_resilience_suite"):
        if not method_calls(methods.get(method_name), "spawn_tool_acceptance_error"):
            failures.append(f"{method_name} uses structured spawn acceptance")
    accepted = json.dumps(
        {
            "ok": True,
            "requestedAgentCount": 1,
            "agents": [
                {
                    "run": {
                        "status": "queued",
                        "errorCode": None,
                        "errorMessage": None,
                        "input": {"prompt": "track a failed-build marker safely"},
                    },
                    "delegation": {"status": "running"},
                }
            ],
        }
    )
    if spawn_tool_acceptance_error(accepted) is not None:
        failures.append("ok=true queued delegation is accepted despite nested error keys")
    starting = json.dumps(
        {"ok": True, "requestedAgentCount": 1, "agents": [{"run": {"status": "starting"}}]}
    )
    if spawn_tool_acceptance_error(starting) is not None:
        failures.append("ok=true starting child is accepted as an admitted asynchronous spawn")
    rejected = json.dumps(
        {"ok": False, "error": {"code": "spawn_denied", "message": "denied by policy"}}
    )
    if spawn_tool_acceptance_error(rejected) is None:
        failures.append("ok=false response is rejected")
    failed_child = json.dumps(
        {
            "ok": True,
            "requestedAgentCount": 1,
            "agents": [{"run": {"status": "failed"}}],
        }
    )
    if spawn_tool_acceptance_error(failed_child) is None:
        failures.append("non-accepted child run status is rejected")
    if spawn_tool_acceptance_error("not-json") is None:
        failures.append("malformed tool output is rejected")
    return failures


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
        "RuntimeOwnerIdentityTests",
    ]
    for class_name in required_filter_classes:
        if class_name not in harness:
            failures.append(f"agent-logic-harness filter includes {class_name}")

    projection = (tests_dir / "KernelTurnRecordedProjectionTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testRejectedJournalExchangeNeverCreatesAVisibleOrphan(",
        "func testJournalAdmissionPublishesImmediateProjectionWithOneStableIdentity(",
        "func testJournalProjectionUpsertsMutationByCanonicalTurnID(",
        "func testJournalChangedHandlerIsReplaceOnly(",
        "func testAgentCompletionEnrichesProducingSpawnTurnIdempotently(",
        "func testIdenticalTextWithDistinctTurnIDsRemainsDistinct(",
        "func testStructuredBlocksResourcesAndContinuityMetadataSurviveProjection(",
    ):
        if needle not in projection:
            failures.append(f"KernelTurnRecordedProjectionTests.{needle.split('(')[0].removeprefix('func ')}")

    timeline = (tests_dir / "ChatTimelineContinuityTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testHydratePreferencePrefersRunThenSessionThenPill(",
        "func testFindPillMatchesByHydratePreferenceOrder(",
        "func testAgentCompletionBlockExposesOpenRefAndStaysVisible(",
        "func testChatSelectionDoesNotWrapStackChromeInSelectionOverlay(",
        "func testAgentPreviewTextPrefersPromptOverOutput(",
        "func testAgentCompletionCardsUsePromptPreviewHelper(",
        "func testFloatingResourceStripsBindPerMessageNotProviderWide(",
        "func testForbiddenContinuityPatternsAbsentFromWritePath(",
    ):
        if needle not in timeline:
            failures.append(f"ChatTimelineContinuityTests.{needle.split('(')[0].removeprefix('func ')}")

    floating_state = (tests_dir / "FloatingControlBarStateTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testViewportDerivesCurrentAnswerAndHistoryFromProviderMessages(",
        "func testCanRestoreUsesViewportAnchorsAndActivityWindow(",
        "func testViewportDisplayResourcesOnlyFromAnchoredMessageIds(",
        "chatViewport",
    ):
        if needle not in floating_state:
            label = needle.split("(")[0].removeprefix("func ") if needle.startswith("func ") else needle
            failures.append(f"FloatingControlBarStateTests covers {label}")

    owner_identity = (tests_dir / "RuntimeOwnerIdentityTests.swift").read_text(encoding="utf-8")
    for needle in (
        "func testOverrideDoesNotRewriteAuthUserIdOrTokens(",
        "func testSwapPathSourceNeverWritesAuthUserId(",
    ):
        if needle not in owner_identity:
            failures.append(f"RuntimeOwnerIdentityTests.{needle.split('(')[0].removeprefix('func ')}")

    # Forbidden-pattern tripwires must stay present in hermetic coverage.
    if "suppressNextRecordedTurn" not in timeline:
        failures.append("ChatTimelineContinuityTests forbids suppressNextRecordedTurn")
    if "setTurnRecordedHandler" not in timeline:
        failures.append("ChatTimelineContinuityTests forbids setTurnRecordedHandler")
    if "@Published var chatHistory" not in timeline:
        failures.append("ChatTimelineContinuityTests forbids @Published var chatHistory")

    return failures


def exact_voice_acceptance_self_check_failures(driver_source: str) -> list[str]:
    """Static wiring plus a hermetic parser/ledger fixture for the live #9515 gate."""
    failures: list[str] = []
    tree = ast.parse(driver_source)
    runner = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GauntletRunner"
        ),
        None,
    )
    methods = {
        node.name: node
        for node in (runner.body if runner is not None else [])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    exact = methods.get("run_exact_voice_memory_agent_step")
    agents = methods.get("run_agents_suite")
    for method_name in (
        "run_exact_voice_memory_agent_step",
        "wait_for_exact_voice_spawn",
        "wait_for_run_success",
        "wait_for_single_parent_spawn_invocation",
        "wait_for_exact_voice_producing_turn",
        "wait_for_agent_lifecycle_convergence",
        "restart_named_bundle_and_wait",
    ):
        if method_name not in methods:
            failures.append(f"GauntletRunner.{method_name}")
    if not method_calls(agents, "run_exact_voice_memory_agent_step"):
        failures.append("agents suite dispatches exact voice acceptance")
    for literal in (
        "ptt_test_turn",
        "coordinator_awareness_snapshot",
        "agent_lifecycle_convergence_snapshot",
        "coordinator_continue_agent",
        "get_memories",
        "zero-legacy-jsonl-tool-routing-evidence.json",
        "coordinator_inspect_run",
        "quit_and_reopen",
        "spawn_agent",
        "run.succeeded",
        "unrouted_tool_call",
        "malformed jsonl",
        "legacy_path_invoked",
        "agentSpawn",
        "agentCompletion",
        "producingTurnSurvivedRestart",
    ):
        if literal not in driver_source:
            failures.append(f"exact voice acceptance gates {literal}")
    if exact is None:
        failures.append("exact voice acceptance method parses")
    if EXACT_VOICE_AGENT_MEMORY_REQUEST not in driver_source:
        failures.append("exact issue #9515 voice request")

    sample_snapshot = {
        "messages_json": json.dumps(
            [
                {
                    "id": "stale-user",
                    "role": "user",
                    "text": EXACT_VOICE_AGENT_MEMORY_REQUEST,
                    "raw_text": EXACT_VOICE_AGENT_MEMORY_REQUEST,
                },
                {
                    "id": "stale-assistant",
                    "role": "assistant",
                    "text": "I started a background agent for that.",
                    "raw_text": "I started a background agent for that.",
                    "content_blocks_json": json.dumps(
                        [
                            {
                                "type": "agentSpawn",
                                "id": "stale-spawn",
                                "pillId": "00000000-0000-0000-0000-000000000950",
                                "sessionId": "stale-child-session",
                                "runId": "stale-child-run",
                            },
                            {
                                "type": "agentCompletion",
                                "id": "stale-completion",
                                "pillId": "00000000-0000-0000-0000-000000000950",
                                "sessionId": "stale-child-session",
                                "runId": "stale-child-run",
                                "status": "completed",
                            },
                        ]
                    ),
                    "resources_json": "[]",
                },
                {
                    "id": "user-1",
                    "role": "user",
                    "text": EXACT_VOICE_AGENT_MEMORY_REQUEST,
                    "raw_text": EXACT_VOICE_AGENT_MEMORY_REQUEST,
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "text": "I started a background agent for that.",
                    "raw_text": "I started a background agent for that.",
                    "content_blocks_json": json.dumps(
                        [
                            {
                                "type": "agentSpawn",
                                "id": "spawn-1",
                                "pillId": "00000000-0000-0000-0000-000000000951",
                                "sessionId": "child-session",
                                "runId": "child-run",
                            },
                            {
                                "type": "agentCompletion",
                                "id": "completion-1",
                                "pillId": "00000000-0000-0000-0000-000000000951",
                                "sessionId": "child-session",
                                "runId": "child-run",
                                "status": "completed",
                            },
                            {
                                "type": "agentCompletion",
                                "id": "continuation-completion-1",
                                "pillId": "00000000-0000-0000-0000-000000000951",
                                "sessionId": "child-session",
                                "runId": "continued-child-run",
                                "status": "completed",
                            },
                        ]
                    ),
                    "resources_json": "[]",
                },
            ]
        )
    }
    try:
        sample_signature = exact_voice_agent_turn_signature(
            sample_snapshot,
            child_session_id="child-session",
            child_run_id="child-run",
        )
    except ValueError as exc:
        failures.append(f"exact voice journal fixture: {exc}")
    else:
        if sample_signature.get("messageId") != "assistant-1":
            failures.append("exact voice journal fixture preserves producing message identity")

    sample_awareness = {
        "ok": True,
        "result": {
            "detail": {
                "snapshot": json.dumps(
                    {
                        "ok": True,
                        "snapshot": {
                            "ownerId": "owner-a",
                            "sessions": [],
                            "runs": [],
                        },
                    }
                )
            }
        },
    }
    try:
        parsed_awareness = coordinator_awareness_payload(sample_awareness)
    except ValueError as exc:
        failures.append(f"awareness embedded JSON parser: {exc}")
    else:
        if parsed_awareness.get("ownerId") != "owner-a":
            failures.append("awareness embedded JSON parser preserves owner")

    sample_invocation = {
        "invocationId": "inv-1",
        "runId": "run-1",
        "attemptId": "attempt-1",
        "toolName": "get_memories",
        "status": "succeeded",
        "errorCode": None,
        "preparedAtMs": 1,
        "dispatchedAtMs": 2,
        "completedAtMs": 3,
        "updatedAtMs": 3,
    }
    sample_run = {
        "attempts": [{"attemptId": "attempt-1", "status": "succeeded"}],
        "toolInvocations": [sample_invocation],
    }
    contract_errors = tool_invocation_contract_errors(sample_run, "run-1")
    if contract_errors:
        failures.append(f"bounded invocation parser fixture: {contract_errors}")
    leaked_run = {
        **sample_run,
        "toolInvocations": [{**sample_invocation, "result": "private memory output"}],
    }
    if not tool_invocation_contract_errors(leaked_run, "run-1"):
        failures.append("bounded invocation parser rejects raw tool results")
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
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    if "AutomationTokenError" not in classes:
        failures.append("AutomationTokenError class")
    token_fn = funcs.get("automation_token")
    if token_fn is None:
        failures.append("automation_token helper")
    else:
        if not method_contains_string(token_fn, "OMI_AUTOMATION_TOKEN"):
            failures.append("automation_token reads OMI_AUTOMATION_TOKEN")
        if not method_contains_string(token_fn, "omi-automation-"):
            failures.append("automation_token reads omi-automation-{port}.token")
        if not method_references_name(token_fn, "FileNotFoundError"):
            failures.append("automation_token treats missing file as optional")
        if not method_references_name(token_fn, "AutomationTokenError"):
            failures.append("automation_token fails closed on unreadable token")
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
    if not method_contains_string_prefix(bridge, "automation_token_unreadable"):
        failures.append("bridge_request fails closed on unreadable token")
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
    else:
        r3 = methods.get("run_resilience_r3_race_policy")
        if not method_contains_string(r3, "hold_busy_ms"):
            failures.append("run_resilience_r3_race_policy arms hold_busy_ms latch")
        if not method_contains_string(r3, "provider_busy_missing"):
            failures.append("run_resilience_r3_race_policy requires provider is_sending/is_streaming")
        if not method_contains_string(r3, "hold_completed_early"):
            failures.append("run_resilience_r3_race_policy handles hold_completed_early")
        if not method_contains_string(r3, "drain"):
            failures.append("run_resilience_r3_race_policy asserts wait_main_chat_idle drain")
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


def method_contains_string_prefix(node: ast.AST | None, prefix: str) -> bool:
    return node is not None and any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and child.value.startswith(prefix)
        for child in ast.walk(node)
    )


def method_references_name(node: ast.AST | None, name: str) -> bool:
    return node is not None and any(
        isinstance(child, ast.Name) and child.id == name
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
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--turn-timeout-ms", type=int, default=180_000)
    parser.add_argument(
        "--suite",
        default="core",
        help=(
            "Comma-separated suites: continuity (steps 1-3, includes PTT), agents "
            "(exact #9515 voice-memory authority plus steps 4-5), "
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
    args.log_path = resolve_active_log_path(args.port, args.log_path)
    return GauntletRunner(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
