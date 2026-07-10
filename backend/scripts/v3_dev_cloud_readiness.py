#!/usr/bin/env python3
"""Prepare safe local artifacts for memory `/v3` dev-cloud proof.

Default mode prints a JSON preflight/readiness report and performs no network or
Firestore writes. `--write-bundle-dir` writes placeholder evidence files locally
so CI/deployment jobs have the exact artifact contract to fill during the real
deployed dev-cloud proof.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (BACKEND_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from v3_dev_cloud_proof import (
    build_candidate_manifest,
    build_dev_cloud_fixture_bundle,
    build_proof_matrix,
    build_target_preflight_report,
    write_prepared_bundle,
)
from readiness_gate_common import (
    add_require_go_arg,
    evaluate_gates,
    exit_code_for_status,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Prepare memory /v3 dev-cloud proof artifacts safely.')
    parser.add_argument('--repo-root', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--run-id', default='not-run')
    parser.add_argument('--uid-a', default='memory-dev-synthetic-user-a')
    parser.add_argument('--uid-b', default='memory-dev-synthetic-user-b')
    parser.add_argument('--write-bundle-dir', default='')
    parser.add_argument('--fixture-only', action='store_true')
    parser.add_argument('--proof-matrix-only', action='store_true')
    parser.add_argument('--candidate-manifest-only', action='store_true')
    add_require_go_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = dict(os.environ)
    if args.fixture_only:
        result = build_dev_cloud_fixture_bundle(uid_a=args.uid_a, uid_b=args.uid_b, run_id=args.run_id)
    elif args.proof_matrix_only:
        result = build_proof_matrix()
    elif args.candidate_manifest_only:
        result = build_candidate_manifest(repo_root=args.repo_root, env=env, run_id=args.run_id)
    elif args.write_bundle_dir:
        result = write_prepared_bundle(
            repo_root=args.repo_root,
            output_dir=args.write_bundle_dir,
            uid_a=args.uid_a,
            uid_b=args.uid_b,
            run_id=args.run_id,
            env=env,
        )
    else:
        result = build_target_preflight_report(env)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if args.require_go:
        overall_status, _ = evaluate_gates({'preflight': {'status': result.get('status', 'NOT_RUN')}})
        return exit_code_for_status(overall_status, require_go=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
