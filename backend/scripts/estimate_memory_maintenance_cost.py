#!/usr/bin/env python3
"""Print Luna Flex dreaming cost for an average user and one sample account.

Does not call the public API. Token counts are planning estimates; pass
``--pending-l2`` / ``--pending-consolidation`` from a Firestore inspect or
from ``llm_gateway_attempts`` after the job has run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from utils.memory.maintenance_cost import estimate_pass


def _render(label: str, pending_l2: int, pending_consolidation: int, *, flex: bool) -> str:
    estimate = estimate_pass(
        pending_l2=pending_l2,
        pending_consolidation=pending_consolidation,
        flex=flex,
    )
    return (
        f"{label}: pending_l2={pending_l2} pending_consolidation={pending_consolidation} "
        f"l2_calls={estimate.l2_calls} consolidation_calls={estimate.consolidation_calls} "
        f"tokens_in={estimate.input_tokens} tokens_out={estimate.output_tokens} "
        f"${estimate.usd:.6f}/pass  ${estimate.usd * 30:.4f}/month"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flex", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--average-pending-l2", type=int, default=1)
    parser.add_argument("--average-pending-consolidation", type=int, default=3)
    parser.add_argument(
        "--uid", default="", help="Optional sample UID label only; this script does not read Firestore."
    )
    parser.add_argument("--uid-pending-l2", type=int, default=5)
    parser.add_argument("--uid-pending-consolidation", type=int, default=15)
    args = parser.parse_args(argv)

    print("model=gpt-5.6-luna lanes=omi:auto:memory-l2-flex,omi:auto:memory-conflict-flex service_tier=flex")
    print("rates=short-context $0.20/M in $1.20/M out * 50% Flex; consolidation batch=20; job L2 folded")
    print(_render("average_user", args.average_pending_l2, args.average_pending_consolidation, flex=args.flex))
    sample = args.uid or "sample_uid"
    print(_render(sample, args.uid_pending_l2, args.uid_pending_consolidation, flex=args.flex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
