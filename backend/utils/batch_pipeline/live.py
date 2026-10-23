"""Durable live/desktop admission, drained on the existing CPU reconciliation loop.

Capture reserves its route in the existing conversation create. Finalization
registers a privacy-fenced pending job before closing its own durable job. No
Firestore reads are added to audio frames, provisional segments or pusher flush.
"""

from dataclasses import replace
from collections.abc import Generator
from typing import Any
import hashlib
import json
import logging
import os
import time

from config.policy import resolve_batch_policy
from database.batch_pipeline_policy import load_job_policy
from database.batch_ramp import ramp_admission_policy
from config.batch_pipeline import Priority, RecordOwnerContention, record_capture_eligible
from database.conversations import claim_record_lane_owner
from database.batch_pipeline_intake import admit
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.source_audio import MAGIC, MAX_REFERENCES, read_reference
from utils.executors import db_executor, storage_executor, sync_executor, run_blocking
from utils.other.local_storage import create_storage_client
from utils.other.storage import list_audio_chunks, private_cloud_sync_bucket
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)
OWNER = 'batch_live_v1'
UPLOAD_GRACE_SECONDS = 0


def record_identity(uid: str, conversation_id: str) -> tuple[str, str]:
    content = hashlib.sha256(f'record-v1:{uid}:{conversation_id}'.encode()).hexdigest()
    return content, hashlib.sha256(f'{content}:0'.encode()).hexdigest()


def reserve_recording(uid: str, conversation: dict) -> str | None:
    """Cover captures already in progress at enablement, before legacy admission."""
    owner = conversation.get('record_lane_owner')
    if owner:
        return owner
    policy = resolve_batch_policy(uid)
    if conversation.get('status') not in {'in_progress', 'processing'} or not record_capture_eligible(
        uid, conversation, policy=policy
    ):
        return None
    if not ramp_admission_policy(uid, policy).live_record_enabled:
        return None
    revision = claim_record_lane_owner(uid, conversation['id'], OWNER, conversation.get('updated_at'))
    if revision is None:
        raise RecordOwnerContention('record route snapshot changed')
    conversation.update(record_lane_owner=OWNER, updated_at=revision)
    return OWNER


def register_recording(uid: str, conversation: dict, *, store=None, now=None) -> bool:
    if conversation.get('record_lane_owner') != OWNER:
        return False
    if conversation.get('deleted') or conversation.get('discarded') or conversation.get('uses_custom_stt'):
        return False
    if not conversation.get('private_cloud_sync_enabled'):
        return False
    store = store or shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))
    now = time.time() if now is None else now
    content, segment = record_identity(uid, conversation['id'])
    # The immutable native owner is main's earlier admission receipt. A later
    # cohort rollback cannot cancel it before finalization registers the unit.
    policy = replace(
        resolve_batch_policy(uid), batch_enabled=True, live_admission_enabled=True, live_record_enabled=True
    )
    snapshot = {
        key: conversation.get(key)
        for key in (
            'id',
            'source',
            'language',
            'client_device_id',
            'client_platform',
            'started_at',
            'finished_at',
            'data_protection_level',
        )
    }

    def commit(tx):
        previous = tx.get('jobs', segment)
        if previous:
            return True
        generation = tx.check_privacy(uid, (conversation['id'],))
        tx.put(
            'jobs',
            segment,
            {
                'segment_id': segment,
                'owner_id': uid,
                'owner_key': owner_key(uid),
                'conversation_id': conversation['id'],
                'privacy_generation': generation,
                'priority': int(Priority.FRESH),
                'state': 'record_pending',
                'available_at': now + UPLOAD_GRACE_SECONDS,
                'enqueued_at': now,
                'record_content_id': content,
                'record_snapshot': snapshot,
                'policy': policy.to_dict(),
                'policy_source': 'admission',
                'merge_pending': False,
            },
        )
        return True

    return store.run(commit)


