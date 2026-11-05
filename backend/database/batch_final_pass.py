"""Read-only, privacy-fenced references for enrichment's batch final pass."""

import hashlib
from datetime import datetime, timezone
from typing import NoReturn

from config.policy import ProjectionPolicy
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding
from utils.conversations.final_pass_errors import REFERENCE_REASONS


class ReferenceUnavailable(ValueError):
    """A valid owner reference whose lifecycle prevents this pass."""

    def __init__(self, outcome, reason=None):
        if reason is not None and reason not in REFERENCE_REASONS:
            raise ValueError('invalid reference reason')
        self.outcome = outcome
        self.reason = reason or outcome
        super().__init__(self.reason)


def load_reference(store, uid, unit, conversation_id, *, read_budget=None):
    def read(tx):
        def unavailable(reason: str) -> NoReturn:
            raise ReferenceUnavailable('failed_incomplete_coverage', reason)

        job = tx.get('jobs', unit)
        if not job:
            unavailable('no_job')
        result = tx.get('results', unit)
        if not result:
            unavailable('no_result')
        binding = job.get('projection_binding') or {}
        receipts = list((result.get('projection_parts') or {}).values()) or [result.get('projection') or {}]
        for matches, reason in (
            (job.get('owner_id') == uid, 'job_owner_mismatch'),
            (job.get('segment_id') == unit, 'job_unit_mismatch'),
            (binding.get('owner_id') == uid, 'binding_owner_mismatch'),
        ):
            if not matches:
                unavailable(reason)
        item = WorkItem(**{k: job[k] for k in WorkItem.__dataclass_fields__ if k in job})
        if not any(
            r.get('conversation_id') == conversation_id and r.get('speaker_scope') == f'final:batch:{unit}'
            for r in receipts
        ):
            if any(r.get('conversation_id') and r.get('speaker_scope') == f'final:batch:{unit}' for r in receipts):
                raise ReferenceUnavailable('skipped_merged')
            unavailable('receipt_missing')
        # PCM belongs to the entire staged unit, including other projection parts
        # and size-rollover outputs. Until reconstruction can trim that geometry,
        # never send a shared unit to the conversation diarizer.
        outputs = [
            output for receipt in receipts for output in [receipt, *(receipt.get('size_rollover_outputs') or [])]
        ]
        if len(receipts) != result.get('projection_part_count', len(receipts)) or any(
            output.get('conversation_id') != conversation_id for output in outputs
        ):
            raise ReferenceUnavailable('skipped_shared_unit')
        tx.check_privacy(uid, (conversation_id,), expected_generation=item.privacy_generation)
        uri = (result.get('result') or {}).get('result_uri')
        for kind, reference in (('audio', item.audio_uri), ('results', uri)):
            if not reference or '#' not in reference:
                unavailable('uri_mismatch')
            key = hashlib.sha256(f"{unit}\0{reference.split('#')[0]}".encode()).hexdigest()
            metadata = tx.get('artifacts', key)
            if not metadata:
                unavailable('artifact_row_missing')
            for matches, reason in (
                (metadata.get('kind') == kind, 'artifact_kind_mismatch'),
                (metadata.get('owner_id') == uid, 'artifact_owner_mismatch'),
                (metadata.get('segment_id') == unit, 'artifact_unit_mismatch'),
                (metadata.get('privacy_generation') == item.privacy_generation, 'generation_mismatch'),
                (not metadata.get('erasure_requested'), 'erasure'),
            ):
                if not matches:
                    unavailable(reason)
            # Retention deletes the object before removing uri/cleanup_after
            # and setting expires_at for the metadata receipt's 45-day TTL.
            # That TTL is not authority to read the deleted object, even when
            # the artifact key still binds its former base URI.
            if not metadata.get('uri') and metadata.get('expires_at'):
                raise ReferenceUnavailable('skipped_expired', 'artifact_cleaned')
            if metadata.get('uri') not in (reference, reference.split('#')[0]):
                unavailable('uri_mismatch')
            if metadata.get('cleanup_after') and metadata['cleanup_after'] <= datetime.now(timezone.utc):
                raise ReferenceUnavailable('skipped_expired')
        return (
            item,
            uri,
            ProjectionBinding(**binding),
            ProjectionPolicy.from_dict((job.get('policy_parts') or {}).get('projection', {})),
        )

    if read_budget is None:
        return store.run(read)
    # Budgeted SDK snapshots are a Firestore adapter detail, not an addition to
    # the Store protocol shared with Postgres and the pipeline simulators.
    from database.batch_pipeline_reads import read_snapshot

    return read_snapshot(store, read, read_budget)
