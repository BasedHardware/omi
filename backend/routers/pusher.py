"""The /v1/trigger/listen WebSocket: binary device-audio ingestion, live STT and
speaker dispatch, and record-barrier custody for realtime capture.

Each long-lived connection supervises several concurrent tasks under a strict
executor-pool discipline (workers are leaf operations; coordinators never share
a pool with their children), and uncommitted audio is never dropped -- durable
receipts and backpressure own the handoff. backend/docs/listen_pusher_pipeline.mdx
owns the wire and finalization contract this file implements.
"""

import hashlib
import os
import struct
import asyncio
import time
import uuid
from contextlib import ExitStack
from grpc import StatusCode
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple, cast
from utils.pusher_audio_window import append_window_run, v2_overlap_conflict, AUDIO_TIMELINE_CONTINUITY_TOLERANCE
from config.audio_custody import framed_pack
from config.audio_outbox import enabled as audio_outbox_enabled
from utils.pusher_audio_projection import PusherAudioProjection
from utils.batch_pipeline.record_projection_rebuild import projection_owner_gone
from utils.pusher_record_barrier import PusherRecordBarrier
from utils.pusher_storage_budget import RetainedPcmWindow, StoragePcmBudget, storage_pcm_budget_bytes
from utils.observability.reasons import PusherPcmErrorReason, PusherPcmStage, ReasonFamily, reason_label
from utils.pusher_receive_metrics import SocketObservation, observe_work
from utils.pusher_record_finish import (
    ProjectionQueueWaitTimeout,
    RecordProjectionQueue,
    retain_closed_record_drain,
    abandon_evicted_record_drain,
    log_closed_record_drain_cap,
)

from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from starlette.websockets import WebSocketState
from google.cloud.exceptions import NotFound
from google.api_core.exceptions import InvalidArgument

from database.privacy_check_metrics import with_session_census
from database import users as users_db
from database.legal_holds import DestructiveOperationInProgress
from utils.conversations.speaker_identity_retry import schedule_completed_identity_retries
from utils.pusher_finalization import FINALIZATION_RESULT_PROTOCOL_LEGACY, process_conversation_task
from utils.pusher_protocol import (
    BUFFERED_AUDIO_MAX_BYTES,
    MAX_SAMPLE_RATE,
    MIN_SAMPLE_RATE,
    PRIVATE_CLOUD_QUEUE_MAX_SIZE,
    AUDIO_TIMELINE_PROTOCOL,
    AudioBytesQueueItem,
    ByteBudget,
    PrivateCloudChunk,
    PrivateCloudSpan,
    SpeakerSampleRequest,
    TranscriptQueueItem,
    append_bounded,
    audio_timeline_ack_frame,
    audio_custody_ack_frame,
    bound_private_pending,
    extend_bounded,
    frame_header,
    json_object,
    pusher_session_outcome,
)
from utils.apps import is_audio_bytes_app_enabled
from utils.app_integrations import (
    trigger_realtime_integrations,
    trigger_realtime_audio_bytes,
)
from utils.executors import (
    db_executor,
    storage_executor,
    record_barrier_executor,
    run_blocking,
    start_background_task,
    ExecutorFutureTracker,
)
from utils.episodes.live import on_session_end as flush_episode_moment
from utils.async_tasks import (
    supervise_tasks,
    drain_tasks,
    create_named_task,
    wait_for_event,
)
from utils.webhooks import (
    send_audio_bytes_developer_webhook,
    realtime_transcript_webhook,
    get_audio_bytes_webhook_seconds,
)
from utils.other.storage import AudioChunkContentConflict, upload_audio_chunks_batch
from utils.other.audio_outbox import AudioReceipt, AudioProjection, commit_pcm_window, read_pcm
from utils.other.audio_outbox_metrics import BACKPRESSURE, record_failure, record_would_drop
from utils.journey_metrics_contract import ClientKind, bounded_client_kind
from utils.metrics import (
    OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL,
    OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL,
    PUSHER_ACTIVE_WS_CONNECTIONS,
    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS,
    PUSHER_RECONCILE_LISTS_SKIPPED_TOTAL,
    PUSHER_SILENT_RUN_FLUSHES_SKIPPED_TOTAL,
    PUSHER_STORAGE_PCM_INFLIGHT_BYTES,
    PUSHER_STORAGE_PCM_BUDGET_LIMIT_BYTES,
    PUSHER_STORAGE_PCM_REFUSALS_TOTAL,
    PUSHER_STORAGE_PCM_ERRORS_TOTAL,
)
from utils.readiness import ReadinessGate
from utils.observability.fallback import record_fallback
from utils.observability.journeys import JourneyAttempt
from utils.speaker_learning_jobs import run_authorized_person_learning, schedule_person_voice_learning_retry
import logging

from config.rollout_cohorts import warm_rollout_cohorts

logger = logging.getLogger(__name__)

router = APIRouter()
_pcm_commits: set[asyncio.Task[Any]] = set()
MAX_PCM_WINDOW_FRAMES = 4096
storage_pcm_budget = StoragePcmBudget(storage_pcm_budget_bytes())
PUSHER_STORAGE_PCM_BUDGET_LIMIT_BYTES.set(storage_pcm_budget.limit)
_pcm_error_logged_at: dict[str, float] = {}
# Count every fail-open through the shared helper; the caller supplies the
# rate-limited warning below instead of a duplicate warning for every window.
_pcm_fallback_metrics_log = logging.Logger(f'{__name__}.pcm_fallback', level=logging.CRITICAL)


def _record_pcm_error(reason: PusherPcmErrorReason, error: Exception) -> None:
    """Bounded telemetry must never interfere with custody or socket survival."""
    try:
        PUSHER_STORAGE_PCM_ERRORS_TOTAL.labels(
            reason=reason_label(ReasonFamily.PUSHER_PCM, reason, PusherPcmErrorReason)
        ).inc()
    except Exception:
        pass
    try:
        if reason is PusherPcmErrorReason.ACQUIRE:
            record_fallback(
                component='pusher',
                from_mode='storage_pcm_budget',
                to_mode='unbudgeted_storage',
                reason='gate_unavailable',
                outcome='degraded',
                log=_pcm_fallback_metrics_log,
            )
    except Exception:
        pass
    try:
        now = time.monotonic()
        if now - _pcm_error_logged_at.get(reason.value, float('-inf')) >= 60:
            _pcm_error_logged_at[reason.value] = now
            logger.warning('event=pusher_pcm_error reason=%s error_type=%s', reason.value, type(error).__name__)
    except Exception:
        pass


def _parse_finalization_result_protocol(value: Any) -> int:
    """Return the result capability, defaulting callers to the legacy wire contract."""
    if value is None:
        return FINALIZATION_RESULT_PROTOCOL_LEGACY
    if isinstance(value, bool) or not isinstance(value, int) or value < FINALIZATION_RESULT_PROTOCOL_LEGACY:
        raise ValueError('finalization_result_protocol must be a positive integer')
    return value


# Constants for speaker sample extraction
SPEAKER_SAMPLE_PROCESS_INTERVAL = 15.0
SPEAKER_SAMPLE_MIN_AGE = 120.0

# Constants for private cloud sync
PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL = 1.0
PRIVATE_CLOUD_CHUNK_DURATION = 60.0
PRIVATE_CLOUD_BATCH_MAX_AGE = 60.0  # seconds — flush batch if oldest chunk exceeds this age
PRIVATE_CLOUD_SYNC_MAX_RETRIES = 3
# Bounded requeue passes for a transient durable-projection failure before the
# batch drops to raw-live receipt recovery (matching the legacy batch path's
# three attempts). Deterministic ValueError conflicts never retry.
PROJECTION_RETRY_BUDGET = 2
# Audio-timeline v2 continuity: 1 ms filename-rounding tolerance. A positive
# discontinuity beyond it flushes the partial chunk and pending batch; an
# overlap is trimmed (or an exact replay ignored); conflicting bytes for the
# same range fail closed and are never overwritten.


def _projection_raising_frame(exc: BaseException) -> str:
    """Innermost raising frame name, for RCA attribution of projection failures.

    Only the code object's name is ever returned — the exception message and
    args can carry user-identifying object paths and must not reach logs.
    """
    frame_name = 'unknown'
    tb = exc.__traceback__
    while tb is not None:
        frame_name = tb.tb_frame.f_code.co_name
        tb = tb.tb_next
    return frame_name


def _projection_grpc_code(exc: BaseException) -> str:
    """Only the SDK's closed gRPC status enum; never message/metadata/reason text."""
    code = cast(object, getattr(exc, 'grpc_status_code', None))
    if isinstance(code, StatusCode):
        return code.name
    return 'UNKNOWN'


# Queue size limits
SPEAKER_SAMPLE_QUEUE_WARN_SIZE = 100

# Bounded ledger of recently flushed v2 runs: (start_wall, end_wall, sha256 of
# the flushed bytes). An overlapping replay whose conflict window reaches past
# the live buffer can only be reconciled against these digests; anything the
# ledger no longer covers fails closed. 64 runs bounds the memory (~200 B)
# while covering over an hour of 60 s chunks.
V2_FLUSHED_RUN_LEDGER_SIZE = 64

# Constants for transcript queue batching
TRANSCRIPT_QUEUE_FLUSH_INTERVAL = 1.0  # seconds
TRANSCRIPT_QUEUE_WARN_SIZE = 50

# Constants for audio bytes queue
AUDIO_BYTES_QUEUE_WARN_SIZE = 20

# Receive timeout: if no data arrives for this long, the connection is considered dead.
# Backend-listen sends heartbeats every ~30s, so 5 minutes without ANY data means the
# upstream connection is gone.  Without this, half-open TCP connections hang forever,
# leaking the gauge + ~15 MB per ghost connection.
WS_RECEIVE_TIMEOUT = 300.0  # seconds

# After receive_task exits, background tasks get this long to drain their queues
# before being force-cancelled.  Prevents hung GCS uploads or webhook calls from
# blocking cleanup indefinitely.
BG_DRAIN_TIMEOUT = 30.0  # seconds
RECORD_INLINE_FINISH_TIMEOUT = 20.0  # projection wait and metadata combined


def _projection_wait_bound_enabled() -> bool:
    """Emergency rollback of the capacity deadline only; custody ownership stays."""
    return os.getenv('PUSHER_PROJECTION_QUEUE_WAIT_BOUND_ENABLED', 'true').strip().lower() != 'false'


