"""Proof checks for promoting a native Finish after transcript projection."""

from datetime import datetime, timezone

from utils.batch_pipeline.scheduler import owner_key
from utils.sync import capture_end
from utils.conversations.v3.policy import (
    NATIVE_MANUAL_INPUT_REVISION,
    NATIVE_MANUAL_PROOF,
    NATIVE_MANUAL_READY,
    NATIVE_MANUAL_STOP,
    native_manual_binding,
)


def upload_revision(job) -> int | None:
    legacy = job.get('record_input_upload_revision')
    explicit = job.get(NATIVE_MANUAL_INPUT_REVISION)
    if type(explicit) is not int or explicit < 1:
        return None
    if legacy is not None and (type(legacy) is not int or explicit != legacy):
        return None
    return explicit


def unit_matches(job, entry, binding, sibling, expected_revision, sealed_at):
    parts = entry.get('projection_parts')
    count = entry.get('projection_part_count')
    return (
        upload_revision(job) == expected_revision
        and job.get('record_sealed_at') == sealed_at
        and job.get('owner_id') == binding.owner_id
        and job.get('privacy_generation') == binding.privacy_generation
        and job.get('result') is not None
        and job.get('result') == entry.get('result')
        and entry.get('owner_key') == owner_key(binding.owner_id)
        and entry.get('segment_id') == sibling
        and entry.get('capture_at') == job.get('capture_at')
        and entry.get('projection_state') in {'ready', 'completed'}
        and not entry.get('projection_redriven_at')
        and (
            not parts
            and count is None
            or type(count) is int
            and count > 0
            and count == len(parts or {})
            and set(parts or {}) == {str(index) for index in range(count)}
        )
    )


def receipts_match(target, receipts):
    # Match original destinations, before _visible follows donor redirects and deduplicates.
    return bool(
        receipts
        and all(
            receipt.get('state') == 'ready'
            and receipt.get('conversation_id') == target
            and not any(receipt.get(key) for key in ('disposition', 'privacy_reason', 'size_rollover_outputs'))
            for receipt in receipts
        )
    )


def ready_patch(row, upload_revision, sealed_at, now):
    if (
        row.get(NATIVE_MANUAL_READY) is not None
        or row.get('v3_manual_end')
        or capture_end.seal_barrier(row) is not None
    ):
        return None
    patch = {
        'v3_manual_end': True,
        NATIVE_MANUAL_READY: upload_revision,
        NATIVE_MANUAL_PROOF: {'seal': sealed_at, 'intent': row.get(NATIVE_MANUAL_STOP)},
        'v3_pending': True,
        'v3_pending_since': row.get('v3_pending_since') or datetime.fromtimestamp(now, timezone.utc),
    }
    return patch if native_manual_binding({**row, **patch}) else None
