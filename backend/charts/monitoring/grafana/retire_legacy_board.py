#!/usr/bin/env python3
"""Parent-only: retire the private board's old anonymous copy AFTER closing access."""

import argparse
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from grafana_business import Grafana  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()
    bases = ["https://admin.omi.me/grafana", "https://omi-grafana-208440318997.us-central1.run.app/grafana"]
    for base in bases:
        try:
            with urllib.request.urlopen(base + "/api/datasources", timeout=30):
                raise ValueError("Legacy anonymous access is still enabled")
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                raise
            exc.close()
    client = Grafana(bases[0], os.environ["GRAFANA_TOKEN"])
    path = "/api/dashboards/uid/omi-tv-v2"
    if client.optional(path) is not None:
        client.call("DELETE", path)
    if client.optional(path) is not None:
        raise ValueError("Legacy board still exists")
    print("PASS legacy anonymous access denied on both origins; legacy omi-tv-v2 removed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL legacy retirement; details suppressed", file=sys.stderr)
        raise SystemExit(1)
