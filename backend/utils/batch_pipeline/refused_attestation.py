"""Recorded vendor evidence for a read-only historical refusal plan."""

from datetime import datetime
import math
import re

from utils.batch_pipeline import redrive_scope as scope


def utc(value):
    scope.require(isinstance(value, str), 'attestation_utc_required')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise scope.ScopeRefused('attestation_utc_required')
    offset = stamp.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise scope.ScopeRefused('attestation_utc_required')
    return stamp.timestamp()


def checked_proof(proof, scope_spec):
    scope.require(
        isinstance(proof, dict)
        and set(proof)
        == {
            'version',
            'vendor',
            'source',
            'files_created',
            'complete',
            'window_start',
            'window_end',
            'recorded_at',
            'usage_evidence_sha256',
            'apply_log_sha256',
            'scope_sha256',
        },
        'invalid_zero_files_proof',
    )
    scope.require(
        proof['version'] == 1
        and proof['vendor'] == 'soniox'
        and proof['source'] == 'vendor_usage_export'
        and type(proof['files_created']) is int
        and proof['files_created'] == 0
        and proof['complete'] is True,
        'zero_vendor_files_required',
    )
    scope.require(
        all(
            isinstance(proof[key], str) and re.fullmatch('[a-f0-9]{64}', proof[key])
            for key in ('usage_evidence_sha256', 'apply_log_sha256', 'scope_sha256')
        ),
        'attestation_evidence_required',
    )
    scope.require(proof['scope_sha256'] == scope.digest(scope_spec), 'attestation_scope_changed')
    start, end, recorded = (utc(proof[key]) for key in ('window_start', 'window_end', 'recorded_at'))
    scope.require(0 < start < end <= recorded, 'attestation_window_invalid')
    return start, end


def refused_candidate(job, *, prepared, after, cutoff, max_seconds, window):
    """Never reinterpret a validated answer, active job, or completed obligation."""
    scope.require(
        after <= job.get('quarantined_at', 0) <= cutoff
        and job.get('state') == 'quarantined'
        and job.get('quarantine_reason') == 'worker_failed'
        and job.get('recovery_state') == 'failed_held'
        and (job.get('worker_failure') or {}).get('reason') == 'unsupported_language'
        and not job.get('result')
        and not job.get('token')
        and job.get('merge_pending') is False
        and not job.get('silence_disposition')
        and not job.get('terminal_disposition'),
        'attestation_unit_not_held',
    )
    recovery = job.get('recovery') or {}
    marker = recovery if prepared else job.get('speech_redrive') or {}
    if prepared:
        scope.require(
            recovery.get('epoch') == 1
            and recovery.get('provider') == 'modulate'
            and not job.get('speech_redrive')
            and 60 < job.get('duration_seconds', 0) <= max_seconds
            and set(marker.get('recognizers') or {}) == {'soniox'}
            and (marker.get('recognizers') or {}).get('soniox', {}).get('outcome') == 'error',
            'attestation_route_mismatch',
        )
    else:
        scope.require(
            marker.get('paid_epoch') == 3
            and marker.get('provider') == 'soniox'
            and marker.get('prior_recovery') == recovery
            and recovery.get('provider') == 'modulate'
            and marker.get('state') in {'prepared', 'failed_held'}
            and 0 < job.get('duration_seconds', 0) <= 60,
            'attestation_route_mismatch',
        )
    failure = marker.get('failure') or {}
    scope.require(
        'attempt_history' not in marker and 'original_token' not in marker,
        'attestation_attempt_history_forbidden',
    )
    scope.require(
        bool(marker.get('token'))
        and marker.get('paid_state') != 'spent'
        and ((marker.get('recognizers') or {}).get('soniox') or {}).get('outcome') in {None, 'error', 'refused'}
        and (
            not failure
            or failure == {'stage': 'provider', 'reason': 'provider_failed'}
            or failure == {'stage': 'provider', 'reason': 'operation_failed'}
        ),
        'attestation_has_paid_evidence',
    )
    when = marker.get('started_at', marker.get('prepared_at'))
    scope.require(
        isinstance(when, (int, float))
        and not isinstance(when, bool)
        and math.isfinite(when)
        and window[0] <= when < window[1],
        'attempt_outside_attested_window',
    )
    return scope.digest({'job': job, 'attested_intent': marker})
