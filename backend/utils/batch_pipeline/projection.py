"""Replayable projection of committed batch output through legacy sync intake.

Synchronous worker seam: offload the call from an async serving coordinator.
No admission flag is consulted: already accepted work drains after rollback.
"""

from config.stt_cap_dispatch import execution_admission_enabled as cap_dispatch_enabled
from config.policy import ProjectionPolicy
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
import math
import logging
from typing import TYPE_CHECKING, Callable, NamedTuple
from uuid import NAMESPACE_URL, uuid5

from config.batch_pipeline import (
    owner_drain_enabled,
    projection_index_deferred_enabled,
    projection_pending_page_enabled,
    projection_predecessor_replay_enabled,
    projection_prefetch_depth,
    sweep_owner_chain_enabled,
)
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay, ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionGenerationAmbiguous
from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_quarantine_recovery import held_candidates
from database.batch_pipeline_store import PROJECTION_ASSIGNMENT_STATES, PROJECTION_FINISH_STATES, FirestoreStore
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from utils.batch_pipeline.projection_disposition import persist_disposition, mirror_assignment
from utils.batch_pipeline.projection_index import ProjectionIndex
from database import conversations as conversations_db
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, projection_speech_spans
from utils.batch_pipeline.correctness_metrics import record_labels
from utils.batch_pipeline.recovery_disposition import result_outcome
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.assignment_errors import SyncAssignmentSuperseded
from utils.sync.intake_completion import log_sync_lineage_stamp_gap_refused

if TYPE_CHECKING:
    from utils.batch_pipeline.projection_prefetch import Prefetched

logger = logging.getLogger(__name__)
# One owner-chain walk's bound (recovery wake or sweep continuation); the
# periodic sweep resumes beyond it. One sweep spends at most the same budget on
# continuations across all owners, so a heavy owner cannot stall the loop.
OWNER_CHAIN_LIMIT = 64
OWNER_CHAIN_SECONDS = 30.0
# Row bound of one owner-drain step; its time bound is the drain's.
OWNER_DRAIN_STEP_ROWS = 128
# A parallel candidate lookup slower than this is redone on the chain.
CANDIDATE_WAIT_SECONDS = 10.0
# Held units read per partial-completion scan.
HELD_PARTIAL_PAGE = 32


@dataclass(frozen=True)
class WalkHint:
    """What an owner-chain walk already knows about one row. Never an authority.

    ``successor``: the walk reached this row as its projection watermark's
    successor while holding the owner claim, so the read-only pre-check
    transactions are skipped; the assignment transaction reruns the same
    predecessor, privacy, binding and receipt fences.
    """

    successor: bool = False
    prefetched: 'Prefetched | None' = None
    defer_index: bool = False
    parallel_candidate: bool = False
    # The walk step's monotonic deadline: checked between parts, caps waits.
    deadline: float | None = None


class StepDeadline(Exception):
    """A walk step's budget ran out between parts of one multipart row."""


class Walk(NamedTuple):
    followups: list[str]
    advanced: list[str]
    # Stopped at its time or row bound with the chain still continuing.
    more: bool = False


def error_type(error: BaseException) -> str:
    """Bounded exception class token for an error log line.

    google-cloud-firestore's ``@transactional`` retries a commit ``Aborted``
    a fixed number of times, then raises ``ValueError('Failed to commit
    transaction in N attempts')`` from the last ``Aborted``. That is commit
    contention, the class the bounded outer retry names
    ``FirestoreContentionExhausted``, so it is logged under that name. Any
    other ``ValueError`` keeps its own name.
    """
    from database.firestore_transaction_retry import FirestoreAborted

    if (
        type(error) is ValueError
        and isinstance(error.__cause__, FirestoreAborted)
        and str(error).startswith('Failed to commit transaction')
    ):
        return 'FirestoreContentionExhausted'
    return type(error).__name__


def error_site_field(error: BaseException) -> str:
    """` site=<file>:<line>` of the innermost backend frame; static code location only."""
    import os
    import traceback

    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:
        return ''
    for frame in reversed(frames):
        if 'site-packages' not in frame.filename and 'dist-packages' not in frame.filename:
            return f' site={os.path.basename(frame.filename)}:{frame.lineno}'
    return ''


def fence_reason_field(error: BaseException) -> str:
    """Bounded privacy-fence reason for an error log line; never IDs or text."""
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    if isinstance(error, BatchPrivacyBlocked):
        return f' fence_reason={error.reason.value}'
    return ''


@contextmanager
def projection_phase(phase: str, policy: ProjectionPolicy | None = None) -> Iterator[None]:
    """Static phase tokens only; never log bindings, payloads or exception text."""
    if policy is None or not policy.projection_timing:
        yield
        return
    started = time.monotonic()
    logger.info('event=batch_projection_phase phase=%s outcome=started', phase)
    try:
        yield
    except Exception as error:
        logger.info(
            'event=batch_projection_phase phase=%s outcome=error elapsed_ms=%d exception_type=%s%s%s',
            phase,
            int((time.monotonic() - started) * 1000),
            error_type(error),
            fence_reason_field(error),
            error_site_field(error),
        )
        raise
    else:
        logger.info(
            'event=batch_projection_phase phase=%s outcome=completed elapsed_ms=%d',
            phase,
            int((time.monotonic() - started) * 1000),
        )