def _ack_peer_departed(exc: Exception, websocket: Any) -> bool:
    if isinstance(exc, (WebSocketDisconnect, OSError)):
        return True
    return isinstance(exc, RuntimeError) and (
        getattr(websocket, 'application_state', None) == WebSocketState.DISCONNECTED
        or getattr(websocket, 'client_state', None) == WebSocketState.DISCONNECTED
        or str(exc) == 'Cannot call "send" once a close message has been sent.'
    )


async def _dispatch_transcript_item(
    uid: str, segments: List[Dict[str, Any]], memory_id: Optional[str], client_kind: ClientKind = 'unknown'
) -> None:
    async def run(sink: str, call: Awaitable[Any]) -> None:
        try:
            await call
        except Exception as e:
            logger.error('Error processing transcript %s type=%s uid=%s', sink, type(e).__name__, uid)

    await asyncio.gather(
        run('integrations', trigger_realtime_integrations(uid, segments, memory_id, client_kind=client_kind)),
        run('webhook', realtime_transcript_webhook(uid, segments, client_kind=client_kind)),
    )


def _queue_speaker_sample_request(data: bytes, speaker_sample_queue: 'Deque[SpeakerSampleRequest]', uid: str) -> None:
    """Parse and queue an opcode-105 speaker sample request; malformed frames raise."""
    res = json_object(data)
    person_id = res.get('person_id')
    conv_id = res.get('conversation_id')
    segment_ids = res.get('segment_ids', [])
    if person_id is not None and not isinstance(person_id, str):
        raise ValueError('person_id must be a string')
    if conv_id is not None and not isinstance(conv_id, str):
        raise ValueError('conversation_id must be a string')
    if not isinstance(segment_ids, list) or not all(isinstance(segment_id, str) for segment_id in segment_ids):
        raise ValueError('segment_ids must be a list of strings')
    if person_id and conv_id and segment_ids:
        if len(speaker_sample_queue) >= SPEAKER_SAMPLE_QUEUE_WARN_SIZE:
            logger.warning(f"Warning: speaker_sample_queue size {len(speaker_sample_queue)} {uid}")
        logger.info(f"Queued speaker sample request: person={person_id}, {len(segment_ids)} segments {uid}")
        append_bounded(
            speaker_sample_queue,
            {
                'person_id': person_id,
                'conversation_id': conv_id,
                'segment_ids': segment_ids,
                'queued_at': time.time(),
            },
            'speaker_sample',
        )


async def _commit_durable_audio_window(
    *,
    uid: str,
    payload: bytes,
    frames: List[Dict[str, Any]],
    conversation_id: Optional[str],
    start: Optional[float],
    sample_rate: int,
    custody_root: str,
    protection_level: Optional[str],
    audio_custody: Optional[int],
    timeline_v2: bool,
    websocket: Any,
    durable_queue: RecordProjectionQueue,
    budget: ByteBudget,
    queue_wait_timeout: float | None,
    on_committed: Optional[Callable[[], None]] = None,
    framed: bool = False,
    tail: bool = False,
) -> Optional[AudioReceipt]:
    """Commit one immutable media+manifest pair for a buffered audio window.

    The per-message path this replaces wrote a custody pair per opcode-101
    frame; at the ~0.5-1 s message cadence that was ~15-18M GCS writes/day
    fleet-wide. Windows ride the same flush boundaries the batched .batch.enc
    path always used (60 s of audio, conversation switch, discontinuity,
    process request, shutdown), so a receipt still exists only after both
    immutable objects commit and nothing acknowledged is ever uncommitted.
    An audio ACK still requires both remote objects; a failed commit leaves
    the producer unacknowledged. Returns None when there is no window to
    commit.
    """
    if not frames or start is None:
        return None
    # Refusal is an ordinary non-ACK outcome, never an exception into socket
    # supervision. Nothing owns a receipt and the caller retains its buffers.
    admission = storage_pcm_budget
    payload_size = len(payload)
    reserved = False
    admitted = True
    try:
        if admission.limit:
            admitted = admission.admit(payload_size, tail=tail)
            reserved = admitted
    except Exception as exc:
        # admit rolls back even a partially mutated counter. A budget fault
        # uses the flag-0 dispatch path; it cannot become a socket failure.
        _record_pcm_error(PusherPcmErrorReason.ACQUIRE, exc)
    if not admitted:
        try:
            PUSHER_STORAGE_PCM_REFUSALS_TOTAL.labels(
                stage=reason_label(
                    ReasonFamily.PUSHER_PCM, PusherPcmStage.TAIL if tail else PusherPcmStage.LIVE, PusherPcmStage
                )
            ).inc()
        except Exception:
            pass
        return None
    pcm_observed = False
    storage_task = None
    try:
        try:
            PUSHER_STORAGE_PCM_INFLIGHT_BYTES.inc(len(payload))
            pcm_observed = True
        except Exception:
            pass
        with observe_work('custody_commit'):
            storage_call = run_blocking(
                storage_executor,
                commit_pcm_window,
                uid,
                payload,
                conversation_id,
                start,
                sample_rate,
                custody_root,
                frames[0]['sequence'],
                frames,
                data_protection_level=protection_level,
                clock_source='server_projected' if timeline_v2 else 'arrival_estimate',
                framed=framed,
            )
            if reserved:
                # Shield this await independently of the socket tracker: byte
                # capacity belongs to the actual storage completion, including
                # cancellation before submission or during a running thread.
                storage_task = create_named_task(storage_call, name='pusher_pcm_commit', task_set=_pcm_commits)
                receipt = await asyncio.shield(storage_task)
            else:
                receipt = await storage_call  # Flag 0 retains today's exact dispatch.
    finally:

        def settled(done=None):
            if done is not None and not done.cancelled():
                error = done.exception()
                if error is not None:
                    _record_pcm_error(PusherPcmErrorReason.LATE_STORAGE, error)
            if reserved:
                try:
                    admission.settle(payload_size)
                except Exception as exc:
                    # settle retires exactly this reservation even when the
                    # underlying release fails before or after mutation.
                    _record_pcm_error(PusherPcmErrorReason.RELEASE, exc)
            if pcm_observed:
                try:
                    PUSHER_STORAGE_PCM_INFLIGHT_BYTES.dec(payload_size)
                except Exception:
                    pass

        if storage_task is not None and not storage_task.done():
            storage_task.add_done_callback(settled)
        else:
            settled()
    if receipt.conversation_id and receipt.samples:
        durable_queue.stage_committed(
            AudioProjection(receipt, start, 0, receipt.samples, tuple(frames) if framed else ())
        )
    payload_size = len(payload)
    del payload  # Queue-capacity wait owns a receipt only, never a second PCM copy.
    budget.release(payload_size)
    if on_committed is not None:
        on_committed()  # Drop the PCM buffer now; the committed reference has an owner.
    with observe_work('projection_enqueue'):
        if audio_custody == 1:
            try:
                await websocket.send_bytes(audio_custody_ack_frame(receipt.to_dict()))
            except Exception as exc:
                # Slot ownership precedes the ACK: peer departure cannot bypass
                # projection delivery. The ordinary close worker promotes it.
                if _ack_peer_departed(exc, websocket):
                    raise WebSocketDisconnect(code=1006) from None
                raise
        if receipt.conversation_id and receipt.samples:
            if durable_queue.full():
                BACKPRESSURE.labels(stage='pusher_queue').inc()
                record_would_drop('pusher_queue')
            await durable_queue.deliver_pending(timeout=queue_wait_timeout)
    return receipt


async def _websocket_util_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
    client_kind: str = 'unknown',
    audio_timeline: Optional[int] = None,
    audio_custody: Optional[int] = None,
) -> None:
    observation = SocketObservation()
    try:
        await _run_websocket_util_trigger(
            websocket, uid, sample_rate, client_kind, audio_timeline, audio_custody, observation=observation
        )
    except asyncio.CancelledError:
        observation.reason = 'cancelled'
        raise
    except Exception:
        observation.reason = 'application_error'
        raise
    finally:
        observation.close()  # No await: even repeated cancellation cannot skip close accounting.


