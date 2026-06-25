#!/usr/bin/env python3
"""Readiness/local contract inventory for future server-side memory `/v3` cohort/enrollment/control reader."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.readiness.loader import build_report as _build_gate_report

GATE_ID = "p1_3_v3_control_reader_readiness"


def build_report(*, execute: bool = False):
    return _build_gate_report(GATE_ID, execute=execute)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Emit execute-mode readiness report")
    args = parser.parse_args()
    report = build_report(execute=args.execute)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
