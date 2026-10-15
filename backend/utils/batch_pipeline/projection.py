"""Replayable projection of committed batch output through legacy sync intake.

Synchronous worker seam: offload the call from an async serving coordinator.
No admission flag is consulted: already accepted work drains after rollback.
"""

from datetime import datetime, timezone
import time
import math
import logging
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay, ProjectionStore
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.contracts import WorkItem

logger = logging.getLogger(__name__)


def build_incoming(item: WorkItem, binding, payload: dict, *, geolocation=None) -> dict:
    """Use legacy word alignment, segment grouping and minimum conversation shape."""
    from models.conversation import Conversation, CreateConversation
    from models.conversation_enums import ConversationSource
    from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
    from utils.conversations.final_pass_assignment import assign_words
    from utils.stt.pre_recorded import postprocess_words
    from utils.sync.capture import chunk_identity

    from diarizer.batch_pipeline import validate_words

    words = validate_words(payload['words'], float(payload['audio_seconds']))
    if not words:
        raise ValueError('successful batch result must contain words')
    duration = float(payload['audio_seconds'])
    if not 0 < duration <= 7200 or abs(duration - item.duration_seconds) > 0.1:
        raise ValueError('result audio duration differs from admitted capture')
    # The existing final-pass aligner abstains in diarization gaps; the existing
    # prerecorded grouper supplies the same sentence/segment shapes as sync.
    aligned = assign_words(words, payload['diarization']['turns'])
    segments = postprocess_words([{**word, 'text': word['word']} for word in aligned], 0)
    if not segments:
        raise ValueError('successful batch result produced no transcript')
    # Legacy sync transcribes a VAD-isolated file whose capture timestamp is
    # already shifted. Batch words cover the full capture; undo the grouper's
    # first-word normalization to keep absolute speech/playback clocks intact.
    offset = round(float(words[0]['timestamp'][0]), 2)
    for index, segment in enumerate(segments):
        segment.start = round(segment.start + offset, 2)
        segment.end = round(segment.end + offset, 2)
        segment.id = str(uuid5(NAMESPACE_URL, f'batch:{item.segment_id}:{index}'))
        segment.speaker_id_scope = f'sync:{item.segment_id}'
        segment.stt_provider = payload.get('words_provider')
    started = datetime.fromtimestamp(item.capture_at, timezone.utc)
    create = CreateConversation(
        started_at=started,
        finished_at=datetime.fromtimestamp(item.capture_at + max(s.end for s in segments), timezone.utc),
        transcript_segments=segments,
        source=ConversationSource(binding.source),
        language=binding.language or payload.get('language'),
        is_locked=binding.is_locked,
        private_cloud_sync_enabled=binding.private_cloud_sync_enabled,
        client_device_id=binding.client_device_id,
        client_platform=binding.client_platform,
        geolocation=geolocation,
    )
    incoming = Conversation(
        id=chunk_identity(item.owner_id, binding.source, binding.client_device_id, binding.is_locked, item.capture_at),
        created_at=started,
        structured=build_deterministic_minimum_structured(create),
        **create.model_dump(),
    ).model_dump()
    incoming['data_protection_level'] = binding.data_protection_level
    from utils.sync.intake_completion import apply_capture_evidence_dark_write

    apply_capture_evidence_dark_write(incoming, None, segments)
    return incoming


def publish_client_completion(binding, result: dict) -> None:
    """A current Redis lease publishes only the already durable ledger result.

    Missing Redis jobs are recovered by intake/WAL from the content ledger;
    they must never make an accepted job eligible for legacy compute again.
    """
    from database.sync_jobs import (
        get_sync_job,
        try_acquire_sync_job_run_lock,
        release_job_run_lock,
        fenced_finalize_sync_job_from_durable_ledger,
    )

    job = get_sync_job(binding.job_id)
    if job is None:
        return
    if job.get('uid') != binding.owner_id or job.get('content_id') != binding.content_id:
        raise ProjectionBlocked('client job binding mismatch')
    if job.get('status') == 'completed' and job.get('result') == result:
        return
    token = try_acquire_sync_job_run_lock(binding.job_id)
    if token is None:
        raise ProjectionBlocked('client job publication lease busy')
    try:
        mutation = fenced_finalize_sync_job_from_durable_ledger(binding.job_id, token, result)
        if not mutation.applied:
            raise ProjectionBlocked('client job publication fenced')
    finally:
        release_job_run_lock(binding.job_id, token)


