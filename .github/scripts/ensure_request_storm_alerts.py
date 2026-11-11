#!/usr/bin/env python3
"""Reconcile built-in LB metric storm alerts. Only the prod deploy runs writes."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ensure_firestore_missing_index_alert import _notification_channels
from ensure_monitoring_metric_alert_policy import ensure_json_policy

CONFIG_DIR = Path(__file__).resolve().parent.parent / "monitoring"
POLICIES = ("api_edge_429_policy.json", "sync_upload_409_policy.json")


def ensure_alerts(*, project: str, notification_channels: str, runner=subprocess.run) -> list[str]:
    if project != "based-hardware":
        raise ValueError("Request-storm policies are scoped to based-hardware production")
    channels = _notification_channels(notification_channels)
    names = []
    for filename in POLICIES:
        body = json.loads((CONFIG_DIR / filename).read_text())
        body["notificationChannels"] = channels
        names.append(ensure_json_policy(project=project, body=body, runner=runner))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--notification-channels", required=True)
    args = parser.parse_args()
    try:
        print("\n".join(ensure_alerts(project=args.project, notification_channels=args.notification_channels)))
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
