"""Bounded reason and producer labels for projection diagnostics."""

import re
from typing import cast

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import (
    ProjectionBlocked,
    ProjectionGenerationAmbiguous,
    ProjectionPredecessorPending,
)

BATCH_PROJECTION_BLOCK_REASONS = frozenset(
    {
        'intake_binding_mismatch',
        'invalid_recording_clock',
        'invalid_recording_identity',
        'invalid_recording_interval',
        'invalid_upload_filenames',
        'lineage_identity_missing',
        'lineage_ambiguous',
        'other',
    }
)


def projection_block_reason(error: BaseException) -> str:
    """Return only the closed, log-safe projection block reason token."""
    try:
        attributes = cast(object, error.__dict__)
        reason = attributes.get('block_reason') if isinstance(attributes, dict) else None
    except Exception:
        reason = None
    if type(reason) is str and reason in BATCH_PROJECTION_BLOCK_REASONS:
        return reason
    return 'other'


# Only known literals enter telemetry. Never turn arbitrary exception text into a label.
_SWEEP_BLOCK_MESSAGES = {
    'privacy disposition requires a source deletion tombstone': 'source_deletion_tombstone_required',
    'canonical source result not ready': 'canonical_source_not_ready',
    'source fallback processing pending': 'source_fallback_pending',
    'projection assignment claim busy': 'assignment_claim_busy',
    'committed result and durable intake binding required': 'missing_committed_result_or_binding',
}


def sweep_block_reason(error: ProjectionBlocked | BatchPrivacyBlocked) -> str:
    if isinstance(error, ProjectionPredecessorPending):
        return 'predecessor_pending'
    if isinstance(error, BatchPrivacyBlocked):
        return f'privacy_{error.reason.value}'
    if isinstance(error, ProjectionGenerationAmbiguous):
        return 'lineage_ambiguous'
    message = error.args[0] if len(error.args) == 1 else None
    if type(message) is str and message in _SWEEP_BLOCK_MESSAGES:
        return _SWEEP_BLOCK_MESSAGES[message]
    return projection_block_reason(error)


def sweep_block_group(entry: dict | None, reason: str) -> tuple[str, str]:
    # The committed result belongs to this attempt. A job, fleet setting, or
    # previous page row could describe an entirely different producer.
    result = entry.get('result') if isinstance(entry, dict) else None
    digest = result.get('worker_image_digest') if isinstance(result, dict) else None
    if type(digest) is not str or re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is None:
        digest = 'unknown'
    return reason, digest