class Projector:
    def __init__(
        self,
        store: FirestoreStore,
        load_result: Callable[[WorkItem, str], dict],
        *,
        publish: Callable = publish_client_completion,
        playback: Callable | None = None,
        fetch_audio: Callable[[WorkItem], bytes] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.store = ProjectionStore(store)
        self.load_result, self.publish, self.playback, self.clock = load_result, publish, playback, clock
        self.fetch_audio = fetch_audio

    def project(self, segment_id: str) -> dict | None:
        from database.conversations import assign_sync_conversation

        job, entry, binding = self.store.read(segment_id)
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        session = self.store.session(segment_id, binding, self.clock())
        try:
            # Check replay/order/privacy before downloading any transcript body.
            self.store.check(session)
            if entry['result']['outcome'] == 'silence':
                receipt = session.persist_empty()
            else:
                payload = self.load_result(item, entry['result']['result_uri'])
                from utils.batch_pipeline.context import ResolvedContext, resolve_context

                context = ResolvedContext(binding.target_conversation_id)
                if item.requires_compute_admission:
                    if self.fetch_audio is None:
                        raise ProjectionBlocked('authenticated intake manifest loader required')
                    from utils.batch_pipeline.audio import read_context

                    context = resolve_context(item, binding, read_context(self.fetch_audio(item)), self.store.client)
                incoming = build_incoming(item, binding, payload, geolocation=context.geolocation)
                if context.binding_reason is not None and context.target_id:
                    incoming['_sync_lineage_binding'] = context.binding_reason
                from utils.conversation_continuity import intervals_connect

                segments = incoming['transcript_segments']
                if any(
                    not intervals_connect(a['start'], a['end'], b['start'], b['end'])
                    for a, b in zip(segments, segments[1:])
                ):
                    raise ProjectionBlocked('capture spans multiple legacy conversation groups')
                speech = payload.get('speech_seconds')
                if (
                    not isinstance(speech, (int, float))
                    or not math.isfinite(speech)
                    or not 0 < speech <= float(payload['audio_seconds'])
                ):
                    raise ProjectionBlocked('validated VAD speech accounting required')
                session.speech_seconds = float(speech)
                session.incoming_segment_count = len(incoming['transcript_segments'])
                receipt_box = []

                def persisted(transaction, planned):
                    receipt_box[:] = [session.persist(transaction, planned)]

                candidate = None
                if context.target_id is None:
                    from database.conversations import get_closest_conversation_to_timestamps

                    candidate = get_closest_conversation_to_timestamps(
                        binding.owner_id,
                        int(incoming['started_at'].timestamp()),
                        int(incoming['finished_at'].timestamp()),
                    )
                assign_sync_conversation(
                    binding.owner_id,
                    incoming,
                    target_id=context.target_id,
                    candidate_id=candidate['id'] if candidate else None,
                    firestore_client=self.store.client,
                    before_assign=session.prepare,
                    validate_plan=session.validate_plan,
                    after_assign=persisted,
                )
                receipt = receipt_box[0]
        except ProjectionReplay as replay:
            receipt = replay.receipt
        if receipt['state'] != 'ready':
            if receipt.get('conversation_id'):
                # Retractions/audio copying use the same replayable bridge helper.
                from utils.sync.bridge import finish_sync_bridges

                canonical = finish_sync_bridges(binding.owner_id, receipt['conversation_id'])
                if receipt.get('audio_required'):
                    if self.playback is not None:
                        self.playback(item, canonical)
                    else:
                        self.persist_playback(item, binding, canonical, receipt)
                if receipt['enrichment_required']:
                    self.store.mark_enrichment(segment_id, binding, self.clock(), canonical, receipt['language'])
                else:
                    self.store.ready(segment_id, binding, self.clock())
            else:
                self.store.ready(segment_id, binding, self.clock())
        accounting = self.store.prepare_accounting(binding, self.clock())
        if accounting is None:
            return None
        if accounting['seconds'] > 0 and not accounting['completed']:
            from utils.fair_use import record_speech_ms

            record_speech_ms(
                binding.owner_id,
                int(accounting['seconds'] * 1000),
                source=accounting['source'],
                idempotency_key=binding.content_id,
                raise_on_error=True,
            )
        result = self.store.complete(segment_id, binding, self.clock(), accounting)
        if result is not None:
            self.publish(binding, result)
            from utils.batch_pipeline.retention import expire_completed_segment

            if not expire_completed_segment(self.store.store, binding.owner_id, segment_id, self.clock()):
                raise ProjectionBlocked('completion retention receipt unavailable')
            self.store.acknowledge(segment_id, binding, self.clock())
        return result

    def persist_playback(self, item: WorkItem, binding, canonical: str, receipt: dict):
        if self.fetch_audio is None:
            raise ProjectionBlocked('private playback requires ArtifactStore.fetch_audio')
        from database.conversations import decode_transcript_segments_verified

        # Reconstruct only this input's retained ranges from the stored legacy
        # transcript. Never put transcripts or unbounded survivor IDs in receipts.
        row = (
            self.store.client.collection('users')
            .document(binding.owner_id)
            .collection('conversations')
            .document(canonical)
            .get()
            .to_dict()
            or {}
        )
        if not row or row.get('deleted'):
            raise ProjectionBlocked('playback target deleted')
        segments = decode_transcript_segments_verified(
            binding.owner_id,
            row.get('transcript_segments'),
            bool(row.get('transcript_segments_compressed')),
        )
        origin = row['started_at'].timestamp()
        survivors = []
        for segment in segments:
            if segment.get('speaker_id_scope') == f'sync:{item.segment_id}':
                stamp = origin + segment['start']
                survivors.append(
                    {
                        **segment,
                        'timestamp': stamp,
                        'start': stamp - item.capture_at,
                        'end': origin + segment['end'] - item.capture_at,
                    }
                )
        if not survivors:
            return
        audio = self.fetch_audio(item)
        # Deliberately share the legacy audio persistence and partial-overlap
        # policy; its stable chunk timestamps make replay an overwrite.
        from utils.sync.merge_audio import store_intake_audio

        store_intake_audio(
            binding.owner_id,
            item.capture_at,
            audio,
            binding.data_protection_level,
            survivors,
            receipt['incoming_segment_count'],
            True,
            canonical,
        )

    def status(self, uid: str, content_id: str) -> dict | None:
        return self.store.status(uid, content_id)

    def sweep(self, limit: int = 100) -> dict[str, int]:
        """Bounded durable-log recovery; no in-memory callback is an outbox."""
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        counts = {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
        for segment_id in self.store.store.projection_pending(limit=max(1, min(limit, 100))):
            try:
                result = self.project(segment_id)
                counts['completed' if result is not None else 'waiting'] += 1
            except (ProjectionBlocked, BatchPrivacyBlocked):
                counts['blocked'] += 1
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s', type(error).__name__
                )
        return counts
