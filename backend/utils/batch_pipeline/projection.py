"""Replayable projection of committed batch output through legacy sync intake.

Synchronous worker seam: offload the call from an async serving coordinator.
No admission flag is consulted: already accepted work drains after rollback.
"""

from config.stt_cap_dispatch import enabled as cap_dispatch_enabled
from config.batch_pipeline import (
    authoritative_labels_enabled,
    require_live_target_enabled,
    projection_contention_enabled,
    async_projection_enabled,
    projection_timing_enabled,
)
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import time
import math
import logging
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay, ProjectionStore
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from database import conversations as conversations_db
from utils.batch_pipeline.contracts import WorkItem, projection_speech_spans
from utils.batch_pipeline.correctness_metrics import record_labels
from utils.batch_pipeline.recovery_disposition import result_outcome
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.scheduler import owner_key

logger = logging.getLogger(__name__)


@contextmanager
def projection_phase(phase: str) -> Iterator[None]:
    """Static phase tokens only; never log bindings, payloads or exception text."""
    if not projection_timing_enabled():
        yield
        return
    started = time.monotonic()
    logger.info('event=batch_projection_phase phase=%s outcome=started', phase)
    try:
        yield
    except Exception as error:
        logger.info(
            'event=batch_projection_phase phase=%s outcome=error elapsed_ms=%d exception_type=%s',
            phase,
            int((time.monotonic() - started) * 1000),
            type(error).__name__,
        )
        raise
    else:
        logger.info(
            'event=batch_projection_phase phase=%s outcome=completed elapsed_ms=%d',
            phase,
            int((time.monotonic() - started) * 1000),
        )


