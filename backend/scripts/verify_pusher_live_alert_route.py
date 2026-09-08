#!/usr/bin/env python3
"""Fail closed unless the finalization alert is live, queryable, and routed."""

from __future__ import annotations

import argparse
import json
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "backend/charts/monitoring/alerts/resilience.json"
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


class AlertRouteError(ValueError):
    pass


def _token(path: Path) -> str:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise AlertRouteError("Grafana token file must not be accessible by group or others")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise AlertRouteError("Grafana token file is empty")
    return value


def _request_json(base_url: str, path: str, token: str) -> Any:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(1_000_001)
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
    if len(body) > 1_000_000:
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
        for key in ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "labels"):
            if rule.get(key) != expected.get(key):
                errors.append(f"live alert rule {uid} {key} does not match the committed rule")
        if rule.get("isPaused") is not False:
            errors.append(f"live alert rule {uid} must be unpaused")
        receiver = expected.get("notification_settings", {}).get("receiver")
        if not isinstance(receiver, str) or rule.get("notification_settings", {}).get("receiver") != receiver:
            errors.append(f"live alert rule {uid} receiver does not match the committed route")
        else:
            receivers.add(receiver)
    if str(datasource.get("status", "")).upper() != "OK":
        errors.append("live Prometheus datasource health is not OK")
    up_results = up_query.get("data", {}).get("result", []) if up_query.get("status") == "success" else []
    healthy_jobs = {
        item.get("metric", {}).get("job")
        for item in up_results
        if isinstance(item, dict)
        and isinstance(item.get("metric"), dict)
        and isinstance(item.get("value"), list)
        and len(item["value"]) == 2
        and str(item["value"][1]) == "1"
    }
    if healthy_jobs != REQUIRED_JOBS:
        errors.append("current Pusher and backend-listen Prometheus scrape targets are not both healthy")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepublish", "postrollout"), required=True)
    parser.add_argument("--attempts", type=int, default=1)
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.grafana_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        print("FAIL: Grafana URL must be an approved HTTPS monitoring origin")
        return 1
    try:
        token = _token(args.token_file)
        if args.attempts < 1 or args.attempts > 12:
            raise AlertRouteError("attempts must be between 1 and 12")
        up_query_path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode(
            {"query": 'min(up{job=~"pusher-metrics|backend-listen-metrics"}) by (job)'}
        )
        metric_query_path = "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode(
            {
                "query": 'count({__name__=~"omi_capture_finalization_failures_total|omi_journey_accepted_total|omi_journey_terminal_total",job=~"pusher-metrics|backend-listen-metrics"}) by (__name__,job)'
            }
        )
        for attempt in range(args.attempts):
            failures = validate_live_route(
                {
                    uid: _request_json(args.grafana_url, f"/api/v1/provisioning/alert-rules/{uid}", token)
                    for uid in RULE_UIDS
                },
                _request_json(args.grafana_url, "/api/datasources/uid/prometheus/health", token),
                _request_json(args.grafana_url, up_query_path, token),
                _request_json(args.grafana_url, metric_query_path, token),
                _request_json(args.grafana_url, "/api/v1/provisioning/contact-points", token),
                phase=args.phase,
            )
            if not failures or attempt + 1 == args.attempts:
                break
            time.sleep(5)
    except (AlertRouteError, OSError, json.JSONDecodeError) as exc:
        failures = [str(exc)]
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: live finalization outcome rules, telemetry sources, datasource, and Telegram routes match the contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
