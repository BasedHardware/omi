#!/usr/bin/env python3
"""Provision checked-in Grafana dashboards via the HTTP API.

Called by .github/workflows/grafana_dashboard_provisioning.yml after a merge
touches backend/charts/monitoring/dashboards/. For every dashboard JSON in
the directory:

1. Parse and validate (must be an object with a uid).
2. POST it to Grafana's /api/dashboards/db with overwrite=true, so the
   checked-in file becomes the served board in place.
3. Read the dashboard back and assert the served version advanced, so a
   silent no-op (auth scopes, wrong folder policy) fails the job instead of
   shipping "merged but invisible" dashboards.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _post_dashboard(base: str, token: str, dashboard: dict, source_sha: str) -> tuple[int, dict]:
    body = json.dumps(
        {
            "dashboard": dashboard,
            "overwrite": True,
            "message": f"provisioned from main {source_sha}",
        }
    ).encode()
    request = urllib.request.Request(
        f"{base}/api/dashboards/db",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.load(response)


def _get_dashboard(base: str, token: str, uid: str) -> dict:
    request = urllib.request.Request(
        f"{base}/api/dashboards/uid/{uid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("dashboard") or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboards-dir", type=Path, required=True)
    parser.add_argument("--grafana-url", required=True)
    parser.add_argument("--token-env", default="MONITOR_GRAFANA_TOKEN")
    parser.add_argument("--source-sha", default="main")
    parser.add_argument(
        "--allowlist",
        default="",
        help="Comma-separated filenames to provision; empty = all dashboards",
    )
    args = parser.parse_args()

    token = os.environ.get(args.token_env) or ""
    if not token:
        print(f"FAIL: {args.token_env} is empty", file=sys.stderr)
        return 1
    base = args.grafana_url.rstrip("/")

    files = sorted(args.dashboards_dir.rglob("*.json"))
    if args.allowlist:
        allowed = {name.strip() for name in args.allowlist.split(",") if name.strip()}
        files = [path for path in files if path.name in allowed]
    if not files:
        print(f"FAIL: no dashboard JSON under {args.dashboards_dir}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in files:
        label = str(path)
        try:
            dashboard = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            failures.append(f"{label}: invalid JSON ({exc})")
            continue
        uid = dashboard.get("uid") or ""
        if not uid:
            failures.append(f"{label}: missing uid; POST would create an orphan board")
            continue

        try:
            _status, body = _post_dashboard(base, token, dashboard, args.source_sha)
        except urllib.error.HTTPError as exc:
            failures.append(f"{label}: POST failed HTTP {exc.code}: {exc.read().decode()[:200]}")
            continue
        if body.get("status") not in ("success", None):
            failures.append(f"{label}: POST returned {body}")
            continue

        # Read-back guards against silent no-ops. Assert the served version
        # is >= the POSTed version (equality is too strict: a concurrent
        # legitimate save in the UI advances the version past ours, which is
        # still proof the board is live and writable). A 404 during
        # propagation is retried, not fatal.
        served_version = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                served_version = _get_dashboard(base, token, uid).get("version")
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and time.monotonic() < deadline - 5:
                    time.sleep(1.5)
                    continue
                failures.append(f"{label}: read-back failed HTTP {exc.code}")
                break
            if isinstance(served_version, int) and served_version >= body.get("version", 0):
                break
            time.sleep(1.5)
        if not isinstance(served_version, int) or served_version < body.get("version", 0):
            failures.append(
                f"{label}: read-back version {served_version} did not advance past POST version {body.get('version')}"
            )
            continue
        print(f"OK {label}: uid={uid} version={served_version}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"Provisioned {len(files)} dashboard(s) to {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