def build_incoming(item: WorkItem, binding, payload: dict, *, geolocation=None, batch_segment_id=None) -> dict:
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
    aligned = words if payload.get('recovery_version') == 1 else assign_words(words, payload['diarization']['turns'])
    authoritative = (binding.record_origin or authoritative_labels_enabled()) and payload.get('recovery_version') != 1
    if authoritative:
        # The legacy grouper imputes None from adjacent voices. Keep each gap an
        # explicit anonymous abstention instead of borrowing a speaker/owner.
        gap = 0
        in_gap = False
        prepared = []
        for word in aligned:
            if word['speaker'] is None:
                if not in_gap:
                    gap += 1
                in_gap = True
                word = {**word, 'speaker': f'BATCH_UNASSIGNED_{item.segment_id}_{gap}'}
            else:
                in_gap = False
            prepared.append(word)
        aligned = prepared
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
        segment.speaker_id_scope = (
            f'final:batch:{batch_segment_id or item.segment_id}' if authoritative else f'sync:{item.segment_id}'
        )
        segment.stt_provider = payload.get('words_provider')
        if authoritative:
            abstained = (segment.speaker or '').startswith('BATCH_UNASSIGNED_')
            segment.is_user, segment.person_id = False, None
            segment.speaker_identity_status = 'ambiguous' if abstained else 'no_match'
            segment.speaker_match_source = 'batch_abstention' if abstained else 'batch_pyannote'
    started = datetime.fromtimestamp(item.capture_at, timezone.utc)
    create = CreateConversation(
        started_at=started,
        finished_at=datetime.fromtimestamp(item.capture_at + max(s.end for s in segments), timezone.utc),
        transcript_segments=segments,
        source=ConversationSource(binding.source),
        language=binding.language or payload.get('language'),
        is_locked=False if cap_dispatch_enabled() else binding.is_locked,
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

    if binding.native_record:
        return
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
        self.followups = None
        self.discovery = ProjectionDiscovery(store)

    def persist(self, segment_id: str) -> None:
        """Only ordered assignment holds the owner claim; receipts are the outbox."""
        with projection_phase('read'):
            job, entry, binding = self.store.read(segment_id)
        with projection_claim(self.store.store.namespace, owner_key(binding.owner_id)) as acquired:
            if not acquired:
                raise ProjectionBlocked('projection assignment claim busy')
            self._assign(segment_id, job, entry, binding, finish=False)

    async def start_followups(self):
        # Imported lazily: the synchronous worker seam remains lightweight.
        from utils.batch_pipeline.projection_followup import ProjectionFollowups

        if self.followups is None:
            self.followups = ProjectionFollowups(self)
        await self.followups.schedule()

    def project(self, segment_id: str) -> dict | None:
        if async_projection_enabled():
            self.persist(segment_id)
            job, entry, binding = self.store.read(segment_id)
            return self._finish(segment_id, job, entry, binding)
        with projection_phase('read'):
            job, entry, binding = self.store.read(segment_id)
        if projection_contention_enabled():
            with projection_claim(self.store.store.namespace, owner_key(binding.owner_id)) as acquired:
                if not acquired:
                    logger.info('event=batch_projection action=claim outcome=busy')
                    return None
                with projection_phase('project'):
                    result = self._project(segment_id, job, entry, binding)
                logger.info(
                    'event=batch_projection action=project outcome=%s',
                    'completed' if result is not None else 'waiting',
                )
                return result
        with projection_phase('project'):
            return self._project(segment_id, job, entry, binding)

    def _project(self, segment_id, job, entry, binding):
        self._assign(segment_id, job, entry, binding)
        return self._finish(segment_id, job, entry, binding)

    def _assign(self, segment_id, job, entry, binding, *, finish=True):
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        session = self.store.session(segment_id, binding, self.clock())
        try:
            with projection_phase('predecessor'):
                self.store.check(session)
        except ProjectionReplay:
            pass
        else:
            if entry['result']['outcome'] in {'silence', 'no_recoverable_speech'}:
                if entry['result']['outcome'] == 'no_recoverable_speech':
                    payload = self.load_result(item, entry['result']['result_uri'])
                    if (
                        entry.get('recovery_version') != 1
                        or result_outcome(payload) != 'no_recoverable_speech'
                        or abs(payload['audio_seconds'] - item.duration_seconds) > 0.1
                    ):
                        raise ProjectionBlocked('terminal empty recovery evidence required')
                try:
                    if binding.record_origin:
                        self.assign_record_silence(item, binding, session)
                    else:
                        session.persist_empty()
                except ProjectionReplay:
                    if not projection_contention_enabled():
                        raise
                    # A receipt is assignment progress, not completion. Resume
                    # every post-persist obligation after losing the empty race.
            else:
                with projection_phase('assignment'):
                    self.assign_parts(item, entry, binding, finish=finish)

    def _finish(self, segment_id, job, entry, binding):
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        entry = self.store.ref('results', segment_id).get().to_dict() or {}
        parts = entry.get('projection_parts')
        for index, receipt in (
            sorted(parts.items(), key=lambda pair: int(pair[0])) if parts else [(None, entry['projection'])]
        ):
            self.finish_part(item, binding, receipt, int(index) if index is not None else None)
        return self.complete_content(item.segment_id, binding)

    def complete_content(self, segment_id, binding):
        with projection_phase('accounting'):
            accounting = self.store.prepare_accounting(binding, self.clock())
        if accounting is None:
            self.store.hold_for_quarantine(segment_id, binding, self.clock())
            return None
        if accounting['seconds'] > 0 and not accounting['completed']:
            from utils.fair_use import record_speech_ms

            with projection_phase('usage'):
                record_speech_ms(
                    binding.owner_id,
                    int(accounting['seconds'] * 1000),
                    source=accounting['source'],
                    idempotency_key=binding.content_id,
                    raise_on_error=True,
                )
        with projection_phase('completion'):
            result = self.store.complete(segment_id, binding, self.clock(), accounting)
        if result is not None:
            with projection_phase('publication'):
                self.publish(binding, result)
            from utils.batch_pipeline.retention import expire_completed_segment

            for sibling in binding.segment_ids:
                retained = self.store.ref('results', sibling).get().to_dict() or {}
                if retained.get('projection_state') == 'erased':
                    continue
                with projection_phase('retention'):
                    if not expire_completed_segment(self.store.store, binding.owner_id, sibling, self.clock()):
                        raise ProjectionBlocked('completion retention receipt unavailable')
                    self.store.acknowledge(sibling, binding, self.clock())
        return result

    def assign_record_silence(self, item, binding, session):
        incoming = {
            'id': binding.target_conversation_id,
            'started_at': datetime.fromtimestamp(item.capture_at, timezone.utc),
            'finished_at': datetime.fromtimestamp(item.capture_at + item.duration_seconds, timezone.utc),
            'transcript_segments': [],
            'data_protection_level': binding.data_protection_level,
            '_batch_require_live_target': True,
            '_batch_replace_live': {'start': item.capture_at, 'end': item.capture_at + item.duration_seconds},
        }
        conversations_db.assign_sync_conversation(
            binding.owner_id,
            incoming,
            target_id=binding.target_conversation_id,
            firestore_client=self.store.client,
            before_assign=session.prepare,
            validate_plan=session.validate_plan,
            after_assign=lambda transaction, planned: session.persist(transaction, planned),
            retry_contention=projection_contention_enabled(),
        )

    def assign_parts(self, item, entry, binding, *, finish=True):
        from database.conversations import get_closest_conversation_to_timestamps
        from utils.batch_pipeline.context import ResolvedContext, resolve_context
        from utils.batch_pipeline.projection_parts import split_result

        payload = self.load_result(item, entry['result']['result_uri'])
        if payload.get('recovery_version') == 1 and entry.get('recovery_version') != 1:
            raise ProjectionBlocked('recovery result requires recovery handoff')
        speech = payload.get('speech_seconds')
        if (
            not isinstance(speech, (int, float))
            or isinstance(speech, bool)
            or not math.isfinite(speech)
            or not 0 < speech <= float(payload['audio_seconds'])
        ):
            raise ProjectionBlocked('validated VAD speech accounting required')
        if binding.record_origin:
            projection_speech_spans(payload, item.duration_seconds)
        parts = [(item, payload)] if binding.record_origin else split_result(item, payload)
        manifest = None
        if item.requires_compute_admission:
            if self.fetch_audio is None:
                raise ProjectionBlocked('authenticated intake manifest loader required')
            from utils.batch_pipeline.audio import read_context

            manifest = read_context(self.fetch_audio(item))
        for index, (part, part_payload) in enumerate(parts):
            session = self.store.session(
                item.segment_id,
                binding,
                self.clock(),
                part_index=index,
                part_count=len(parts),
            )
            session.capture_at, session.audio_end = part.capture_at, part.capture_at + part.duration_seconds
            session.speaker_scope = f'sync:{part.segment_id}'
            session.speech_seconds = float(part_payload['speech_seconds'])
            session.total_speech_seconds = float(speech)
            try:
                # Resume at the first uncommitted group before rebuilding it.
                self.store.check(session)
                context = ResolvedContext(binding.target_conversation_id)
                if manifest is not None:
                    context = resolve_context(item, binding, manifest, self.store.client, projection_item=part)
                if not part_payload['words']:
                    receipt = session.persist_empty()
                else:
                    incoming = build_incoming(
                        part, binding, part_payload, geolocation=context.geolocation, batch_segment_id=item.segment_id
                    )
                    session.speaker_scope = incoming['transcript_segments'][0]['speaker_id_scope']
                    if binding.record_origin:
                        incoming['_batch_replace_live'] = {
                            'start': item.capture_at,
                            'end': item.capture_at + item.duration_seconds,
                        }
                    if (binding.record_origin or require_live_target_enabled()) and context.target_id:
                        incoming['_batch_require_live_target'] = True
                    if context.binding_reason is not None and context.target_id:
                        incoming['_sync_lineage_binding'] = context.binding_reason
                    session.incoming_segment_count = len(incoming['transcript_segments'])
                    receipt_box = []

                    def persisted(transaction, planned):
                        receipt_box[:] = [session.persist(transaction, planned)]

                    candidate = None
                    if context.target_id is None:
                        candidate = get_closest_conversation_to_timestamps(
                            binding.owner_id,
                            int(incoming['started_at'].timestamp()),
                            int(incoming['finished_at'].timestamp()),
                        )
                    assigned = conversations_db.assign_sync_conversation(
                        binding.owner_id,
                        incoming,
                        target_id=context.target_id,
                        candidate_id=candidate['id'] if candidate else None,
                        firestore_client=self.store.client,
                        before_assign=session.prepare,
                        validate_plan=session.validate_plan,
                        after_assign=persisted,
                        retry_contention=projection_contention_enabled(),
                    )
                    receipt = receipt_box[0]
                    record_labels(assigned[2])
            except ProjectionReplay as replay:
                receipt = replay.receipt
            except Exception as error:
                if projection_contention_enabled():
                    logger.error(
                        'event=batch_projection action=assignment outcome=error exception_type=%s', type(error).__name__
                    )
                raise
            if finish:
                self.finish_part(item, binding, receipt, index)

    def finish_part(self, item, binding, receipt, index):
        if receipt['state'] == 'ready':
            return
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            with projection_phase('bridge'):
                canonical = (
                    receipt['conversation_id']
                    if binding.record_origin
                    else finish_sync_bridges(binding.owner_id, receipt['conversation_id'])
                )
            if receipt.get('audio_required') and not binding.native_record:
                with projection_phase('playback'):
                    if self.playback is not None:
                        self.playback(item, canonical)
                    else:
                        self.persist_playback(item, binding, canonical, receipt)
            if receipt['enrichment_required']:
                with projection_phase('enrichment'):
                    self.store.mark_enrichment(
                        item.segment_id,
                        binding,
                        self.clock(),
                        canonical,
                        receipt['language'],
                        part_index=index,
                    )
                return
        self.store.ready(item.segment_id, binding, self.clock(), part_index=index)

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
        capture_at = receipt.get('capture_at') or item.capture_at
        scope = receipt.get('speaker_scope') or f'sync:{item.segment_id}'
        survivors = []
        for segment in segments:
            if segment.get('speaker_id_scope') == scope:
                stamp = origin + segment['start']
                if scope.startswith('final:batch:') and not (
                    capture_at <= stamp < (receipt.get('audio_end') or item.capture_at + item.duration_seconds)
                ):
                    continue
                survivors.append(
                    {
                        **segment,
                        'timestamp': stamp,
                        'start': stamp - capture_at,
                        'end': origin + segment['end'] - capture_at,
                    }
                )
        if not survivors:
            return
        audio = self.fetch_audio(item)
        audio_end = receipt.get('audio_end') or item.capture_at + item.duration_seconds
        if capture_at != item.capture_at or audio_end != item.capture_at + item.duration_seconds:
            import io
            from pydub import AudioSegment

            # Match legacy retrieve_vad_segments slicing before full/partial
            # audio policy. Never copy a whole multipart capture to each row.
            decoded = AudioSegment.from_wav(io.BytesIO(audio))
            sliced = decoded[(capture_at - item.capture_at) * 1000 : (audio_end - item.capture_at) * 1000]
            output = io.BytesIO()
            sliced.export(output, format='wav')
            audio = output.getvalue()
        # Deliberately share the legacy audio persistence and partial-overlap
        # policy; its stable chunk timestamps make replay an overwrite.
        from utils.sync.merge_audio import store_intake_audio

        store_intake_audio(
            binding.owner_id,
            capture_at,
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
        for segment_id in self.discovery.next(limit=max(1, min(limit, 100))):
            try:
                if async_projection_enabled():
                    self.persist(segment_id)
                    result = None
                else:
                    result = self.project(segment_id)
                counts['completed' if result is not None else 'waiting'] += 1
            except (ProjectionBlocked, BatchPrivacyBlocked):
                counts['blocked'] += 1
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s', type(error).__name__
                )
        if projection_contention_enabled():
            logger.info(
                'event=batch_projection action=sweep outcome=summary completed=%d waiting=%d blocked=%d error=%d',
                counts['completed'],
                counts['waiting'],
                counts['blocked'],
                counts['error'],
            )
        return counts
