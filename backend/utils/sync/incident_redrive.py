"""Fail-closed planning for the October 2026 codec incident; no IO or clients."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

POPULATIONS = ('finalize_legacy', 'persistence_suspected_open_loop')
FIX_COMMIT = '87083b7b9c298c915de89ff6e8054eb94c4e7661'
SERVICES = ('backend-sync', 'backend-sync-backfill', 'backend-integration')
# The exact admission schema, shared with the production enqueue boundary by its
# validator at the adapter boundary. Explicit nulls carry capture context too.
PAYLOAD_FIELDS = (
    'schema_version',
    'job_id',
    'uid',
    'raw_blob_paths',
    'source',
    'should_lock',
    'conversation_id',
    'recording_session_id',
    'audio_start_seconds',
    'audio_end_seconds',
    'geolocation',
    'client_device_id',
    'client_platform',
    'enqueued_at',
    'lane',
    'capture_time_trust',
    'recording_age_seconds',
    'content_id',
    'ledger_fence_mode',
)
OPTIONAL_FIELDS = (
    'raw_capture_paths',
    'capture_evidence_claims',
    'sequencer_epoch',
    'budget_deferrals',
    'redrive_mode',
)
LEDGER_FIELDS = (
    'job_id',
    'status',
    'lane',
    'dispatch_protocol',
    'partial_result',
    'processed_segment_ids',
    'result.failed_segments',
    'result.total_segments',
    'result.errors',
    'result.outcome',
    'result.held_audio',
    'ledger_run_token',
    'ledger_run_epoch',
    'repeat_failure_pause_until',
    'updated_at',
    'metered_at',
    'usage_recorded_at',
    'dg_recorded_at',
    'openloop_redrive',
)
REASONS = frozenset(
    {
        'task_payload_read_denied',
        'no_ready_jobs',
        'ready',
        'invalid_input',
        'metadata_read_failed',
        'payload_missing',
        'payload_conflict',
        'payload_invalid',
        'identity_conflict',
        'ledger_missing',
        'ledger_completed',
        'ledger_not_retryable',
        'ledger_owner_changed',
        'checkpoint_missing',
        'finalize_receipt_replay_required',
        'runtime_probe_required',
        'job_missing',
        'job_changed',
        'active_owner',
        'sequenced_job',
        'source_missing',
        'already_dispatched',
        'operation_conflict',
        'serving_commit_unverified',
        'plan_changed',
        'dry_run_required',
        'dispatch_uncertain',
        'dispatched',
        'operator_runtime_required',
    }
)


@dataclass
class Evidence:
    payloads: dict[str, dict] = field(default_factory=dict)
    ledger: dict | None = None
    content_id: str | None = None
    job: dict | None = None
    runtime_checked: bool = False
    active_owner: bool = False
    sources_present: bool = False
    read_failed: bool = False
    task_read_denied: bool = False
    source_checks: dict[str, str] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def operation_key(row: dict, content_id: str) -> str:
    return digest({'redrive_key': row['redrive_key'], 'content_id': content_id})


def resolve_payload(evidence: Evidence) -> tuple[dict | None, str]:
    values = list(evidence.payloads.values())
    if not values:
        return None, 'payload_missing'
    # A retained task may have an execution epoch/deferral count added after
    # admission. Those fields cannot change the original request's semantics.
    comparable = [{k: v for k, v in p.items() if k not in ('sequencer_epoch', 'budget_deferrals')} for p in values]
    if any(p != comparable[0] for p in comparable[1:]):
        return None, 'payload_conflict'
    source = next(iter(evidence.payloads))
    payload = values[0]
    evidence.field_sources.update({k: source for k in payload})
    evidence.field_sources['filenames'] = source + '.raw_blob_paths'
    evidence.field_sources['language'] = 'worker_current_transcription_preferences_not_in_original_payload'
    return payload, 'ready'


def classify(row: dict, evidence: Evidence) -> str:
    if row.get('population') not in POPULATIONS or row.get('status') not in ('failed', 'partial_failure'):
        return 'invalid_input'
    key = row.get('redrive_key')
    if not isinstance(key, dict) or not row.get('job_id') or key.get('job_id') != row['job_id']:
        return 'invalid_input'
    if evidence.read_failed:
        return 'metadata_read_failed'
    payload, reason = resolve_payload(evidence)
    if payload is None:
        return 'task_payload_read_denied' if evidence.task_read_denied else reason
    if not set(PAYLOAD_FIELDS).issubset(payload) or set(payload) - set(PAYLOAD_FIELDS + OPTIONAL_FIELDS):
        return 'payload_invalid'
    uid, content = payload.get('uid'), payload.get('content_id')
    if not all(isinstance(v, str) and v and '/' not in v for v in (uid, content)):
        return 'payload_invalid'
    if payload['job_id'] != row['job_id'] or any(key.get(k) and key[k] != payload[k] for k in ('uid', 'content_id')):
        return 'identity_conflict'
    if evidence.content_id is not None and evidence.content_id != content:
        return 'identity_conflict'
    paths = payload.get('raw_blob_paths')
    if (
        payload.get('schema_version') != 1
        or payload.get('lane') not in ('fresh', 'backfill')
        or payload.get('ledger_fence_mode') != 'active'
        or not isinstance(paths, list)
        or not paths
        or any(not isinstance(p, str) or not p.startswith(f'syncing/{uid}/{row["job_id"]}/') for p in paths)
        or len(paths) != len(set(paths))
    ):
        return 'payload_invalid'
    ledger = evidence.ledger
    if not ledger:
        return 'ledger_missing'
    if ledger.get('status') == 'completed':
        return 'ledger_completed'
    marker = ledger.get('openloop_redrive') or {}
    if marker:
        if marker.get('key') != operation_key(row, content):
            return 'operation_conflict'
        if marker.get('state') == 'dispatched':
            return 'already_dispatched'
    if ledger.get('ledger_run_token') is not None or ledger.get('ledger_run_epoch') is not None:
        return 'active_owner'
    if ledger.get('job_id') != row['job_id'] and not (
        ledger.get('status') == 'retryable'
        and ledger.get('job_id') is None
        and ledger.get('ledger_run_token') is None
        and ledger.get('ledger_run_epoch') is None
    ):
        return 'ledger_owner_changed'
    if ledger.get('status') not in ('processing', 'retryable') or ledger.get('dispatch_protocol'):
        return 'ledger_not_retryable'
    if not isinstance(ledger.get('processed_segment_ids'), list) or not isinstance(ledger.get('partial_result'), dict):
        return 'checkpoint_missing'
    evidence.field_sources.update({k: 'sync_content_ledger' for k in ('partial_result', 'processed_segment_ids')})
    # These failures happen AFTER intake committed, BEFORE the processed marker.
    # Re-transcribing them would spend again on an already-persisted segment.
    if row['population'] == 'finalize_legacy':
        return 'finalize_receipt_replay_required'
    if 'sequencer_epoch' in payload:
        return 'sequenced_job'
    if evidence.active_owner:
        return 'active_owner'
    if not evidence.runtime_checked:
        return 'runtime_probe_required'
    job = evidence.job
    if not job:
        return 'job_missing'
    if job.get('status') not in ('failed', 'partial_failure') and not (
        marker.get('state') == 'prepared'
        and job.get('status') == 'queued'
        and job.get('openloop_redrive_key') == marker.get('key')
    ):
        return 'job_changed'
    if marker.get('state') == 'prepared':
        if job.get('openloop_redrive_key') == marker.get('key') and job.get('status') in ('failed', 'partial_failure'):
            return 'already_dispatched'
        # Cloud Tasks' deleted-name retention is finite. Never recreate a task
        # after an old uncertain acknowledgement could outlive its tombstone.
        if time.time() >= marker.get('enqueue_until', 0):
            return 'dispatch_uncertain'
    if 'sync_finalize_failed' in (job.get('result') or {}).get('errors', []):
        return 'finalize_receipt_replay_required'
    if any(job.get(k) != payload[k] for k in ('uid', 'job_id', 'content_id', 'lane', 'ledger_fence_mode')):
        return 'identity_conflict'
    # Never pin policy from this operator's laptop environment.
    if not isinstance(job.get('policy'), dict) or job.get('dispatch_mode') != 'cloud_tasks':
        return 'job_changed'
    if not evidence.sources_present:
        return 'source_missing'
    return 'ready'


def evidence_digest(evidence: Evidence) -> str:
    return digest({'payloads': evidence.payloads, 'ledger': evidence.ledger, 'job': evidence.job})


def select_population(rows: list[dict], population: str, limit: int) -> list[dict]:
    if population not in POPULATIONS or type(limit) is not int or limit <= 0:
        raise ValueError('invalid_input')
    return [row for row in rows if row.get('population') == population][:limit]


def serving_commits_valid(commits: dict[str, list[str]], contains_fix: Any) -> bool:
    return set(commits) == set(SERVICES) and all(
        revisions and all(isinstance(sha, str) and len(sha) == 40 and contains_fix(sha) for sha in revisions)
        for revisions in commits.values()
    )
