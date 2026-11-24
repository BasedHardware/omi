"""Replayable projection of committed batch output through legacy sync intake.

Synchronous worker seam: offload the call from an async serving coordinator.
No admission flag is consulted: already accepted work drains after rollback.
"""

from config.stt_cap_dispatch import execution_admission_enabled as cap_dispatch_enabled
from config.policy import ProjectionPolicy, kill_switch
from config.policy.batch import cohort_bucket
from config.policy.stages import projection_phase_sample_percent
from collections.abc import Iterator
from collections import Counter
from contextlib import ExitStack, contextmanager
from cryptography.exceptions import InvalidTag
from dataclasses import dataclass
from datetime import datetime, timezone
from google.api_core.exceptions import NotFound
import threading
import time
import math
import logging
from random import randrange
import json
from typing import TYPE_CHECKING, Callable, NamedTuple

from config.batch_pipeline import (
    owner_drain_enabled,
    owner_drain_admission_diagnostics_enabled,
    projection_index_deferred_enabled,
    projection_pending_page_enabled,
    projection_predecessor_replay_enabled,
    projection_prefetch_depth,
    projection_hold_recovery_enabled,
    sweep_owner_chain_enabled,
    serving_sweep_page_rows,
    silence_read_skip_enabled,
)
from config.record_latency import recent_native_record
from database import batch_pipeline_projection_release as projection_release
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay, ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionGenerationAmbiguous
from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending
from utils.batch_pipeline.projection_delivery import assert_delivery_claim
from database.batch_pipeline_projection_protocol import PROJECTION_HEAD_BLOCK_TYPE as PROJECTION_HEAD_BLOCK_TYPE
from database.batch_pipeline_projection_protocol import PROJECTION_HEAD_BLOCKED_SINCE
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_quarantine_recovery import held_candidates
from database.batch_pipeline_store import PROJECTION_ASSIGNMENT_STATES, PROJECTION_FINISH_STATES, FirestoreStore
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from utils.batch_pipeline.projection_finish_page import FinishPage
from utils.batch_pipeline.projection_disposition import persist_disposition, mirror_assignment
from utils.batch_pipeline.projection_prefetch import NativeAudioPending
from utils.batch_pipeline.projection_privacy import PRIVACY_HELD, settle_refusals
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason
from utils.batch_pipeline.projection_index import ProjectionIndex
from database import conversations as conversations_db
from utils.batch_pipeline.projection_block_reasons import projection_block_reason, sweep_block_group, sweep_block_reason
from utils.batch_pipeline.projection_walk_stop import walk_block_stop, walk_head_stop
from utils.batch_pipeline import projection_drain_diagnostics as drain_diagnostics
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, projection_speech_spans
from utils.batch_pipeline import artifact_missing
from utils.batch_pipeline.errors import error_site_field
from utils.batch_pipeline.correctness_metrics import record_labels
from utils.batch_pipeline.metrics import (
    PROJECTION_FINISH_COMPLETED,
    PROJECTION_FINISH_READS,
    SilentReadOutcome,
    SilentReadStage,
    record_silent_completion_reads,
    record_silent_read_skip,
)
from utils.batch_pipeline.recovery_disposition import result_outcome
from utils.batch_pipeline.projection_hold_policy import quarantines_assignment_conflict, log_conflict_hold
from database.batch_pipeline_projection_claim import projection_claim
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.voice_evidence import prepare as prepare_voice_evidence
from utils.batch_pipeline.projection_segments import projection_segments
from utils.sync.assignment_errors import (
    SyncAssignmentConflict,
    SyncAssignmentSuperseded,
)
from utils.stt.transcript_admission import filter_admission
from utils.episodes import transcript_receipts

if TYPE_CHECKING:
    from asyncio import Semaphore
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
    # Closed, log-safe token naming why the walk stopped (WALK_STOPS, or blocked_<token>).
    stop: str = ''
    # Scheduling hint only: the privacy-blocked head and its observed row version.
    blocked_head: tuple[str, object] | None = None
    # Already-read recent single-unit records can finish without another scan.
    eager_followups: tuple[str, ...] = ()


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


def fence_reason_field(error: BaseException) -> str:
    """Bounded privacy-fence reason for an error log line; never IDs or text."""
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    if isinstance(error, BatchPrivacyBlocked):
        return f' fence_reason={error.reason.value}'
    return ''


# Bounded retry for a failing owner-chain head. Infrastructure contention and
# fresh awaiting-writer conflicts may keep a head waiting, but not forever:
# once a head has failed for this long it takes the held disposition so the
# chain can advance (audio retained; a reviewed redrive owns the unit).
PROJECTION_HEAD_RETRY_SECONDS = 24 * 3600.0


def projection_exception_transient(error: BaseException) -> bool:
    """Whether a failing step is infrastructure contention, not content poison.

    Keeps the exception taxonomy's declared retryable kinds waiting (#23946):
    storage/authorization OSErrors (PermissionError included) wait for the
    sweep, under this rule's durable bound, never a first-failure hold.
    """
    from database.firestore_transaction_retry import FirestoreContentionExhausted
    from google.api_core import exceptions as api_exceptions

    if isinstance(error, (ConnectionError, TimeoutError, OSError, FirestoreContentionExhausted)):
        return True
    if isinstance(
        error,
        (
            api_exceptions.Aborted,
            api_exceptions.BadGateway,
            api_exceptions.DeadlineExceeded,
            api_exceptions.ServiceUnavailable,
            api_exceptions.TooManyRequests,
            api_exceptions.ResourceExhausted,
            api_exceptions.InternalServerError,
            api_exceptions.GatewayTimeout,
        ),
    ):
        return True
    # google-cloud-firestore's exhausted commit retry: contention, not content.
    return type(error) is ValueError and isinstance(error.__cause__, api_exceptions.Aborted)


def payload_contract_violation(error: BaseException) -> bool:
    """Whether retrying the same committed bytes cannot fix this error.

    Every other ValueError on the assignment path is a contract violation of
    the committed result or manifest (spans, split, word bounding, source
    decode). A tampered or wrongly-keyed artifact body fails authenticated
    decryption as ``InvalidTag`` — equally permanent. Firestore commit
    contention also surfaces as ``ValueError`` and must stay retryable;
    ``error_type`` names that shape ``FirestoreContentionExhausted``.
    """
    if isinstance(error, InvalidTag):
        return True
    return isinstance(error, ValueError) and error_type(error) != 'FirestoreContentionExhausted'