async def _run_websocket_util_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int,
    client_kind: str,
    audio_timeline: Optional[int],
    audio_custody: Optional[int],
    *,
    observation: SocketObservation,
) -> None:
    logger.info(f'_websocket_util_trigger {uid}')
    resolved_client_kind = bounded_client_kind(client_kind)

    try:
        await websocket.accept()
    except RuntimeError as e:
        logger.error(e)
        await websocket.close(code=1011, reason="Dirty state")
        return

    if not MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE:
        await websocket.close(code=1008, reason='Invalid sample rate')
        return
    if audio_custody not in (None, 1):
        await websocket.close(code=1008, reason='Unsupported audio custody version')
        return

    # Audio-timeline v2 opt-in: only acknowledged connections get v2
    # continuity handling. The acknowledgment is sent before any other frame
    # so the listen side consumes it in its connect path; an old listen that
    # never sent the query parameter sees nothing change.
    audio_timeline_v2 = False
    if audio_timeline is not None:
        if isinstance(audio_timeline, bool) or audio_timeline != AUDIO_TIMELINE_PROTOCOL:
            await websocket.close(code=1008, reason='Unsupported audio timeline version')
            return
        audio_timeline_v2 = True
        try:
            await websocket.send_bytes(audio_timeline_ack_frame())
        except Exception as e:
            logger.error(f'Failed to send audio timeline ack: {e} {uid}')
            return

    # Defense-in-depth: during drain the LB should already have removed us from
    # the NEG, but reject straggler NEW connections.  We accept the handshake
    # FIRST so the client sees a clean WS close frame (1001 Going Away) rather
    # than a failed HTTP upgrade — a pre-accept close is surfaced as an
    # exception by the websockets client and recorded as a circuit-breaker
    # failure in backend-listen (backend/utils/pusher.py), which can trip the
    # pod's pusher circuit during a normal rollout.
    if not ReadinessGate.is_serving():
        logger.info(f'Rejecting new WS for {uid}: pusher is draining')
        await websocket.close(code=1001)
        return

    await warm_rollout_cohorts(uid)
    observation.reason = 'peer'
    journey_attempt = JourneyAttempt('pusher_session')
    websocket_active = True
    shutdown_event = asyncio.Event()
    websocket_close_code = 1000
    application_failed = False

    try:
        # audio bytes
        audio_bytes_webhook_delay_seconds = await run_blocking(db_executor, get_audio_bytes_webhook_seconds, uid)
        audio_bytes_trigger_delay_seconds = 4
        has_audio_apps_enabled = await run_blocking(db_executor, is_audio_bytes_app_enabled, uid)
        private_cloud_sync_enabled = await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
        cached_protection_level = (
            (await run_blocking(db_executor, users_db.get_data_protection_level, uid))
            if private_cloud_sync_enabled
            else None
        )
    except asyncio.CancelledError:
        journey_attempt.finish('cancelled')
        raise
    except Exception:
        journey_attempt.finish('failure')
        raise

    # Bounded queues — prevent unbounded memory growth during backpressure
    speaker_sample_queue: deque[SpeakerSampleRequest] = deque(maxlen=SPEAKER_SAMPLE_QUEUE_WARN_SIZE)
    transcript_queue: deque[TranscriptQueueItem] = deque(maxlen=TRANSCRIPT_QUEUE_WARN_SIZE)
    audio_bytes_queue: deque[AudioBytesQueueItem] = deque(maxlen=AUDIO_BYTES_QUEUE_WARN_SIZE)

    # private_cloud_queue caps at PRIVATE_CLOUD_QUEUE_MAX_SIZE to prevent OOM kills.
    # An OOM kill loses ALL queued data for ALL users on the pod — dropping the oldest
    # chunk for one user is strictly better than killing the pod.
    private_cloud_queue: deque[PrivateCloudChunk] = deque(maxlen=PRIVATE_CLOUD_QUEUE_MAX_SIZE)
    audio_bytes_event = asyncio.Event()  # Signals when items are added for instant wake
    audio_budget = ByteBudget(BUFFERED_AUDIO_MAX_BYTES)
    durable_audio = audio_outbox_enabled()
    log_closed_record_drain_cap()
    record_futures = ExecutorFutureTracker(storage_executor, record_barrier_executor)
    framed_audio = durable_audio and audio_timeline_v2 and sample_rate == 16000 and framed_pack(uid)
    # The bounded lane holds generation-pinned references, never the only PCM.
    # A crash after commit but before queue.put is recoverable via raw-live's
    # existing per-conversation playback index, independent of this process.
    durable_queue = RecordProjectionQueue(maxsize=PRIVATE_CLOUD_QUEUE_MAX_SIZE)
    refused_windows: deque[RetainedPcmWindow] = deque()
    pcm_admission_wait_active = False
    queue_wait_timeout = WS_RECEIVE_TIMEOUT if _projection_wait_bound_enabled() else None
    inline_finish_conversation: Optional[str] = None
    inline_projection_drained = asyncio.Event()
    inline_finish_done = asyncio.Event()
    custody_root = uuid.uuid4().hex
    custody_sequence = 0

    audio_projection = PusherAudioProjection(uid)
    deleted_conversations: set[str] = set()

    async def process_durable_private_cloud_queue() -> None:
        # Pending conversations hold only receipts. Hydrate at most one bounded
        # contiguous batch for the legacy playback projection, preserving the
        # old 60-second write cadence without retaining 60 seconds of PCM.
        pending_refs: dict[str, list[AudioProjection]] = {}
        queued_at: dict[str, float] = {}
        identity_refreshed: set[str] = set()
        projection_retries: dict[str, int] = {}

        async def flush_refs(conv_id: str) -> None:
            refs = pending_refs.pop(conv_id, [])
            queued_at.pop(conv_id, None)
            if not refs or conv_id in deleted_conversations:
                return

            try:
                chunks: List[Dict[str, Any]] = []
                with observe_work('drain_readback'):
                    for ref in refs:
                        pcm = await run_blocking(storage_executor, read_pcm, uid, ref.receipt)
                        pcm = pcm[ref.offset_samples * 2 : (ref.offset_samples + ref.samples) * 2]
                        if len(pcm) != ref.samples * 2:
                            raise ValueError('durable projection sample range is incomplete')
                        chunk: Dict[str, Any] = {'data': pcm, 'timestamp': ref.start}
                        if ref.frames:
                            chunk['custody_receipt'] = ref.receipt.to_dict()
                        if audio_timeline_v2:
                            chunk['span'] = {'start': ref.start, 'samples': ref.samples, 'sample_rate': ref.sample_rate}
                        chunks.append(chunk)
                if not audio_timeline_v2:
                    # Legacy headers are last-arrival-minus-duration estimates,
                    # not capture positions. Preserve the old continuous batch
                    # and its first timestamp; jitter cannot create v2 spans.
                    chunks = [{'data': b''.join(chunk['data'] for chunk in chunks), 'timestamp': refs[0].start}]
                with observe_work('drain_upload'):
                    uploaded_paths = await run_blocking(
                        storage_executor,
                        upload_audio_chunks_batch,
                        chunks,
                        uid,
                        conv_id,
                        cached_protection_level,
                        sample_rate=sample_rate,
                    )
                OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL.labels(
                    reason='with_spans' if audio_timeline_v2 else 'without_spans'
                ).inc()
                with observe_work('drain_refresh'):
                    applied = await run_blocking(
                        storage_executor,
                        audio_projection.refresh,
                        conv_id,
                        uploaded_paths,
                        force=not websocket_active or conv_id in record_close_requests,
                    )
                if applied:
                    schedule_person_voice_learning_retry(uid, conv_id)
                    if len(identity_refreshed) < 128:
                        identity_refreshed.add(conv_id)
                elif applied is False:
                    deleted_conversations.add(conv_id)
                projection_retries.pop(conv_id, None)
            except AudioChunkContentConflict:
                audio_projection.inventory.pop(conv_id, None)
                # Deterministic projection conflict: different bytes already
                # live at this run's content-addressed name. Every retry would
                # re-run the same collision, so the batch drops now.
                # Projection is optional for custody: media AND its exact
                # manifest survive in remote storage and are discoverable
                # by raw-live playback after restart/reconnect.
                await record_barrier.fail_recording(conv_id)
                record_failure('projection', reason='conflict')
                record_fallback(
                    component='pusher',
                    from_mode='private_cloud_sync',
                    to_mode='raw_audio',
                    reason='other',
                    outcome='degraded',
                    log=logger,
                )
                logger.warning('Durable audio projection conflict; archive receipt retained')
            except InvalidArgument as exc:
                audio_projection.inventory.pop(conv_id, None)
                await audio_projection.defer_rebuild(conv_id)
                # Custody and its generation-pinned manifest remain durable.
                # Retrying a deterministic projection rejection cannot repair
                # the payload, and a sticky custody failure would strand it.
                projection_retries.pop(conv_id, None)
                record_failure('projection', reason='invalid_argument')
                record_fallback(
                    component='pusher',
                    from_mode='private_cloud_sync',
                    to_mode='raw_audio',
                    reason='other',
                    outcome='degraded',
                    log=logger,
                )
                logger.warning(
                    'Durable audio projection failure class: %s raised by %s grpc_code=%s',
                    type(exc).__name__,
                    _projection_raising_frame(exc),
                    _projection_grpc_code(exc),
                )
                logger.info('Durable audio projection rejected; archive receipt retained')
            except NotFound as exc:
                # A pinned-generation 404 during projection means the objects
                # were purged. Conversation deletion (user delete, merge,
                # empty-recording cleanup) removes the conversation's whole
                # audio prefix, so a gone owner has nothing left to project:
                # the receipts drop without a custody failure or a
                # failed_recordings entry, which also keeps deleted
                # conversations out of the session's 128-cap fail-closed
                # budget. A live conversation that 404s is never hidden as a
                # gone owner — it keeps the transient retry/terminal path.
                # If the deletion-intent read itself fails, treat the owner
                # as live rather than propagate out of the drain loop.
                gone = False
                try:
                    gone = await run_blocking(db_executor, projection_owner_gone, uid, conv_id)
                except Exception:
                    logger.warning('Durable audio projection gone-owner check failed; treating as transient')
                if gone:
                    deleted_conversations.add(conv_id)
                    audio_projection.inventory.pop(conv_id, None)
                    projection_retries.pop(conv_id, None)
                    logger.info('Durable audio projection skipped; conversation gone')
                    return
                await _transient_projection_failure(exc, conv_id, refs)
            except Exception as exc:
                await _transient_projection_failure(exc, conv_id, refs)

        async def _transient_projection_failure(exc: Exception, conv_id: str, refs: List[AudioProjection]) -> None:
            # Transient projection failure: while the session is live the
            # receipts requeue for one bounded retry pass instead of
            # dropping the projection outright; the drain loop's age and
            # duration scans re-flush them without a new scheduler. At
            # teardown there is no later pass, so the tail keeps today's
            # drop semantics. Only the deterministic conflict above is
            # exempt — plain ValueError upload wrappers (probe/read
            # errors) and custody read-back mismatches retry here.
            # The exception class and the innermost raising frame name
            # (never the message or args, which can carry user-identifying
            # object paths) are logged on both arms so an RCA can split
            # read-back mismatches from transport timeouts without
            # redeploying.
            logger.warning(
                'Durable audio projection failure class: %s raised by %s grpc_code=%s',
                type(exc).__name__,
                _projection_raising_frame(exc),
                _projection_grpc_code(exc),
            )
            if (
                websocket_active
                and inline_finish_conversation is None
                and projection_retries.get(conv_id, 0) < PROJECTION_RETRY_BUDGET
                and len(projection_retries) < 128
            ):
                projection_retries[conv_id] = projection_retries.get(conv_id, 0) + 1
                pending_refs[conv_id] = refs
                queued_at[conv_id] = time.monotonic()
                logger.warning('Durable audio projection failure; receipts requeued for retry')
                return
            # Terminal for this batch: a later independent batch for the
            # same conversation starts with a fresh budget instead of
            # inheriting this one's exhaustion, and the entry stops
            # counting toward the bounded retry map.
            projection_retries.pop(conv_id, None)
            audio_projection.inventory.pop(conv_id, None)
            # The close-debt cache may be full. Persist terminal projection debt
            # by its exact owner rather than relying on that bounded inventory.
            await audio_projection.defer_rebuild(conv_id)
            await record_barrier.fail_recording(conv_id)
            record_failure('projection', reason='transient')
            record_fallback(
                component='pusher',
                from_mode='private_cloud_sync',
                to_mode='raw_audio',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            logger.warning('Durable audio projection deferred after retries; archive receipt retained')

        while (
            websocket_active
            or not durable_queue.empty()
            or durable_queue.pending_projection is not None
            or pending_refs
            or record_close_requests
        ):
            if websocket_active:
                await wait_for_event(shutdown_event, PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)
            else:
                # This worker may now belong to the process. The socket's
                # shutdown event is set; do not spin on metadata failures.
                await asyncio.sleep(PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)
            # Also deliver a slot left by ACK departure, timeout or cancellation.
            durable_queue.promote_pending()
            # A continuously replenished later recording must not prevent the
            # close scan. Process a bounded snapshot before flushing/finishing.
            for _ in range(durable_queue.qsize()):
                ref = durable_queue.get_nowait()
                conv_id = ref.conversation_id
                if conv_id is not None:
                    refs = pending_refs.get(conv_id, [])
                    if refs:
                        end = refs[-1].start + refs[-1].samples / refs[-1].sample_rate
                        total_bytes = (sum(r.samples for r in refs) + ref.samples) * 2
                        if (
                            framed_audio
                            or (audio_timeline_v2 and abs(ref.start - end) > AUDIO_TIMELINE_CONTINUITY_TOLERANCE)
                            or len(refs) >= 60
                            or total_bytes > BUFFERED_AUDIO_MAX_BYTES
                        ):
                            await flush_refs(conv_id)
                    elif len(pending_refs) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                        BACKPRESSURE.labels(stage='pending_refs').inc()
                        record_would_drop('pending_refs')
                        await flush_refs(next(iter(pending_refs)))
                    pending_refs.setdefault(conv_id, []).append(ref)
                    queued_at.setdefault(conv_id, time.monotonic())
                durable_queue.task_done()
            for conv_id, refs in list(pending_refs.items()):
                if (
                    not websocket_active
                    or conv_id in record_close_requests
                    or time.monotonic() - queued_at[conv_id] >= PRIVATE_CLOUD_BATCH_MAX_AGE
                    or sum(r.samples / r.sample_rate for r in refs) >= PRIVATE_CLOUD_CHUNK_DURATION
                ):
                    await flush_refs(conv_id)
            for conv_id in list(record_close_requests):
                if websocket_active and any(window.conversation_id == conv_id for window in refused_windows):
                    continue  # Uncommitted PCM is still owned by this socket.
                if (
                    conv_id == inline_finish_conversation
                    and conv_id not in pending_refs
                    and not durable_queue.has_conversation(conv_id)
                ):
                    # Wake even on projection failure so the receiver can
                    # observe its sticky failure without waiting out the budget.
                    if not await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                        continue
                    inline_projection_drained.set()
                    await inline_finish_done.wait()
                    if conv_id not in record_close_requests:
                        continue
                if conv_id in pending_refs or durable_queue.has_conversation(conv_id):
                    continue
                if not await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                    continue
                if conv_id not in record_barrier.failed_recordings and not record_barrier.record_upload_failed:
                    if not await record_barrier.finish_recording(conv_id):
                        continue
                retire_record_close(conv_id)
        for conv_id in list(audio_projection.close_debt):
            for _ in range(PROJECTION_RETRY_BUDGET + 1):
                if await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                    break
        if identity_refreshed:
            schedule_completed_identity_retries(uid, identity_refreshed)

    # (start_wall, end_wall, sha256) of v2 runs whose GCS upload SUCCEEDED, for
    # reconciling replays that reach past the live buffer. Entries are appended
    # by the upload task after `upload_audio_chunks_batch` returns, so a chunk
    # evicted by the bounded queue or a batch dropped after exhausting its
    # retries never lends its digest to a later replay: that range stays
    # unverifiable (a counted conflict) instead of trusted.
    v2_flushed_runs: Deque[Tuple[float, float, str]] = deque(maxlen=V2_FLUSHED_RUN_LEDGER_SIZE)
    # Conversations that may skip the per-flush replay-reconcile listing: one
    # span upload already committed this session and no replay signal has been
    # seen since (duplicate frame, trimmed overlap, conflict, or a create-only
    # collision). A replay signal re-enables reconciliation for the rest of
    # the session. The exemption is only a cost skip: the create-only write
    # plus identical-content no-op keeps a missed signal correct.
    # The exemption is windowed by conversation_generation: the continuity
    # window that proved a clean span upload dies at every conversation-id
    # frame (audio_timeline_last_end resets there), so a batch created in a
    # later window must reconcile again instead of trusting a proof earned
    # under a window it can no longer see.
    v2_reconcile_exempt: Dict[str, int] = {}
    conversation_generation = 0
    # Conversations with a chunk already enqueued this session. A skipped
    # all-zero run is only audio-identical when objects exist on BOTH sides:
    # readers zero-fill the gap between two objects, so a leading silent run
    # (no earlier object) must be stored to anchor the recording's start.
    conversations_with_chunks: set[str] = set()
    v2_replay_seen: set[str] = set()
    record_close_requests: set[str] = set()
    record_barrier = PusherRecordBarrier(uid)
    # Durable workers can outlive socket cleanup; transient metadata errors
    # keep their close pending until success or process shutdown.
    record_barrier.keep_close_pending = durable_audio

    def retire_record_close(conv_id: str) -> None:
        record_close_requests.discard(conv_id)
        record_barrier.retire_close(conv_id)

    async def process_private_cloud_queue() -> None:
        """Background task that batches private cloud sync uploads by conversation_id.

        Chunks are accumulated per conversation and flushed when:
        - The batch reaches 60s of audio data, or
        - The oldest chunk in the batch exceeds PRIVATE_CLOUD_BATCH_MAX_AGE, or
        - The websocket disconnects (shutdown flush).
        """
        nonlocal websocket_active
        nonlocal application_failed

        if durable_audio:
            await process_durable_private_cloud_queue()
            return

        # Pending batches keyed by conversation_id
        pending: Dict[str, Dict[str, Any]] = {}

        # Batches closed early by a v2 discontinuity (or a failed upload
        # retrying): uploaded before any pending batch for the same
        # conversation, so noncontiguous PCM is never concatenated.
        ready_batches: List[Dict[str, Any]] = []

        # Conversations deleted underneath us (e.g. discarded as empty at rollover).
        # Their chunks can never be referenced, played or cleaned up again, so we
        # stop uploading rather than leaving more orphans in the bucket (#11742).
        identity_refreshed: set[str] = set()
        # Set when the storage authority refuses this account's writes because a
        # destructive operation owns the gate (account deletion in progress): the
        # refusal is permanent for the session, so later batches drop fast instead
        # of replaying the same fenced write every flush.
        upload_fenced: bool = False

        async def _add_to_batch(chunk_info: PrivateCloudChunk) -> None:
            conv_id = chunk_info['conversation_id']
            if conv_id in deleted_conversations or upload_fenced:
                audio_budget.release(len(chunk_info['data']))
                return
            span = chunk_info.get('span')
            chunk_end: Optional[float] = None
            if span:
                # v2 chunks know their exact end; legacy chunks end where the
                # next chunk's start lands (the old contiguous assumption).
                chunk_end = chunk_info['timestamp'] + span['samples'] / span['sample_rate']
            batch: Optional[Dict[str, Any]] = pending.get(conv_id)
            if batch is not None and chunk_end is not None and batch.get('end') is not None:
                # Never batch noncontiguous PCM: a gap (or overlap) between
                # the batch's current end and this chunk's start closes the
                # pending batch for upload before the new run accumulates.
                if abs(chunk_info['timestamp'] - cast(float, batch['end'])) > AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                    if pending.pop(conv_id, None) is not None:
                        ready_batches.append(batch)
                    batch = None
            if batch is None:
                before = set(pending)
                bound_private_pending(pending, audio_budget)
                for dropped_id in before - set(pending):
                    await record_barrier.fail_recording(dropped_id)
                batch = {
                    'data': bytearray(),
                    'conversation_id': conv_id,
                    'timestamp': chunk_info['timestamp'],  # oldest chunk timestamp
                    'queued_at': time.monotonic(),
                    'retries': 0,
                }
                pending[conv_id] = batch
            batch['data'].extend(chunk_info['data'])
            # Latest chunk's window wins; a generation change always splits
            # noncontiguous v2 runs into their own batch first (above), so a
            # batch never silently mixes windows when the split matters.
            batch['timeline_generation'] = chunk_info.get('timeline_generation')
            if chunk_end is not None and span:
                batch['end'] = chunk_end
                batch['span'] = {
                    'samples': len(batch['data']) // 2,
                    'sample_rate': span['sample_rate'],
                }

        async def _flush_batch(conv_id: str):
            """Upload a conversation's pending batched chunk."""
            await _upload_batch(pending.pop(conv_id, None))

        async def _upload_batch(batch: Optional[Dict[str, Any]]):
            """Upload a batched chunk and update audio files."""
            nonlocal application_failed, upload_fenced
            if not batch or len(batch['data']) == 0:
                return
            if upload_fenced or batch['conversation_id'] in deleted_conversations:
                # The fence latched earlier this session: this batch was already
                # queued before the refusal — drop it instead of replaying a
                # write the authority has refused for the rest of the session.
                audio_budget.release(len(batch['data']))
                batch['data'] = bytearray()
                return
            conv_id = batch['conversation_id']
            if not await record_barrier.renew_recording(conv_id):
                # Metadata refusal is not a storage attempt. Retain the batch
                # and its audio-budget reservation without spending retries.
                batch['retry_at'] = time.monotonic() + PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL
                ready_batches.append(batch)
                if not websocket_active:
                    # The shutdown event is already set; pace the bounded drain.
                    await wait_for_event(asyncio.Event(), PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)
                return
            chunk_data = bytes(batch['data'])
            del batch['data']  # free bytearray immediately — chunk_data holds the bytes copy
            timestamp = batch['timestamp']
            retries = batch.get('retries', 0)
            try:
                late_append = conv_id in record_barrier.late_appends
                upload_chunk: Dict[str, Any] = {'data': chunk_data, 'timestamp': timestamp}
                if batch.get('span'):
                    upload_chunk['span'] = {**batch['span'], 'start': timestamp}
                chunks_to_upload: List[Dict[str, Any]] = [upload_chunk]
                # Skip the replay-reconcile listing once this session has
                # committed a span upload for the conversation with no replay
                # signal since — and only while the batch was buffered under
                # the same continuity window that earned the exemption: a
                # conversation-id frame resets that window, so a batch from a
                # later window reconciles again. The first upload of a
                # session (or any upload after a replay signal, a window
                # change, or a failed attempt) reconciles.
                batch_generation = batch.get('timeline_generation')
                reconcile_prefix = conv_id in v2_replay_seen or v2_reconcile_exempt.get(conv_id) != batch_generation
                if not reconcile_prefix:
                    PUSHER_RECONCILE_LISTS_SKIPPED_TOTAL.inc()
                uploaded_paths = await run_blocking(
                    storage_executor,
                    cast(Any, upload_audio_chunks_batch),
                    chunks_to_upload,
                    uid,
                    conv_id,
                    cast(str, cached_protection_level),
                    sample_rate=sample_rate,
                    reconcile_prefix=reconcile_prefix,
                )
                if uploaded_paths:
                    record_barrier.append_committed(conv_id, observed=late_append)
                OMI_AUDIO_TIMELINE_CHUNKS_WRITTEN_TOTAL.labels(
                    reason='with_spans' if batch.get('span') is not None else 'without_spans'
                ).inc()
                if batch.get('span') is not None and batch.get('end') is not None:
                    if conv_id not in v2_replay_seen and isinstance(batch_generation, int):
                        if len(v2_reconcile_exempt) < 1024:
                            v2_reconcile_exempt[conv_id] = batch_generation
                    # The digest ledger records only runs whose object exists.
                    # Batches are contiguous by construction (discontinuities
                    # close them in `_add_to_batch`), so one entry covers the
                    # whole uploaded run; a batch that never gets here —
                    # evicted before upload, or dropped after exhausting its
                    # retries — leaves no entry and stays unverifiable.
                    v2_flushed_runs.append((timestamp, batch['end'], hashlib.sha256(chunk_data).hexdigest()))
                del chunks_to_upload
                try:
                    applied = await run_blocking(
                        storage_executor,
                        audio_projection.refresh,
                        conv_id,
                        uploaded_paths,
                        force=not websocket_active or conv_id in record_close_requests,
                    )
                    if applied:
                        schedule_person_voice_learning_retry(uid, conv_id)
                        if len(identity_refreshed) < 128:
                            identity_refreshed.add(conv_id)
                    elif applied is False:
                        deleted_conversations.add(conv_id)
                        logger.info(f"Conversation gone, stopped private cloud sync {uid} {conv_id}")
                        record_fallback(
                            component='pusher',
                            from_mode='private_cloud_sync',
                            to_mode='drop',
                            reason='policy',
                            outcome='exhausted',
                            log=logger,
                        )
                except Exception as e:
                    logger.error(f"Error updating audio files: {e} {uid} {conv_id}")
                audio_budget.release(len(chunk_data))
            except Exception as e:
                if isinstance(e, DestructiveOperationInProgress):
                    # The storage authority fenced this account: a destructive
                    # operation (account deletion) owns the gate for hours. The
                    # refusal is permanent — no retry of this batch can pass the
                    # fence, and every later flush would burn the same three
                    # doomed attempts against the same authority reads. Latch
                    # the session: drop what is queued and stop accepting more,
                    # like the deleted-conversation path, and keep the session
                    # itself healthy (the closure is by design, not a fault).
                    upload_fenced = True
                    audio_budget.release(len(chunk_data))
                    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
                    record_fallback(
                        component='pusher',
                        from_mode='private_cloud_sync',
                        to_mode='drop',
                        reason='policy',
                        outcome='exhausted',
                        log=logger,
                    )
                    logger.warning(
                        f'Private cloud sync stopped: account writes are fenced by a destructive operation '
                        f'(no retry) {uid} {conv_id}'
                    )
                elif retries < PRIVATE_CLOUD_SYNC_MAX_RETRIES:
                    batch['retries'] = retries + 1
                    batch['data'] = bytearray(chunk_data)
                    # A failed attempt (including a create-only collision,
                    # which is replay evidence) re-enables the reconcile
                    # listing for this conversation for the rest of the
                    # session; the upload loop also forces reconciliation on
                    # its own retry attempt.
                    v2_replay_seen.add(conv_id)
                    # Retry in the ordered ready lane on a later process tick,
                    # keeping the batch's queue time: an in-turn immediate
                    # retry burns the whole budget on one fast permanent error
                    # (or blocks this uploader for four back-to-back slow
                    # timeouts). The ready lane skips the retry gate during
                    # shutdown so the drain stays bounded.
                    batch['retry_at'] = time.monotonic() + PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL
                    ready_batches.append(batch)
                    logger.error(f"Private cloud batch upload failed (retry {retries + 1}): {e} {uid} {conv_id}")
                else:
                    audio_budget.release(len(chunk_data))
                    PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS.inc()
                    application_failed = True
                    await record_barrier.fail_recording(conv_id)
                    logger.info(
                        f"Private cloud batch upload failed after {PRIVATE_CLOUD_SYNC_MAX_RETRIES} retries, dropping: {e} {uid} {conv_id}"
                    )
            del chunk_data

        while (
            websocket_active
            or len(private_cloud_queue) > 0
            or len(pending) > 0
            or ready_batches
            or record_close_requests
        ):
            await wait_for_event(shutdown_event, PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL)

            if record_barrier.record_upload_failed or upload_fenced:
                for conv_id in list(record_close_requests):
                    retire_record_close(conv_id)
            for conv_id in record_close_requests.intersection(record_barrier.failed_recordings):
                if await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                    retire_record_close(conv_id)

            # Drain queue into pending batches
            if private_cloud_queue:
                chunks_to_process = private_cloud_queue.copy()
                private_cloud_queue.clear()
                for chunk_info in chunks_to_process:
                    await _add_to_batch(chunk_info)

            if upload_fenced:
                # The fence latched mid-session: anything still held is dropped
                # fast (budget released, no upload, no retries) so the loop's
                # drain contract still completes and shutdown stays bounded.
                while ready_batches:
                    dropped = ready_batches.pop(0)
                    payload = dropped.get('data')
                    audio_budget.release(len(payload) if payload else 0)
                for dropped in list(pending.values()):
                    audio_budget.release(len(dropped.get('data', b'')))
                pending.clear()
                continue

            if not pending and not ready_batches and not record_close_requests:
                # `pending` alone must not gate the iteration: a failed
                # upload's retry batch lives in `ready_batches`, and skipping
                # the ready lane below with `continue` would leave the loop
                # condition truthy forever (a busy spin once shutdown is set).
                continue

            now = time.monotonic()
            batch_size_threshold = sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION

            # Discontinuity-closed batches upload first, in order. A failed
            # upload's retry waits one process interval before it is due
            # (`retry_at`); the gate is skipped during shutdown so the drain
            # never stalls on it.
            while ready_batches:
                head = ready_batches[0]
                retry_at = head.get('retry_at')
                if retry_at is not None and websocket_active and now < retry_at:
                    break
                await _upload_batch(ready_batches.pop(0))

            # Determine which conversations to flush
            conv_ids_to_flush: List[str] = []
            for conv_id, batch in pending.items():
                batch_age = now - batch['queued_at']
                is_shutdown = not websocket_active
                is_size_ready = len(batch['data']) >= batch_size_threshold
                is_age_ready = batch_age >= PRIVATE_CLOUD_BATCH_MAX_AGE
                owned_close = conv_id in record_close_requests
                # Leave one uploader tick for the boundary frame/close message
                # to join a size-ready batch. Otherwise a scheduler tick between
                # the full run and its final frame creates a second tiny object.
                # Real discontinuities still close into ready_batches, and age,
                # recording close and disconnect always flush immediately.
                if is_size_ready and 'size_ready_at' not in batch:
                    batch['size_ready_at'] = now
                size_grace_elapsed = (
                    is_size_ready and now - batch['size_ready_at'] >= PRIVATE_CLOUD_SYNC_PROCESS_INTERVAL
                )
                if is_shutdown or size_grace_elapsed or is_age_ready or owned_close:
                    conv_ids_to_flush.append(conv_id)

            for conv_id in conv_ids_to_flush:
                await _flush_batch(conv_id)
            for conv_id in list(record_close_requests):
                if (
                    not record_barrier.record_upload_failed
                    and conv_id not in record_barrier.failed_recordings
                    and not upload_fenced
                    and conv_id not in pending
                    and not any(b['conversation_id'] == conv_id for b in ready_batches)
                    and not any(b['conversation_id'] == conv_id for b in private_cloud_queue)
                ):
                    if not await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                        continue
                    if await record_barrier.finish_recording(conv_id):
                        retire_record_close(conv_id)

        # Only authoritative uploaded manifests qualify. Admission is process-wide
        # and eligibility precedes the eight-pass selection limit.
        for conv_id in list(audio_projection.close_debt):
            for _ in range(PROJECTION_RETRY_BUDGET + 1):
                if await audio_projection.finish_pending(conv_id, deleted_conversations, identity_refreshed):
                    break
        if identity_refreshed:
            schedule_completed_identity_retries(uid, identity_refreshed)

    async def process_speaker_sample_queue() -> None:
        """Background task that processes speaker sample extraction requests."""
        nonlocal websocket_active

        while websocket_active or len(speaker_sample_queue) > 0:
            await wait_for_event(shutdown_event, SPEAKER_SAMPLE_PROCESS_INTERVAL)

            if not speaker_sample_queue:
                continue

            current_time = time.time()
            is_shutdown = not websocket_active

            # Separate ready and pending requests.
            # On shutdown, skip the age check — process everything so pending
            # samples aren't silently dropped when the drain timeout fires.
            ready_requests: List[SpeakerSampleRequest] = []
            pending_requests: List[SpeakerSampleRequest] = []

            for request in list(speaker_sample_queue):
                if is_shutdown or current_time - request['queued_at'] >= SPEAKER_SAMPLE_MIN_AGE:
                    ready_requests.append(request)
                else:
                    pending_requests.append(request)

            # Keep pending requests in queue (rebuild deque with pending only)
            speaker_sample_queue.clear()
            speaker_sample_queue.extend(pending_requests)

            # Process ready requests (fire and forget)
            for request in ready_requests:
                person_id = request['person_id']
                conv_id = request['conversation_id']
                segment_ids = request['segment_ids']

                try:
                    await run_authorized_person_learning(
                        uid=uid,
                        person_id=person_id,
                        conversation_id=conv_id,
                        segment_ids=segment_ids,
                        sample_rate=sample_rate,
                    )
                except Exception as e:
                    logger.error(f"Error extracting speaker samples: {e} {uid} {conv_id}")

    async def process_transcript_queue() -> None:
        """Batched consumer for transcript events (realtime integrations + webhooks)."""
        nonlocal websocket_active

        while websocket_active or len(transcript_queue) > 0:
            await wait_for_event(shutdown_event, TRANSCRIPT_QUEUE_FLUSH_INTERVAL)

            if not transcript_queue:
                continue

            # Process batch
            batch: List[TranscriptQueueItem] = list(transcript_queue)
            transcript_queue.clear()

            for item in batch:
                await _dispatch_transcript_item(uid, item['segments'], item['memory_id'], resolved_client_kind)

    async def process_audio_bytes_queue() -> None:
        """Event-driven consumer for audio bytes triggers (app integrations + webhooks)."""
        nonlocal websocket_active

        while websocket_active or len(audio_bytes_queue) > 0:
            # Wait for signal or check periodically for shutdown
            try:
                await asyncio.wait_for(audio_bytes_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                if shutdown_event.is_set() and not audio_bytes_queue:
                    break
                continue

            audio_bytes_event.clear()

            if not audio_bytes_queue:
                continue

            # Process all queued items
            batch: List[AudioBytesQueueItem] = list(audio_bytes_queue)
            audio_bytes_queue.clear()

            for item in batch:
                try:
                    if item['type'] == 'app':
                        await trigger_realtime_audio_bytes(uid, item['sample_rate'], item['data'])
                    elif item['type'] == 'webhook':
                        await send_audio_bytes_developer_webhook(uid, item['sample_rate'], item['data'])
                except Exception as e:
                    logger.error(f"Error processing audio bytes: {e} {uid}")
                finally:
                    audio_budget.release(len(item['data']))

    # The conversation this session last streamed, for the episode moment flush at teardown.
    episode_session: Dict[str, Optional[str]] = {'conversation_id': None}

    async def receive_tasks() -> None:
        nonlocal websocket_active
        nonlocal inline_finish_conversation
        nonlocal websocket_close_code
        nonlocal application_failed
        nonlocal speaker_sample_queue
        nonlocal transcript_queue
        nonlocal audio_bytes_queue
        nonlocal conversation_generation
        nonlocal custody_sequence

        audiobuffer = bytearray()
        trigger_audiobuffer = bytearray()
        private_cloud_sync_buffer = bytearray()
        private_cloud_chunk_start_time: Optional[float] = None
        current_conversation_id: Optional[str] = None
        # Durable custody window: per-frame checkpoints for the PCM currently
        # buffered in private_cloud_sync_buffer, pinned verbatim into one
        # manifest when the window commits at a flush boundary.
        durable_window_frames: List[Dict[str, Any]] = []
        private_cloud_window_opened_at: Optional[float] = None
        durable_tail_has_receipt = False
        durable_commit_unresolved = False
        pcm_admission_cancelled = False
        # Audio-timeline v2 continuity for this socket: the projected end of
        # the last accepted run and its conversation. None until first audio
        # or after a conversation switch (which flushes the run).
        audio_timeline_last_end: Optional[float] = None

        async def commit_durable_window(window: RetainedPcmWindow, *, tail: bool = False) -> Optional[AudioReceipt]:
            """Commit the buffered window as one custody pair (see _commit_durable_audio_window)."""
            nonlocal durable_tail_has_receipt
            nonlocal durable_commit_unresolved
            durable_tail_has_receipt = False
            late_append = False

            def committed():
                nonlocal durable_tail_has_receipt
                durable_tail_has_receipt = True
                record_barrier.append_committed(window.conversation_id, observed=late_append)
                refused_windows.popleft()
                window.payload.clear()
                window.frames.clear()

            if window.conversation_id and window.payload:
                if not await record_barrier.renew_recording(window.conversation_id):
                    return None  # Keep this window and its WAL unacknowledged.
                late_append = window.conversation_id in record_barrier.late_appends
            try:
                return await _commit_durable_audio_window(
                    uid=uid,
                    payload=bytes(window.payload),
                    frames=list(window.frames),
                    conversation_id=window.conversation_id,
                    start=window.start,
                    sample_rate=sample_rate,
                    custody_root=custody_root,
                    protection_level=cached_protection_level,
                    audio_custody=audio_custody,
                    timeline_v2=audio_timeline_v2,
                    websocket=websocket,
                    durable_queue=durable_queue,
                    budget=audio_budget,
                    queue_wait_timeout=queue_wait_timeout,
                    on_committed=committed,
                    framed=framed_audio,
                    tail=tail,
                )
            except BaseException:
                # A failed/cancelled dispatch can have committed remotely. The
                # shutdown tail must never rerun that unknown storage operation.
                if not durable_tail_has_receipt:
                    durable_commit_unresolved = True
                raise

        async def _queue_private_cloud_chunk(*, skip_if_silent: bool = False, tail: bool = False) -> None:
            nonlocal durable_window_frames, pcm_admission_wait_active, pcm_admission_cancelled
            if current_conversation_id in deleted_conversations:
                # A gone-owner result is terminal for both encoded projection
                # and future raw custody windows in this socket.
                audio_budget.release(len(private_cloud_sync_buffer))
                _reset_private_cloud_buffer()
                durable_window_frames.clear()
                if not durable_audio:
                    return
            if durable_audio:
                if durable_commit_unresolved:
                    raise RuntimeError('custody commit unresolved; producer fence retained')
                if private_cloud_sync_enabled and private_cloud_sync_buffer:
                    # Move the originals, without copying or releasing their
                    # per-socket byte charge. A refused conversation/size/gap
                    # boundary cannot reset or rebind this retained window.
                    refused_windows.append(
                        RetainedPcmWindow(
                            private_cloud_sync_buffer,
                            durable_window_frames,
                            current_conversation_id,
                            private_cloud_chunk_start_time,
                        )
                    )
                    _reset_private_cloud_buffer()
                    durable_window_frames = []
                while refused_windows:
                    window = refused_windows[0]
                    if window.conversation_id in deleted_conversations:
                        # Apply the existing gone-owner disposition to each
                        # retained owner, even after the socket switches owner.
                        audio_budget.release(len(window.payload))
                        refused_windows.popleft()
                        window.payload.clear()
                        window.frames.clear()
                        continue
                    if await commit_durable_window(refused_windows[0], tail=tail) is None:
                        if not tail:
                            # Stop intake on the FIRST refusal: another PCM
                            # window must never consume the socket's remaining
                            # byte budget while pod admission is full. Sleep
                            # is cancellable; tails and metadata never wait.
                            pcm_admission_wait_active = True
                            try:
                                await asyncio.sleep(0.05)
                            except asyncio.CancelledError:
                                pcm_admission_cancelled = True
                                raise
                            finally:
                                pcm_admission_wait_active = False
                            continue
                        break  # Tail refusal leaves the producer unacknowledged.
                return
            if not (private_cloud_sync_enabled and current_conversation_id and len(private_cloud_sync_buffer) > 0):
                return
            if not any(private_cloud_sync_buffer):
                # An all-zero run carries no audio information: every reader
                # zero-fills gaps between objects with these same bytes, so
                # skipping the run is audio-identical to storing it, without
                # one sub-1 KB object per silence boundary. Two conditions
                # must hold, or the zero-fill gap has no boundary to fill
                # against: the flush must be a discontinuity (audio for this
                # conversation has arrived beyond the gap, so a later object
                # is guaranteed — worst case at the next terminal flush), and
                # the conversation must already have an earlier chunk (a
                # leading silent run would otherwise shift the recording's
                # start to the first stored object). Shutdown, conversation
                # switch, process handoff and size triggers never skip: with
                # no guaranteed later object the zeros must be stored.
                if skip_if_silent and current_conversation_id in conversations_with_chunks:
                    PUSHER_SILENT_RUN_FLUSHES_SKIPPED_TOTAL.inc()
                    audio_budget.release(len(private_cloud_sync_buffer))
                    _reset_private_cloud_buffer()
                    return
            if len(private_cloud_queue) >= PRIVATE_CLOUD_QUEUE_MAX_SIZE:
                await record_barrier.fail_recording(private_cloud_queue[0]['conversation_id'])
                logger.warning(
                    f"private_cloud_queue full ({len(private_cloud_queue)}/{PRIVATE_CLOUD_QUEUE_MAX_SIZE}), "
                    f"dropping oldest chunk to prevent OOM {uid}"
                )
            chunk_payload: PrivateCloudChunk = {
                'data': bytes(private_cloud_sync_buffer),
                'conversation_id': current_conversation_id,
                'timestamp': private_cloud_chunk_start_time or time.time(),
            }
            if audio_timeline_v2:
                # v2 runs carry their authoritative PCM sample count so
                # coverage never has to be inferred from encoded blob size.
                # The flushed-run digest is recorded by the upload task only
                # after this chunk's batch lands in GCS (see _upload_batch).
                span: PrivateCloudSpan = {
                    'samples': len(private_cloud_sync_buffer) // 2,
                    'sample_rate': int(sample_rate),
                }
                chunk_payload['span'] = span
            # The continuity window this chunk was buffered under; the upload
            # path compares it against the conversation's clean-upload window.
            chunk_payload['timeline_generation'] = conversation_generation
            # This chunk anchors every later gap for the conversation,
            # including the zero-fill left by any skipped silent run.
            conversations_with_chunks.add(current_conversation_id)
            append_bounded(
                private_cloud_queue,
                chunk_payload,
                'private_cloud',
                byte_budget=audio_budget,
                size_of=lambda chunk: len(chunk['data']),
            )

        def _reset_private_cloud_buffer() -> None:
            nonlocal private_cloud_sync_buffer
            nonlocal private_cloud_chunk_start_time
            nonlocal private_cloud_window_opened_at
            private_cloud_sync_buffer = bytearray()
            private_cloud_chunk_start_time = None
            private_cloud_window_opened_at = None

        async def finish_receive() -> None:
            nonlocal inline_finish_conversation, websocket_active, websocket_close_code
            nonlocal application_failed, durable_tail_has_receipt
            # Flush any remaining private cloud sync buffer before shutdown.
            # The durable window tail is the last-chance custody commit: if it
            # fails, the producer stays unacknowledged (never a false receipt)
            # and the tail is replayable by the client — count it, never mask
            # the close path with the commit failure.
            if len(private_cloud_sync_buffer) > 0:
                logger.info(f"Flushed final private cloud buffer: {len(private_cloud_sync_buffer)} bytes {uid}")
            tail_committed = False
            durable_tail_has_receipt = False
            try:
                # Cancelling admission leaves the unacknowledged window for
                # WAL replay. Never start storage (or ACK a departed peer) in
                # this cancellation cleanup, which must not wait on GCS retries.
                if not pcm_admission_cancelled:
                    await _queue_private_cloud_chunk(tail=True)
                    tail_committed = durable_audio and not refused_windows
            except ProjectionQueueWaitTimeout:
                observation.reason = 'queue_wait_timeout'
                websocket_close_code = 1011
                application_failed = True
                tail_committed = durable_tail_has_receipt
            except WebSocketDisconnect as exc:
                websocket_close_code = exc.code or 1006
                tail_committed = durable_tail_has_receipt
            except Exception:
                if durable_audio:
                    record_failure('window_tail')
                    record_would_drop('window_tail')
                    # Fail closed to the producer: the unacknowledged tail must
                    # be replayable, so signal the same error close the
                    # mid-session commit failure path uses.
                    websocket_close_code = 1011
                    observation.reason = 'application_error'
                    logger.exception(f'Durable audio window tail commit failed at shutdown {uid}')
                    if current_conversation_id:
                        # The immutable commit may have landed before ACK or
                        # queue delivery failed. Keep the producer token, but
                        # do not permanently poison retained custody.
                        record_barrier.hold_recording(current_conversation_id, tail_committed=durable_tail_has_receipt)
            finally:
                # Every unresolved owner must stay fenced on every exit,
                # including a prior owner's storage failure, cancellation or
                # ACK departure before later retained windows are attempted.
                # A receipt for A can never certify the buffered tail of B.
                if durable_audio:
                    if refused_windows:
                        tail_committed = False
                    for window in refused_windows:
                        if window.conversation_id:
                            record_barrier.hold_recording(window.conversation_id)
                    if private_cloud_sync_buffer and current_conversation_id:
                        tail_committed = False
                        record_barrier.hold_recording(current_conversation_id)
            if private_cloud_sync_enabled and current_conversation_id and len(record_close_requests) < 128:
                record_close_requests.add(current_conversation_id)
            if (
                tail_committed
                and current_conversation_id in record_close_requests
                and current_conversation_id not in record_barrier.failed_recordings
                and not record_barrier.record_upload_failed
                and os.getenv('RECORD_BARRIER_INLINE_FINISH', 'true').strip().lower() != 'false'
            ):
                inline_finish_conversation = current_conversation_id
                try:
                    with observe_work('inline_finish'):
                        async with asyncio.timeout(RECORD_INLINE_FINISH_TIMEOUT):
                            await inline_projection_drained.wait()
                            if (
                                current_conversation_id not in record_barrier.failed_recordings
                                and not record_barrier.record_upload_failed
                            ):
                                if await record_barrier.finish_recording(current_conversation_id):
                                    retire_record_close(current_conversation_id)
                except TimeoutError:
                    logger.info('event=record_inline_finish outcome=timeout')
                finally:
                    inline_finish_conversation = None
                    inline_finish_done.set()
                    websocket_active = False
                    audio_bytes_event.set()
            else:
                websocket_active = False
                audio_bytes_event.set()

        async def process_frame(data: bytes) -> None:
            nonlocal conversation_generation, custody_sequence
            nonlocal audiobuffer, trigger_audiobuffer, private_cloud_chunk_start_time, private_cloud_window_opened_at
            nonlocal current_conversation_id, audio_timeline_last_end
            try:
                header_type = frame_header(data)
            except (ValueError, struct.error):
                observation.frame(None)
                raise
            observation.frame(header_type)

            # Heartbeat (data-frame keepalive from backend to reset GKE ILB idle timer)
            if header_type == 100:
                return

            # Conversation ID
            if header_type == 103:
                new_conversation_id = bytes(data[4:]).decode("utf-8")
                # Flush the private cloud buffer before switching. When no
                # conversation id was set yet, durable custody may still hold
                # pre-ID audio: it commits under 'unlinked' here rather than
                # riding into the new conversation's window.
                if current_conversation_id != new_conversation_id and (
                    current_conversation_id or len(private_cloud_sync_buffer) > 0
                ):
                    logger.info(
                        f"Flushed private cloud buffer on conversation switch: "
                        f"{len(private_cloud_sync_buffer)} bytes {uid}"
                    )
                    await _queue_private_cloud_chunk()
                    _reset_private_cloud_buffer()
                    if current_conversation_id and private_cloud_sync_enabled and len(record_close_requests) < 128:
                        record_close_requests.add(current_conversation_id)
                current_conversation_id = new_conversation_id
                episode_session['conversation_id'] = new_conversation_id
                # A conversation boundary ends the current v2 run: the
                # next audio starts a fresh continuity window. Every
                # clean-span exemption was proven under the old window;
                # the generation bump retires them all, so a rebound
                # conversation's next upload reconciles again.
                conversation_generation += 1
                audio_timeline_last_end = None
                logger.info(f"Pusher received conversation_id: {current_conversation_id} {uid}")
                return

            # Transcript - queue for batched processing
            if header_type == 102:
                res = json_object(data)
                segments = res.get('segments')
                memory_id = res.get('memory_id')
                if not isinstance(segments, list) or not all(isinstance(segment, dict) for segment in segments):
                    raise ValueError('segments must be a list of objects')
                if memory_id is not None and not isinstance(memory_id, str):
                    raise ValueError('memory_id must be a string')
                # A transcript's memory_id must NOT overwrite the session's authoritative
                # current_conversation_id (which is set only by header 103). Doing so let a stale
                # lifecycle event carrying an older conversation's memory_id rebind a newer recording
                # session, mis-associating subsequent private-cloud audio (see issue #6952).
                if len(transcript_queue) >= TRANSCRIPT_QUEUE_WARN_SIZE:
                    logger.warning(f"Warning: transcript_queue size {len(transcript_queue)} {uid}")
                # Route this transcript by its own memory_id when present, falling back to the
                # session's conversation id. This does not mutate session-scoped state.
                conversation_or_memory_id = memory_id or current_conversation_id
                append_bounded(
                    transcript_queue,
                    {'segments': segments, 'memory_id': conversation_or_memory_id},
                    'transcript',
                )
                return

            # Process conversation request
            if header_type == 104:
                res = json_object(data)
                conversation_id = res.get('conversation_id')
                language = res.get('language', 'en')
                byok_keys = res.get('byok_keys') or None
                finalization_job_id = res.get('finalization_job_id')
                dispatch_generation = res.get('dispatch_generation')
                finalization_result_protocol = _parse_finalization_result_protocol(
                    res.get('finalization_result_protocol')
                )
                if conversation_id is not None and not isinstance(conversation_id, str):
                    raise ValueError('conversation_id must be a string')
                if not isinstance(language, str):
                    raise ValueError('language must be a string')
                if byok_keys is not None and (
                    not isinstance(byok_keys, dict)
                    or not all(isinstance(key, str) and isinstance(value, str) for key, value in byok_keys.items())
                ):
                    raise ValueError('byok_keys must be an object')
                if finalization_job_id is not None and not isinstance(finalization_job_id, str):
                    raise ValueError('finalization_job_id must be a string')
                if dispatch_generation is not None and (
                    isinstance(dispatch_generation, bool) or not isinstance(dispatch_generation, int)
                ):
                    raise ValueError('dispatch_generation must be an integer')
                if conversation_id:
                    if private_cloud_sync_enabled:
                        await _queue_private_cloud_chunk()
                        _reset_private_cloud_buffer()
                        if len(record_close_requests) < 128:
                            record_close_requests.add(conversation_id)
                    logger.info(f"Pusher received process_conversation request: {conversation_id} {uid}")
                    # Durable finalization already has a Firestore owner. It
                    # must survive an originating listen socket close after
                    # this handoff, so pusher owns it at process scope. Its
                    # lifespan drains tracked tasks on process shutdown.
                    start_background_task(
                        process_conversation_task(
                            uid,
                            conversation_id,
                            language,
                            websocket,
                            byok_keys=byok_keys,
                            finalization_job_id=(finalization_job_id if isinstance(finalization_job_id, str) else None),
                            dispatch_generation=(dispatch_generation if isinstance(dispatch_generation, int) else None),
                            client_kind=resolved_client_kind,
                            finalization_result_protocol=finalization_result_protocol,
                        ),
                        name=f'pusher_finalization:{uid}:{conversation_id}',
                    )
                return

            # Speaker sample extraction request - queue for background processing
            if header_type == 105:
                _queue_speaker_sample_request(data, speaker_sample_queue, uid)
                return

            # Audio bytes
            if header_type == 101:
                # Parse: header(4) | timestamp(8 bytes double) | audio_data
                buffer_start_timestamp = struct.unpack("d", data[4:12])[0]
                audio_data = data[12:]
                run_gap_before = False

                if audio_timeline_v2:
                    # v2: the timestamp is the projected start of this
                    # run's first sample. Compare against the last accepted
                    # run's end with 1 ms tolerance: a positive
                    # discontinuity flushes the partial chunk (and the
                    # pending batch downstream) instead of concatenating
                    # across a gap; an overlap is reconciled exactly.
                    run_seconds = len(audio_data) / (sample_rate * 2)
                    run_start = buffer_start_timestamp
                    run_end = run_start + run_seconds
                    if audio_timeline_last_end is not None:
                        delta = run_start - audio_timeline_last_end
                        run_gap_before = delta > 0.002
                        if delta > AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                            # skip_if_silent: audio for this conversation
                            # has arrived beyond the gap, so a later
                            # object is guaranteed to follow whatever this
                            # flush stores (or drops) — the only flush
                            # where a skipped all-zero run is provably
                            # interior, never the recording's last.
                            if not framed_audio:
                                await _queue_private_cloud_chunk(skip_if_silent=True)
                                _reset_private_cloud_buffer()
                        elif delta < -AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                            # Any overlap of already-accepted audio is
                            # replay evidence for this conversation: the
                            # upload path must keep reconciling against
                            # committed objects this session.
                            if current_conversation_id:
                                v2_replay_seen.add(current_conversation_id)
                            if run_end <= audio_timeline_last_end + AUDIO_TIMELINE_CONTINUITY_TOLERANCE:
                                # Exact replay of an already accepted
                                # range: never re-store or re-emit it.
                                logger.info(
                                    f'Ignored duplicate v2 audio replay '
                                    f'start={run_start:.3f}s {len(audio_data)}B {uid}'
                                )
                                return
                            overlap_bytes = int((audio_timeline_last_end - run_start) * sample_rate * 2)
                            overlap_bytes -= overlap_bytes % 2
                            if overlap_bytes >= len(audio_data):
                                return
                            # Verify the overlapping prefix against every
                            # retained copy of that range — the live buffer
                            # by bytes, anything older by flushed-run
                            # digest. Differing or unverifiable bytes for
                            # an accepted range are never re-stored; the
                            # frame's genuinely new tail past the accepted
                            # end still continues the run from there.
                            if v2_overlap_conflict(
                                run_start,
                                overlap_bytes,
                                audio_data,
                                sample_rate=sample_rate,
                                private_cloud_chunk_start_time=private_cloud_chunk_start_time,
                                private_cloud_sync_buffer=private_cloud_sync_buffer,
                                v2_flushed_runs=v2_flushed_runs,
                                frames=durable_window_frames if framed_audio else None,
                            ):
                                OMI_AUDIO_TIMELINE_REPLAY_CONFLICTS_TOTAL.inc()
                                logger.warning(
                                    f'Conflicting v2 audio for an accepted range '
                                    f'start={run_start:.3f}s overlap={overlap_bytes}B; '
                                    f'dropping the unverified overlap, keeping the new tail {uid}'
                                )
                            audio_data = audio_data[overlap_bytes:]
                            run_start = audio_timeline_last_end
                            run_end = run_start + len(audio_data) / (sample_rate * 2)
                    audio_timeline_last_end = run_end
                    buffer_start_timestamp = run_start

                # Only accumulate audio buffers if there's a consumer (app trigger or webhook)
                # Without this guard, buffers grow ~16KB/s indefinitely for users with no audio apps
                if has_audio_apps_enabled:
                    extend_bounded(trigger_audiobuffer, audio_data, 'audio_app_buffer', audio_budget)
                if audio_bytes_webhook_delay_seconds is not None:
                    extend_bounded(audiobuffer, audio_data, 'audio_webhook_buffer', audio_budget)

                # Private cloud sync - queue chunks for background processing.
                # Durable custody buffers the accepted stream the same way
                # (including audio that arrives before the first conversation
                # id, committed under 'unlinked' at the next flush boundary);
                # the window itself commits in _queue_private_cloud_chunk.
                if private_cloud_sync_enabled and (current_conversation_id or durable_audio):
                    if storage_pcm_budget.limit and len(durable_window_frames) >= MAX_PCM_WINDOW_FRAMES:
                        await _queue_private_cloud_chunk()
                        _reset_private_cloud_buffer()
                    if (
                        framed_audio
                        and private_cloud_sync_buffer
                        and (
                            len(private_cloud_sync_buffer) + len(audio_data)
                            > min(16 * 1024 * 1024, sample_rate * 2 * 60)
                            or len(durable_window_frames) >= 4096
                            or time.monotonic() - (private_cloud_window_opened_at or time.monotonic()) >= 60
                        )
                    ):
                        await _queue_private_cloud_chunk()
                        _reset_private_cloud_buffer()
                    if current_conversation_id:
                        with observe_work('record_begin'):
                            await record_barrier.begin_recording(current_conversation_id)
                            await record_barrier.renew_recording(current_conversation_id)
                    if private_cloud_chunk_start_time is None:
                        # Use timestamp from first buffer of this 5-second chunk
                        private_cloud_chunk_start_time = buffer_start_timestamp
                        private_cloud_window_opened_at = time.monotonic()

                    frame_checkpoint, stored_capture = append_window_run(
                        durable=durable_audio,
                        sequence=custody_sequence,
                        buffer=private_cloud_sync_buffer,
                        audio_data=audio_data,
                        start=buffer_start_timestamp,
                        budget=audio_budget,
                        gap_before=run_gap_before,
                    )
                    custody_sequence += 1
                    if not stored_capture:
                        if current_conversation_id:
                            await record_barrier.fail_recording(current_conversation_id)
                    elif frame_checkpoint is not None:
                        durable_window_frames.append(frame_checkpoint)
                    # Queue chunk every PRIVATE_CLOUD_CHUNK_DURATION seconds
                    if len(private_cloud_sync_buffer) >= sample_rate * 2 * PRIVATE_CLOUD_CHUNK_DURATION:
                        await _queue_private_cloud_chunk()
                        _reset_private_cloud_buffer()

                # Queue audio bytes triggers for batched processing
                if (
                    has_audio_apps_enabled
                    and len(trigger_audiobuffer) > sample_rate * audio_bytes_trigger_delay_seconds * 2
                ):
                    if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                        logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                    append_bounded(
                        audio_bytes_queue,
                        {
                            'type': 'app',
                            'sample_rate': sample_rate,
                            'data': trigger_audiobuffer.copy(),
                        },
                        'audio_bytes',
                        byte_budget=audio_budget,
                        size_of=lambda item: len(item['data']),
                    )
                    audio_bytes_event.set()  # Wake consumer immediately
                    trigger_audiobuffer = bytearray()
                if (
                    audio_bytes_webhook_delay_seconds is not None
                    and len(audiobuffer) > sample_rate * audio_bytes_webhook_delay_seconds * 2
                ):
                    if len(audio_bytes_queue) >= AUDIO_BYTES_QUEUE_WARN_SIZE:
                        logger.warning(f"Warning: audio_bytes_queue size {len(audio_bytes_queue)} {uid}")
                    append_bounded(
                        audio_bytes_queue,
                        {
                            'type': 'webhook',
                            'sample_rate': sample_rate,
                            'data': audiobuffer.copy(),
                        },
                        'audio_bytes',
                        byte_budget=audio_budget,
                        size_of=lambda item: len(item['data']),
                    )
                    audio_bytes_event.set()  # Wake consumer immediately
                    audiobuffer = bytearray()
                return

        try:
            while websocket_active:
                try:
                    data = await asyncio.wait_for(websocket.receive_bytes(), timeout=WS_RECEIVE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(f"WebSocket receive timeout ({WS_RECEIVE_TIMEOUT}s), closing connection {uid}")
                    observation.reason = 'receive_timeout'
                    # This is a dead upstream, not a normal remote close. Keep its
                    # terminal outcome distinct from protocol close codes 1000/1001.
                    websocket_close_code = 1011
                    application_failed = True
                    break
                await process_frame(data)

        except ProjectionQueueWaitTimeout:
            observation.reason = 'queue_wait_timeout'
            websocket_close_code = 1011
            application_failed = True
        except asyncio.CancelledError:
            if observation.reason == 'peer' and not application_failed:
                observation.reason = 'cancelled'
            raise
        except (ValueError, struct.error, UnicodeDecodeError) as exc:
            observation.reason = 'protocol_error'
            websocket_close_code = 1003
            logger.warning(f'Invalid pusher frame: {type(exc).__name__} {uid}')
        except WebSocketDisconnect as exc:
            websocket_close_code = exc.code or 1006
            logger.info("WebSocket disconnected")
        except Exception as e:
            observation.reason = 'application_error'
            logger.error(f'Could not process audio: error {e}')
            websocket_close_code = 1011
            application_failed = True
        finally:
            await finish_receive()

    bg_main_tasks: List[asyncio.Task[Any]] = []
    receive_task: asyncio.Task[Any] | None = None
    record_drain_observed = False

    async def drain_socket_tasks() -> None:
        nonlocal record_drain_observed
        shutdown_event.set()
        if durable_audio:
            # Preserve the *same* worker and its in-flight projection. Cancelling
            # and restarting would lose the drain proof for a thread still doing
            # storage I/O. All other socket tasks keep bounded cleanup.
            private_worker = bg_main_tasks[1]
            if not private_worker.done() and not record_drain_observed:
                # Start at close, even if the worker is already stuck inside a
                # projection operation. Its timer follows the same worker into
                # the process owner and unwinds on success or cancellation.
                observation_stack = ExitStack()
                observation_stack.enter_context(observe_work('drain'))
                private_worker.add_done_callback(lambda _: observation_stack.close())
                record_drain_observed = True
            await asyncio.wait(bg_main_tasks, timeout=BG_DRAIN_TIMEOUT)
            has_record_debt = (
                record_barrier.upload_sessions or record_barrier.pending_clears or record_barrier.close_failures
            )
            if (has_record_debt or record_barrier.close_retry_at) and retain_closed_record_drain(
                private_worker,
                on_capacity=lambda: abandon_evicted_record_drain(private_worker, record_barrier, record_futures),
            ):
                bg_main_tasks.remove(private_worker)
        else:
            with observe_work('drain'):
                await drain_tasks(bg_main_tasks, timeout=BG_DRAIN_TIMEOUT, label="pusher_bg", cancel=False)

    try:
        PUSHER_ACTIVE_WS_CONNECTIONS.inc()
        with record_futures.scope():
            receive_task = create_named_task(receive_tasks(), name=f"ws:{uid}:receive")
            bg_main_tasks = [
                create_named_task(process_speaker_sample_queue(), name=f"ws:{uid}:speaker_samples"),
                create_named_task(process_private_cloud_queue(), name=f"ws:{uid}:private_cloud"),
                create_named_task(process_transcript_queue(), name=f"ws:{uid}:transcripts"),
                create_named_task(process_audio_bytes_queue(), name=f"ws:{uid}:audio_bytes"),
            ]

        exit_result = await supervise_tasks(
            receive_task=receive_task,
            bg_tasks=bg_main_tasks,
            finite_tasks=None,
            label="pusher",
        )
        logger.info(f"Supervisor exited: reason={exit_result.reason} task={exit_result.task_name} {uid}")
        if exit_result.reason in {'crash', 'lifetime_done'}:
            # A background worker dying or unexpectedly returning ends an accepted
            # session abnormally even though the socket itself has no close frame.
            websocket_close_code = 1011
            application_failed = True

        if receive_task.done() and not receive_task.cancelled():
            exc = receive_task.exception()
            if exc is not None:
                raise exc

        if not receive_task.done():
            websocket_active = False
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass

        await drain_socket_tasks()

    except asyncio.CancelledError:
        websocket_close_code = 1006
        observation.reason = 'cancelled'
        if receive_task is not None and (durable_queue.capacity_wait_active or pcm_admission_wait_active):
            # Interrupt projection capacity after custody, or PCM admission
            # before submission. A cancelled admission pause keeps its tail
            # unacknowledged for WAL replay without starting storage in cleanup.
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
            await drain_socket_tasks()
        raise
    except Exception as e:
        logger.error(f"Error during WebSocket operation: {e}")
        websocket_close_code = 1011
        application_failed = True
    finally:
        shutdown_event.set()
        websocket_active = False

        all_to_cancel = [t for t in bg_main_tasks if not t.done()]
        await drain_tasks(all_to_cancel, timeout=5.0, label="pusher_cleanup", cancel=True)
        await audio_projection.persist_pending()

        if application_failed and observation.reason == 'peer':
            observation.reason = 'application_error'
        PUSHER_ACTIVE_WS_CONNECTIONS.dec()
        # Live episode moments buffer in this process; a pod move or reconnect must not strand them.
        await flush_episode_moment(uid, episode_session['conversation_id'])

        journey_attempt.finish(pusher_session_outcome(websocket_close_code, application_failed=application_failed))

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")


@router.websocket("/v1/trigger/listen")
@with_session_census('pusher')
async def websocket_endpoint_trigger(
    websocket: WebSocket,
    uid: str,
    sample_rate: int = 8000,
    client_kind: str = 'unknown',
    audio_timeline: Optional[int] = None,
    audio_custody: Optional[int] = None,
) -> None:
    await _websocket_util_trigger(websocket, uid, sample_rate, client_kind, audio_timeline, audio_custody)
