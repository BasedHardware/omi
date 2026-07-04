#!/usr/bin/env python3
"""memory-V3-F5 real-service read-only evidence preparation runner.

Default invocation is preparation/default-NOT_RUN: it constructs no cloud client,
performs no network/provider/Firestore calls, imports no production app/router,
and leaves all readiness decisions BLOCKED/NO_GO.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from testing.memory.v3_f5_evidence import EvidenceRunConfig, build_evidence_report, render_redacted_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="prepare an execute-gated run; still requires injected client"
    )
    parser.add_argument("--environment")
    parser.add_argument("--project-id")
    parser.add_argument("--project-number")
    parser.add_argument("--expected-principal")
    parser.add_argument("--approval-subject")
    parser.add_argument("--approval-artifact-path")
    parser.add_argument("--approved-path", action="append", default=[])
    parser.add_argument("--oracle-review-artifact")
    return parser


def main(argv: list[str] | None = None, client_factory: Callable[[], Any] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    config = EvidenceRunConfig(
        execute=args.execute,
        environment=args.environment,
        project_id=args.project_id,
        project_number=args.project_number,
        expected_principal=args.expected_principal,
        approval_subject=args.approval_subject,
        approval_artifact_path=args.approval_artifact_path,
        approved_paths=tuple(args.approved_path),
        oracle_review_artifact=args.oracle_review_artifact,
    )
    report = build_evidence_report(config, client_factory=client_factory)
    if argv is None:
        print(render_redacted_json(report))
    return report


if __name__ == "__main__":
    main()