def _units(
    uid, conversation_id, chunks, client, key
) -> Generator[tuple[float, float, list[dict[str, Any]]], None, None]:
    """Bounded one-hour units, preserving capture clocks and verified overlaps."""
    allowed = {private_cloud_sync_bucket, os.getenv('BUCKET_AUDIO_DERIVED', '').strip()}
    references, start, end, previous_pcm = [], None, None, b''
    for chunk in chunks:
        ref = {
            'path': chunk['path'],
            'bucket': chunk.get('bucket', private_cloud_sync_bucket),
            'generation': int(chunk['generation']),
            'sample_rate': int((chunk.get('span') or {}).get('sample_rate', 16000)),
        }
        # Metadata is tied to the same immutable object version used by readers.
        blob = client.bucket(ref['bucket']).blob(ref['path'], generation=ref['generation'])
        blob.reload(if_generation_match=ref['generation'], timeout=30, retry=None)
        ref['metadata'] = blob.metadata or {}
        if not chunk.get('span'):
            ref['sample_rate'] = int(ref['metadata'].get('record_sample_rate', 16000))
        pcm = read_reference(client, ref, uid, conversation_id, allowed, key)
        if not pcm or len(pcm) % 2:
            raise ValueError('retained source has no aligned audio')
        source_digest = hashlib.sha256(pcm).hexdigest()
        source_skip = 0
        capture = float(chunk['timestamp'])
        if end is not None and capture < end - 1 / 16000:
            # Reject an ambiguous overlap rather than process it twice or drop it.
            # Raw and PCM representations must prove the same overlapping bytes.
            overlap = round((end - capture) * 16000) * 2
            if overlap > len(previous_pcm) or pcm[:overlap] != previous_pcm[-overlap:]:
                raise ValueError('conflicting retained audio overlap')
            source_skip = overlap // 2
            pcm, capture = pcm[overlap:], end
            if not pcm:
                continue
        if start is not None and end is not None and capture - end > 30:
            yield start, end - start, references
            references, start = [], None
        offset = 0
        while offset < len(pcm):
            if start is None:
                start = capture + offset / 32000
            position = round((capture + offset / 32000 - start) * 16000)
            if position >= 3600 * 16000:
                if end is None:
                    raise ValueError('unit has no capture end')
                yield start, end - start, references
                references, start = [], None
                continue
            frames = min(len(pcm[offset:]) // 2, 3600 * 16000 - position)
            references.append(
                {
                    **ref,
                    'pcm_sha256': source_digest,
                    'start_frame': position,
                    'offset_frame': source_skip + offset // 2,
                    'frames': frames,
                }
            )
            if len(references) > MAX_REFERENCES:
                raise ValueError('retained capture reference budget exceeded')
            offset += frames * 2
            end = capture + offset / 32000
            if position + frames == 3600 * 16000:
                yield start, end - start, references
                references, start = [], None
        previous_pcm = pcm
    if references and start is not None and end is not None:
        yield start, end - start, references


async def admit_recording(store, pending, *, now=None):
    now = time.time() if now is None else now
    uid, conversation_id = pending['owner_id'], pending['conversation_id']
    row = pending['record_snapshot']
    content = pending['record_content_id']

    def read_current():
        return (
            store.client.collection('users')
            .document(uid)
            .collection('conversations')
            .document(conversation_id)
            .get()
            .to_dict()
            or {}
        )

    current = await run_blocking(db_executor, read_current)
    if current.get('status') != 'completed' or not current.get('record_audio_closed'):
        raise ValueError('capture upload/finalization barrier not closed')
    client = await run_blocking(storage_executor, create_storage_client)
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    artifacts = create_artifact_store(store, client, bucket, os.getenv('ENCRYPTION_SECRET', '').encode())
    # A failed raw-archive listing raises (drain retries in 60 s) rather than
    # admitting a recording whose later packs are silently missing.
    chunks = await run_blocking(
        storage_executor, list_audio_chunks, uid, conversation_id, max_count=4096, require_archive=True
    )
    if not chunks:
        raise ValueError('retained capture not durable yet')
    seed = WorkItem(
        pending['segment_id'],
        uid,
        0,
        'record:pending',
        1,
        Priority.FRESH,
        conversation_id=conversation_id,
        privacy_generation=pending['privacy_generation'],
    )
    protection = await run_blocking(db_executor, artifacts.authorize, seed)
    iterator = _units(uid, conversation_id, chunks, client, artifacts.key_for_owner(uid))
    units = []
    try:
        while unit := await run_blocking(sync_executor, next, iterator, None):
            units.append(unit)
            if len(units) > 128:
                raise ValueError('retained capture unit budget exceeded')
    finally:
        iterator.close()
    if not 1 <= len(units) <= 128:
        raise ValueError('retained capture unit budget exceeded')
    # Never claim a successful record whose final recognized speech is missing
    # from the durable upload. The pending obligation has no TTL.
    finish = row.get('finished_at')
    if finish is not None and units[-1][0] + units[-1][1] + 0.1 < finish.timestamp():
        raise ValueError('retained capture tail not durable yet')
    items = [
        WorkItem(
            hashlib.sha256(f'{content}:{i}'.encode()).hexdigest(),
            uid,
            start,
            'record:pending',
            duration,
            Priority.FRESH,
            conversation_id=conversation_id,
            privacy_generation=pending['privacy_generation'],
            requires_compute_admission=True,
        )
        for i, (start, duration, _) in enumerate(units)
    ]
    _, policy = await run_blocking(db_executor, load_job_policy, store, pending['segment_id'])
    binding = ProjectionBinding(
        uid,
        'bp_' + content,
        content,
        tuple(i.segment_id for i in items),
        source=row.get('source') or 'omi',
        client_device_id=row.get('client_device_id'),
        client_platform=row.get('client_platform'),
        private_cloud_sync_enabled=True,
        target_conversation_id=conversation_id,
        privacy_generation=pending['privacy_generation'],
        language=row.get('language'),
        data_protection_level=protection.level,
        record_origin=True,
        native_record=True,
    )
    staged = []
    for item, (_, _, refs) in zip(items, units):
        context = {
            'owner_id': uid,
            'job_id': binding.job_id,
            'content_id': content,
            'segment_id': item.segment_id,
            'capture_at': item.capture_at,
            'source': binding.source,
            'should_lock': False,
            'client_device_id': binding.client_device_id,
            'client_platform': binding.client_platform,
            'conversation_id': conversation_id,
            # Native record admission already requires a fully supported
            # declared language profile. Preserve that proof in its manifest.
            'stt_language': binding.language or '',
            'stt_language_evidence': 'declared',
            'stt_language_confidence': 1.0,
        }
        manifest = {
            'owner_id': uid,
            'conversation_id': conversation_id,
            'capture_at': item.capture_at,
            'references': refs,
            'context': context,
        }
        uri = await run_blocking(
            storage_executor, artifacts.stage_audio, item, MAGIC + json.dumps(manifest, separators=(',', ':')).encode()
        )
        staged.append(replace(item, audio_uri=uri))
    return await run_blocking(
        db_executor,
        admit,
        store,
        staged,
        binding,
        now,
        namespace=store.namespace,
        policy=policy,
        require_artifacts=True,
        intake={
            'owner_id': uid,
            'owner_key': owner_key(uid),
            'content_id': content,
            'conversation_id': conversation_id,
            'segment_ids': list(binding.segment_ids),
            'total_files': len(chunks),
            'total_audio_seconds': sum(i.duration_seconds for i in staged),
            'lane': 'fresh',
            'record_ranges': [{'start': i.capture_at, 'end': i.capture_at + i.duration_seconds} for i in staged],
        },
    )


async def drain_recordings(store):
    segments = await run_blocking(db_executor, store.due, 'record_pending', time.time(), 10)
    for segment in segments:
        pending = await run_blocking(db_executor, store.run, lambda tx: tx.get('jobs', segment))
        if pending.get('state') != 'record_pending':
            continue
        try:
            await admit_recording(store, pending)
        except BatchPrivacyBlocked:
            # Privacy cleanup owns erasure; an admission retry cannot bypass it.
            continue
        except Exception as error:
            logger.warning('event=batch_live_admission outcome=retry exception_type=%s', type(error).__name__)

            def defer(tx):
                latest = tx.get('jobs', segment)
                if latest.get('state') == 'record_pending':
                    latest['available_at'] = time.time() + 60
                    tx.put('jobs', segment, latest)

            await run_blocking(db_executor, store.run, defer)
