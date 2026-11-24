"""Per-recording admission receipts; namespace-wide existence is never proof."""

from dataclasses import dataclass, fields
import hashlib
import json
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Recording:
    owner_id: str
    owner_key: str
    conversation_id: str
    content_id: str
    segment_id: str
    capture_at: float
    duration_seconds: float
    privacy_generation: int = 0

    @property
    def job_id(self):
        return 'bp_' + self.content_id


class EvidenceMismatch(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise EvidenceMismatch(code)


def validate_recording(record, job, intake, artifact, manifest, *, namespace, bucket):
    """Pure identity checks. Inputs are this recording's exact keyed documents."""
    require(job.get('state') == 'ready', 'expected_ready_state')
    identity = {
        'owner_id': record.owner_id,
        'segment_id': record.segment_id,
        'conversation_id': record.conversation_id,
        'privacy_generation': record.privacy_generation,
        'capture_at': record.capture_at,
        'duration_seconds': record.duration_seconds,
    }
    require(all(job.get(k) == v for k, v in identity.items()), 'job_identity')
    binding = job.get('projection_binding') or {}
    expected_binding = {
        'owner_id': record.owner_id,
        'content_id': record.content_id,
        'job_id': record.job_id,
        'target_conversation_id': record.conversation_id,
        'segment_ids': [record.segment_id],
        'privacy_generation': record.privacy_generation,
        'record_origin': True,
        'native_record': True,
    }
    require(all(binding.get(k) == v for k, v in expected_binding.items()), 'binding_identity')
    expected_intake = {
        'owner_id': record.owner_id,
        'owner_key': record.owner_key,
        'content_id': record.content_id,
        'conversation_id': record.conversation_id,
        'segment_ids': [record.segment_id],
        'total_audio_seconds': record.duration_seconds,
    }
    require(all(intake.get(k) == v for k, v in expected_intake.items()), 'intake_identity')
    parsed = urlsplit(job.get('audio_uri') or '')
    prefix = f'batch-pipeline/{namespace}/owners/{hashlib.sha256(record.owner_id.encode()).hexdigest()}/audio/{record.segment_id}/'
    require(
        parsed.scheme == 'gs'
        and parsed.netloc == bucket
        and parsed.path.lstrip('/').startswith(prefix)
        and parsed.fragment.isdigit()
        and int(parsed.fragment) > 0,
        'staged_uri_identity',
    )
    expected_artifact = {
        'owner_id': record.owner_id,
        'owner_key': record.owner_key,
        'segment_id': record.segment_id,
        'kind': 'audio',
        'privacy_generation': record.privacy_generation,
        'uri': job['audio_uri'].split('#', 1)[0],
        'capture_at': record.capture_at,
        'duration_seconds': record.duration_seconds,
    }
    require(
        all(artifact.get(k) == v for k, v in expected_artifact.items())
        and set(artifact.get('conversation_ids', [])) == {record.conversation_id}
        and not any(artifact.get(k) for k in ('cleanup_after', 'erasure_requested', 'write_pending_until')),
        'artifact_identity',
    )
    require(
        manifest.get('owner_id') == record.owner_id
        and manifest.get('conversation_id') == record.conversation_id
        and manifest.get('capture_at') == record.capture_at,
        'manifest_identity',
    )
    context = manifest.get('context') or {}
    expected_context = {
        'owner_id': record.owner_id,
        'conversation_id': record.conversation_id,
        'job_id': record.job_id,
        'content_id': record.content_id,
        'segment_id': record.segment_id,
        'capture_at': record.capture_at,
    }
    require(all(context.get(k) == v for k, v in expected_context.items()), 'manifest_context_identity')
    references = manifest.get('references') or []
    require(
        bool(references)
        and all(
            ref.get('path', '').startswith(
                (
                    f'chunks/{record.owner_id}/{record.conversation_id}/',
                    f'raw-live/{record.owner_id}/{record.conversation_id}/',
                )
            )
            for ref in references
        ),
        'manifest_reference_identity',
    )


def verify_recordings(store, storage, recordings):
    """Read exact receipts and decrypt/materialize each real staged artifact."""
    from database.batch_pipeline_staging import artifact_id
    from utils.batch_pipeline.artifact_policy import create_artifact_store
    from utils.batch_pipeline.artifacts import AUDIO_LIMIT
    from utils.batch_pipeline.contracts import WorkItem
    from utils.batch_pipeline.source_audio import MAGIC, materialize, read_reference

    bucket = os.environ['BUCKET_BATCH_PIPELINE']
    artifacts = create_artifact_store(store, storage, bucket, os.environ['ENCRYPTION_SECRET'].encode())

    def row(table, key):
        return store.client.collection(f'{store.namespace}_{table}').document(key).get().to_dict() or {}

    for record in recordings:
        job = row('jobs', record.segment_id)
        require(job.get('state') == 'ready', 'expected_ready_state')
        uri = job.get('audio_uri') or ''
        intake = row('intakes', record.job_id)
        artifact = row('artifacts', artifact_id(record.segment_id, uri))
        require(bool(artifact), 'missing_artifact')
        item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
        body = artifacts._read(item, uri, 'audio', AUDIO_LIMIT)
        require(body.startswith(MAGIC), 'missing_staged_manifest')
        manifest = json.loads(body[len(MAGIC) :])
        validate_recording(record, job, intake, artifact, manifest, namespace=store.namespace, bucket=bucket)
        allowed = {os.environ['BUCKET_PRIVATE_CLOUD_SYNC'], os.environ['BUCKET_AUDIO_DERIVED']}
        materialize(
            body,
            item,
            lambda ref: read_reference(
                storage, ref, record.owner_id, record.conversation_id, allowed, artifacts.key_for_owner(record.owner_id)
            ),
        )
