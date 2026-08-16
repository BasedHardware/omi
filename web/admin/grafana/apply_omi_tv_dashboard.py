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
DASHBOARD_PATH = ROOT / "web/admin/grafana/dashboards/omi-tv.json"
DEFAULT_GRAFANA_URL = "https://admin.omi.me/grafana"


def grafana_base_url() -> str:
    raw = os.environ.get("GRAFANA_URL") or os.environ.get("GRAFANA_ORIGIN") or DEFAULT_GRAFANA_URL
    return raw.rstrip("/")


def load_dashboard() -> dict:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    if dashboard.get("uid") != "omi-tv":
        raise SystemExit(f"{DASHBOARD_PATH}: dashboard uid must remain omi-tv")
    dashboard.pop("id", None)
    dashboard.pop("version", None)
    return dashboard


def apply(token: str) -> None:
    payload = json.dumps(
        {
            "dashboard": load_dashboard(),
            "overwrite": True,
            "message": "apply checked-in omi-tv dashboard",
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
            print(f"applied omi-tv ({response.status}): {body}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Grafana apply failed ({exc.code}): {detail}") from exc


def main() -> int:
    token = os.environ.get("GRAFANA_TOKEN", "").strip()
    if not token:
        print("skipping omi-tv apply: GRAFANA_TOKEN is unset")
        return 0
    apply(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
