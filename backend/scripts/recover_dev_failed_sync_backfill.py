"""Review and optionally requeue dev-failed production backfill jobs.

Input is an operator-exported JSONL of task metadata, not audio or transcript
content. Each row needs failure_origin='dev', failure_code, and the original
Cloud Tasks payload. Historical aggregate counts alone cannot reconstruct a
UID, job ID, or staged paths after pending/owner documents were consumed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from utils.cloud_tasks import sync_job_payload_keys_valid


def selection_reason(row: dict[str, Any], job: dict[str, Any] | None, blobs_present: bool) -> str:
    """Pure fail-closed selection, shared by dry-run and apply."""
    payload = row.get('payload')
    if not isinstance(payload, dict):
        return 'missing_payload'
    if not sync_job_payload_keys_valid(payload):
        return 'invalid_payload_schema'
    job_id, uid = row.get('job_id'), row.get('uid')
    if not isinstance(job_id, str) or not job_id or not isinstance(uid, str) or not uid:
        return 'missing_identity'
    if payload.get('job_id') != job_id or payload.get('uid') != uid or payload.get('lane') != 'backfill':
        return 'payload_mismatch'
    paths = payload.get('raw_blob_paths')
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(path, str) and path.startswith(f'syncing/{uid}/{job_id}/') for path in paths)
    ):
        return 'invalid_staged_paths'
    if row.get('failure_code') != 'sync_staged_audio_expired':
        return 'other_failure'
    # New jobs carry a persisted worker marker. Historical jobs need a
    # correlated dev Cloud Run failure event supplied by the operator export.
    if row.get('failure_origin') != 'dev' or row.get('origin_evidence') not in ('job_marker', 'dev_log'):
        return 'unproven_dev_failure'
    if job is None:
        # Redis jobs last 24 hours; a correlated dev failure event can still
        # identify a candidate while the prod bucket retains its staged blob.
        if row.get('origin_evidence') != 'dev_log' or not isinstance(row.get('failure_at'), str):
            return 'job_metadata_missing'
    else:
        if job.get('job_id') != job_id or job.get('uid') != uid:
            return 'job_metadata_missing'
        if job.get('status') != 'failed' or job.get('reason_code') != 'sync_staged_audio_expired':
            return 'job_not_matching_failure'
        if job.get('failure_stage') not in (None, 'dev'):
            return 'worker_marker_mismatch'
        if job.get('content_id') != payload.get('content_id'):
            return 'content_identity_missing'
    if not isinstance(payload.get('content_id'), str) or not payload.get('content_id'):
        return 'content_identity_missing'
    if not blobs_present:
        return 'staged_audio_missing'
    return 'ready'


def _metadata_present(paths: list[str]) -> bool:
    from google.cloud import storage

    bucket_name = os.environ['BUCKET_TEMPORAL_SYNC_LOCAL']
    bucket = storage.Client().bucket(bucket_name)
    return all(bucket.blob(path).exists() for path in paths)


def _requeue(row: dict[str, Any], old_job: dict[str, Any] | None) -> str:
    from database.sync_jobs import TERMINAL_STATUSES, create_sync_job, get_sync_job
    from database.sync_ledger import claim_sync_content
    from database import sync_backfill_sequencer
    from utils.sync.uid_sequencer import kick

    uid = row['uid']
    old_id = row['job_id']
    old_job = old_job or {}
    new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'omi:dev-failed-backfill:{old_id}'))
    payload = dict(row['payload'])
    payload.pop('sequencer_epoch', None)
    payload['job_id'] = new_id
    existing = get_sync_job(new_id)
    if existing is not None:
        if any(
            existing.get(field) != value
            for field, value in (
                ('job_id', new_id),
                ('uid', uid),
                ('content_id', payload['content_id']),
                ('lane', 'backfill'),
                ('dispatch_mode', 'sequenced'),
                ('created_stage', 'prod'),
            )
        ):
            return 'recovery_job_mismatch'
        if existing.get('status') in TERMINAL_STATUSES or existing.get('status') == 'processing':
            return 'recovery_job_started_or_terminal'
        if existing.get('status') != 'queued':
            return 'recovery_job_unknown_status'
    else:
        # A retry after any later interruption keeps this deterministic job ID
        # and completes the remaining steps below.
        # Retain original staged paths and content identity; a new job ID avoids
        # reviving a terminal client-visible result or an old lease epoch.
        create_sync_job(
            uid,
            total_files=len(payload['raw_blob_paths']),
            total_segments=0,
            job_id=new_id,
            lane='backfill',
            capture_time_trust=old_job.get('capture_time_trust') or payload.get('capture_time_trust') or 'legacy',
            recording_age_seconds=old_job.get('recording_age_seconds') or payload.get('recording_age_seconds'),
            content_id=payload['content_id'],
            dispatch_mode='sequenced',
            ledger_fence_mode=old_job.get('ledger_fence_mode') or payload.get('ledger_fence_mode') or 'legacy',
        )
    claimed = claim_sync_content(uid, payload['content_id'], new_id, 'backfill')
    if claimed.get('outcome') != 'owned':
        # A previous run may own this job and ledger. Keep its Redis metadata
        # so an operator can retry after the competing claim resolves.
        return f'skipped_claim_{claimed.get("outcome", "unknown")}'
    if not sync_backfill_sequencer.is_registered(uid, new_id):
        # A lost acknowledgement is safe to retry: the same job and claim
        # remain, and registration is idempotent for this job ID.
        sync_backfill_sequencer.register_job(uid, new_id, payload, None)
    kick(uid)
    return new_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--manifest', type=Path, required=True, help='JSONL task metadata and correlated failure evidence'
    )
    parser.add_argument(
        '--apply', action='store_true', help='write a fresh prod job and dispatch through the UID sequencer'
    )
    args = parser.parse_args(argv)
    if os.getenv('OMI_ENV_STAGE', '').strip().lower() != 'prod':
        parser.error('OMI_ENV_STAGE=prod is required; do not use dev credentials')
    if not os.getenv('BUCKET_TEMPORAL_SYNC_LOCAL'):
        parser.error('BUCKET_TEMPORAL_SYNC_LOCAL is required')

    from database.sync_jobs import get_sync_job

    ready = 0
    with args.manifest.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f'line {line_number} must be an object')
            job = get_sync_job(row.get('job_id', '')) if isinstance(row.get('job_id'), str) else None
            reason = selection_reason(row, job, False)
            if reason == 'staged_audio_missing':
                metadata_ok = _metadata_present(row['payload']['raw_blob_paths'])
                reason = selection_reason(row, job, metadata_ok)
            if reason == 'ready':
                ready += 1
                result = _requeue(row, job) if args.apply else 'dry_run_ready'
            else:
                result = reason
            print(json.dumps({'line': line_number, 'job_id': row.get('job_id'), 'result': result}))
    print(json.dumps({'ready': ready, 'mode': 'apply' if args.apply else 'dry_run'}), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
