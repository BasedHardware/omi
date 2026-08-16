#!/usr/bin/env python3
"""Emit the memory-V3-F6H pre-GCP aggregate readiness report.

This runner performs only local contract smoke checks. It never constructs GCP
clients, reads credentials, or performs network/cloud/provider calls. A
PRE_GCP_READY result means the branch is locally ready to move to a host with
GCP access; it does not approve dev/prod evidence execution or any rollout.
"""

# LIFECYCLE: one-time
# DELETE-AFTER: INV-MEM-3

from __future__ import annotations
from typing import Any, Dict

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from testing.memory.v3_f6.local_smoke import build_report_from_current_local_contracts


def main() -> Dict[str, Any]:
    report = build_report_from_current_local_contracts()
    print(json.dumps(report, sort_keys=True, indent=2))
    return report


if __name__ == "__main__":
    main()
