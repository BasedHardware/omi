#!/usr/bin/env python3
"""Measure the macOS proactive-advice user rate over a rolling PT24H window."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TIME_WINDOW = "PT24H"
MINIMUM_DAU = 50
MINIMUM_ELIGIBLE_DELIVERIES = 10
APP_NAMESPACE = "com.omi.computer-macos"
HOGQL = f"""
SELECT
    uniq(person_id) AS macos_dau,
    uniqIf(person_id, event = 'Advice Generated') AS advice_users,
    countIf(event = 'Advice Delivery Outcome' AND properties['outcome'] IN ('delivered', 'failed')) AS eligible_delivery_outcomes,
    countIf(event = 'Advice Delivery Outcome' AND properties['outcome'] = 'delivered') AS delivered_outcomes,
    uniqIf(person_id, event = 'Advice Delivery Outcome' AND properties['outcome'] = 'delivered') AS delivered_users
FROM events
WHERE timestamp >= now() - INTERVAL 24 HOUR
  AND properties['$app_namespace'] = '{APP_NAMESPACE}'
  AND properties['$os_name'] = 'macOS'
""".strip()


class PostHogQueryError(RuntimeError):
    """A bounded PostHog query failed without exposing a response body."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def evaluate_counts(
    macos_dau: int,
    advice_users: int,
    eligible_delivery_outcomes: int = 0,
    delivered_outcomes: int = 0,
    delivered_users: int = 0,
    *,
    minimum_dau: int = MINIMUM_DAU,
    minimum_eligible_deliveries: int = MINIMUM_ELIGIBLE_DELIVERIES,
) -> dict[str, object]:
    if (
        macos_dau < 0
        or advice_users < 0
        or advice_users > macos_dau
        or eligible_delivery_outcomes < 0
        or delivered_outcomes < 0
        or delivered_outcomes > eligible_delivery_outcomes
        or delivered_users < 0
        or delivered_users > macos_dau
    ):
        raise ValueError("metric counts must satisfy 0 <= advice_users <= macos_dau")
    if minimum_dau < 1 or minimum_eligible_deliveries < 1:
        raise ValueError("minimum samples must be positive")

    if macos_dau < minimum_dau:
        status, alarm_reason = "unknown", None
    elif advice_users == 0:
        status, alarm_reason = "unhealthy", "advice_users_exactly_zero"
    elif eligible_delivery_outcomes < minimum_eligible_deliveries:
        status, alarm_reason = "unknown", None
    elif delivered_outcomes == 0:
        status, alarm_reason = "unhealthy", "delivered_outcomes_exactly_zero"
    else:
        status, alarm_reason = "healthy", None
    return {
        "metric": "proactive_delivery",
        "status": status,
        "generated_at": _utc_now(),
        "time_window": TIME_WINDOW,
        "minimum_sample": minimum_dau,
        "minimum_eligible_deliveries": minimum_eligible_deliveries,
        "denominator": macos_dau,
        "numerator": advice_users,
        "value": round(advice_users / macos_dau, 6) if macos_dau else None,
        "eligible_delivery_outcomes": eligible_delivery_outcomes,
        "delivered_outcomes": delivered_outcomes,
        "delivered_users": delivered_users,
        "delivery_success_rate": (
            round(delivered_outcomes / eligible_delivery_outcomes, 6) if eligible_delivery_outcomes else None
        ),
        "alarm_reason": alarm_reason,
        "privacy": {"user_identifiers_included": False, "content_included": False},
    }


def _posthog_endpoint(host: str, project_id: str) -> str:
    parsed = urllib.parse.urlparse(host)
    if parsed.scheme != "https" or not parsed.netloc or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("POSTHOG_HOST must be an HTTPS origin")
    if not project_id.isdigit():
        raise ValueError("POSTHOG_PROJECT_ID must be numeric")
    return f"{parsed.scheme}://{parsed.netloc}/api/projects/{project_id}/query/"


def query_counts(*, host: str, project_id: str, personal_api_key: str) -> tuple[int, int, int, int, int]:
    if not personal_api_key:
        raise ValueError("POSTHOG_PERSONAL_API_KEY is required")
    payload = json.dumps({"query": {"kind": "HogQLQuery", "query": HOGQL}}).encode("utf-8")
    request = urllib.request.Request(
        _posthog_endpoint(host, project_id),
        data=payload,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {personal_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310: validated HTTPS origin.
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise PostHogQueryError(f"PostHog query returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise PostHogQueryError(f"PostHog query failed: {type(error).__name__}") from error

    rows = body.get("results") if isinstance(body, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list) or len(rows[0]) < 5:
        raise PostHogQueryError("PostHog query returned an unexpected result shape")
    try:
        return tuple(int(value) for value in rows[0][:5])
    except (TypeError, ValueError) as error:
        raise PostHogQueryError("PostHog query returned non-numeric counts") from error


def collect_from_env(*, minimum_dau: int = MINIMUM_DAU) -> dict[str, object]:
    counts = query_counts(
        host=os.environ.get("POSTHOG_HOST", ""),
        project_id=os.environ.get("POSTHOG_PROJECT_ID", ""),
        personal_api_key=os.environ.get("POSTHOG_PERSONAL_API_KEY", ""),
    )
    return evaluate_counts(*counts, minimum_dau=minimum_dau)


def doctor_metric(result: dict[str, object]) -> dict[str, object]:
    return {
        "health_status": result["status"],
        "denominator": result["denominator"],
        "numerator": result["numerator"],
        "time_window": result["time_window"],
        "minimum_sample": result["minimum_sample"],
        "value": result["value"],
        "alarm_reason": result["alarm_reason"],
        "eligible_delivery_outcomes": result["eligible_delivery_outcomes"],
        "delivered_outcomes": result["delivered_outcomes"],
        "delivery_success_rate": result["delivery_success_rate"],
    }


def format_summary(result: dict[str, object]) -> str:
    value = "unknown" if result["value"] is None else f"{float(result['value']):.2%}"
    return (
        f"Proactive delivery health: {str(result['status']).upper()}\n"
        f"Advice users / macOS DAU: {result['numerator']} / {result['denominator']} ({value})\n"
        f"Delivered / eligible delivery outcomes: {result['delivered_outcomes']} / "
        f"{result['eligible_delivery_outcomes']}\n"
        f"Window: {result['time_window']}; minimum DAU: {result['minimum_sample']}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--minimum-dau", type=int, default=MINIMUM_DAU)
    args = parser.parse_args()

    result = collect_from_env(minimum_dau=args.minimum_dau)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = format_summary(result)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary, encoding="utf-8")
    print(summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
