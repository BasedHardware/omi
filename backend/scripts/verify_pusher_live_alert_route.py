#!/usr/bin/env python3
"""Fail closed unless the finalization alert is live, queryable, and routed.

The default invocation is the Pusher release gate: the gated UID set, scrape
targets, finalization metrics, and Telegram receiver. Optional ``--mode fleet``
classifies every committed Grafana rule against live provisioning without
changing that gate. Fleet drift is report-only unless ``--fail-on`` is raised.
"""

from __future__ import annotations

import argparse
import json
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "backend/charts/monitoring/alerts/resilience.json"
ALERT_SOURCES = ROOT / "backend/charts/monitoring/alerts"
GATE_FILE = ROOT / "backend/charts/monitoring/live-alert-gate.json"
RULE_UIDS = (
    "omi-capture-finalization-memory-fence",
    "omi-journey-capture-success-critical",
    "omi-journey-capture-settle-gap",
    "omi-capture-oldest-nonterminal",
    "omi-capture-dead-letter-surge",
    "omi-journey-scrape-missing",
    "omi-journey-capture-fail",
)
REQUIRED_METRICS = {
    "omi_capture_finalization_failures_total",
    "omi_journey_accepted_total",
    "omi_journey_terminal_total",
}
REQUIRED_JOBS = {"pusher-metrics", "backend-listen-metrics"}
ALLOWED_HOSTS = {"monitor.omiapi.com", "monitor.omi.me"}
DEFINITION_KEYS = ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "labels")
SINGLE_RULE_SIZE_LIMIT = 1_000_000
FLEET_LIST_SIZE_LIMIT = 4_000_000
ALERT_RULE_LIST_PATH = "/api/v1/provisioning/alert-rules"


class AlertRouteError(ValueError):
    pass


@dataclass(frozen=True)
class FleetCoverage:
    committed_but_absent: tuple[str, ...]
    live_but_uncommitted: tuple[str, ...]
    present_but_paused: tuple[str, ...]
    present_but_divergent: tuple[str, ...]
    live_and_matching: tuple[str, ...]
    live_count: int


def _token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise AlertRouteError("Grafana token file must not be accessible by group or others")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise AlertRouteError("Grafana token file is empty")
    return value


