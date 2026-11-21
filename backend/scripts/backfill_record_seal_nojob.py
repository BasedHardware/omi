#!/usr/bin/env python3
"""One-time no-job seal backfill; default dry-run, counts and digest only.

Use ro-prod OR prod-operator for dry-run; apply requires prod-operator and
--approve-plan-sha256 from the same page's fresh dry-run. No ambient admission.
--after-file is an optional PRIVATE input cursor; --next-file receives the
PRIVATE next-page cursor. Keep the input unchanged between dry-run and apply.
Advance to the output cursor only after settling the page. Refusals need a
separate pass from the beginning after remediation. Never commit cursor files.
An empty page ends one pass and resets the output cursor to the beginning; it
does not prove the live backlog is empty. Repeat complete passes and reconcile
the aggregate no-job backlog before declaring settlement.
"""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database._client import get_firestore_client
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.record_seal_nojob import (
    discover,
    plan_backfill,
    apply_backfill,
    summary,
    validate_server_flags,
)
from utils.batch_pipeline.record_producer_proof import load_pusher_pod_proof
from utils.other.local_storage import create_storage_client


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default includes rejected argument values and file paths.
        print(json.dumps({'operation': 'record-seal-nojob-v1', 'outcome': 'invalid_arguments'}))
        raise SystemExit(2)


def write_cursor(path, after):
    path = Path(path)
    parent = path.parent.resolve()
    scratch = Path('/Volumes/Ephemeral/scratch').resolve()
    if not parent.is_relative_to(scratch) or parent.stat().st_mode & 0o077:
        raise ValueError('cursor directory must be private scratch (0700)')
    # Atomic replace avoids following a target symlink; tempfile is mode 0600.
    with tempfile.NamedTemporaryFile(mode='w', dir=parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump({'after': after}, handle)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def read_server_flags(path):
    # Copy only admission inputs from the serving role, never credentials or
    # unrelated workload configuration. An explicit map bypasses laptop env.
    keys = {
        'K_SERVICE',
        'OMI_SYNC_STACK_ROLE',
        'BATCH_PIPELINE_ENABLED',
        'BATCH_PIPELINE_PERCENT',
        'BATCH_PIPELINE_UID_ALLOWLIST',
        'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED',
        'BATCH_LIVE_STT_RETIRE_PERCENT',
        'TRANSCRIPTION_FINAL_PASS_DIARIZER',
        'TRANSCRIPTION_FINAL_PASS_PERCENT',
        'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST',
        'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE',
    }
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError('explicit serving-role flags required')
    flags = {key: value for key, value in raw.items() if key in keys}
    validate_server_flags(flags)
    return flags


def main(argv=None):
    parser = CountsOnlyParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=128)
    parser.add_argument('--after-file')
    parser.add_argument('--next-file', required=True)
    parser.add_argument('--server-flags-file', required=True, help='private admission flags from the serving role')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--pusher-pods-file')
    parser.add_argument('--pusher-pods-captured-at')
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    allowed = {'prod-operator'} if args.apply else {'ro-prod', 'prod-operator'}
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('GCP_AGENT_TIER') not in allowed:
        parser.error('wrong identity for requested operation')
    if not 1 <= args.limit <= 128:
        parser.error('limit must be 1..128')
    if args.apply and not args.approve_plan_sha256:
        parser.error('apply requires a dry-run plan digest')
    if bool(args.pusher_pods_file) != bool(args.pusher_pods_captured_at):
        parser.error('pod inventory file and capture time are required together')
    if args.after_file and Path(args.after_file).resolve() == Path(args.next_file).resolve():
        parser.error('input and output cursor files must differ')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    after = json.loads(Path(args.after_file).read_text())['after'] if args.after_file else None
    server_flags = read_server_flags(args.server_flags_file)
    client = get_firestore_client()
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)
    proof = (
        load_pusher_pod_proof(args.pusher_pods_file, args.pusher_pods_captured_at) if args.pusher_pods_file else None
    )
    paths, next_after = discover(client, limit=args.limit, after=after)
    plan = plan_backfill(
        store, paths, create_storage_client(), artifacts_for(store), server_flags=server_flags, producer_proof=proof
    )
    report = {**summary(plan), 'apply': args.apply}
    # Validate/write the private cursor before any data mutation. It does not
    # advance the input; operators choose when to start the next page.
    write_cursor(args.next_file, next_after)
    if args.apply:
        report['outcomes'] = apply_backfill(store, plan, args.approve_plan_sha256)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': 'record-seal-nojob-v1', 'outcome': 'error'}))
        sys.exit(1)