def build_incoming(
    item: WorkItem, binding, payload: dict, *, geolocation=None, batch_segment_id=None, policy=None
) -> dict:
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
    authoritative = (binding.record_origin or (policy or ProjectionPolicy()).authoritative_labels) and payload.get(
        'recovery_version'
    ) != 1
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
        is_locked=False if cap_dispatch_enabled(item.owner_id, 'batch') else binding.is_locked,
        private_cloud_sync_enabled=binding.private_cloud_sync_enabled,
        client_device_id=binding.client_device_id,
        client_platform=binding.client_platform,
        geolocation=geolocation,
    )
    incoming = Conversation(
        id=chunk_identity(item.owner_id, binding.source, binding.client_device_id, binding.is_locked, item.capture_at),
        created_at=started,
        structured=build_deterministic_minimum_structured(create, uid=item.owner_id),
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


def record_speech_step(binding, source: str, previous: float, committed: float) -> None:
    """Fair-use speech for one durable charge step, exactly once per step."""
    if committed <= previous:
        return
    from utils.fair_use import record_speech_ms

    record_speech_ms(
        binding.owner_id,
        int(committed * 1000) - int(previous * 1000),
        source=source,
        # The first charge keeps the historical key; a later one is keyed by
        # what was already charged, so each step lands once.
        idempotency_key=binding.content_id if not previous else f'{binding.content_id}:{int(previous * 1000)}',
        raise_on_error=True,
    )


def reissue_window_seconds() -> float:
    """Re-issue a step only while its once-key is certainly live (TTL less a two-day margin)."""
    from utils.fair_use import FAIR_USE_REDIS_RETENTION_SECONDS

    return max(0.0, FAIR_USE_REDIS_RETENTION_SECONDS - 2 * 86400)


def record_speech_steps(binding, source: str, steps, times, now: float) -> None:
    """Re-issue every recent durable charge step; each once-key lands at most once.

    A step whose Redis write was lost after its commit is repaired by any later
    attempt, even one that charges a newer step. A step of unknown age, or older
    than the window, is skipped: its once-key may have expired, and re-admitting
    it would count the same speech twice (it is outside the fair-use read anyway).
    """
    window = reissue_window_seconds()
    for (previous, committed), at in zip(zip(steps, steps[1:]), times):
        if at is not None and now - at <= window:
            record_speech_step(binding, source, previous, committed)


def record_speech(binding, accounting: dict, now: float) -> None:
    """Fair-use speech before an ordinary completion; after a partial only the remainder."""
    if not accounting['completed']:
        steps = list(accounting.get('steps') or [0.0])
        times: list[float | None] = list(accounting.get('step_times') or [None] * (len(steps) - 1))
        if accounting['seconds'] > steps[-1]:
            steps.append(accounting['seconds'])
            times.append(now)
        record_speech_steps(binding, accounting['source'], steps, times, now)


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
        require_lineage_fence: bool = False,
    ):
        self.store = ProjectionStore(store)
        self.load_result, self.publish, self.playback, self.clock = load_result, publish, playback, clock
        self.fetch_audio = fetch_audio
        self.require_lineage_fence = require_lineage_fence
        self.followups = None
        self.has_async_followups = False
        # Async rows a sweep walk persisted. Handed to the follow-up queue
        # behind work already queued, never ahead of it, so discovery's cursor
        # position cannot strand them and other owners are not starved.
        self.chain_followups: list[str] = []
        self.discovery = ProjectionDiscovery(store)
        # Pending-page mode: assignment never spends page slots on rows it can
        # only replay, and persisted/ready rows advance on their own cursor.
        self.assignment_discovery = ProjectionDiscovery(store, states=PROJECTION_ASSIGNMENT_STATES)
        self.finish_discovery = ProjectionDiscovery(store, states=PROJECTION_FINISH_STATES)
        # Search/people-stats work walks owe, converged off the ordered chain.
        self.index = ProjectionIndex()
        # Owners a sweep or wake wants drained; ``draining`` is live in this process.
        self.drain_requests: dict[str, None] = {}
        self.draining: set[str] = set()
        self.drains = None
        # Sweeps and wakes hand off from sync-pool threads while overlapping
        # reconcile passes and drains swap or extend on the event loop.
        self.handoff = threading.Lock()
        # Resume point of the held-partial scan; a short page wraps it.
        self.held_after: str | None = None

    def request_drain(self, owner_id: str) -> None:
        with self.handoff:
            self.drain_requests[owner_id] = None

    def owe_followups(self, segment_ids) -> None:
        with self.handoff:
            self.chain_followups.extend(segment_ids)

    @property
    def owes_followups(self) -> bool:
        """Walk-owed follow-ups are waiting even if no async row was seen this pass."""
        return bool(self.chain_followups) or bool(self.followups is not None and self.followups.owed)

    @property
    def owes_drains(self) -> bool:
        return bool(self.drain_requests)

    @property
    def owes_index(self) -> bool:
        return self.index.owed

    def start_drains(self) -> None:
        """Hand discovered owners to this process's drain. Event-loop thread only."""
        # Imported lazily: the synchronous worker seam remains lightweight.
        from utils.batch_pipeline.projection_drain import OwnerDrains

        if self.drains is None:
            self.drains = OwnerDrains(self)
        with self.handoff:
            requests, self.drain_requests = self.drain_requests, {}
        self.drains.request(requests)

    def schedule_index_flush(self) -> None:
        """Converge owed search/people-stats work off the chain. Event-loop thread only."""
        from utils.executors import db_executor, run_blocking, start_background_task

        if self.index.owed:
            start_background_task(run_blocking(db_executor, self.index.flush), name='batch_projection_index')

    def persist(self, segment_id: str) -> None:
        """Only ordered assignment holds the owner claim; receipts are the outbox."""
        with projection_phase('read'):
            job, entry, binding = self.store.read(segment_id)
        self._persist_read(segment_id, job, entry, binding)

    def _persist_read(self, segment_id, job, entry, binding, *, hint=None, claimed=False):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        if claimed:
            # The walk holds this owner's claim for its whole step.
            self._assign(segment_id, job, entry, binding, finish=False, hint=hint)
            return
        with projection_claim(self.store.store.namespace, owner_key(binding.owner_id)) as acquired:
            if not acquired:
                raise ProjectionBlocked('projection assignment claim busy')
            self._assign(segment_id, job, entry, binding, finish=False, hint=hint)

    async def start_followups(self, priority=()):
        # Imported lazily: the synchronous worker seam remains lightweight.
        from utils.batch_pipeline.projection_followup import ProjectionFollowups

        if self.followups is None:
            self.followups = ProjectionFollowups(self)
        with self.handoff:
            tail, self.chain_followups = self.chain_followups, []
        await self.followups.schedule(priority, tail=tail)

    def project(self, segment_id: str) -> dict | None:
        return self._project_read(segment_id, *self.store.read(segment_id))

    def _project_read(self, segment_id, job, entry, binding, *, hint=None, claimed=False):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        if policy.async_projection:
            self._persist_read(segment_id, job, entry, binding, hint=hint, claimed=claimed)
            job, entry, binding = self.store.read(segment_id)
            return self._finish(segment_id, job, entry, binding)
        if policy.projection_contention:
            with ExitStack() as stack:
                if not claimed:
                    acquired = stack.enter_context(
                        projection_claim(self.store.store.namespace, owner_key(binding.owner_id))
                    )
                    if not acquired:
                        logger.info('event=batch_projection action=claim outcome=busy')
                        return None
                with projection_phase('project', policy):
                    result = self._project(segment_id, job, entry, binding, hint=hint)
                logger.info(
                    'event=batch_projection action=project outcome=%s',
                    'completed' if result is not None else 'waiting',
                )
                return result
        with projection_phase('project', policy):
            return self._project(segment_id, job, entry, binding, hint=hint)

    def _project(self, segment_id, job, entry, binding, *, hint=None):
        self._assign(segment_id, job, entry, binding, hint=hint)
        return self._finish(segment_id, job, entry, binding)

    def _assign(self, segment_id, job, entry, binding, *, finish=True, hint=None):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        session = self.store.session(segment_id, binding, self.clock(), policy=policy)
        # A walk's fresh read showed no receipt; the transaction still fences.
        prechecked = not (hint is not None and hint.successor and not entry.get('projection'))
        if prechecked:
            try:
                with projection_phase('predecessor', policy):
                    self.store.check(session)
            except ProjectionReplay:
                return
        if entry['result']['outcome'] in {'silence', 'no_recoverable_speech'}:
            if entry['result']['outcome'] == 'no_recoverable_speech':
                payload = self._payload(item, entry, hint)
                if (
                    entry.get('recovery_version') != 1
                    or result_outcome(payload) != 'no_recoverable_speech'
                    or abs(payload['audio_seconds'] - item.duration_seconds) > 0.1
                ):
                    raise ProjectionBlocked('terminal empty recovery evidence required')
            try:
                if binding.record_origin:
                    self.assign_record_silence(item, binding, session, hint=hint)
                else:
                    session.persist_empty()
            except ProjectionReplay:
                if prechecked and not policy.projection_contention:
                    raise
                # A receipt is assignment progress, not completion. Resume
                # every post-persist obligation after losing the empty race.
                # Without the pre-check this is the replay it would have seen.
            except SyncAssignmentSuperseded:
                self.supersede(session)
        else:
            with projection_phase('assignment', policy):
                self.assign_parts(item, entry, binding, finish=finish, policy=policy, hint=hint)

    def _payload(self, item, entry, hint):
        prefetched = hint.prefetched if hint is not None else None
        if prefetched is not None and prefetched.payload is not None:
            return prefetched.payload
        return self.load_result(item, entry['result']['result_uri'])

    def _index_options(self, hint) -> dict:
        return {'defer_index': self.index.defer} if hint is not None and hint.defer_index else {}

    def _start_candidate(self, binding, part, part_payload):
        """Run the candidate hint lookup beside context and build.

        It starts after this row's predecessor committed, exactly when the
        serial lookup would have run, for the span the words predict. Returns
        (span, future), or None when the span cannot be predicted.
        """
        from utils.executors import db_executor

        try:
            words = part_payload['words']
            if not words:
                return None
            span = (int(part.capture_at), int(part.capture_at + max(float(word['timestamp'][1]) for word in words)))
            future = db_executor.submit(
                conversations_db.get_closest_conversation_to_timestamps, binding.owner_id, *span
            )
        except Exception:
            return None
        return span, future

    @staticmethod
    def _parallel_candidate(pending, span, deadline=None) -> tuple[bool, dict | None]:
        """(found, candidate): the parallel lookup's conversation for exactly this span.

        No match is not trusted: a conversation committed after the lookup
        started would be missed, so the caller looks again inline, as the
        serial path does. The wait never outlasts the walk step.
        """
        if pending is None or pending[0] != span:
            return False, None
        timeout = CANDIDATE_WAIT_SECONDS
        if deadline is not None:
            timeout = min(timeout, max(0.0, deadline - time.monotonic()))
        try:
            candidate = pending[1].result(timeout=timeout)
        except Exception:
            return False, None
        return candidate is not None, candidate

    def _finish(self, segment_id, job, entry, binding):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        entry = self.store.ref('results', segment_id).get().to_dict() or {}
        parts = entry.get('projection_parts')
        for index, receipt in (
            sorted(parts.items(), key=lambda pair: int(pair[0])) if parts else [(None, entry['projection'])]
        ):
            self.finish_part(item, binding, receipt, int(index) if index is not None else None, policy=policy)
        return self.complete_content(item.segment_id, binding, policy=policy)

    def complete_content(self, segment_id, binding, *, policy=None):
        policy = policy or self.store.policy(segment_id)
        with projection_phase('accounting', policy):
            accounting = self.store.prepare_accounting(binding, self.clock())
        if accounting is None:
            self.store.hold_for_quarantine(segment_id, binding, self.clock(), policy=policy)
            return None
        with projection_phase('usage', policy):
            record_speech(binding, accounting, self.clock())
        with projection_phase('completion', policy):
            result = self.store.complete(segment_id, binding, self.clock(), accounting, policy=policy)
        if result is not None:
            with projection_phase('publication', policy):
                self.publish(binding, result)
            from utils.batch_pipeline.retention import expire_completed_segment

            for sibling in binding.segment_ids:
                retained = self.store.ref('results', sibling).get().to_dict() or {}
                if retained.get('projection_state') == 'erased':
                    continue
                with projection_phase('retention', policy):
                    if not expire_completed_segment(self.store.store, binding.owner_id, sibling, self.clock()):
                        raise ProjectionBlocked('completion retention receipt unavailable')
                    self.store.acknowledge(sibling, binding, self.clock(), policy=policy)
        return result

    def complete_held(self, binding):
        """Complete an upload as partial once its unprojected units are all held.

        No provider call, no job/intent write and no retention: held audio stays
        for a reviewed redrive, whose ordinary completion upgrades the ledger.
        The poll reads the partial from the ledger, so nothing is published to
        the legacy Redis job (its fence accepts only all-success results).
        """
        accounting = self.store.prepare_accounting(binding, self.clock(), held=True)
        if accounting is None:
            return None
        outcome = self.store.complete_partial(binding, self.clock(), accounting)
        if outcome is None:
            return None
        result, (steps, times) = outcome
        # Fair use follows the durable steps, never an uncommitted attempt. A
        # crash before this call is repaired by the next scan or the ordinary
        # completion, which re-issue every stored step under the same keys.
        if not accounting['completed']:
            record_speech_steps(binding, accounting['source'], steps, times, self.clock())
        return result

    def sweep_held(self, limit: int = HELD_PARTIAL_PAGE) -> dict[str, int]:
        """Bounded page of held units; one partial attempt per upload."""
        counts = {'partial': 0, 'waiting': 0, 'error': 0}
        page = held_candidates(self.store.client, self.store.store.namespace, limit, after_id=self.held_after)
        self.held_after = page[-1][0] if len(page) >= limit else None
        seen = set()
        for _, job in page:
            try:
                binding = normalized_binding(job['projection_binding'])
                if (binding.owner_id, binding.content_id) in seen:
                    continue
                seen.add((binding.owner_id, binding.content_id))
                counts['partial' if self.complete_held(binding) is not None else 'waiting'] += 1
            except Exception as error:
                counts['error'] += 1
                logger.warning('event=batch_held_partial outcome=retry exception_type=%s', error_type(error))
        return counts

    def assign_record_silence(self, item, binding, session, *, hint=None):
        incoming = {
            'id': binding.target_conversation_id,
            'started_at': datetime.fromtimestamp(item.capture_at, timezone.utc),
            'finished_at': datetime.fromtimestamp(item.capture_at + item.duration_seconds, timezone.utc),
            'transcript_segments': [],
            'data_protection_level': binding.data_protection_level,
            '_batch_require_live_target': True,
            '_batch_replace_live': {'start': item.capture_at, 'end': item.capture_at + item.duration_seconds},
        }
        try:
            conversations_db.assign_sync_conversation(
                binding.owner_id,
                incoming,
                target_id=binding.target_conversation_id,
                firestore_client=self.store.client,
                before_assign=session.prepare,
                validate_plan=session.validate_plan,
                after_assign=lambda transaction, planned: session.persist(transaction, planned),
                retry_contention=session.policy.projection_contention,
                timing=session.policy.projection_timing,
                **self._index_options(hint),
            )
        finally:
            self._mirror_assignment(session)

    def _mirror_assignment(self, session) -> None:
        mirror_assignment(self.store, session)

    def assign_parts(self, item, entry, binding, *, finish=True, policy=None, hint=None):
        policy = policy or self.store.policy(item.segment_id)
        from database.conversations import get_closest_conversation_to_timestamps
        from utils.batch_pipeline.context import ResolvedContext, resolve_context, require_repair_manifest
        from utils.batch_pipeline.projection_parts import split_result

        with projection_phase('load_result', policy):
            payload = self._payload(item, entry, hint)
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
        from utils.capture.batch_coverage import optional_manifest

        manifest = None if item.requires_compute_admission else optional_manifest(self, item, hint)
        if item.requires_compute_admission:
            if self.fetch_audio is None:
                raise ProjectionBlocked('authenticated intake manifest loader required')
            from utils.batch_pipeline.audio import read_context

            with projection_phase('manifest', policy):
                prefetched = hint.prefetched if hint is not None else None
                if prefetched is not None and prefetched.manifest is not None:
                    manifest = prefetched.manifest
                else:
                    manifest = read_context(self.fetch_audio(item))
        require_repair_manifest(item, binding, manifest, self.require_lineage_fence)
        receipts = entry.get('projection_parts') or {}
        for index, (part, part_payload) in enumerate(parts):
            if index and hint is not None and hint.deadline is not None and time.monotonic() >= hint.deadline:
                raise StepDeadline()
            session = self.store.session(
                item.segment_id,
                binding,
                self.clock(),
                part_index=index,
                part_count=len(parts),
                policy=policy,
            )
            session.capture_at, session.audio_end = part.capture_at, part.capture_at + part.duration_seconds
            session.speaker_scope = f'sync:{part.segment_id}'
            session.speech_seconds = float(part_payload['speech_seconds'])
            session.total_speech_seconds = float(speech)
            pending_candidate = None
            try:
                if not (
                    hint is not None and hint.successor and not entry.get('projection') and str(index) not in receipts
                ):
                    self.store.check(session)
                if hint is not None and hint.parallel_candidate and not binding.target_conversation_id:
                    pending_candidate = self._start_candidate(binding, part, part_payload)
                context = ResolvedContext(binding.target_conversation_id)
                if manifest is not None and item.requires_compute_admission:
                    with projection_phase('context', policy):
                        context = resolve_context(
                            item,
                            binding,
                            manifest,
                            self.store.client,
                            projection_item=part,
                            require_lineage_fence=self.require_lineage_fence,
                        )
                if not part_payload['words']:
                    receipt = session.persist_empty()
                else:
                    with projection_phase('build', policy):
                        incoming = build_incoming(
                            part,
                            binding,
                            part_payload,
                            geolocation=context.geolocation,
                            batch_segment_id=item.segment_id,
                            policy=policy,
                        )
                    session.speaker_scope = incoming['transcript_segments'][0]['speaker_id_scope']
                    if binding.record_origin:
                        incoming['_batch_replace_live'] = {
                            'start': item.capture_at,
                            'end': item.capture_at + item.duration_seconds,
                        }
                    if (binding.record_origin or policy.require_live_target) and context.target_id:
                        incoming['_batch_require_live_target'] = True
                    if context.binding_reason is not None and context.target_id:
                        incoming['_sync_lineage_binding'] = context.binding_reason
                    if context.lineage_eligible:
                        incoming['_sync_lineage_eligible'] = True
                    from utils.capture.batch_coverage import admit_projection, record_projection

                    admit_projection(binding.owner_id, incoming, manifest, capture_at=item.capture_at)
                    session.incoming_segment_count = len(incoming['transcript_segments'])
                    receipt_box = []

                    def persisted(transaction, planned):
                        receipt_box[:] = [session.persist(transaction, planned)]

                    candidate = None
                    if context.target_id is None:
                        with projection_phase('candidate', policy):
                            span = (int(incoming['started_at'].timestamp()), int(incoming['finished_at'].timestamp()))
                            deadline = hint.deadline if hint is not None else None
                            found, candidate = self._parallel_candidate(pending_candidate, span, deadline)
                            if not found:
                                candidate = get_closest_conversation_to_timestamps(binding.owner_id, *span)
                    if not incoming['transcript_segments']:
                        receipt = session.persist_empty()
                    else:
                        try:
                            assigned = conversations_db.assign_sync_conversation(
                                binding.owner_id,
                                incoming,
                                target_id=context.target_id,
                                candidate_id=candidate['id'] if candidate else None,
                                firestore_client=self.store.client,
                                before_assign=session.prepare,
                                validate_plan=session.validate_plan,
                                after_assign=persisted,
                                retry_contention=policy.projection_contention,
                                timing=policy.projection_timing,
                                **self._index_options(hint),
                            )
                        finally:
                            self._mirror_assignment(session)
                        incoming.pop('_sync_lineage_eligible', None)
                        record_projection(
                            binding.owner_id,
                            incoming,
                            assigned[0],
                            manifest,
                            capture_at=item.capture_at,
                            survivors=assigned[2],
                        )
                        receipt = receipt_box[0]
                        record_labels(assigned[2])
                        if assigned[0].pop('_sync_lineage_stamp_gap_refused', False):
                            log_sync_lineage_stamp_gap_refused()
            except ProjectionReplay as replay:
                receipt = replay.receipt
            except ProjectionGenerationAmbiguous:
                receipt = persist_disposition(session, quarantined=True)
            except SyncAssignmentSuperseded:
                receipt = self.supersede(session)
            except Exception as error:
                if policy.projection_contention:
                    logger.error(
                        'event=batch_projection action=assignment outcome=error exception_type=%s%s',
                        error_type(error),
                        fence_reason_field(error),
                    )
                raise
            if finish:
                self.finish_part(item, binding, receipt, index, policy=policy)

    def supersede(self, session):
        return persist_disposition(session)

    def finish_part(self, item, binding, receipt, index, *, policy=None):
        policy = policy or self.store.policy(item.segment_id)
        if receipt['state'] in {'ready', 'quarantined'}:
            return
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            with projection_phase('bridge', policy):
                canonical = (
                    receipt['conversation_id']
                    if binding.record_origin
                    else finish_sync_bridges(
                        binding.owner_id,
                        receipt['conversation_id'],
                        silent=receipt.get('silent_redrive') is True,
                    )
                )
            if receipt.get('audio_required') and not binding.native_record:
                with projection_phase('playback', policy):
                    if self.playback is not None:
                        self.playback(item, canonical)
                    else:
                        self.persist_playback(item, binding, canonical, receipt)
            if receipt['enrichment_required']:
                with projection_phase('enrichment', policy):
                    self.store.mark_enrichment(
                        item.segment_id,
                        binding,
                        self.clock(),
                        canonical,
                        receipt['language'],
                        part_index=index,
                        policy=policy,
                    )
                return
        self.store.ready(item.segment_id, binding, self.clock(), part_index=index, policy=policy)

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

    def project_owner(
        self,
        owner_id: str,
        *,
        recovered: str | None = None,
        limit: int = OWNER_CHAIN_LIMIT,
        budget_seconds: float = OWNER_CHAIN_SECONDS,
    ) -> list[str]:
        """Walk one owner's result log forward from its projection watermark.

        A recovered unit commits at the log tail, behind successors the global
        cursor may already have passed. This targeted wake assigns the owner's
        unprojected rows in chain order within one pass and stops at the first
        row that does not advance the watermark. Every row still passes the
        transactional predecessor, privacy and receipt fences. Returns async
        rows whose follow-ups should run next: the rows this walk persisted
        plus their contents' persisted, not-yet-ready siblings, grouped by
        content with the ``recovered`` unit's content first. With the owner
        drain on, an owner the wake left unfinished is handed to the drain.
        """
        walk = self._walk(owner_id, recovered=recovered, limit=limit, budget_seconds=budget_seconds)
        if walk.more and owner_drain_enabled():
            self.request_drain(owner_id)
        logger.info(
            'event=batch_projection action=owner_chain outcome=summary advanced=%d followups=%d',
            len(walk.advanced),
            len(walk.followups),
        )
        return walk.followups

    def drain_step(self, owner_id: str, budget_seconds: float, *, prefetch=None) -> Walk:
        """One bounded, claim-holding step of the owner drain (blocking).

        ``prefetch`` is the drain turn's read-ahead, kept across its steps.
        """
        return self._walk(
            owner_id, recovered=None, limit=OWNER_DRAIN_STEP_ROWS, budget_seconds=budget_seconds, prefetch=prefetch
        )

    def chain_prefetch(self, owner_id: str):
        """A read-ahead for one owner's chain, or None when switched off."""
        depth = projection_prefetch_depth()
        if not depth:
            return None
        from utils.batch_pipeline.projection_prefetch import ChainPrefetch

        return ChainPrefetch(self, owner_key(owner_id), depth)

    def _walk_owner(
        self,
        owner_id: str,
        *,
        recovered: str | None,
        limit: int,
        budget_seconds: float,
        seed: tuple[str, ProjectionBinding] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Returns (follow-ups, rows this walk advanced in chain order)."""
        walk = self._walk(owner_id, recovered=recovered, limit=limit, budget_seconds=budget_seconds, seed=seed)
        return walk.followups, walk.advanced

    def _walk(
        self,
        owner_id: str,
        *,
        recovered: str | None,
        limit: int,
        budget_seconds: float,
        seed: tuple[str, ProjectionBinding] | None = None,
        prefetch=None,
    ) -> Walk:
        """Walk the owner's log in chain order from its projection watermark.

        ``seed`` is an async row the caller just persisted. It is owed a
        follow-up when the watermark shows it advanced (a partial multipart
        did not), or when the watermark cannot be read.

        With the owner drain on, a budgeted walk holds the advisory owner claim
        for its whole step and passes each row it reached as the watermark's
        successor a ``WalkHint``. Read-ahead and deferred indexing follow their
        own switches. The ordered transaction fences are unchanged either way.
        """
        with ExitStack() as stack:
            drain = budget_seconds > 0 and owner_drain_enabled()
            if drain:
                acquired = stack.enter_context(projection_claim(self.store.store.namespace, owner_key(owner_id)))
                if not acquired:
                    logger.info('event=batch_projection action=owner_chain outcome=claim_busy')
                    return Walk([], [])
            if prefetch is None and budget_seconds > 0:
                prefetch = self.chain_prefetch(owner_id)
                if prefetch is not None:
                    stack.callback(prefetch.close)
            deferred = budget_seconds > 0 and projection_index_deferred_enabled()
            return self._walk_rows(
                owner_id,
                recovered=recovered,
                limit=limit,
                budget_seconds=budget_seconds,
                seed=seed,
                drain=drain,
                prefetch=prefetch,
                deferred=deferred,
            )

    def _walk_rows(self, owner_id, *, recovered, limit, budget_seconds, seed, drain, prefetch, deferred) -> Walk:
        from database.batch_pipeline_privacy import BatchPrivacyBlocked
        from utils.batch_pipeline.projection_prefetch import NOT_READY, Prefetched

        key = owner_key(owner_id)
        deadline = time.monotonic() + budget_seconds
        groups: dict[str, dict[str, None]] = {}
        first = None
        advanced: list[str] = []
        more = False

        def failed(error: BaseException) -> None:
            # Keep what this walk already persisted; the sweep resumes later.
            logger.error(
                'event=batch_projection action=owner_chain outcome=error exception_type=%s%s',
                error_type(error),
                error_site_field(error),
            )

        def owe(segment_id: str, binding: ProjectionBinding) -> bool:
            """Queue this row and its content's persisted, not-ready siblings.

            The sibling scan stops at the walk deadline, and a seed-only walk
            (no budget) skips it: unscanned siblings stay durable and are
            rediscovered.
            """
            group = groups.get(binding.content_id)
            if group is None:
                group = groups[binding.content_id] = {}
                try:
                    for sibling in binding.segment_ids:
                        if time.monotonic() >= deadline:
                            break
                        receipt = (self.store.ref('results', sibling).get().to_dict() or {}).get('projection') or {}
                        if receipt and receipt.get('state') != 'ready':
                            group[sibling] = None
                except Exception as error:
                    group[segment_id] = None  # The persisted row is still owed.
                    failed(error)
                    return False
            group[segment_id] = None
            return True

        try:
            previous = self.store.projection_watermark(key)
        except Exception as error:
            if seed is not None:
                owe(*seed)
            failed(error)
            return Walk(list(dict.fromkeys(sid for group in groups.values() for sid in group)), advanced)
        if seed is not None and previous == seed[0] and not owe(*seed):
            return Walk(list(dict.fromkeys(sid for group in groups.values() for sid in group)), advanced)
        for _ in range(max(1, limit)):
            if time.monotonic() >= deadline:
                more = True
                break
            try:
                segment_id = None
                if prefetch is not None:
                    prefetch.advance(previous)
                    segment_id = prefetch.successor(previous)
                if segment_id is None:
                    segment_id = self.store.store.projection_successor(key, previous)
                row = {}
                if segment_id is not None:
                    row = self.store.ref('results', segment_id).get().to_dict() or {}
            except Exception as error:
                failed(error)
                break
            if segment_id is None:
                break
            if row.get('projection_state') == 'erased':
                # The predecessor check walks erased receipts; so does discovery.
                previous = segment_id
                continue
            try:
                prefetched = None
                if prefetch is not None:
                    prefetched = prefetch.take(segment_id, timeout=deadline - time.monotonic())
                    if prefetched is NOT_READY:
                        # Still loading at the step deadline: the next step
                        # resumes here instead of holding this pool slot.
                        more = True
                        break
                inputs = prefetched if isinstance(prefetched, Prefetched) and row else None
                if inputs is not None:
                    # Immutable job and binding from the read-ahead; the
                    # mutable receipt state is this walk's fresh read.
                    job, entry, binding = inputs.job, row, inputs.binding
                else:
                    job, entry, binding = self.store.read(segment_id)
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                hint = WalkHint(
                    successor=drain,
                    prefetched=inputs,
                    defer_index=deferred,
                    parallel_candidate=prefetch is not None,
                    deadline=deadline,
                )
                if policy.async_projection:
                    self._persist_read(segment_id, job, entry, binding, hint=hint, claimed=drain)
                else:
                    self._project_read(segment_id, job, entry, binding, hint=hint, claimed=drain)
            except StepDeadline:
                more = True  # a partial multipart; the next step resumes it
                break
            except (ProjectionBlocked, BatchPrivacyBlocked):
                break
            except Exception as error:
                failed(error)
                break
            try:
                watermark = self.store.projection_watermark(key)
            except Exception as error:
                # Persist succeeded but its advance is unknown: still owe it.
                if policy.async_projection:
                    owe(segment_id, binding)
                failed(error)
                break
            if watermark != segment_id:
                break  # Busy claim or partial multipart: the sweep retries it.
            previous = segment_id
            advanced.append(segment_id)
            if policy.async_projection:
                if segment_id == recovered:
                    first = binding.content_id
                if not owe(segment_id, binding):
                    break
        else:
            more = True
        ordered = [groups.pop(first)] if first is not None else []
        followups = list(dict.fromkeys(sid for group in ordered + list(groups.values()) for sid in group))
        return Walk(followups, advanced, more)

    def sweep(self, limit: int = 100) -> dict[str, int]:
        """Bounded durable-log recovery; no in-memory callback is an outbox."""
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        counts = {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
        contention = False
        self.has_async_followups = False
        size = max(1, min(limit, 100))
        pending_page = projection_pending_page_enabled()
        chain = sweep_owner_chain_enabled()
        # The owner drain walks chains continuously; the sweep only discovers
        # owners for it and still hands its own persisted page rows off.
        drain = chain and owner_drain_enabled()
        discovery = self.assignment_discovery if pending_page else self.discovery
        # At most one walk per owner per sweep. Page rows a walk already
        # persisted are skipped unread and left out of ``counts``: the
        # sweep_chain summary owns them. Every other row is attempted as before.
        # ``touched`` rows were assigned or finished this sweep; the finish page
        # does not repeat them.
        walked: set[str] = set()
        chained: set[str] = set()
        touched: set[str] = set()
        # Owners this pass handed to the drain. Owners still queued from an
        # earlier pass keep their page progress until a drain picks them up.
        handed: set[str] = set()
        # The shared budget starts with the first walk, not the page.
        chain_deadline: float | None = None
        for segment_id in discovery.next(limit=size):
            if segment_id in chained:
                continue
            binding = None
            try:
                job, entry, binding = self.store.read(segment_id)
                if drain and (binding.owner_id in self.draining or binding.owner_id in handed):
                    # That chain is the drain's: walking now (its claim would
                    # only refuse the row) or handed over earlier in this pass.
                    counts['waiting'] += 1
                    continue
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                contention = contention or policy.projection_contention
                if policy.async_projection:
                    self.has_async_followups = True
                    self._persist_read(segment_id, job, entry, binding)
                    result = None
                else:
                    result = self._project_read(segment_id, job, entry, binding)
                counts['completed' if result is not None else 'waiting'] += 1
                touched.add(segment_id)
            except ProjectionPredecessorPending:
                counts['blocked'] += 1
                # Discovery may have paged past the unprojected head. Rebuild it
                # from the watermark rather than waiting for the cursor to wrap.
                # The walk still runs every transactional assignment fence.
                if (
                    binding is not None
                    and chain
                    and projection_predecessor_replay_enabled()
                    and binding.owner_id not in walked
                ):
                    walked.add(binding.owner_id)
                    if drain:
                        handed.add(binding.owner_id)
                        self.request_drain(binding.owner_id)
                    else:
                        if chain_deadline is None:
                            chain_deadline = time.monotonic() + OWNER_CHAIN_SECONDS
                        budget = max(0.0, chain_deadline - time.monotonic())
                        try:
                            followups, advanced = self._walk_owner(
                                binding.owner_id, recovered=None, limit=OWNER_CHAIN_LIMIT, budget_seconds=budget
                            )
                            if followups:
                                self.has_async_followups = True
                                self.owe_followups(followups)
                            chained.update(advanced)
                        except Exception as error:
                            logger.error(
                                'event=batch_projection action=sweep_chain outcome=error exception_type=%s',
                                error_type(error),
                            )
                continue
            except (ProjectionBlocked, BatchPrivacyBlocked):
                counts['blocked'] += 1
                continue
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s%s',
                    error_type(error),
                    error_site_field(error),
                )
                continue
            if chain and entry.get('projection_state') == 'pending':
                # This row was assignable and passed every fence: keep walking
                # the owner's chain now instead of waiting for the cursor to
                # wrap. Each row still takes the owner claim and predecessor
                # fence one at a time; nothing runs concurrently per owner.
                # The page row itself is owed a follow-up too. Only the first
                # row per owner walks; later rows, or rows with no budget left,
                # get a seed-only walk (one watermark read, persists nothing).
                budget = 0.0
                if drain:
                    handed.add(binding.owner_id)
                    self.request_drain(binding.owner_id)
                elif binding.owner_id not in walked:
                    if chain_deadline is None:
                        chain_deadline = time.monotonic() + OWNER_CHAIN_SECONDS
                    budget = max(0.0, min(OWNER_CHAIN_SECONDS, chain_deadline - time.monotonic()))
                seed = (segment_id, binding) if policy.async_projection else None
                if budget > 0 or seed is not None:
                    if budget > 0:
                        walked.add(binding.owner_id)
                    try:
                        followups, advanced = self._walk_owner(
                            binding.owner_id,
                            recovered=None,
                            limit=OWNER_CHAIN_LIMIT,
                            budget_seconds=budget,
                            seed=seed,
                        )
                        # Walked async rows are owed follow-ups even when no
                        # other async row is on either page this pass.
                        if followups:
                            self.has_async_followups = True
                            self.owe_followups(followups)
                        chained.update(advanced)
                    except Exception as error:
                        logger.error(
                            'event=batch_projection action=sweep_chain outcome=error exception_type=%s',
                            error_type(error),
                        )
        if pending_page:
            contention = self._sweep_finish(size, counts, touched | chained) or contention
        if contention:
            logger.info(
                'event=batch_projection action=sweep outcome=summary completed=%d waiting=%d blocked=%d error=%d',
                counts['completed'],
                counts['waiting'],
                counts['blocked'],
                counts['error'],
            )
        if chain and walked:
            logger.info(
                'event=batch_projection action=sweep_chain outcome=summary owners=%d advanced=%d',
                len(walked),
                len(chained),
            )
        return counts

    def _sweep_finish(self, size: int, counts: dict[str, int], touched: set[str]) -> bool:
        """Advance persisted/ready rows that the pending-only assignment page skips.

        Async rows belong to the follow-up drain; seeing one keeps it scheduled.
        Synchronous-policy rows replay assignment and finish exactly as the
        mixed page did, so no persisted or ready obligation loses its retry.
        """
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        contention = False
        for segment_id in self.finish_discovery.next(limit=size):
            if segment_id in touched:
                continue
            try:
                job, entry, binding = self.store.read(segment_id)
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                contention = contention or policy.projection_contention
                if policy.async_projection:
                    self.has_async_followups = True
                    continue
                result = self._project_read(segment_id, job, entry, binding)
                counts['completed' if result is not None else 'waiting'] += 1
            except (ProjectionBlocked, BatchPrivacyBlocked):
                counts['blocked'] += 1
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s%s',
                    error_type(error),
                    error_site_field(error),
                )
        return contention