def _request_json(base_url: str, path: str, token: str, *, size_limit: int = SINGLE_RULE_SIZE_LIMIT) -> Any:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(size_limit + 1)
    except urllib.error.HTTPError as exc:
        # Name the status. Collapsing every failure into "HTTPError" cost ~37h of red
        # deploys in #12668 because CI could not tell an unprovisioned rule (404) from a
        # revoked token (401) — two failures with completely different owners and fixes.
        # Status and reason phrase only: the response body can carry Grafana detail we do
        # not want in a public log.
        raise AlertRouteError(f"Grafana API request failed for {path}: HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        # Subclass of OSError, superclass of HTTPError, so it has to sit between the two.
        raise AlertRouteError(f"Grafana API request failed for {path}: URLError {exc.reason}") from exc
    except OSError as exc:
        raise AlertRouteError(f"Grafana API request failed for {path}: {type(exc).__name__}") from exc
    if len(body) > size_limit:
        raise AlertRouteError(f"Grafana API response exceeded the size limit for {path}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise AlertRouteError(f"Grafana API returned invalid JSON for {path}") from exc


def _committed_rules() -> dict[str, dict[str, Any]]:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    by_uid = {rule.get("uid"): rule for rule in rules if isinstance(rule, dict) and isinstance(rule.get("uid"), str)}
    missing = [uid for uid in RULE_UIDS if uid not in by_uid]
    if missing:
        raise AlertRouteError(f"committed finalization alert set is incomplete: {','.join(missing)}")
    return {uid: by_uid[uid] for uid in RULE_UIDS}


def load_all_committed_rules() -> dict[str, dict[str, Any]]:
    by_uid: dict[str, dict[str, Any]] = {}
    for path in sorted(ALERT_SOURCES.glob("*.json")):
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise AlertRouteError(f"committed alert file {path.name} is not a list")
        for item in loaded:
            if not isinstance(item, dict):
                raise AlertRouteError(f"committed alert file {path.name} contains a non-object rule")
            uid = item.get("uid")
            if not isinstance(uid, str) or not uid:
                raise AlertRouteError(f"committed alert file {path.name} contains a rule without a uid")
            if uid in by_uid:
                raise AlertRouteError(f"duplicate committed alert uid {uid}")
            by_uid[uid] = item
    if not by_uid:
        raise AlertRouteError("committed alert exports contain no rules")
    return by_uid


def load_gated_uids(committed: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    loaded: object = json.loads(GATE_FILE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AlertRouteError("live-alert-gate.json must be an object")
    raw = loaded.get("uids")
    if not isinstance(raw, list) or not raw:
        raise AlertRouteError("live-alert-gate.json uids must be a non-empty list")
    uids: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item:
            raise AlertRouteError("live-alert-gate.json uids must be non-empty strings")
        if item in seen:
            raise AlertRouteError(f"live-alert-gate.json duplicate uid {item}")
        if item not in committed:
            raise AlertRouteError(f"live-alert-gate.json uid {item} is not a committed alert")
        seen.add(item)
        uids.append(item)
    return tuple(uids)


def index_live_rules(payload: object, *, path: str) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        raise AlertRouteError(f"Grafana API returned a non-list payload for {path}")
    by_uid: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise AlertRouteError(f"Grafana API returned a non-object rule for {path}")
        uid = item.get("uid")
        if not isinstance(uid, str) or not uid:
            raise AlertRouteError(f"Grafana API returned a rule without a uid for {path}")
        if uid in by_uid:
            raise AlertRouteError(f"Grafana API returned duplicate uid {uid} for {path}")
        by_uid[uid] = item
    return by_uid


def _receiver(rule: dict[str, Any]) -> Any:
    settings = rule.get("notification_settings", {})
    if not isinstance(settings, dict):
        return None
    return settings.get("receiver")


def mismatched_definition_keys(live: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    keys = [key for key in DEFINITION_KEYS if live.get(key) != expected.get(key)]
    receiver = _receiver(expected)
    if not isinstance(receiver, str) or _receiver(live) != receiver:
        keys.append("receiver")
    return keys


def rule_definition_errors(uid: str, live: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    keys = mismatched_definition_keys(live, expected)
    errors = [f"live alert rule {uid} {key} does not match the committed rule" for key in keys if key != "receiver"]
    if live.get("isPaused") is not False:
        errors.append(f"live alert rule {uid} must be unpaused")
    if "receiver" in keys:
        errors.append(f"live alert rule {uid} receiver does not match the committed route")
    return errors


def classify_fleet_coverage(
    committed: dict[str, dict[str, Any]], live_by_uid: dict[str, dict[str, Any]]
) -> FleetCoverage:
    committed_but_absent: list[str] = []
    present_but_paused: list[str] = []
    present_but_divergent: list[str] = []
    live_and_matching: list[str] = []
    for uid in sorted(committed):
        live = live_by_uid.get(uid)
        if not isinstance(live, dict):
            committed_but_absent.append(uid)
            continue
        keys = mismatched_definition_keys(live, committed[uid])
        paused = live.get("isPaused") is not False
        if paused:
            present_but_paused.append(uid)
        if keys:
            present_but_divergent.append(f"{uid} ({','.join(keys)})")
        if not paused and not keys:
            live_and_matching.append(uid)
    live_but_uncommitted = tuple(sorted(uid for uid in live_by_uid if uid not in committed))
    return FleetCoverage(
        committed_but_absent=tuple(committed_but_absent),
        live_but_uncommitted=live_but_uncommitted,
        present_but_paused=tuple(present_but_paused),
        present_but_divergent=tuple(present_but_divergent),
        live_and_matching=tuple(live_and_matching),
        live_count=len(live_by_uid),
    )


def format_fleet_report(coverage: FleetCoverage, *, committed_count: int, gated_uids: tuple[str, ...]) -> list[str]:
    gated_matching = tuple(uid for uid in gated_uids if uid in coverage.live_and_matching)
    ungated_unproven = committed_count - len(gated_uids)
    lines = [
        (
            f"FLEET committed={committed_count} live={coverage.live_count} gated={len(gated_uids)} "
            f"matching={len(coverage.live_and_matching)} gated_matching={len(gated_matching)}"
        ),
        (
            f"COMMITTED_BUT_ABSENT ({len(coverage.committed_but_absent)}): "
            f"{', '.join(coverage.committed_but_absent) or '-'}"
        ),
        (
            f"LIVE_BUT_UNCOMMITTED ({len(coverage.live_but_uncommitted)}): "
            f"{', '.join(coverage.live_but_uncommitted) or '-'}"
        ),
        (
            f"PRESENT_BUT_PAUSED ({len(coverage.present_but_paused)}): "
            f"{', '.join(coverage.present_but_paused) or '-'}"
        ),
        (
            f"PRESENT_BUT_DIVERGENT ({len(coverage.present_but_divergent)}): "
            f"{', '.join(coverage.present_but_divergent) or '-'}"
        ),
        f"LIVE_AND_MATCHING ({len(coverage.live_and_matching)})",
        (
            "UNPROVEN: live status of ungated committed rules is classified above; "
            f"{ungated_unproven} committed UIDs are outside the fail-closed gate "
            "until live-alert-gate.json is widened after a token-backed proof."
        ),
    ]
    return lines


def _divergent_uid(entry: str) -> str:
    return entry.split(" (", 1)[0]


def fleet_gate_failures(coverage: FleetCoverage, gated_uids: tuple[str, ...], fail_on: str) -> list[str]:
    if fail_on == "none":
        return []
    absent = set(coverage.committed_but_absent)
    paused = set(coverage.present_but_paused)
    divergent = {_divergent_uid(entry): entry for entry in coverage.present_but_divergent}
    uncommitted = set(coverage.live_but_uncommitted)
    uids = gated_uids if fail_on == "gated" else tuple(sorted(absent | paused | set(divergent) | uncommitted))
    failures: list[str] = []
    for uid in uids:
        if uid in uncommitted:
            failures.append(f"live alert rule {uid} is not in the committed exports")
            continue
        if uid in absent:
            failures.append(f"live alert rule {uid} is absent from Grafana")
        if uid in paused:
            failures.append(f"live alert rule {uid} must be unpaused")
        if uid in divergent:
            failures.append(f"live alert rule {divergent[uid]} does not match the committed rule")
    return failures


def validate_live_route(
    live_rules: dict[str, dict[str, Any]],
    datasource: dict[str, Any],
    up_query: dict[str, Any],
    metric_query: dict[str, Any],
    contact_points: Any,
    *,
    phase: str,
) -> list[str]:
    expected_rules = _committed_rules()
    errors: list[str] = []
    receivers: set[str] = set()
    for uid, expected in expected_rules.items():
        rule = live_rules.get(uid, {})
        rule_errors = rule_definition_errors(uid, rule, expected)
        errors.extend(rule_errors)
        if not any("receiver does not match" in error for error in rule_errors):
            receiver = _receiver(expected)
            if isinstance(receiver, str):
                receivers.add(receiver)
    if str(datasource.get("status", "")).upper() != "OK":
        errors.append("live Prometheus datasource health is not OK")
    up_results = up_query.get("data", {}).get("result", []) if up_query.get("status") == "success" else []
    observed_up: dict[str, str] = {}
    for item in up_results:
        if (
            isinstance(item, dict)
            and isinstance(item.get("metric"), dict)
            and isinstance(item.get("value"), list)
            and len(item["value"]) == 2
        ):
            job = item["metric"].get("job")
            if isinstance(job, str):
                observed_up.setdefault(job, str(item["value"][1]))
    healthy_jobs = {job for job, value in observed_up.items() if value == "1"}
    if healthy_jobs != REQUIRED_JOBS:
        observed = ", ".join(f"{job}={observed_up.get(job, 'absent')}" for job in sorted(REQUIRED_JOBS))
        errors.append(
            "current Pusher and backend-listen Prometheus scrape targets are not both healthy"
            f" (observed min(up) by job: {observed})"
        )
    results = metric_query.get("data", {}).get("result", []) if metric_query.get("status") == "success" else []
    observed_metrics = {
        (item.get("metric", {}).get("__name__"), item.get("metric", {}).get("job"))
        for item in results
        if isinstance(item, dict) and isinstance(item.get("metric"), dict)
    }
    required_metric_jobs = {(metric, job) for metric in REQUIRED_METRICS for job in REQUIRED_JOBS}
    if phase == "postrollout" and observed_metrics != required_metric_jobs:
        errors.append("live Prometheus finalization telemetry sources are missing or incomplete")
    points = contact_points if isinstance(contact_points, list) else []
    for receiver in receivers:
        if not any(
            isinstance(point, dict)
            and point.get("name") == receiver
            and str(point.get("type", "")).lower() == "telegram"
            and point.get("disableResolveMessage") is not True
            for point in points
        ):
            errors.append("committed Telegram receiver is missing or resolve notifications are disabled")
    return errors


def _approved_grafana_url(raw: str) -> bool:
    parsed = urllib.parse.urlparse(raw)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_HOSTS
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _run_pusher_gate(grafana_url: str, token: str, phase: str, attempts: int) -> list[str]:
    up_query_path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode(
        {"query": 'min(up{job=~"pusher-metrics|backend-listen-metrics"}) by (job)'}
    )
    metric_query_path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode(
        {
            "query": 'count({__name__=~"omi_capture_finalization_failures_total|omi_journey_accepted_total|omi_journey_terminal_total",job=~"pusher-metrics|backend-listen-metrics"}) by (__name__,job)'
        }
    )
    failures: list[str] = []
    for attempt in range(attempts):
        failures = validate_live_route(
            {uid: _request_json(grafana_url, f"/api/v1/provisioning/alert-rules/{uid}", token) for uid in RULE_UIDS},
            _request_json(grafana_url, "/api/datasources/uid/prometheus/health", token),
            _request_json(grafana_url, up_query_path, token),
            _request_json(grafana_url, metric_query_path, token),
            _request_json(grafana_url, "/api/v1/provisioning/contact-points", token),
            phase=phase,
        )
        if not failures or attempt + 1 == attempts:
            break
        time.sleep(5)
    return failures


def _run_fleet_coverage(grafana_url: str, token: str, attempts: int, fail_on: str) -> tuple[list[str], list[str]]:
    committed = load_all_committed_rules()
    gated_uids = load_gated_uids(committed)
    coverage: FleetCoverage | None = None
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            payload = _request_json(grafana_url, ALERT_RULE_LIST_PATH, token, size_limit=FLEET_LIST_SIZE_LIMIT)
            live_by_uid = index_live_rules(payload, path=ALERT_RULE_LIST_PATH)
            coverage = classify_fleet_coverage(committed, live_by_uid)
            last_error = None
            break
        except AlertRouteError as exc:
            last_error = str(exc)
            if attempt + 1 == attempts:
                break
            time.sleep(5)
    if coverage is None:
        return [last_error or "fleet coverage request failed"], []
    report = format_fleet_report(coverage, committed_count=len(committed), gated_uids=gated_uids)
    return fleet_gate_failures(coverage, gated_uids, fail_on), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepublish", "postrollout"))
    parser.add_argument("--mode", choices=("pusher", "fleet"), default="pusher")
    parser.add_argument("--fail-on", choices=("none", "gated", "all"))
    parser.add_argument("--attempts", type=int, default=1)
    args = parser.parse_args()
    if not _approved_grafana_url(args.grafana_url):
        print("FAIL: Grafana URL must be an approved HTTPS monitoring origin")
        return 1
    if args.mode == "pusher" and args.phase is None:
        print("FAIL: pusher mode requires --phase")
        return 1
    if args.mode == "pusher" and args.fail_on is not None:
        print("FAIL: --fail-on is only valid with --mode fleet")
        return 1
    fail_on = "none" if args.mode == "fleet" and args.fail_on is None else args.fail_on
    report_lines: list[str] = []
    try:
        token = _token(args.token_file)
        if args.attempts < 1 or args.attempts > 12:
            raise AlertRouteError("attempts must be between 1 and 12")
        if args.mode == "pusher":
            phase = args.phase
            if phase is None:
                raise AlertRouteError("pusher mode requires --phase")
            failures = _run_pusher_gate(args.grafana_url, token, phase, args.attempts)
        else:
            if fail_on is None:
                raise AlertRouteError("fleet mode requires --fail-on none, gated, or all")
            failures, report_lines = _run_fleet_coverage(args.grafana_url, token, args.attempts, fail_on)
    except (AlertRouteError, OSError, json.JSONDecodeError) as exc:
        failures = [str(exc)]
    for line in report_lines:
        print(line)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    if args.mode == "pusher":
        print(
            "OK: live finalization outcome rules, telemetry sources, datasource, and Telegram routes match the contract."
        )
    else:
        print("OK: fleet Grafana coverage report completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
