#!/usr/bin/env python3
"""Reconcile daily billed Firestore read operations with process ledger logs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping
from typing import Any

TABLE = "based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256"
# Services we ship that read Firestore. A ledger row from any of them,
# including pusher, still sums into the scaled sample.
SHIPPED_SERVICES = frozenset(
    {
        "backend",
        "backend-sync",
        "backend-sync-backfill",
        "backend-integration",
        "desktop-backend",
        "backend-listen",
        "pusher",
    }
)
# Prod pusher is still the pre-ledger image. Its ledger promotion was
# refused because main had moved, and this measurement card must not
# qualify or ship a later main to drag pusher onto the ledger. Until a
# normal promotion is serving pusher on a ledger SHA, a missing pusher
# snapshot is a known exclusion: it does not make the day incomplete, and
# pusher is not part of the hot tail.
# Rollback: set this to an empty frozenset once that promotion is live.
# Pusher then returns to the required set and the hot tail, and a missing
# snapshot exits loud again.
COMPLETENESS_EXCLUDED = frozenset({"pusher"})
REQUIRED_SERVICES = SHIPPED_SERVICES - COMPLETENESS_EXCLUDED
# Always-on services that receive traffic through the end of a UTC day.
# Idle or cron processes flush their own final snapshot and are not required
# to emit again in the last minutes of the day.
HOT_SERVICES = frozenset({"backend", "backend-listen", "pusher"}) - COMPLETENESS_EXCLUDED
HOT_TAIL = dt.timedelta(minutes=15)
COUNTERS = ("lookup", "not_found", "query")
ERROR_BAR = {
    "sampling": "0 (p=1)",
    "tail": (
        "bounded for backend and backend-listen when a snapshot exists in the last 15 minutes of the UTC day; "
        "pusher is a recorded completeness exclusion until a normal promotion serves a ledger SHA; otherwise unknown"
    ),
    "bias": "index-entry and other billing-model bias is not quantified; ±2% is an operational allowance, not proof bias is under 2%",
}


def _parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def reduce_ledger(
    day: str, records: Iterable[Mapping[str, Any]]
) -> tuple[int, bool, set[str], dict[tuple[str, str], dt.datetime | None]]:
    """Deduplicate snapshots by service/epoch/day and sum their cumulative values."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record.get("event") != "firestore_read_ledger" or record.get("day") != day:
            continue
        service, epoch = record.get("service"), record.get("epoch")
        if not isinstance(service, str) or not isinstance(epoch, str):
            continue
        key = (service, epoch)
        candidate = dict(record)
        candidate["_seq"] = int(record.get("seq", 0) or 0)
        candidate["_emitted_at"] = _parse_time(record.get("emitted_at") or record.get("timestamp"))
        old = latest.get(key)
        if old is None or candidate["_seq"] > old["_seq"]:
            latest[key] = candidate
        elif candidate["_seq"] == old["_seq"]:
            for counter in COUNTERS:
                candidate[counter] = max(int(candidate.get(counter, 0) or 0), int(old.get(counter, 0) or 0))
            candidate["unscoped"] = int(bool(candidate.get("unscoped")) or bool(old.get("unscoped")))
            prior_time = old.get("_emitted_at")
            new_time = candidate.get("_emitted_at")
            candidate["_emitted_at"] = max((t for t in (prior_time, new_time) if t is not None), default=None)
            latest[key] = candidate
    instrumented = sum(int(record.get(counter, 0) or 0) for record in latest.values() for counter in COUNTERS)
    unscoped = any(bool(record.get("unscoped")) for record in latest.values())
    services = {service for service, _ in latest}
    emitted = {(service, epoch): record.get("_emitted_at") for (service, epoch), record in latest.items()}
    return instrumented, unscoped, services, emitted