# The contract catch shape: both classes can carry a permanent payload
# violation; payload_contract_violation decides which instances disposition.
PAYLOAD_CONTRACT_ERRORS = (ValueError, InvalidTag)


def head_holds_without_retry(error: BaseException, job: dict | None, *, now: float | None = None) -> bool:
    """The generic poison-head rule: only a writer or infrastructure may keep
    a chain head waiting. Everything else holds the unit on first failure.

    The assign seams already disposition payload-contract violations and
    structural conflicts (#23946, #23932); this walk/sweep-level rule is the
    floor beneath every other escaping kind, and the backstop for a contract
    ValueError raised outside those seams.
    """
    if payload_contract_violation(error):
        return True
    if projection_exception_transient(error):
        return False
    if isinstance(error, SyncAssignmentConflict) and not quarantines_assignment_conflict(error, job, now=now):
        # Awaiting-writer on a fresh row: the writer may still land.
        return False
    return True


def head_retry_bound_exceeded(entry: dict, now: float) -> bool:
    since = entry.get(PROJECTION_HEAD_BLOCKED_SINCE)
    return isinstance(since, (int, float)) and now - since > PROJECTION_HEAD_RETRY_SECONDS


@contextmanager
def projection_phase(
    phase: str, policy: ProjectionPolicy | None = None, *, unit_key: str | None = None
) -> Iterator[None]:
    """Static phase tokens only; never log bindings, payloads or exception text."""
    if policy is None or not policy.projection_timing:
        yield
        return
    percent = projection_phase_sample_percent()
    log_success = percent == 100
    if 0 < percent < 100:
        bucket = cohort_bucket(unit_key, 'batch-projection-phase') if unit_key else randrange(100)
        log_success = bucket < percent
    started = time.monotonic()
    if log_success:
        logger.info('event=batch_projection_phase phase=%s outcome=started', phase)
    try:
        yield
    except NativeAudioPending:
        raise
    except Exception as error:
        logger.info(
            'event=batch_projection_phase phase=%s outcome=error elapsed_ms=%d exception_type=%s%s%s block_reason=%s',
            phase,
            int((time.monotonic() - started) * 1000),
            error_type(error),
            fence_reason_field(error),
            error_site_field(error),
            projection_block_reason(error),
        )
        raise
    else:
        if log_success:
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
    from utils.sync.capture import chunk_identity

    segments = projection_segments(item, binding, payload, batch_segment_id=batch_segment_id, policy=policy)
    started = datetime.fromtimestamp(item.capture_at, timezone.utc)
    finished = datetime.fromtimestamp(item.capture_at + max(s.end for s in segments), timezone.utc)
    # Projected sync must use the same narrow admission rules as legacy sync.
    # Keep original clocks/accounting; shadow retains the identical segments.
    segments, admission_receipts = filter_admission(item.owner_id, segments, origin='sync')
    for reason in sorted({receipt.rule for receipt in admission_receipts}):
        logger.info(
            'event=batch_media_admission reason=%s count=%d serving=%s',
            reason,
            sum(receipt.rule == reason for receipt in admission_receipts),
            str(any(receipt.dropped for receipt in admission_receipts)).lower(),
        )
    create = CreateConversation(
        started_at=started,
        finished_at=finished,
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
    # Consumed by the existing assignment transaction, never a separate write.
    incoming['_episode_transcript_receipt'] = True
    if item.capture_time_trust is not None:
        incoming['capture_time_trust'] = item.capture_time_trust
        # Use raw-source identity rather than receipt time for replay. This
        # pre-existing partition also fences new rows from older row readers.
        incoming['id'] = item.conversation_id or incoming['id']
        incoming['sync_clock_run'] = incoming['id']
        incoming['clock'] = 'imported'
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
        projection_store=None,
        assign_conversation: Callable | None = None,
        publish: Callable = publish_client_completion,
        playback: Callable | None = None,
        fetch_audio: Callable[[WorkItem], bytes] | None = None,
        clock: Callable[[], float] = time.time,
        require_lineage_fence: bool = False,
    ):
        self.store = projection_store if projection_store is not None else ProjectionStore(store)
        self.assign_conversation = assign_conversation
        self.load_result, self.publish, self.playback, self.clock = load_result, publish, playback, clock
        self.fetch_audio = fetch_audio
        self.require_lineage_fence = require_lineage_fence
        self.followups = None
        self.has_async_followups = False
        # Async rows a sweep walk persisted. Handed to the follow-up queue
        # behind work already queued, never ahead of it, so discovery's cursor
        # position cannot strand them and other owners are not starved.
        self.chain_followups: list[str] = []
        self.outbox_coverage: Callable[[], bool] | None = None
        self.outbox_followup_slots: Semaphore | None = None
        self.discovery = ProjectionDiscovery(store, outbox_coverage=self.has_outbox_coverage)
        self.finish_page = FinishPage(self)
        # Pending-page mode: assignment never spends page slots on rows it can
        # only replay, and persisted/ready rows advance on their own cursor.
        self.assignment_discovery = ProjectionDiscovery(
            store, states=PROJECTION_ASSIGNMENT_STATES, recent=True, outbox_coverage=self.has_outbox_coverage
        )
        self.finish_discovery = ProjectionDiscovery(
            store, states=PROJECTION_FINISH_STATES, outbox_coverage=self.has_outbox_coverage
        )
        # Search/people-stats work walks owe, converged off the ordered chain.
        self.index = ProjectionIndex()
        # Owners a sweep or wake wants drained; ``draining`` is live in this process.
        self.drain_requests: dict[str, int | None] = {}
        self.drain_request_counts = Counter() if owner_drain_admission_diagnostics_enabled() else None
        self.draining: set[str] = set()
        self.drains = None
        # Sweeps and wakes hand off from sync-pool threads while overlapping
        # reconcile passes and drains swap or extend on the event loop.
        self.handoff = threading.Lock()
        # Resume point of the held-partial scan; a short page wraps it.
        self.held_after: str | None = None
        self._held_cursor_baseline: dict | None = None
        self._held_sweep_lock = threading.Lock()
        # Upload dedupe of the held-partial pass in flight; spans budget stops
        # and wraps only when the scan's cursor does.
        self.held_pass_seen: set[tuple[str, str]] = set()
        # Resume point of the held-release scan; a short page wraps it.
        self.release_after: str | None = None

    def has_outbox_coverage(self) -> bool:
        return self.outbox_coverage is not None and self.outbox_coverage()

    def request_drain(self, owner_id: str, *, reason: str = 'unknown') -> None:
        with self.handoff:
            previous = self.drain_requests.get(owner_id)
            if self.drain_request_counts is not None:
                self.drain_request_counts['handoff_requests'] += 1
                self.drain_request_counts['handoff_coalesced'] += int(owner_id in self.drain_requests)
                if previous is not None or len(self.drain_requests) < drain_diagnostics.MAX_OWNERS:
                    self.drain_requests[owner_id] = (previous or 0) | drain_diagnostics.origin_mask(reason)
                    return
                self.drain_request_counts['handoff_overflow'] += 1
            self.drain_requests[owner_id] = None

    def owe_followups(self, segment_ids) -> None:
        with self.handoff:
            self.chain_followups = list(dict.fromkeys(self.chain_followups + list(segment_ids)))

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
            counts = self.drain_request_counts
            if counts is not None:
                self.drain_request_counts = Counter()
        if counts is not None and self.drains.diagnostics is not None:
            self.drains.diagnostics.counts.update(counts)
        self.drains.request(requests)

    def schedule_index_flush(self, owner_id: str | None = None) -> None:
        """Converge owed search work off-chain, optionally for one owner."""
        from utils.executors import db_executor, run_blocking, start_background_task

        if self.index.owed if owner_id is None else self.index.has_owed(owner_id):
            start_background_task(run_blocking(db_executor, self.index.flush, owner_id), name='batch_projection_index')

    def persist(self, segment_id: str) -> None:
        """Only ordered assignment holds the owner claim; receipts are the outbox."""
        with projection_phase('read'):
            job, entry, binding = self.store.read(segment_id)
        self._persist_read(segment_id, job, entry, binding)

    @settle_refusals(assignment=True)
    def _persist_read(self, segment_id, job, entry, binding, *, hint=None, claimed=False):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        if claimed:
            # The walk holds this owner's claim for its whole step.
            return self._assign(segment_id, job, entry, binding, finish=False, hint=hint)
        with projection_claim(self.store.store.namespace, owner_key(binding.owner_id)) as acquired:
            if not acquired:
                raise ProjectionBlocked('projection assignment claim busy')
            return self._assign(segment_id, job, entry, binding, finish=False, hint=hint)

    async def start_followups(self, priority=(), *, discover=True, include_walk=False):
        # Imported lazily: the synchronous worker seam remains lightweight.
        from utils.batch_pipeline.projection_followup import ProjectionFollowups

        if self.followups is None:
            self.followups = ProjectionFollowups(self)
        with self.handoff:
            tail, self.chain_followups = (
                (self.chain_followups, []) if discover or include_walk else ((), self.chain_followups)
            )
        if not discover and include_walk:
            priority, tail = (*priority, *tail), ()
        await self.followups.schedule(priority, tail=tail, discover=discover)

    def project(self, segment_id: str) -> dict | None:
        return self._project_read(segment_id, *self.store.read(segment_id))

    def apply_outbox_snapshot(self, segment_id, job, entry, binding) -> str:
        """Apply a delivery through the ordinary policy and receipt fences."""
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        try:
            if not policy.async_projection:
                self._project_read(segment_id, job, entry, binding)
                return 'incomplete'
            if entry['projection_state'] == 'pending':
                if self._persist_read(segment_id, job, entry, binding) is PRIVACY_HELD:
                    return 'blocked'
        except ProjectionPredecessorPending:
            if sweep_owner_chain_enabled() and projection_predecessor_replay_enabled():
                if owner_drain_enabled():
                    self.request_drain(binding.owner_id, reason='predecessor_replay')
                else:
                    try:
                        self.owe_followups(self.project_owner(binding.owner_id))
                    except Exception as error:
                        logger.error(
                            'event=batch_projection action=outbox_chain outcome=error exception_type=%s',
                            error_type(error),
                        )
            raise
        return 'followup'

    @settle_refusals()
    def _project_read(self, segment_id, job, entry, binding, *, hint=None, claimed=False):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        if policy.async_projection:
            if self._persist_read(segment_id, job, entry, binding, hint=hint, claimed=claimed) is PRIVACY_HELD:
                return None
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
                with projection_phase('project', policy, unit_key=segment_id):
                    result = self._project(segment_id, job, entry, binding, hint=hint)
                logger.info(
                    'event=batch_projection action=project outcome=%s',
                    'completed' if result is not None else 'waiting',
                )
                return result
        with projection_phase('project', policy, unit_key=segment_id):
            return self._project(segment_id, job, entry, binding, hint=hint)

    def _project(self, segment_id, job, entry, binding, *, hint=None):
        self._assign(segment_id, job, entry, binding, hint=hint)
        return self._finish(segment_id, job, entry, binding)

    def _assign(self, segment_id, job, entry, binding, *, finish=True, hint=None):
        if job.get('shadow'):
            raise ProjectionBlocked('shadow publication forbidden')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        item = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
        if item.source_reuse_key:
            from database.batch_pipeline_source_projection import project_alias

            if project_alias(self.store, item, binding, self.clock(), policy=policy):
                return
        session = self.store.session(segment_id, binding, self.clock(), policy=policy)
        if job.get('_projection_privacy_deleted'):
            persist_disposition(session, privacy_deleted=True)
            return
        skip_enabled = silence_read_skip_enabled()
        eligible = (
            (entry.get('result') or {}).get('outcome') == 'silence'
            and not binding.record_origin
            and not binding.native_record
        )
        silent = skip_enabled and eligible
        outcome = SilentReadOutcome.NOT_SILENT
        if eligible:
            outcome = SilentReadOutcome.SKIPPED if silent else SilentReadOutcome.DISABLED
        # A walk's fresh read showed no receipt; the transaction still fences.
        walk_skips_check = hint is not None and hint.successor and not entry.get('projection')
        if not walk_skips_check:
            record_silent_read_skip(SilentReadStage.ASSIGNMENT_PRECHECK, outcome)
        prechecked = not silent and not walk_skips_check
        if prechecked:
            try:
                with projection_phase('predecessor', policy, unit_key=segment_id):
                    self.store.check(session, speculative=True)
            except ProjectionReplay:
                return
            except BatchPrivacyBlocked as error:
                if error.reason != BatchPrivacyReason.CONVERSATION_DELETED:
                    raise
                persist_disposition(session, privacy_deleted=True)
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
                    if silent:
                        # prepare() in this transaction retains every authority,
                        # binding and predecessor fence. No follow-up is owed.
                        session.persist_empty(silence=True)
                        record_silent_read_skip(SilentReadStage.READY_ACK, outcome)
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
            except SyncAssignmentConflict as error:
                if not quarantines_assignment_conflict(error, job, now=self.clock()):
                    raise
                receipt = persist_disposition(session, quarantined=True, hold_reason='conflict')
                if receipt.get('state') == 'quarantined':
                    log_conflict_hold(error)
            except BatchPrivacyBlocked as error:
                if error.reason != BatchPrivacyReason.CONVERSATION_DELETED:
                    raise
                persist_disposition(session, privacy_deleted=True)
        else:
            with projection_phase('assignment', policy, unit_key=segment_id):
                self.assign_parts(item, entry, binding, finish=finish, policy=policy, hint=hint, job=job)
        if not silent:
            record_silent_read_skip(SilentReadStage.READY_ACK, outcome)

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

    @settle_refusals()
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
        return self.complete_content(
            item.segment_id,
            binding,
            policy=policy,
            silence=entry.get('result', {}).get('outcome') == 'silence',
        )

    def complete_content(self, segment_id, binding, *, policy=None, silence=False):
        policy = policy or self.store.policy(segment_id)
        entries = None
        eligible = silence and not binding.record_origin and not binding.native_record
        skip_enabled = eligible and silence_read_skip_enabled()
        if skip_enabled:
            # Reuse ordinary accounting's result reads to rule out known mixed
            # uploads before paying for a speculative completion transaction.
            with projection_phase('completion_scan', policy, unit_key=segment_id):
                entries = self.store.completion_entries(binding)
            if len(entries) == len(binding.segment_ids) and all(
                entry.get('result', {}).get('outcome') == 'silence'
                and (entry.get('projection') or {}).get('state') == 'ready'
                and not entry.get('projection_parts')
                for entry in entries.values()
            ):
                # This hint never authorizes completion: ALL sibling identities,
                # outcomes, privacy and accounting are verified transactionally.
                with projection_phase('completion', policy, unit_key=segment_id):
                    result = self.store.complete(segment_id, binding, self.clock(), None, policy=policy)
                if result is not None:
                    record_silent_read_skip(SilentReadStage.ACCOUNTING, SilentReadOutcome.SKIPPED)
                    record_silent_completion_reads(SilentReadOutcome.SKIPPED)
                    return self.publish_completion(binding, result, policy=policy, segment_id=segment_id)
        outcome = SilentReadOutcome.DISABLED if eligible and not skip_enabled else SilentReadOutcome.NOT_SILENT
        record_silent_read_skip(SilentReadStage.ACCOUNTING, outcome)
        with projection_phase('accounting', policy, unit_key=segment_id):
            accounting = (
                self.store.prepare_accounting(binding, self.clock(), result_entries=entries)
                if entries is not None
                else self.store.prepare_accounting(binding, self.clock())
            )
        if accounting is None:
            self.store.hold_for_quarantine(segment_id, binding, self.clock(), policy=policy)
            return None
        if not accounting.get('source_deleted'):
            with projection_phase('usage', policy, unit_key=segment_id):
                # Accounting may have waited on reads after this worker lost
                # its claim. Recheck before dispatching the idempotent Redis step.
                assert_delivery_claim(segment_id, lambda: self.store.ref('results', segment_id).get().to_dict() or {})
                record_speech(binding, accounting, self.clock())
        with projection_phase('completion', policy, unit_key=segment_id):
            result = self.store.complete(segment_id, binding, self.clock(), accounting, policy=policy)
        if result is not None:
            record_silent_completion_reads(outcome)
        return self.publish_completion(binding, result, policy=policy, segment_id=segment_id)

    def publish_completion(self, binding, result, *, policy, segment_id=None):
        if result is not None:
            # complete() aggregated every part before setting this disposition.
            # Never call the publisher, even with empty IDs, for a deleted job.
            if result.get('reason_code') != 'source_deleted':
                with projection_phase('publication', policy, unit_key=segment_id):
                    self.publish(binding, result)
            from utils.batch_pipeline.retention import expire_completed_segment

            for sibling in binding.segment_ids:
                retained = self.store.ref('results', sibling).get().to_dict() or {}
                if retained.get('projection_state') == 'erased':
                    continue
                with projection_phase('retention', policy, unit_key=sibling):
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
        if not accounting['completed'] and result.get('reason_code') != 'source_deleted':
            record_speech_steps(binding, accounting['source'], steps, times, self.clock())
        return result

    def sweep_held(
        self, limit: int = HELD_PARTIAL_PAGE, *, deadline: float | None = None, max_pages: int | None = None
    ) -> dict[str, int]:
        """Resume from the shared checkpoint, with local progress during read or write failures."""
        with self._held_sweep_lock:
            durable = projection_release.load_held_partial_cursor(self.store)
            if durable is not None and durable != self._held_cursor_baseline:
                # A first successful read of a missing document confirms the
                # local scan started at the beginning. Keep any unsaved work.
                if self._held_cursor_baseline is not None or durable:
                    self.held_after = projection_release.cursor_after_id(durable)
                    self.held_pass_seen.clear()
                self._held_cursor_baseline = durable
            counts = self._sweep_held_pages(limit, deadline=deadline, max_pages=max_pages)
            counts['reads'] += 1  # The initial checkpoint lookup.

            def record_cursor_read():
                counts['reads'] += 1

            confirmed = durable is not None
            # A nonempty pass can scan from None back to None. Publish that
            # wrap too, so a concurrent advance can fence out its completion.
            wrapped_with_work = not counts['more'] and counts['units'] > 0
            if durable is not None and (
                self.held_after != projection_release.cursor_after_id(durable) or wrapped_with_work
            ):
                committed = projection_release.advance_held_partial_cursor(
                    self.store, durable, self.held_after, self.clock(), record_read=record_cursor_read
                )
                confirmed = committed is not None
                if committed is not None:
                    self._held_cursor_baseline = committed
            if not counts['more'] and not confirmed:
                counts['wrap_unconfirmed'] = 1
            return counts

    def _sweep_held_pages(
        self, limit: int = HELD_PARTIAL_PAGE, *, deadline: float | None = None, max_pages: int | None = None
    ) -> dict[str, int]:
        """Pages of held units chained into one bounded pass; one partial attempt per upload.

        A ``deadline`` (a ``time.monotonic`` instant) or ``max_pages`` chains
        full pages back to back — checked only between pages, so a pass
        overruns its deadline by at most one page — while neither bound keeps
        the legacy single-page contract. ``pages`` counts the pages fetched by
        this call; ``units`` counts held documents
        examined; ``reads`` is what the caller should charge its read budget:
        one read per examined document plus, per attempted upload, 5 reads per
        sibling and 7 (the code-derived worst case of prepare_accounting plus
        the complete_partial transaction, which walk every sibling), floored
        at the benchmark's measured per-attempt worst case.
        ``more`` marks a pass stopped on a full page or a failed fetch with the
        cursor kept, so the caller can resume it without waiting out its
        interval. The upload dedupe spans the whole pass — across budget stops
        too — and resets only when a short page wraps the cursor.
        """
        counts = {'partial': 0, 'waiting': 0, 'error': 0, 'units': 0, 'reads': 0, 'more': 0, 'pages': 0}
        while True:
            try:
                page = held_candidates(self.store.client, self.store.store.namespace, limit, after_id=self.held_after)
            except Exception as error:
                # A failed fetch bills nothing but must not lose the pages the
                # pass already served: end the segment resumable, not by raise.
                counts['more'] = 1
                logger.warning(
                    'event=batch_held_partial action=fetch outcome=retry exception_type=%s', error_type(error)
                )
                return counts
            full = len(page) >= limit
            self.held_after = page[-1][0] if full else None
            counts['units'] += len(page)
            counts['reads'] += len(page)
            counts['more'] = 1 if full else 0
            counts['pages'] += 1
            for _, job in page:
                try:
                    binding = normalized_binding(job['projection_binding'])
                    if (binding.owner_id, binding.content_id) in self.held_pass_seen:
                        continue
                    self.held_pass_seen.add((binding.owner_id, binding.content_id))
                    # 5 reads per sibling and 7 more per attempt bound both
                    # accounting passes; the floor keeps a one-segment upload
                    # at the benchmark's measured per-attempt worst case.
                    counts['reads'] += max(16, 5 * len(binding.segment_ids) + 7)
                    counts['partial' if self.complete_held(binding) is not None else 'waiting'] += 1
                except Exception as error:
                    counts['error'] += 1
                    logger.warning('event=batch_held_partial outcome=retry exception_type=%s', error_type(error))
            if not full:
                # The scan wrapped: the pass is complete and the next one starts fresh.
                self.held_pass_seen = set()
                return counts
            if deadline is None and max_pages is None:
                return counts
            if deadline is not None and time.monotonic() >= deadline:
                return counts
            if max_pages is not None and counts['pages'] >= max_pages:
                return counts

    def release_held_scan(self, limit: int | None = None) -> dict[str, int]:
        """One bounded page of held units whose record target may be restored."""
        from database.batch_pipeline_projection_release import (
            RELEASE_PAGE,
            RELEASE_TICK_SECONDS,
            GHOST_SKIP_CLASSES,
            GHOST_AGE_BUCKETS,
            release_scan_pass_settled,
        )

        enabled = projection_hold_recovery_enabled()
        started = time.monotonic()
        counts, self.release_after, settled = release_scan_pass_settled(
            self.store,
            limit=limit if limit is not None else RELEASE_PAGE if enabled else HELD_PARTIAL_PAGE,
            after_id=self.release_after,
            now=self.clock(),
            deadline=time.monotonic() + RELEASE_TICK_SECONDS if enabled else None,
        )
        if settled and kill_switch('BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_WAKE_ENABLED'):
            self.owe_followups(settled)
        if counts.get('examined'):
            logger.info(
                'event=batch_projection action=release_held outcome=summary released=%d examined=%d waiting=%d error=%d elapsed_ms=%d ghost_settled=%d classified=%d skipped_by_class=%s age_buckets=%s',
                counts['released'],
                counts['examined'],
                counts['waiting'],
                counts['error'],
                int((time.monotonic() - started) * 1000),
                counts['ghost_settled'],
                counts['ghost_classified'],
                ','.join(f'{name}:{counts[f"ghost_skipped_{name}"]}' for name in GHOST_SKIP_CLASSES),
                ','.join(f'{name}:{counts[f"ghost_age_{name}"]}' for name in GHOST_AGE_BUCKETS),
            )
        return counts

    def assign_record_silence(self, item, binding, session, *, hint=None):
        incoming = {
            'id': binding.target_conversation_id,
            'started_at': datetime.fromtimestamp(item.capture_at, timezone.utc),
            'finished_at': datetime.fromtimestamp(item.capture_at + item.duration_seconds, timezone.utc),
            'transcript_segments': [],
            'data_protection_level': binding.data_protection_level,
            '_batch_require_live_target': True,
            '_batch_redrive_target': bool(session.entry.get('projection_redriven_at')),
            '_batch_replace_live': {
                'start': item.capture_at,
                'end': item.capture_at + item.duration_seconds,
                'terminal_empty_outcome': (session.entry.get('result') or {}).get('outcome'),
            },
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

    def _note_head_blocked(self, segment_id: str, error: BaseException) -> None:
        """Stamp a bounded-retry head's first failure time; one write per episode."""
        try:
            self.store.note_head_blocked(segment_id, self.clock(), error_type(error))
        except Exception as note_error:
            logger.warning(
                'event=batch_projection action=head_block_note outcome=retry exception_type=%s',
                error_type(note_error),
            )

    def _hold_failing_head(self, segment_id: str, job: dict, binding: ProjectionBinding) -> bool:
        """Hold a poison head: quarantine_held receipt, audio retained, watermark advanced."""
        try:
            policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
            session = self.store.session(segment_id, binding, self.clock(), policy=policy)
            persist_disposition(session, quarantined=True, hold_reason='poison_head')
            return True
        except Exception as error:
            logger.error(
                'event=batch_projection action=poison_hold outcome=retry exception_type=%s%s',
                error_type(error),
                error_site_field(error),
            )
            return False

    def resolve_failing_head(self, segment_id, job, entry, binding, error: BaseException) -> bool:
        """The generic poison-head rule at a chain head (lead ruling 5d2ae7).

        A non-transient exception nothing can resolve holds this unit and
        advances the watermark; transient failures and fresh awaiting-writer
        conflicts retry with a durable bound. ``ProjectionBlocked`` and privacy
        fences keep their own, more precise dispositions and never pass here.
        """
        if head_holds_without_retry(error, job, now=self.clock()) or head_retry_bound_exceeded(entry, self.clock()):
            return self._hold_failing_head(segment_id, job, binding)
        self._note_head_blocked(segment_id, error)
        return False

    def assign_parts(self, item, entry, binding, *, finish=True, policy=None, hint=None, job=None):
        policy = policy or self.store.policy(item.segment_id)
        from database.conversations import get_closest_conversation_to_timestamps
        from utils.batch_pipeline.context import ResolvedContext, resolve_context, require_repair_manifest
        from utils.batch_pipeline.projection_parts import split_result

        try:
            with projection_phase('load_result', policy, unit_key=item.segment_id):
                payload = self._payload(item, entry, hint)
            if not isinstance(payload, dict):
                # load_result is json.loads over the committed artifact: a
                # valid non-object body must take the contract disposition,
                # not an AttributeError that wedges the chain head.
                raise ValueError('batch result must be a JSON object')
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

                with projection_phase('manifest', policy, unit_key=item.segment_id):
                    prefetched = hint.prefetched if hint is not None else None
                    if prefetched is not None and prefetched.manifest is not None:
                        prefetched.settle_audio('consumed')
                        manifest = prefetched.manifest
                    elif prefetched is not None and prefetched.native_audio is not None:
                        assert hint is not None
                        manifest = prefetched.native_audio.context(self.fetch_audio, item, hint.deadline)
                    else:
                        manifest = read_context(self.fetch_audio(item))
            require_repair_manifest(item, binding, manifest, self.require_lineage_fence)
        except PAYLOAD_CONTRACT_ERRORS as error:
            if not payload_contract_violation(error):
                raise
            # The committed result/manifest itself violates the contract: no
            # retry can fix those bytes, and an unhandled raise would wedge
            # every later capture behind this chain head.
            self._quarantine_payload_contract(item, binding, policy, error)
            return
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
                if (
                    hint is not None
                    and hint.parallel_candidate
                    and not binding.target_conversation_id
                    and item.capture_time_trust != 'untrusted'
                ):
                    pending_candidate = self._start_candidate(binding, part, part_payload)
                context = ResolvedContext(binding.target_conversation_id)
                if manifest is not None and item.requires_compute_admission:
                    with projection_phase('context', policy, unit_key=item.segment_id):
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
                    with projection_phase('build', policy, unit_key=item.segment_id):
                        incoming = build_incoming(
                            part,
                            binding,
                            part_payload,
                            geolocation=context.geolocation,
                            batch_segment_id=item.segment_id,
                            policy=policy,
                        )
                    if incoming['transcript_segments']:
                        session.speaker_scope = incoming['transcript_segments'][0]['speaker_id_scope']
                    if binding.record_origin:
                        incoming['_batch_replace_live'] = {
                            'start': item.capture_at,
                            'end': item.capture_at + item.duration_seconds,
                            **({'preserve_existing': True} if binding.partial_record else {}),
                        }
                    if (binding.record_origin or policy.require_live_target) and context.target_id:
                        incoming['_batch_require_live_target'] = True
                    if entry.get('projection_redriven_at'):
                        incoming['_batch_redrive_target'] = True
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
                    if (
                        context.target_id is None
                        and incoming['transcript_segments']
                        and item.capture_time_trust != 'untrusted'
                    ):
                        with projection_phase('candidate', policy, unit_key=item.segment_id):
                            span = (int(incoming['started_at'].timestamp()), int(incoming['finished_at'].timestamp()))
                            deadline = hint.deadline if hint is not None else None
                            found, candidate = self._parallel_candidate(pending_candidate, span, deadline)
                            if not found:
                                candidate = get_closest_conversation_to_timestamps(binding.owner_id, *span)
                    if not incoming['transcript_segments']:
                        receipt = session.persist_empty()
                    else:
                        from utils.conversations.v3 import triggers as v3_triggers

                        # Same v3 admission as sync intake, or admitted owners get legacy duplicates.
                        v3_triggers.mark_new(binding.owner_id, incoming)
                        try:
                            assigned = (self.assign_conversation or conversations_db.assign_sync_conversation)(
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
                        v3_triggers.committed_sync_assignment(binding.owner_id, assigned[0])
                        transcript_receipts.enqueue(binding.owner_id, assigned[0], firestore_client=self.store.client)
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
            except ProjectionReplay as replay:
                receipt = replay.receipt
            except ProjectionGenerationAmbiguous:
                receipt = persist_disposition(session, quarantined=True, hold_reason='ambiguous_generation')
            except SyncAssignmentSuperseded:
                receipt = self.supersede(session)
            except SyncAssignmentConflict as error:
                if not quarantines_assignment_conflict(error, job, now=self.clock()):
                    raise
                receipt = persist_disposition(session, quarantined=True, hold_reason='conflict')
                if receipt.get('state') == 'quarantined':
                    log_conflict_hold(error)
            except BatchPrivacyBlocked as error:
                if error.reason != BatchPrivacyReason.CONVERSATION_DELETED:
                    if policy.projection_contention:
                        logger.error(
                            'event=batch_projection action=assignment outcome=error exception_type=%s%s',
                            error_type(error),
                            fence_reason_field(error),
                        )
                    raise
                receipt = persist_disposition(session, privacy_deleted=True)
            except PAYLOAD_CONTRACT_ERRORS as error:
                if not payload_contract_violation(error):
                    raise
                receipt = self._quarantine_payload_contract(item, binding, policy, error, session=session)
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

    def _quarantine_payload_contract(self, item, binding, policy, error, *, session=None):
        """Hold a committed payload that can never validate: the walk retries a
        chain head forever, so an unhandled contract ``ValueError`` wedges every
        later capture behind it. Same held disposition as a structural
        assignment conflict: quarantine receipt, watermark advance, recovery
        owns the unit, audio retained."""
        session = session or self.store.session(item.segment_id, binding, self.clock(), policy=policy)
        receipt = persist_disposition(session, quarantined=True, hold_reason='payload_contract')
        logger.warning(
            'event=batch_projection action=assignment outcome=payload_contract_quarantined exception_type=%s%s',
            error_type(error),
            error_site_field(error),
        )
        return receipt

    def supersede(self, session):
        return persist_disposition(session)

    def finish_part(self, item, binding, receipt, index, *, policy=None):
        policy = policy or self.store.policy(item.segment_id)
        if receipt.get('conversation_id'):
            self.store.settle_deleted_output(
                item.segment_id, binding, self.clock(), receipt, part_index=index, policy=policy
            )
        if receipt['state'] in {'ready', 'quarantined'}:
            return
        if receipt.get('conversation_id'):
            from utils.sync.bridge import finish_sync_bridges

            with projection_phase('bridge', policy, unit_key=item.segment_id):
                canonical = (
                    receipt['conversation_id']
                    if binding.record_origin
                    else finish_sync_bridges(
                        binding.owner_id,
                        receipt['conversation_id'],
                        silent=receipt.get('silent_redrive') is True,
                        require_python_owner=True,
                    )
                )
            outputs = receipt.get('size_rollover_outputs') or [{'conversation_id': canonical}]
            for output in outputs:
                output_id = output['conversation_id']
                if receipt.get('audio_required') and not binding.native_record:
                    with projection_phase('playback', policy, unit_key=item.segment_id):
                        if self.playback is not None:
                            self.playback(item, output_id)
                        else:
                            self.persist_playback(item, binding, output_id, receipt)
            if receipt['enrichment_required']:
                if (receipt.get('speaker_scope') or '').startswith('final:batch:'):
                    for output in outputs:
                        prepare_voice_evidence(self, item, binding, output['conversation_id'])
                with projection_phase('enrichment', policy, unit_key=item.segment_id):
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
        try:
            audio = self.fetch_audio(item)
        except NotFound:  # Transcript is projected; close like a no-survivor input.
            return artifact_missing.record('playback')
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
            self.request_drain(owner_id, reason='targeted_wake')
        logger.info(
            'event=batch_projection action=owner_chain outcome=summary advanced=%d followups=%d stop=%s',
            len(walk.advanced),
            len(walk.followups),
            walk.stop or 'end',
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
                acquired = drain_diagnostics.observe(
                    'claim_acquire',
                    stack.enter_context,
                    projection_claim(self.store.store.namespace, owner_key(owner_id)),
                )
                if not acquired:
                    logger.info('event=batch_projection action=owner_chain outcome=claim_busy')
                    return Walk([], [], stop='claim_busy')
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
        eager_followups: list[str] = []
        more = False
        blocked_head = snapshot = None

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

        stop = 'end'
        try:
            previous = self.store.projection_watermark(key)
        except Exception as error:
            if seed is not None:
                owe(*seed)
            failed(error)
            return Walk(
                list(dict.fromkeys(sid for group in groups.values() for sid in group)), advanced, stop='watermark_error'
            )
        if seed is not None and previous == seed[0] and not owe(*seed):
            return Walk(
                list(dict.fromkeys(sid for group in groups.values() for sid in group)), advanced, stop='owe_error'
            )
        for _ in range(max(1, limit)):
            if time.monotonic() >= deadline:
                more = True
                stop = 'deadline'
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
                    snapshot = self.store.ref('results', segment_id).get()
                    row = snapshot.to_dict() or {}
            except Exception as error:
                failed(error)
                stop = 'read_error'
                break
            if segment_id is None:
                break
            if row.get('projection_state') == 'erased':
                # The predecessor check walks erased receipts; so does discovery.
                previous = segment_id
                continue
            job = entry = binding = prefetched = None
            try:
                if prefetch is not None:
                    prefetched = drain_diagnostics.observe(
                        'prefetch_wait', prefetch.take, segment_id, timeout=deadline - time.monotonic()
                    )
                    if prefetched is NOT_READY:
                        # Still loading at the step deadline: the next step
                        # resumes here instead of holding this pool slot.
                        more = True
                        stop = 'prefetch_wait'
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
                privacy_held = False
                if policy.async_projection:
                    privacy_held = (
                        self._persist_read(segment_id, job, entry, binding, hint=hint, claimed=drain) is PRIVACY_HELD
                    )
                else:
                    self._project_read(segment_id, job, entry, binding, hint=hint, claimed=drain)
            except NativeAudioPending:
                if (
                    prefetch is not None
                    and isinstance(prefetched, Prefetched)
                    and prefetch.defer(segment_id, prefetched)
                ):
                    prefetched = None  # The turn still owns the pending candidate.
                more = True
                stop = 'prefetch_wait'
                break
            except StepDeadline:
                more = True  # a partial multipart; the next step resumes it
                stop = 'step_deadline'
                break
            except BatchPrivacyBlocked:
                stop, blocked_head = 'privacy_blocked', (segment_id, getattr(snapshot, 'update_time', None))
                break
            except ProjectionBlocked as error:
                stop = walk_block_stop(error, projection_block_reason(error))
                if stop.startswith('blocked_privacy_'):
                    blocked_head = (segment_id, getattr(snapshot, 'update_time', None))
                break
            except Exception as error:
                failed(error)
                if binding is None or not self.resolve_failing_head(segment_id, job, entry, binding, error):
                    stop = walk_head_stop(error) if binding is not None else 'head_error'
                    break
                # Held (or already terminal): continue iff the chain advanced.
                try:
                    watermark = self.store.projection_watermark(key)
                except Exception as watermark_error:
                    failed(watermark_error)
                    stop = 'watermark_error'
                    break
                if watermark != segment_id:
                    stop = 'hold_not_landed'
                    break  # the hold did not land; the sweep retries this head
                previous = segment_id
                advanced.append(segment_id)
                continue
            finally:
                if isinstance(prefetched, Prefetched):
                    prefetched.abandon_audio()
            try:
                watermark = self.store.projection_watermark(key)
            except Exception as error:
                # Persist succeeded but its advance is unknown: still owe it.
                if policy.async_projection:
                    owe(segment_id, binding)
                failed(error)
                stop = 'watermark_error'
                break
            if watermark != segment_id:
                stop = 'not_advanced'
                break  # Busy claim or partial multipart: the sweep retries it.
            previous = segment_id
            advanced.append(segment_id)
            if policy.async_projection:
                if segment_id == recovered:
                    first = binding.content_id
                if not privacy_held and not owe(segment_id, binding):
                    stop = 'owe_error'
                    break
                if not privacy_held and len(binding.segment_ids) == 1 and recent_native_record(job, self.clock()):
                    eager_followups.append(segment_id)
        else:
            more = True
            stop = 'limit'
        ordered = [groups.pop(first)] if first is not None else []
        followups = list(dict.fromkeys(sid for group in ordered + list(groups.values()) for sid in group))
        return Walk(followups, advanced, more, stop, blocked_head, tuple(eager_followups))

    def sweep(self, limit: int | None = None) -> dict[str, int]:
        """Bounded durable-log recovery; no in-memory callback is an outbox."""
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        counts = {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
        blocked: Counter[tuple[str, str]] = Counter()
        contention = False
        self.has_async_followups = False
        page_rows = serving_sweep_page_rows()
        size = page_rows if limit is None else max(1, min(limit, page_rows))
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
            job = entry = None
            try:
                job, entry, binding = self.store.read(segment_id)
                if drain and (binding.owner_id in self.draining or binding.owner_id in handed):
                    # That chain is the drain's: walking now (its claim would
                    # only refuse the row) or handed over earlier in this pass.
                    counts['waiting'] += 1
                    continue
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                contention = contention or policy.projection_contention
                privacy_held = False
                if policy.async_projection:
                    self.has_async_followups = True
                    privacy_held = self._persist_read(segment_id, job, entry, binding) is PRIVACY_HELD
                    result = None
                else:
                    result = self._project_read(segment_id, job, entry, binding)
                counts['completed' if result is not None else 'waiting'] += 1
                touched.add(segment_id)
            except ProjectionPredecessorPending:
                blocked[sweep_block_group(entry, 'predecessor_pending')] += 1
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
                        self.request_drain(binding.owner_id, reason='predecessor_replay')
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
            except (ProjectionBlocked, BatchPrivacyBlocked) as error:
                blocked[sweep_block_group(entry, sweep_block_reason(error))] += 1
                continue
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s%s',
                    error_type(error),
                    error_site_field(error),
                )
                if job is not None and binding is not None:
                    # Same generic poison-head rule as the walk: a page row
                    # whose step fails terminally holds instead of re-erroring
                    # on every pass.
                    if self.resolve_failing_head(segment_id, job, entry, binding, error):
                        blocked[sweep_block_group(entry, 'failing_head_held')] += 1
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
                    self.request_drain(binding.owner_id, reason='discovery_after_assignment')
                elif binding.owner_id not in walked:
                    if chain_deadline is None:
                        chain_deadline = time.monotonic() + OWNER_CHAIN_SECONDS
                    budget = max(0.0, min(OWNER_CHAIN_SECONDS, chain_deadline - time.monotonic()))
                seed = (segment_id, binding) if policy.async_projection and not privacy_held else None
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
            contention = self._sweep_finish(size, counts, blocked, touched | chained) or contention
        counts['blocked'] = sum(blocked.values())
        # A read can be fenced before its policy is available. Include those
        # attempts without changing the historical contention-summary denominator.
        if contention or blocked:
            logger.info(
                'event=batch_projection action=%s outcome=summary completed=%d waiting=%d blocked=%d error=%d '
                'blocked_groups=%s',
                'sweep' if contention else 'sweep_blocked',
                counts['completed'],
                counts['waiting'],
                counts['blocked'],
                counts['error'],
                json.dumps(
                    [[reason, digest, n] for (reason, digest), n in sorted(blocked.items())], separators=(',', ':')
                ),
            )
        if chain and walked:
            logger.info(
                'event=batch_projection action=sweep_chain outcome=summary owners=%d advanced=%d',
                len(walked),
                len(chained),
            )
        return counts

    def _sweep_finish(
        self, size: int, counts: dict[str, int], blocked: Counter[tuple[str, str]], touched: set[str]
    ) -> bool:
        """Advance persisted/ready rows that the pending-only assignment page skips.

        Async rows belong to the follow-up drain; seeing one keeps it scheduled.
        Synchronous-policy rows replay assignment and finish exactly as the
        mixed page did, so no persisted or ready obligation loses its retry.
        """
        from database.batch_pipeline_privacy import BatchPrivacyBlocked

        contention = False
        for segment_id in self.finish_page.page(size):
            if segment_id in touched:
                continue
            PROJECTION_FINISH_READS.inc()
            entry = None
            try:
                job, entry, binding = self.store.read(segment_id)
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                contention = contention or policy.projection_contention
                if policy.async_projection:
                    self.finish_page.observed_async(segment_id, entry)
                    continue
                result = self._project_read(segment_id, job, entry, binding)
                counts['completed' if result is not None else 'waiting'] += 1
                if result is not None:
                    PROJECTION_FINISH_COMPLETED.inc()
            except (ProjectionBlocked, BatchPrivacyBlocked) as error:
                blocked[sweep_block_group(entry, sweep_block_reason(error))] += 1
            except Exception as error:
                counts['error'] += 1
                logger.error(
                    'event=batch_projection action=sweep outcome=error exception_type=%s%s',
                    error_type(error),
                    error_site_field(error),
                )
        return contention
