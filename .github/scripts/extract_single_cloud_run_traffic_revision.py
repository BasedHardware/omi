#!/usr/bin/env python3
"""Print the sole 100%-traffic Cloud Run revision from a service document."""

from __future__ import annotations

import json
import sys
from typing import Any


def extract_single_serving_revision(service: dict[str, Any]) -> str:
    traffic = service.get("status", {}).get("traffic", [])
    if not isinstance(traffic, list):
        raise ValueError("Cloud Run service status.traffic must be a list")
    revisions = [
        entry.get("revisionName")
        for entry in traffic
        if isinstance(entry, dict) and entry.get("percent") == 100 and isinstance(entry.get("revisionName"), str)
    ]
    if len(revisions) != 1:
        raise ValueError(f"expected exactly one 100% Cloud Run revision, found {revisions!r}")
    return revisions[0]


def main() -> int:
    try:
        service = json.load(sys.stdin)
        if not isinstance(service, dict):
            raise ValueError("Cloud Run service document must be an object")
        print(extract_single_serving_revision(service))
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Cloud Run traffic revision contract: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