def reconcile(day: str, billed: float, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure day outcome calculation. emitted_at/timestamp values must be parseable for healthy."""
    parsed_day = dt.date.fromisoformat(day)
    day_end = dt.datetime.combine(parsed_day + dt.timedelta(days=1), dt.time(), tzinfo=dt.timezone.utc)
    instrumented, unscoped, services, emitted = reduce_ledger(day, records)
    billed = float(billed)
    residual = billed - instrumented
    residual_pct = residual / billed * 100 if billed else None
    latest_hot: dict[str, dt.datetime | None] = {}
    for (service, _epoch), stamp in emitted.items():
        if service not in HOT_SERVICES:
            continue
        previous = latest_hot.get(service)
        if stamp is not None and (previous is None or stamp > previous):
            latest_hot[service] = stamp
    tail_ok = all(
        (stamp := latest_hot.get(service)) is not None and stamp >= day_end - HOT_TAIL for service in HOT_SERVICES
    )
    complete = REQUIRED_SERVICES <= services and not unscoped and tail_ok and billed > 0
    if not complete:
        outcome = "incomplete"
    elif -0.02 <= residual / billed <= 0.02:
        outcome = "healthy"
    elif residual / billed > 0.02:
        outcome = "audit_required"
    else:
        outcome = "accounting_failure"
    error_bar = dict(ERROR_BAR)
    if not tail_ok:
        error_bar["tail"] = "unknown"
    return {
        "day": day,
        "billed": billed,
        "instrumented": instrumented,
        "residual": residual,
        "residual_pct": residual_pct,
        "outcome": outcome,
        "completeness_excluded": sorted(COMPLETENESS_EXCLUDED),
        "error_bar": error_bar,
    }


_HOUR_LOG_LIMIT = 20000


def _closed_day(day: str) -> dt.date:
    parsed = dt.date.fromisoformat(day)
    if parsed.isoformat() != day:
        raise ValueError("day must be YYYY-MM-DD")
    return parsed


def fetch_day(day: str) -> tuple[float, list[dict[str, Any]]]:
    """Read BigQuery billing and Cloud Logging records via authenticated gcloud/bq CLIs."""
    parsed = _closed_day(day)
    start_dt = dt.datetime.combine(parsed, dt.time(), tzinfo=dt.timezone.utc)
    end_dt = start_dt + dt.timedelta(days=1)
    start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = f"""SELECT COALESCE(SUM(usage.amount), 0) AS billed
FROM `{TABLE}`
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(TIMESTAMP('{start}'), INTERVAL 2 DAY)
  AND _PARTITIONTIME < TIMESTAMP_ADD(TIMESTAMP('{end}'), INTERVAL 2 DAY)
  AND usage_start_time >= TIMESTAMP('{start}') AND usage_start_time < TIMESTAMP('{end}')
  AND project.id = 'based-hardware'
  AND service.description = 'App Engine'
  AND sku.description = 'Cloud Firestore Read Ops'
  AND usage.unit = 'requests'"""
    bq = subprocess.run(
        ["bq", "query", "--project_id=based-hardware", "--use_legacy_sql=false", "--format=json", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    billing_rows = json.loads(bq.stdout)
    billed = float(billing_rows[0]["billed"]) if billing_rows else 0.0
    records: list[dict[str, Any]] = []
    for hour in range(24):
        hour_start = start_dt + dt.timedelta(hours=hour)
        hour_end = hour_start + dt.timedelta(hours=1)
        filter_expr = (
            f'timestamp >= "{hour_start.strftime("%Y-%m-%dT%H:%M:%SZ")}" AND '
            f'timestamp < "{hour_end.strftime("%Y-%m-%dT%H:%M:%SZ")}" AND '
            '(jsonPayload.event="firestore_read_ledger" OR textPayload:"firestore_read_ledger")'
        )
        logs = subprocess.run(
            [
                "gcloud",
                "logging",
                "read",
                filter_expr,
                "--project=based-hardware",
                "--format=json",
                f"--limit={_HOUR_LOG_LIMIT}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        entries = json.loads(logs.stdout or "[]")
        if len(entries) >= _HOUR_LOG_LIMIT:
            raise RuntimeError(
                f"ledger log page for {hour_start.isoformat()} hit {_HOUR_LOG_LIMIT}; refusing a partial day"
            )
        for entry in entries:
            payload = entry.get("jsonPayload")
            if not isinstance(payload, dict):
                text_payload = entry.get("textPayload", "")
                try:
                    payload = json.loads(text_payload)
                except (TypeError, ValueError):
                    brace = text_payload.find("{") if isinstance(text_payload, str) else -1
                    if brace < 0:
                        continue
                    try:
                        payload = json.loads(text_payload[brace:])
                    except ValueError:
                        continue
                if not isinstance(payload, dict):
                    continue
            payload["timestamp"] = entry.get("timestamp")
            records.append(payload)
    return billed, records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True, help="Closed UTC day YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        billed, records = fetch_day(args.day)
        result = reconcile(args.day, billed, records)
    except Exception as exc:
        print(f"firestore read reconciliation fetch failed: {exc}", file=sys.stderr)
        try:
            result = reconcile(args.day, 0, [])
        except ValueError:
            result = {
                "day": args.day,
                "billed": 0,
                "instrumented": 0,
                "residual": 0,
                "residual_pct": None,
                "outcome": "incomplete",
                "completeness_excluded": sorted(COMPLETENESS_EXCLUDED),
                "error_bar": dict(ERROR_BAR),
            }
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 4
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return {"healthy": 0, "audit_required": 2, "accounting_failure": 3, "incomplete": 4}[result["outcome"]]


if __name__ == "__main__":
    raise SystemExit(main())
