#!/usr/bin/env python3
"""Convert an owner-authorized paid-population export to scorecard JSONL.

The input is a local JSON/JSONL/CSV export. This utility never contacts
Stripe, Firestore, PostHog, or any other production service. Each paid user is
represented by one ``Billing Paid Population Snapshot`` event at the explicit
start-of-window time; the scorecard refuses to infer a paid denominator from
subscription-created events alone.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SNAPSHOT_SCHEMA = "billing-paid-snapshot.v1"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PLANS = {"unlimited", "architect", "operator", "plus", "unlimited_v2"}
_SCOPE = re.compile(r"^[A-Za-z0-9_.:@/-]{1,128}$")


def parse_time(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("snapshot_at must be an ISO timestamp or Unix seconds")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        return [row for row in csv.DictReader(text.splitlines())]
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
        if isinstance(value, Mapping):
            rows = value.get("rows")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, Mapping)]
        raise ValueError("JSON input must be a list or an object with rows")
    rows: list[Mapping[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise ValueError("JSONL rows must be objects")
            rows.append(value)
    return rows


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "paid", "active", "trialing"}


def _scope_value(value: Any, *, name: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    if not _SCOPE.fullmatch(normalized):
        raise ValueError(f"{name} must be a bounded cohort identifier")
    return normalized


def convert(
    rows: list[Mapping[str, Any]],
    *,
    snapshot_id: str,
    snapshot_at: datetime,
    namespace: str | None = None,
    environment: str | None = None,
    app_build: str | None = None,
) -> list[dict[str, Any]]:
    if not _ID.fullmatch(snapshot_id):
        raise ValueError("snapshot_id must be 1-128 bounded identifier characters")
    resolved_namespace = _scope_value(namespace, name="namespace")
    resolved_environment = _scope_value(environment, name="environment")
    resolved_build = _scope_value(app_build, name="app_build")
    users: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        uid = str(row.get("uid") or row.get("user_id") or "").strip()
        if not uid:
            continue
        plan = str(row.get("plan") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        paid = _truthy(row.get("paid")) or (status in {"active", "trialing"} and plan in _PLANS)
        if not paid:
            continue
        users.setdefault(uid, row)
    result: list[dict[str, Any]] = []
    occurred_at = snapshot_at.isoformat().replace("+00:00", "Z")
    for uid, row in sorted(users.items()):
        digest = hashlib.sha256(f"{snapshot_id}:{uid}".encode("utf-8")).hexdigest()[:32]
        event: dict[str, Any] = {
            "event_id": f"billing-snapshot:{snapshot_id}:{digest}",
            "event_name": "Billing Paid Population Snapshot",
            "user_id": uid,
            "occurred_at": occurred_at,
            "properties": {
                "billing_snapshot_schema": SNAPSHOT_SCHEMA,
                "snapshot_id": snapshot_id,
                "snapshot_role": "start_of_window",
                "snapshot_at": occurred_at,
                "plan": str(row.get("plan") or "unknown")[:64],
                "interval": str(row.get("interval") or "unknown")[:16],
                "status": str(row.get("status") or "active")[:16],
                "source": "owner_authorized_billing_export",
            }
        }
        # A billing export has no mobile identity by default. Keep it
        # independently scoped unless the operator explicitly supplies the
        # verified client cohort values used by the mobile event stream.
        if resolved_namespace:
            event["client_app_namespace"] = resolved_namespace
        if resolved_environment:
            event["client_app_profile"] = resolved_environment
        if resolved_build:
            event["app_build"] = resolved_build
        event["properties"]["billing_scope"] = "mobile_join" if resolved_namespace and resolved_environment else "billing_independent"
        result.append(event)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="local JSON, JSONL, or CSV owner-authorized export")
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-at", required=True, help="UTC start-of-window timestamp")
    parser.add_argument("--namespace", help="verified client app namespace for a mobile cohort join")
    parser.add_argument("--environment", help="verified client app profile for a mobile cohort join")
    parser.add_argument("--app-build", help="verified mobile app build for a build-isolated join")
    args = parser.parse_args(argv)
    rows = load_rows(Path(args.input))
    events = convert(
        rows,
        snapshot_id=args.snapshot_id,
        snapshot_at=parse_time(args.snapshot_at),
        namespace=args.namespace,
        environment=args.environment,
        app_build=args.app_build,
    )
    output = Path(args.output)
    output.write_text("".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
