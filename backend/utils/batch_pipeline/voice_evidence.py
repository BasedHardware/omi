"""Temporary sync-off speaker evidence, isolated from audio_files and durable caches."""

import logging
import time

import numpy as np

from config.batch_conversation_speakers import sync_off_enabled
from database import batch_voice_evidence as storage
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline import voice_centroids as schema
from utils.speakers.provider_partition import provider_key
from utils.observability.fallback import record_fallback
from utils.stt.speaker_embedding import extract_embedding_from_bytes, speaker_embedding_configured
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)


def unavailable():
    record_fallback(
        component='other',
        from_mode='batch_voice_evidence',
        to_mode='anonymous_batch_labels',
        reason='other',
        outcome='degraded',
        log=logger,
    )


def prepare(projector, item, binding, conversation_id):
    """Called after fenced projection and before enrichment or audio cleanup."""
    if (
        binding.private_cloud_sync_enabled
        or not sync_off_enabled()
        or item.shadow
        or time.time() >= schema.deadline(item.capture_at)
    ):
        return
    store = projector.store.store
    try:
        existing = storage.prepared_reference(store, item)
        if existing:
            storage.publish(store, item, existing, conversation_id)
            return
        if projector.fetch_audio is None or not speaker_embedding_configured():
            unavailable()
            return
        artifacts = artifacts_for(store)
        artifacts.verify_voice_retention()
        job_result = projector.store.ref('results', item.segment_id).get().to_dict() or {}
        payload = projector.load_result(item, job_result['result']['result_uri'])
        if payload.get('recovery_version') == 1:
            return  # Recovered provider words do not have pyannote authority.
        wav = projector.fetch_audio(item)
        stop = time.monotonic() + 8

        def embed(clip):
            remaining = stop - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('voice extraction budget')
            # Never populate the cross-conversation process embedding cache.
            return extract_embedding_from_bytes(clip, 'batch_voice.wav', timeout=min(3, remaining), use_cache=False)

        payload = schema.extract(wav, payload['diarization']['turns'], item.capture_at, embed, execution_deadline=stop)
        del wav
        if not payload['labels']:
            return
        uri = artifacts.persist_voice_evidence(item, payload)
        try:
            storage.publish(store, item, uri, conversation_id)
        except (BatchPrivacyBlocked, PermissionError):
            artifacts.discard_voice_evidence(item, uri)
            raise
    except Exception as error:
        unavailable()
        logger.warning('event=batch_voice_evidence outcome=unavailable exception_type=%s', type(error).__name__)


def load_vectors(uid, conversation, deadline, *, store=None, artifacts=None):
    """Every read rechecks binding/generation/expiry; no audio or cache fallback."""
    if not sync_off_enabled():
        return {}, {}, lambda: None
    store = store or FirestoreStore(f'batch_pipeline_{current_stage()}')
    artifacts = artifacts or artifacts_for(store)
    grouped = {}
    for segment in conversation.transcript_segments:
        key = provider_key(segment)
        if key is None or segment.speaker_match_source == 'batch_abstention':
            continue
        scope = key[0].split('\0')[-1]
        if scope.startswith('final:batch:') and not scope.startswith('final:batch:conversation:'):
            grouped.setdefault(scope.removeprefix('final:batch:'), []).append((segment, key[1]))
    vectors, seconds, checks = {}, {}, []
    byte_count, label_count = 0, 0
    for unit, segments in grouped.items():
        if time.monotonic() >= deadline:
            break
        reference = storage.load_reference(store, uid, unit, conversation.id)
        if reference is None:
            continue
        item, uri, due = reference
        payload = artifacts.load_voice_evidence(item, uri, expires_at=due)
        byte_count += len(schema.encode(payload))
        label_count += len(payload['labels'])
        if byte_count > 2 * 1024 * 1024 or label_count > 1024:
            break
        # No upload/replay can refresh the earliest contributor's expiry.
        checks.append((unit, uri, due))
        labels = {int(row['label'].split('_')[1]): row for row in payload['labels']}
        label_vectors = {label: np.asarray(row['vector'], dtype=np.float32) for label, row in labels.items()}
        used = set()
        for segment, label in segments:
            row = labels.get(label)
            if row is None or segment.end - segment.start < 1:
                continue
            vectors[segment.id] = label_vectors[label]
            seconds[segment.id] = row['seconds'] if label not in used else 0.0
            used.add(label)

    # Repeat authority checks after IO, and again at the caller before projection.
    def validate():
        for unit, uri, due in checks:
            current = storage.load_reference(store, uid, unit, conversation.id)
            if current is None or current[1] != uri or time.time() >= min(due, current[2]):
                raise PermissionError('voice evidence revoked or expired')

    validate()
    return vectors, seconds, validate
