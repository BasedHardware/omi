#!/usr/bin/env python3
"""Inspect or create a migration job; this command never applies memory writes.

The production worker owns the legacy adapter and calls the normal canonical
apply boundary.  Keeping this operator CLI assessment-only prevents a local
command from accidentally treating current canonical rows as a legacy source.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.memory_migration import CanonicalMigrationJob, MigrationSurface


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assess a canonical memory migration job")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--job-json", type=Path, help="Existing job JSON to validate")
    parser.add_argument("--account-generation", type=int, default=0)
    parser.add_argument("--source-generation", type=int, default=0)
    parser.add_argument("--transform-version", default="legacy-v1")
    parser.add_argument("--policy-version", default="canonical-v1")
    parser.add_argument("--source-adapter-version", default="legacy-firestore-v1")
    parser.add_argument("--apply", action="store_true", help="Rejected: only the deployed worker may apply")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply:
        raise SystemExit(
            "--apply is intentionally unavailable: use the deployed migration worker and canonical apply boundary"
        )
    if args.job_json:
        payload = json.loads(args.job_json.read_text(encoding="utf-8"))
        payload.setdefault("uid", args.uid)
        job = CanonicalMigrationJob.model_validate(payload)
    else:
        job = CanonicalMigrationJob.new(
            uid=args.uid,
            transform_version=args.transform_version,
            policy_version=args.policy_version,
            source_adapter_version=args.source_adapter_version,
            account_generation=args.account_generation,
            source_generation=args.source_generation,
            required_surfaces=list(MigrationSurface),
        )
    print(
        json.dumps(
            {
                "uid": job.uid,
                "job_id": job.job_id,
                "state": job.state.value,
                "required_surfaces": [s.value for s in job.required_surfaces],
                "apply_available": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
