#!/usr/bin/env python3
"""Validate or collect PTT/realtime/chat stress diagnostics as JSONL.

This harness is safe by default: offline validation only reads JSONL, and live
mode only talks to a caller-supplied non-production automation bridge URL. It
does not launch, restart, kill, or discover any Omi app bundle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCENARIOS = {"ptt_voiced", "ptt_silent", "chat_bridge", "subagent_launch"}
TERMINAL_REASONS = {
    "ptt_voiced_success",
    "ptt_silent_rejected",
    "chat_bridge_success",
    "subagent_launch_success",
    "too_short_tap",
    "audio_frames_missing",
    "silent_audio",
    "realtime_token_mint_failure",
    "provider_fallback",
    "bridge_launch_failure",
    "response_already_running",
}
FORBIDDEN_TERMINAL_REASONS = {
    "too_short_tap",
    "audio_frames_missing",
    "silent_audio",
    "realtime_token_mint_failure",
    "bridge_launch_failure",
    "response_already_running",
}
ACTION_BY_SCENARIO = {
    "ptt_voiced": "stress_ptt_voiced",
    "ptt_silent": "stress_ptt_silent",
    "chat_bridge": "stress_chat_bridge",
    "subagent_launch": "stress_subagent_launch",
}
SUCCESS_REASON_BY_SCENARIO = {
    "ptt_voiced": "ptt_voiced_success",
    "ptt_silent": "ptt_silent_rejected",
    "chat_bridge": "chat_bridge_success",
    "subagent_launch": "subagent_launch_success",
}


class StressValidationError(Exception):
    pass


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StressValidationError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        validate_event(event, f"{path}:{line_number}")
        events.append(event)
    return events


def validate_event(event: dict[str, Any], where: str) -> None:
    for key in ("run_id", "iteration", "scenario", "terminal_reason", "timestamp"):
        if key not in event:
            raise StressValidationError(f"{where}: missing required field {key}")
    if event["scenario"] not in SCENARIOS:
        raise StressValidationError(f"{where}: unknown scenario {event['scenario']!r}")
    if event["terminal_reason"] not in TERMINAL_REASONS:
        raise StressValidationError(f"{where}: unknown terminal_reason {event['terminal_reason']!r}")
    if not isinstance(event["iteration"], int) or event["iteration"] < 1:
        raise StressValidationError(f"{where}: iteration must be a positive integer")
    if "duration_ms" in event and event["duration_ms"] is not None:
        if not isinstance(event["duration_ms"], int) or event["duration_ms"] < 0:
            raise StressValidationError(f"{where}: duration_ms must be a non-negative integer")
    if "details" in event and not isinstance(event["details"], dict):
        raise StressValidationError(f"{where}: details must be an object when present")


def summarize(events: list[dict[str, Any]], required_scenarios: list[str] | None = None) -> dict[str, Any]:
    terminal_counts = Counter(event["terminal_reason"] for event in events)
    scenario_counts = Counter(event["scenario"] for event in events)
    forbidden = sorted(reason for reason in FORBIDDEN_TERMINAL_REASONS if terminal_counts[reason] > 0)
    missing_required = sorted(
        scenario for scenario in set(required_scenarios or []) if scenario_counts[scenario] < 1
    )
    return {
        "total_events": len(events),
        "passed_release_gate": bool(events) and not forbidden and not missing_required,
        "terminal_reason_counts": dict(sorted(terminal_counts.items())),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "forbidden_terminal_reasons": forbidden,
        "missing_required_scenarios": missing_required,
    }


def request_json(base_url: str, token: str | None, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def terminal_from_bridge_response(scenario: str, payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True).lower()
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
    explicit = detail.get("terminal_reason") or result.get("terminal_reason") or payload.get("terminal_reason")
    if explicit in TERMINAL_REASONS:
        return explicit
    if payload.get("ok") is False or detail.get("error") or payload.get("error"):
        if "already running" in text or "stuck run" in text or "response_already_running" in text:
            return "response_already_running"
        if "realtime_token_mint_failure" in text or "token mint" in text:
            return "realtime_token_mint_failure"
        return "bridge_launch_failure"
    if "already running" in text or "stuck run" in text or "response_already_running" in text:
        return "response_already_running"
    if "realtime_token_mint_failure" in text or "token mint" in text:
        return "realtime_token_mint_failure"
    if "provider_fallback" in text or "fallback" in text:
        return "provider_fallback"
    if explicit is not None:
        return "bridge_launch_failure"
    return SUCCESS_REASON_BY_SCENARIO[scenario]


def is_loopback_url(raw_url: str) -> bool:
    parsed = urllib.parse.urlparse(raw_url)
    hostname = parsed.hostname
    if hostname is None:
        return False
    if hostname == "localhost" or hostname == "::1":
        return True
    return hostname.startswith("127.")


def collect_from_bridge(base_url: str, token: str | None, scenarios: list[str], iterations: int) -> list[dict[str, Any]]:
    run_id = str(uuid.uuid4())
    events: list[dict[str, Any]] = []
    try:
        request_json(base_url, token=None, method="GET", path="/health")
        actions_payload = request_json(base_url, token=token, method="GET", path="/actions")
        action_names = {
            item.get("name")
            for item in actions_payload.get("result", [])
            if isinstance(item, dict)
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        for iteration in range(1, iterations + 1):
            for scenario in scenarios:
                events.append(make_event(run_id, iteration, scenario, "bridge_launch_failure", details={"error": str(exc)}))
        return events

    for iteration in range(1, iterations + 1):
        for scenario in scenarios:
            started = time.monotonic()
            action = ACTION_BY_SCENARIO[scenario]
            try:
                if action not in action_names:
                    raise StressValidationError(f"automation action {action!r} is not registered")
                payload = request_json(base_url, token=token, method="POST", path="/action", body={"name": action})
                reason = terminal_from_bridge_response(scenario, payload)
                events.append(
                    make_event(
                        run_id,
                        iteration,
                        scenario,
                        reason,
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                )
            except (OSError, urllib.error.URLError, json.JSONDecodeError, StressValidationError) as exc:
                events.append(
                    make_event(
                        run_id,
                        iteration,
                        scenario,
                        "bridge_launch_failure",
                        duration_ms=int((time.monotonic() - started) * 1000),
                        details={"error": str(exc)},
                    )
                )
    return events


def make_event(
    run_id: str,
    iteration: int,
    scenario: str,
    terminal_reason: str,
    duration_ms: int | None = None,
    details: dict[str, str] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "run_id": run_id,
        "iteration": iteration,
        "scenario": scenario,
        "terminal_reason": terminal_reason,
        "timestamp": timestamp(),
        "details": details or {},
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    validate_event(event, "generated")
    return event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", type=Path, help="Validate an exported/local stress JSONL file")
    parser.add_argument("--base-url", help="Optional already-running non-production automation bridge URL")
    parser.add_argument("--token", help="Automation bridge bearer token; defaults to OMI_AUTOMATION_TOKEN")
    parser.add_argument(
        "--allow-remote-token",
        action="store_true",
        help="Allow sending an automation token to a non-loopback --base-url",
    )
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help="Scenario to run; repeatable. Defaults to ptt_voiced when --base-url is used.",
    )
    parser.add_argument("--emit-jsonl", action="store_true", help="Print collected live events before the summary")
    parser.add_argument(
        "--require-scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help="Require at least one event for this scenario before the release gate passes. Repeatable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.iterations < 1:
        raise StressValidationError("--iterations must be positive")
    if not args.input_jsonl and not args.base_url:
        raise StressValidationError("provide --input-jsonl for offline validation or --base-url for live bridge collection")

    events: list[dict[str, Any]] = []
    if args.input_jsonl:
        events.extend(load_jsonl(args.input_jsonl))
    if args.base_url:
        token = args.token
        if token is None:
            token = os.environ.get("OMI_AUTOMATION_TOKEN")
        if token and not args.allow_remote_token and not is_loopback_url(args.base_url):
            raise StressValidationError(
                "--base-url must be loopback when an automation token is used; "
                "pass --allow-remote-token only for an intentional non-production bridge"
            )
        scenarios = args.scenario or ["ptt_voiced"]
        events.extend(collect_from_bridge(args.base_url, token, scenarios, args.iterations))
        if args.emit_jsonl:
            for event in events:
                print(json.dumps(event, sort_keys=True))

    summary = summarize(events, args.require_scenario)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed_release_gate"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StressValidationError as exc:
        print(f"stress_ptt_chat.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
