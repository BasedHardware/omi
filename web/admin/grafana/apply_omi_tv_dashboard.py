#!/usr/bin/env python3
"""Publish the checked-in omi-tv dashboard JSON through the Grafana HTTP API.

Skips when GRAFANA_TOKEN is unset. Does not invent credentials.

The live board's layout is the layout master: Nik drags/resizes panels in the
Grafana UI, and an apply must never revert that (it did, three times in one
day — every dashboards-diff merge stamped the checked-in gridPos back over
his arrangement). Checked-in JSONs own panel CONTENT (queries, thresholds,
titles); positions of panels that already exist on the live board are taken
from the live board.
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


def preserve_live_layout(incoming_panels: list, live_panels: list) -> None:
    """Overlay the live board's gridPos onto matching incoming panels, in place.

    Panels are matched by id (stable in the checked-in JSONs). A panel new to
    this apply keeps its authored position; a panel the user moved or resized
    keeps the user's geometry.
    """
    live_by_id = {p.get("id"): p.get("gridPos") for p in live_panels if p.get("id") is not None}
    for panel in incoming_panels:
        live_pos = live_by_id.get(panel.get("id"))
        if live_pos:
            panel["gridPos"] = live_pos


def fetch_live_panels(token: str, uid: str) -> list:
    request = urllib.request.Request(
        f"{grafana_base_url()}/api/dashboards/uid/{uid}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body.get("dashboard", {}).get("panels", []) or []
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []  # first apply of a new board
        raise SystemExit(f"Grafana fetch failed ({exc.code}) for {uid}") from exc


def apply(token: str, path: Path) -> None:
    dashboard = load_dashboard(path)
    preserve_live_layout(
        dashboard.get("panels", []),
        fetch_live_panels(token, dashboard["uid"]),
    )
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
