#!/usr/bin/env python3
"""Publish the checked-in omi-tv dashboard JSON through the Grafana HTTP API.

Skips when GRAFANA_TOKEN is unset. Does not invent credentials.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / "web/admin/grafana/dashboards"
ALLOWED_UIDS = {"omi-tv", "omi-tv-macos", "omi-tv-mobile"}
DEFAULT_GRAFANA_URL = "https://admin.omi.me/grafana"


def grafana_base_url() -> str:
    raw = os.environ.get("GRAFANA_URL") or os.environ.get("GRAFANA_ORIGIN") or DEFAULT_GRAFANA_URL
    return raw.rstrip("/")


def load_dashboard(path: Path) -> dict:
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    if dashboard.get("uid") not in ALLOWED_UIDS:
        raise SystemExit(f"{path}: dashboard uid must be one of {sorted(ALLOWED_UIDS)}")
    dashboard.pop("id", None)
    dashboard.pop("version", None)
    return dashboard


def apply(token: str, path: Path) -> None:
    dashboard = load_dashboard(path)
    payload = json.dumps(
        {
            "dashboard": dashboard,
            "overwrite": True,
            "message": f"apply checked-in {dashboard['uid']} dashboard",
        }
    ).encode("utf-8")
    url = f"{grafana_base_url()}/api/dashboards/db"
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            print(f"applied {dashboard['uid']} ({response.status}): {body}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Grafana apply failed ({exc.code}): {detail}") from exc


def main() -> int:
    token = os.environ.get("GRAFANA_TOKEN", "").strip()
    if not token:
        print("skipping omi-tv apply: GRAFANA_TOKEN is unset")
        return 0
    for path in sorted(DASHBOARD_DIR.glob("*.json")):
        apply(token, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
