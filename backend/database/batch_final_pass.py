"""Read-only, privacy-fenced references for enrichment's batch final pass."""

import hashlib
from datetime import datetime, timezone

from config.policy import ProjectionPolicy
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding


class ReferenceUnavailable(ValueError):
    """A valid owner reference whose lifecycle prevents this pass."""

    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(outcome)


def load_reference(store, uid, unit, conversation_id):
    def read(tx):
        job, result = tx.get('jobs', unit) or {}, tx.get('results', unit) or {}
        binding = job.get('projection_binding') or {}
        receipts = list((result.get('projection_parts') or {}).values()) or [result.get('projection') or {}]
        if job.get('owner_id') != uid or job.get('segment_id') != unit or binding.get('owner_id') != uid:
            return None
        item = WorkItem(**{k: job[k] for k in WorkItem.__dataclass_fields__ if k in job})
        if not any(
            r.get('conversation_id') == conversation_id and r.get('speaker_scope') == f'final:batch:{unit}'
            for r in receipts
        ):
            if any(r.get('conversation_id') and r.get('speaker_scope') == f'final:batch:{unit}' for r in receipts):
                raise ReferenceUnavailable('skipped_merged')
            return None
        tx.check_privacy(uid, (conversation_id,), expected_generation=item.privacy_generation)
        uri = (result.get('result') or {}).get('result_uri')
        for kind, reference in (('audio', item.audio_uri), ('results', uri)):
            if not reference or '#' not in reference:
                return None
            key = hashlib.sha256(f"{unit}\0{reference.split('#')[0]}".encode()).hexdigest()
            metadata = tx.get('artifacts', key) or {}
            if (
                metadata.get('kind') != kind
                or metadata.get('owner_id') != uid
                or metadata.get('segment_id') != unit
                or metadata.get('privacy_generation') != item.privacy_generation
                or metadata.get('erasure_requested')
                or metadata.get('uri') not in (reference, reference.split('#')[0])
            ):
                return None
            if metadata.get('cleanup_after') and metadata['cleanup_after'] <= datetime.now(timezone.utc):
                raise ReferenceUnavailable('skipped_expired')
        return (
            item,
            uri,
            ProjectionBinding(**binding),
            ProjectionPolicy.from_dict((job.get('policy_parts') or {}).get('projection', {})),
        )

    return store.run(read)
