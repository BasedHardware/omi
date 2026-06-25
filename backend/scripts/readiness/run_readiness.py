#!/usr/bin/env python3
"""CLI entrypoint for consolidated memory rollout readiness gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.readiness.loader import build_report, list_gate_ids  # noqa: E402


def main(argv: list[str] | None = None, *, gate_id: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate_id", nargs="?", default=gate_id, help="Readiness gate id (see --list)")
    parser.add_argument("--execute", action="store_true", help="Request execute-mode report emission")
    parser.add_argument("--list", action="store_true", help="List known gate ids")
    args = parser.parse_args(argv)

    if args.list:
        for gid in list_gate_ids():
            print(gid)
        return 0

    if not args.gate_id:
        parser.error("gate_id is required unless --list is set")

    report = build_report(args.gate_id, execute=args.execute)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
