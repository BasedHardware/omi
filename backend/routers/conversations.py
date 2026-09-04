import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, BackgroundTasks
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import database.conversations as conversations_db
import database._client as db_client_module
import database.action_items as action_items_db
import database.redis_db as redis_db
import database.users as users_db
from database.firestore_read_metrics import FirestoreReadSite
from database.vector_db import delete_vector, delete_transcript_chunk_vectors
import database.vector_db as vector_db
from utils.other.storage import delete_conversation_audio_files
from utils.screen_frames.store import delete_conversation_screen_frames
from models.calendar_context import CalendarMeetingContext
from models.client_processing import PROJECTION_FAMILY_FIELDS, ClientProcessing
from models.conversation import (
    BulkAssignSegmentsRequest,
    CalendarEventLink,
    Conversation,
    ConversationAnalytics,
    ConversationFinalizationStatusResponse,
    ConversationMutationResponse,
    CreateConversationResponse,
    DeleteActionItemRequest,
    MergeConversationsRequest,
    MergeConversationsResponse,
    SearchRequest,
    SetConversationActionItemsStateRequest,
    SetConversationEventsStateRequest,
    SharedConversationResponse,
    TestPromptRequest,
    TranscriptMatchSnippet,
    UpdateActionItemDescriptionRequest,
    UpdateSegmentTextRequest,
    UpdateSummaryRequest,
    project_shared_conversation,
)
from utils.conversations.factory import deserialize_conversation
from utils.conversations.analytics import build_conversation_analytics
from utils.conversations.render import redact_conversations_for_list
from utils.conversations.mcp_transcript_search import (
    attach_match_snippets_to_conversations,
    merge_typesense_page_with_transcript_hits,
    search_transcript_conversation_ids,
)
from models.conversation_enums import ConversationStatus, ConversationVisibility
from models.conversation_photo import ConversationPhoto
from models.geolocation import Geolocation
from models.app import App
from pydantic import BaseModel, Field, ValidationError
from models.transcript_segment import TranscriptSegment
from models.other import Person
from models.shared import StatusResponse

from utils.conversations.projection_payload import (
    client_processing_mutation,
    sanitize_untrusted_provenance_field,
)
from utils.conversations.process_conversation import (
    AppUsageAttribution,
    DerivedEffectsDisposition,
    process_conversation,
    run_first_open_derived_work,
    retrieve_in_progress_conversation,
)
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations import share_email
from utils.conversations.meeting_receipt import record_and_persist_finalized_meeting_receipt
from utils.integration_telemetry import emit_posthog_event
from utils.executors import db_executor, llm_executor, postprocess_executor, run_blocking, submit_with_context
from utils.memory.memory_service import MemoryService
from utils.memory.retraction_scope import retraction_can_be_skipped
from utils.memory.canonical_memory_adapter import ConversationReplacementConflictError
from utils import byok
from utils.conversations.search import (
    ConversationSearchUnavailableError,
    clamp_conversation_search_pagination,
    conversation_matches_date_range,
    conversation_matches_speaker,
    parse_exact_conversation_reference,
    search_conversations,
)
from utils.llm.conversation_processing import SummaryProviderError, generate_summary_with_prompt
from utils.speaker_identification import extract_speaker_samples
from utils.other import endpoints as auth
from utils.other.storage import get_conversation_recording_if_exists
from utils.app_integrations import trigger_external_integrations
from utils.request_validation import NonNegativeOffset, PositiveLimit
from utils.journey_metrics_contract import resolve_client_kind
from utils.product_telemetry import emit_product_event
from services.conversation_frame_evidence import delete_conversation_and_frame_evidence
from utils.other.list_budget import (
    OMI_LIST_TRUNCATED_HEADER,
    OMI_LIST_TRUNCATED_VALUE,
    list_read_budget_for_request,
)
from utils.conversations.calendar_linking import (
    get_overlapping_calendar_event,
    write_conversation_link_to_calendar_event,
)
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
from utils.retrieval.tools.calendar_tools import get_google_calendar_event
from utils.retrieval.tools.google_utils import refresh_google_token
from utils.conversations.location import resolve_geolocation
from utils.conversations.transcript_hash import transcript_sha256_for_binding
from utils.observability.fallback import record_fallback
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_valid_conversation_by_id(uid: str, conversation_id: str) -> dict:
    conversation = conversations_db.get_conversation(
        uid, conversation_id, read_site=FirestoreReadSite.CONVERSATIONS_VALID_BY_ID
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    return conversation


def _speaker_assignment(segment: TranscriptSegment) -> str:
    if segment.is_user:
        return 'self'
    if segment.person_id:
        return f"person:{hashlib.sha256(str(segment.person_id).encode('utf-8')).hexdigest()[:16]}"
    return 'unassigned'


def _speaker_assignment_kind(assignment: str) -> str:
    return 'person' if assignment.startswith('person:') else assignment


def _emit_speaker_identity_confirmed(
    *,
    uid: str,
    conversation_id: str,
    scope: str,
    before: List[str],
    after: List[str],
) -> None:
    if not after:
        return
    assignment_kinds = [_speaker_assignment_kind(value) for value in after]
    properties = {
        'conversation_id': conversation_id,
        'confirmation': 'accepted' if before == after else 'corrected',
        'assignment': assignment_kinds[0] if len(set(assignment_kinds)) == 1 else 'mixed',
        'scope': scope,
        'affected_segment_count': len(after),
    }
    if len(set(after)) == 1 and assignment_kinds[0] == 'person':
        properties['assignment_id'] = after[0]
    emit_product_event(
        uid=uid,
        event='Speaker Identity Confirmed',
        properties=properties,
    )


def _enrich_deferred_conversation(uid: str, conversation: dict) -> dict:
    """First open of a lazily-deferred desktop conversation. The LLM enrichment (summary, action
    items, memories, embeddings, app results) takes ~10s, so we run it in the BACKGROUND and return
    the conversation immediately: the client gets an instant open (transcript already present) and
    polls until `status` flips to `completed`. The `deferred` flag is cleared atomically with the
    admission-lease renewal so the stale-processing sweep cannot terminalize the row between clear
    and first heartbeat. On enrichment failure the flag is re-armed and status reset to completed
    so the next open retries cleanly instead of spinning."""
    conversation_id = conversation.get('id')
    try:
        reacquired = lifecycle_service.reacquire_deferred_processing(uid, conversation_id)
    except Exception as e:
        logger.error(f"lazy enrich reacquire failed uid={uid} conv={conversation_id}: {e}")
        return conversation
    if not reacquired:
        # The row was terminalized or discarded before reacquisition. A stale
        # processor must not persist derived side effects after ownership loss.
        return conversation

    def _run_enrichment():
        try:
            conv_obj = deserialize_conversation(conversation)
            conv_obj.deferred = False
            with lifecycle_service.processing_admission_guard(uid, conversation_id, rollback_on_failure=False):
                enriched = process_conversation(
                    uid,
                    conv_obj.language or 'en',
                    conv_obj,
                    force_process=True,
                    is_reprocess=False,
                    app_usage_attribution=AppUsageAttribution.NON_USER_REPROCESS,
                )
            # Deferred desktop meetings must publish their exact Chat receipt
            # at the same terminal transition as ordinary finalization. The
            # initial lazy row deliberately skipped this adapter, so doing it
            # here closes the gap without waking Chat for processing rows.
            if enriched is not None:
                record_and_persist_finalized_meeting_receipt(uid, enriched)
            logger.info(f"lazy enrich complete uid={uid} conv={conversation_id}")
        except Exception as e:
            logger.error(f"lazy enrich failed uid={uid} conv={conversation_id}: {e}")
            try:
                recovered = lifecycle_service.recover_deferred_processing_failure(uid, conversation_id)
                if not recovered:
                    logger.warning(
                        'lazy enrich recovery lost ownership uid=%s conv=%s',
                        uid,
                        conversation_id,
                    )
            except Exception:
                logger.exception(
                    'lazy enrich recovery failed uid=%s conv=%s',
                    uid,
                    conversation_id,
                )

    submit_with_context(postprocess_executor, _run_enrichment)
    # Return immediately — still status=processing, no summary yet; the client polls for completion.
    conversation['deferred'] = False
    return conversation


def _dispatch_first_open_work(uid: str, conversation: dict) -> None:
    """Claim once and run in the background; failure remains retryable."""
    conversation_id = conversation.get('id')
    if not conversation_id or not conversation.get('jit_first_open'):
        return
    try:
        token = conversations_db.claim_authorized_first_open_work(uid, conversation_id, conversation.get('source'))
    except Exception as error:
        logger.warning('JIT first-open claim failed uid=%s conv=%s: %s', uid, conversation_id, error)
        return
    if token is None:
        return

    def _run() -> None:
        succeeded = False
        try:
            latest = conversations_db.get_conversation(uid, conversation_id)
            if latest is None:
                raise RuntimeError('conversation disappeared before first-open work')
            run_first_open_derived_work(uid, latest, token)
            succeeded = True
        except Exception as error:
            logger.exception('JIT first-open worker failed uid=%s conv=%s: %s', uid, conversation_id, error)
        finally:
            try:
                conversations_db.finish_first_open_work(uid, conversation_id, token, succeeded=succeeded)
            except Exception as error:
                logger.exception(
                    'JIT first-open lease finalization failed uid=%s conv=%s: %s', uid, conversation_id, error
                )

    submit_with_context(postprocess_executor, _run)


class ProcessConversationRequest(BaseModel):
    calendar_meeting_context: Optional[CalendarMeetingContext] = None
    # Unvalidated on purpose: a malformed projection must not 422 a finished recording.
    # Schema, size caps, and transcript-hash binding run in the handler.
    client_processing: Optional[Any] = Field(
        default=None,
        description=(
            "Untrusted client-authored display projection. Accepted as a raw payload "
            "and validated in the handler so a malformed projection cannot 422 a "
            "finished recording. Hash-bound to the persisted transcript. Display only "
            "— never an input to intelligence."
        ),
    )


# Provenance is untrusted client input. Bound it before it reaches a log
# record so a newline / C0 control / oversized token cannot forge a second line.
def _projection_provenance_for_log(raw: Any) -> tuple[Any, Any, Any]:
    """Pull provenance for logs. Never raises; never returns body text."""
    try:
        if raw is None or isinstance(raw, (str, bytes, list, tuple, int, float, bool)):
            return None, None, None
        if isinstance(raw, dict):
            provenance = raw.get('provenance')
        else:
            provenance = getattr(raw, 'provenance', None)
        if provenance is None or isinstance(provenance, (str, bytes, list, tuple, int, float, bool)):
            return None, None, None
        if isinstance(provenance, dict):
            return (
                sanitize_untrusted_provenance_field(provenance.get('model_id')),
                sanitize_untrusted_provenance_field(provenance.get('runtime')),
                sanitize_untrusted_provenance_field(provenance.get('device_class')),
            )
        return (
            sanitize_untrusted_provenance_field(getattr(provenance, 'model_id', None)),
            sanitize_untrusted_provenance_field(getattr(provenance, 'runtime', None)),
            sanitize_untrusted_provenance_field(getattr(provenance, 'device_class', None)),
        )
    except Exception:
        return None, None, None


def _log_client_projection_rejected(reason: str, raw: Any) -> None:
    """Content-free reject log. Provenance may be missing or malformed."""
    try:
        model_id, runtime, device_class = _projection_provenance_for_log(raw)
        logger.warning(
            'client_processing rejected reason=%s model_id=%s runtime=%s device_class=%s',
            reason,
            model_id,
            runtime,
            device_class,
        )
    except Exception:
        logger.warning('client_processing rejected reason=%s', reason)


def _accepted_client_projection(raw: Any, segments: Any) -> Optional[ClientProcessing]:
    """Bind a client projection to the persisted transcript, or drop it.

    Schema failures and hash mismatch are not request errors: the conversation
    still finalizes on the deterministic minimum. Warnings are content-free
    (reason plus provenance only — never transcript or body).
    """
    if raw is None:
        return None
    try:
        projection = ClientProcessing.model_validate(raw)
    except (TypeError, ValidationError, ValueError):
        _log_client_projection_rejected('schema_invalid', raw)
        return None
    # Stored rows only: every caller here binds against a persisted transcript.
    # `transcript_sha256_for_binding` returns None for a legacy row whose stored
    # identity is not canonical -- for those, a matching digest would not imply
    # matching rendered attribution, so the projection is dropped, not trusted.
    expected = transcript_sha256_for_binding(segments or [])
    if expected is None:
        _log_client_projection_rejected('stored_transcript_not_canonical', raw)
        return None
    if expected != projection.transcript_sha256:
        _log_client_projection_rejected('hash_mismatch', raw)
        return None
    return projection


def _drop_display_projection(conversation: Conversation) -> None:
    """Clear the in-memory projection after a transcript mutation invalidated storage.

    Consults ``PROJECTION_FAMILY_FIELDS`` rather than naming the field, so a
    sibling projection classified there is dropped here too without a code change.
    """
    for field in PROJECTION_FAMILY_FIELDS:
        setattr(conversation, field, None)


# Must match database.conversations.CLIENT_PROCESSING_BIND_REPORT_KEY.
# Local copy: this router is loaded under a stubbed database.conversations.
_CLIENT_PROCESSING_BIND_REPORT_KEY = '_client_processing_bind_report'


def _projection_bind_report() -> dict[str, bool]:
    return {'submitted_projection_bound': False}


def _carry_projection_bind_report(extra_updates: dict[str, Any]) -> dict[str, bool]:
    """Attach an out-parameter the transactional bind fills. Never persisted."""
    report = _projection_bind_report()
    extra_updates[_CLIENT_PROCESSING_BIND_REPORT_KEY] = report
    return report


def _echo_submitted_projection_if_bound(
    conversation: Conversation,
    client_projection: Optional[ClientProcessing],
    bind_report: dict[str, bool],
) -> Optional[ClientProcessing]:
    """Attach the submitted projection only when THIS transaction stored it.

    The bind report is the transaction's answer. A later request's projection
    on the document is not this request's, and a rejected candidate must not
    appear in the response.
    """
    if client_projection is not None and bind_report.get('submitted_projection_bound') is True:
        conversation.client_processing = client_projection
        return client_projection
    return None


def _bind_late_client_projection(uid: str, conversation: Conversation, raw: Any) -> Conversation:
    """Idempotency hit: bind a late projection to the stored transcript.

    Updates only ``client_processing``. Never touches ``structured``, never
    re-enters processing, never reprocesses. Invalid, mismatched, or missing
    projection: return the existing conversation unchanged (still not a 422).
    The write re-checks the digest against the transactional snapshot so a
    T2 segment update cannot resurrect a T1 projection.
    """
    if raw is None:
        return conversation
    bound = _accepted_client_projection(raw, getattr(conversation, 'transcript_segments', None))
    if bound is None:
        return conversation
    # Route-level hash is a fast drop. The write re-checks the stored
    # transcript inside the same transaction so a T2 segment update that
    # landed after this snapshot cannot resurrect a T1 projection.
    payload = client_processing_mutation(bound)
    if conversations_db.bind_client_processing(uid, conversation.id, payload):
        conversation.client_processing = bound
    return conversation


class ConversationSearchItem(Conversation):
    """Search hit: base conversation fields plus optional transcript match evidence."""

    match_snippets: List[TranscriptMatchSnippet] = []


class SearchConversationsResponse(BaseModel):
    items: List[ConversationSearchItem]
    total_pages: int
    current_page: int
    per_page: int


class ConversationStatusResponse(BaseModel):
    status: str


class ConversationsCountResponse(BaseModel):
    count: int
    sources: List[str] | None = None


class ConversationRecordingResponse(BaseModel):
    has_recording: bool


class ConversationSuggestedAppsResponse(BaseModel):
    suggested_apps: List[App]
    conversation_id: str


class ConversationTestPromptResponse(BaseModel):
    summary: str


@router.post("/v1/conversations", response_model=CreateConversationResponse, tags=['conversations'])
def process_in_progress_conversation(
    request: ProcessConversationRequest = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:create")),
):
    conversation = retrieve_in_progress_conversation(uid)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation in progress not found")

    conversation = deserialize_conversation(conversation)

    # Inject calendar context if provided
    if request and request.calendar_meeting_context:
        if not conversation.external_data:
            conversation.external_data = {}
        conversation.external_data['calendar_meeting_context'] = request.calendar_meeting_context.model_dump()

    client_projection = _accepted_client_projection(
        request.client_processing if request is not None else None,
        getattr(conversation, 'transcript_segments', None),
    )

    # Geolocation
    if conversation.geolocation:
        conversation.geolocation = resolve_geolocation(conversation.geolocation)
    else:
        geolocation = redis_db.get_cached_user_geolocation(uid)
        if geolocation:
            record_fallback(
                component='conversation_finalization',
                from_mode='conversation_snapshot',
                to_mode='redis_user_cache',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            conversation.geolocation = resolve_geolocation(Geolocation(**geolocation))

    # Winner owns ingress. The accepted projection rides the admission CAS:
    # status→processing and client_processing are one write. A later request
    # (including a loser that late-binds) can only land after this commit, so
    # a stalled second write cannot last-writer-wins an older projection over
    # a newer one (section 1.7 (c)). A mutation failure is an admission
    # failure — the row stays in_progress instead of stranding on processing
    # with no durable job. Ingress-owned mutation only; the coordinator's
    # existing-row persist still strips the field. Omit extra_updates when
    # there is no projection so positional admit stubs keep working.
    extra_updates = client_processing_mutation(client_projection) if client_projection is not None else None
    bind_report = _projection_bind_report()
    if extra_updates is None:
        admitted = lifecycle_service.admit_processing(uid, conversation.id)
    else:
        bind_report = _carry_projection_bind_report(extra_updates)
        admitted = lifecycle_service.admit_processing(uid, conversation.id, extra_updates=extra_updates)
    if not admitted:
        latest = _get_valid_conversation_by_id(uid, conversation.id)
        latest_conversation = deserialize_conversation(latest)
        # Losing the compare-and-swap still 200s, but must not silently drop a
        # valid projection. Hash-bind against the conversation actually stored
        # and write client_processing alone — never structured, never reprocess.
        latest_conversation = _bind_late_client_projection(
            uid,
            latest_conversation,
            request.client_processing if request is not None else None,
        )
        return CreateConversationResponse(conversation=latest_conversation, messages=[])

    # The admission CAS reports whether the submitted projection bound.
    # A follow-up read would race a later request's write and could strand
    # this row on processing if it raised before the guard.
    client_projection = _echo_submitted_projection_if_bound(conversation, client_projection, bind_report)

    current_in_progress_id = redis_db.get_in_progress_conversation_id(uid)
    if current_in_progress_id == conversation.id:
        redis_db.remove_in_progress_conversation_id(uid)

    conversation.status = ConversationStatus.processing
    persisted = False
    derived_effects_disposition = DerivedEffectsDisposition.RUN

    def record_persistence(current: bool) -> None:
        nonlocal persisted
        persisted = current

    def record_derived_effects_disposition(current: DerivedEffectsDisposition) -> None:
        nonlocal derived_effects_disposition
        derived_effects_disposition = current

    # This synchronous path has no durable job for the reconciler to replay, so
    # a processing failure must return the admission to in_progress — otherwise
    # the conversation is stranded on "processing" forever and the client shows
    # a stuck Processing card it can never resolve.
    with lifecycle_service.processing_admission_guard(uid, conversation.id):
        conversation = process_conversation(
            uid,
            conversation.language,
            conversation,
            force_process=True,
            persistence_observer=record_persistence,
            derived_effects_disposition_observer=record_derived_effects_disposition,
            client_projection=client_projection,
        )
    if not persisted:
        latest = _get_valid_conversation_by_id(uid, conversation.id)
        return CreateConversationResponse(conversation=deserialize_conversation(latest), messages=[])
    # A terminal free-tier minimum persists successfully but must not fan out
    # apps/webhooks — the same decision the durable finalizer already honours
    # via derived_effects_disposition_observer (section 1.7). The conversation
    # itself still returns to the client; this suppresses derived effects only.
    if derived_effects_disposition == DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS:
        return CreateConversationResponse(conversation=conversation, messages=[])
    messages = asyncio.run(trigger_external_integrations(uid, conversation))

    return CreateConversationResponse(conversation=conversation, messages=messages)


@router.post(
    '/v1/conversations/{conversation_id}/finalize', response_model=CreateConversationResponse, tags=['conversations']
)
def finalize_conversation(
    conversation_id: str,
    request: ProcessConversationRequest = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:create")),
):
    """Finalize exactly one backend conversation.

    Unlike POST /v1/conversations, this does not operate on the user's Redis
    "current in-progress" pointer, so desktop retry/rotation cannot accidentally
    finalize a newer recording.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)

    if conversation.status != ConversationStatus.in_progress:
        # Section 1.7 (c): a later projection overwrites projection fields only.
        # A slow device finishing local inference after the first finalize is
        # the normal case — hash-bind against the stored transcript and persist
        # client_processing alone. Never rewrite structured, never re-enter
        # processing, never reprocess. Mismatch / invalid: drop, still 200.
        conversation = _bind_late_client_projection(
            uid,
            conversation,
            request.client_processing if request is not None else None,
        )
        return CreateConversationResponse(conversation=conversation, messages=[])

    extra_updates = {}
    if request and request.calendar_meeting_context:
        if not conversation.external_data:
            conversation.external_data = {}
        conversation.external_data['calendar_meeting_context'] = request.calendar_meeting_context.model_dump()
        extra_updates['external_data'] = conversation.external_data

    # Persist an accepted projection on the conversation document so the
    # Cloud Tasks worker's stored-projection has_projection path can see it.
    # Drop-never-422: a bad payload must not reject the finished recording.
    # Do not attach yet: the outbox transaction re-checks the digest and may
    # drop a T1-validated candidate after a T2 race.
    client_projection = _accepted_client_projection(
        request.client_processing if request is not None else None,
        getattr(conversation, 'transcript_segments', None),
    )
    bind_report = _projection_bind_report()
    if client_projection is not None:
        extra_updates.update(client_processing_mutation(client_projection))
        bind_report = _carry_projection_bind_report(extra_updates)

    # The durable Cloud Tasks worker cannot inherit this request's BYOK
    # context: the task payload is the opaque {job_id, dispatch_generation}
    # schema, so the worker runs without the X-BYOK-* keys the middleware
    # validated for this request. Admitting a BYOK request here would silently
    # process the conversation with platform credentials. Reject before any
    # mutation so BYOK clients fail fast instead of being processed as Omi keys.
    if byok.has_byok_keys():
        raise HTTPException(
            status_code=409,
            detail='BYOK finalization is not supported on this route; use the live listen session',
        )

    try:
        finalization = lifecycle_service.request_finalization(
            uid,
            conversation.id,
            has_byok_keys=False,
            force_process=True,
            extra_updates=extra_updates or None,
            require_cloud_tasks=True,
            client_kind=resolve_client_kind(x_app_platform=conversation.client_platform, user_agent=None),
        )
    except lifecycle_service.FinalizationDispatchUnavailable as error:
        raise HTTPException(status_code=503, detail='Conversation finalization is temporarily unavailable') from error

    if finalization['route'] == 'noop':
        latest = _get_valid_conversation_by_id(uid, conversation_id)
        return CreateConversationResponse(conversation=deserialize_conversation(latest), messages=[])

    # Requiring Cloud Tasks keeps REST finalization off the pusher-only route.
    # The only accepted outcomes are an enqueued task or an outbox row retained
    # for reconciler retry after an uncertain task-create acknowledgement.
    if finalization['route'] not in {'cloud_tasks', 'queued'}:
        raise HTTPException(status_code=503, detail='Conversation finalization is temporarily unavailable')

    conversation.status = ConversationStatus.processing

    current_in_progress_id = redis_db.get_in_progress_conversation_id(uid)
    if current_in_progress_id == conversation_id:
        redis_db.remove_in_progress_conversation_id(uid)

    # The outbox transaction reports whether the submitted projection bound.
    # A follow-up read would attribute a later request's projection to this one.
    _echo_submitted_projection_if_bound(conversation, client_projection, bind_report)

    # The Cloud Tasks worker owns expensive processing, memory extraction, and
    # integration fanout under the persisted job lease. Returning this snapshot
    # is intentionally prompt; clients may poll the status projection below.
    return CreateConversationResponse(conversation=conversation, messages=[])


@router.get(
    '/v1/conversations/{conversation_id}/finalization',
    response_model=ConversationFinalizationStatusResponse,
    tags=['conversations'],
)
def get_conversation_finalization_status(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    _get_valid_conversation_by_id(uid, conversation_id)
    status = lifecycle_service.get_finalization_status(uid, conversation_id)
    if status is None:
        raise HTTPException(status_code=404, detail='Conversation finalization job not found')
    return status


@router.post(
    '/v1/conversations/{conversation_id}/reprocess',
    response_model=Conversation,
    responses={
        400: {'description': 'The selected app cannot summarize conversations'},
        403: {'description': 'The selected app is not available to this user'},
        404: {'description': 'The conversation or selected app does not exist'},
        409: {'description': 'The selected app is disabled or not enabled by this user'},
    },
    tags=['conversations'],
)
def reprocess_conversation(
    conversation_id: str,
    language_code: Optional[str] = None,
    app_id: Optional[str] = None,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:reprocess")),
):
    """
    Whenever a user wants to reprocess a conversation, or wants to force process a discarded one
    :param conversation_id: The ID of the conversation to reprocess
    :param language_code: Optional language code to use for processing
    :param app_id: Optional app ID to use for processing (if provided, only this app will be triggered)
    :return: The updated conversation after reprocessing.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    # Reprocess force-processes a *discarded* conversation to revive it, but a
    # soft-deleted tombstone is invisible to the user and must not be reprocessed:
    # process_conversation would regenerate structured data, action items, memories
    # and embeddings from content the user deleted, resurrecting it. Same
    # tombstone-eligibility contract as sync (#10119) and merge (#10262). Checked
    # on the raw doc because the Conversation model does not carry `deleted`.
    if conversations_db.is_soft_deleted(conversation):
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation = deserialize_conversation(conversation)
    if not language_code:
        language_code = conversation.language or 'en'

    explicit_app = _validate_reprocess_app_selection(uid, app_id) if app_id else None

    processed_conversation = process_conversation(
        uid,
        language_code,
        conversation,
        force_process=True,
        is_reprocess=True,
        bypass_jit_first_open=True,
        app_id=app_id,
        explicit_app=explicit_app,
        app_usage_attribution=(
            AppUsageAttribution.EXPLICIT_SELECTION if explicit_app else AppUsageAttribution.NON_USER_REPROCESS
        ),
    )

    return processed_conversation


def _validate_reprocess_app_selection(uid: str, app_id: str) -> App:
    """Resolve one explicit selection before reprocessing mutates the conversation."""

    # Imported here, not at module scope, for the same reason line ~1510 already does: the
    # apps chain pulls the memory/social graph at import time, and the sanctioned isolation
    # seam (backend/docs/test_isolation.md) loads this router bare to test pure request
    # validation. A module-level import would make those suites stub a graph they never call.
    from database.apps import get_app_by_id_db
    from utils.apps import get_available_app_model_by_id, is_user_app_enabled

    if get_app_by_id_db(app_id) is None:
        raise HTTPException(status_code=404, detail='App not found')

    app = get_available_app_model_by_id(app_id, uid)
    if app is None:
        raise HTTPException(status_code=403, detail='App is not available to this user')
    if not app.works_with_memories():
        raise HTTPException(status_code=400, detail='App does not support conversation summarization')
    if app.disabled:
        raise HTTPException(status_code=409, detail='App is currently unavailable')
    if not is_user_app_enabled(uid, app_id):
        raise HTTPException(status_code=409, detail='App must be enabled before it can summarize a conversation')
    return app


def _ensure_aware(value: datetime) -> datetime:
    # FastAPI parses a query datetime as naive or timezone-aware depending on whether the client
    # included a UTC offset. Normalize to timezone-aware (UTC) so comparing the two ends of a date
    # range never raises TypeError on mixed awareness (which would surface as a 500).
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


# Firestore 'in' filters accept at most 30 values (see database/apps.py, database/chat.py). Reject
# an oversized status/source filter before it reaches the query so a caller cannot turn a
# comma-separated filter into an unhandled 500. ConversationStatus and the source set are both
# tiny, so a cap of 20 can never reject a request a real client would send.
MAX_IN_FILTER_VALUES = 20
LEGACY_SEGMENT_INDEX_PREFIX = '#index:'


def _reject_oversized_filter(values: List[str], field_name: str) -> None:
    if len(values) > MAX_IN_FILTER_VALUES:
        raise HTTPException(status_code=400, detail=f"{field_name} accepts at most {MAX_IN_FILTER_VALUES} values")


def _resolve_bulk_segment_indices(conversation: Conversation, requested_ids: List[str]) -> List[int]:
    """Resolve assignment targets before mutating any transcript segment.

    Desktop sends positional targets for legacy transcripts that were stored without
    segment IDs. Exact IDs remain the preferred wire contract; positional targets are
    only accepted for completed conversations because an in-progress transcript can
    still be reordered or merged.
    """
    segments = conversation.transcript_segments
    segment_indices_by_id = {segment.id: index for index, segment in enumerate(segments)}
    resolved_indices: List[int] = []
    unresolved_ids: List[str] = []
    allow_legacy_indices = conversation.status == ConversationStatus.completed

    for requested_id in requested_ids:
        segment_index = segment_indices_by_id.get(requested_id)
        if segment_index is None and allow_legacy_indices and requested_id.startswith(LEGACY_SEGMENT_INDEX_PREFIX):
            raw_index = requested_id[len(LEGACY_SEGMENT_INDEX_PREFIX) :]
            if raw_index.isascii() and raw_index.isdecimal():
                candidate_index = int(raw_index)
                if candidate_index < len(segments):
                    segment_index = candidate_index

        if segment_index is None:
            unresolved_ids.append(requested_id)
        elif segment_index not in resolved_indices:
            resolved_indices.append(segment_index)

    if unresolved_ids:
        raise HTTPException(
            status_code=409,
            detail=f'Unable to resolve transcript segment assignment target(s): {", ".join(unresolved_ids)}',
        )

    return resolved_indices


@router.get(
    '/v1/conversations',
    response_model=List[Conversation],
    tags=['conversations'],
    description=(
        "List responses may omit detail-only fields such as transcript_segments. "
        "Clients should treat omitted transcript_segments as unknown/not loaded, not as an empty transcript. "
        "Large accounts can outrun the request budget; such responses return a partial "
        "newest-first array with the X-Omi-List-Truncated: true header instead of a 504 (#11831)."
    ),
)
def get_conversations(
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    limit: PositiveLimit = 100,
    offset: NonNegativeOffset = 0,
    statuses: Optional[str] = "processing,completed",
    include_discarded: bool = True,
    sources: Optional[str] = Query(
        None,
        description="Comma-separated source filter (e.g. friend,omi); combine with statuses only for one source.",
    ),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (inclusive)"),
    folder_id: Optional[str] = Query(None, description="Filter by folder ID"),
    starred: Optional[bool] = Query(None, description="Filter by starred status"),
    uid: str = Depends(auth.get_current_user_uid),
):
    if start_date is not None and end_date is not None and _ensure_aware(start_date) > _ensure_aware(end_date):
        raise HTTPException(status_code=400, detail="start_date must be earlier than or equal to end_date")
    logger.info(f'get_conversations {uid} {limit} {offset} {statuses} {sources} {folder_id} {starred}')
    # force convos statuses to processing, completed on the empty filter
    if len(statuses) == 0:
        statuses = "processing,completed"
    source_list = [source.strip() for source in sources.split(',') if source.strip()] if sources else []
    if len(source_list) > 1 and len([status.strip() for status in statuses.split(',') if status.strip()]) > 1:
        # Firestore permits one disjunctive `in` predicate. The archive's
        # supported `sources=omi&statuses=processing,completed` path uses an
        # equality source filter; reject only the unsupported two-`in` shape.
        raise HTTPException(
            status_code=400,
            detail='multiple sources cannot be combined with multiple statuses',
        )

    status_filter = statuses.split(",") if len(statuses) > 0 else []
    _reject_oversized_filter(status_filter, "statuses")
    _reject_oversized_filter(source_list, "sources")

    # Request-scoped budget: the server-side offset is charged before the
    # query and the page stream runs under the derived per-RPC timeout, so a
    # deep page cannot consume the whole HTTP_GET_TIMEOUT (#11831).
    budget = list_read_budget_for_request(request, route='conversations')
    conversations = conversations_db.get_conversations_without_photos(
        uid,
        limit,
        offset,
        include_discarded=include_discarded,
        statuses=status_filter,
        sources=source_list,
        start_date=start_date,
        end_date=end_date,
        folder_id=folder_id,
        starred=starred,
        budget=budget,
    )

    redact_conversations_for_list(conversations)
    if budget.truncated and response is not None:
        response.headers[OMI_LIST_TRUNCATED_HEADER] = OMI_LIST_TRUNCATED_VALUE
    budget.observe('truncated' if budget.truncated else 'complete')
    return conversations


@router.get('/v1/conversations/count', tags=['conversations'], response_model=ConversationsCountResponse)
def get_conversations_count(
    statuses: Optional[str] = Query(None, description="Comma-separated status filter (e.g. processing,completed)"),
    include_discarded: bool = Query(False),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (inclusive)"),
    folder_id: Optional[str] = Query(None, description="Filter by folder ID"),
    starred: Optional[bool] = Query(None, description="Filter by starred status"),
    sources: Optional[str] = Query(
        None,
        description="Comma-separated source filter (e.g. friend,omi); combine with statuses only for one source.",
    ),
    uid: str = Depends(auth.get_current_user_uid),
):
    if start_date is not None and end_date is not None and _ensure_aware(start_date) > _ensure_aware(end_date):
        raise HTTPException(status_code=400, detail="start_date must be earlier than or equal to end_date")
    status_list = [s.strip() for s in statuses.split(',') if s.strip()] if statuses else []
    source_list = [s.strip() for s in sources.split(',') if s.strip()] if sources else []
    _reject_oversized_filter(status_list, "statuses")
    _reject_oversized_filter(source_list, "sources")
    if len(source_list) > 1 and len(status_list) > 1:
        raise HTTPException(status_code=400, detail='multiple sources cannot be combined with multiple statuses')
    count = conversations_db.get_conversations_count(
        uid,
        include_discarded=include_discarded,
        statuses=status_list,
        start_date=start_date,
        end_date=end_date,
        folder_id=folder_id,
        starred=starred,
        sources=source_list,
    )
    if source_list:
        # Echo the filter so clients can tell this backend applied it (older
        # backends ignore the unknown param and return the unfiltered total).
        return {'count': count, 'sources': source_list}
    return {'count': count}


@router.get(
    "/v1/conversations/{conversation_id}",
    response_model=Conversation,
    tags=['conversations'],
    description=(
        "Detail responses include transcript fields when available. Locked or redacted conversations "
        "may include an empty transcript_segments array even though transcript data exists."
    ),
)
def get_conversation_by_id(
    conversation_id: str,
    source: Optional[str] = Query(None, description="Optional provenance constraint for a detail read"),
    include_discarded: bool = Query(True),
    uid: str = Depends(auth.get_current_user_uid),
):
    logger.info(f'get_conversation_by_id {uid} {conversation_id}')
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    if source is not None:
        if source != 'omi':
            raise HTTPException(
                status_code=400, detail="Only source=omi is supported for provenance-constrained detail reads"
            )
        if conversation.get('source') != 'omi' or (not include_discarded and conversation.get('discarded', False)):
            raise HTTPException(status_code=404, detail="Conversation not found")
    # Lazy processing: a desktop conversation stored raw (deferred) for a freemium/Neo user is
    # enriched on first open. Other conversations are returned unchanged.
    if conversation.get('deferred'):
        conversation = _enrich_deferred_conversation(uid, conversation)
    else:
        _dispatch_first_open_work(uid, conversation)
    return conversation


@router.patch(
    "/v1/conversations/{conversation_id}/title", tags=['conversations'], response_model=ConversationMutationResponse
)
def patch_conversation_title(conversation_id: str, title: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.update_conversation_title(uid, conversation_id, title)
    return {'status': 'Ok', 'conversation': _get_valid_conversation_by_id(uid, conversation_id)}


@router.delete(
    "/v1/conversations/{conversation_id}/calendar-event",
    tags=['conversations'],
    response_model=ConversationStatusResponse,
)
def unlink_calendar_event(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Unlink a calendar event from a conversation.
    This removes the calendar_event field from the conversation.
    """
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.update_conversation(uid, conversation_id, {'calendar_event': None})
    return {'status': 'Ok'}


class LinkCalendarEventRequest(BaseModel):
    event_id: str


def _event_to_calendar_event_link(event: dict) -> Optional[CalendarEventLink]:
    """Convert a raw Google Calendar event to CalendarEventLink model."""
    start_time, end_time = parse_event_times(event)
    if start_time is None or end_time is None:
        return None

    attendee_names, attendee_emails = extract_attendees(event)

    return CalendarEventLink(
        event_id=event.get('id', ''),
        title=event.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=start_time,
        end_time=end_time,
        html_link=event.get('htmlLink'),
    )


@router.post(
    "/v1/conversations/{conversation_id}/calendar-event", response_model=CalendarEventLink, tags=['conversations']
)
async def link_calendar_event(
    conversation_id: str,
    request: LinkCalendarEventRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Link a specific Google Calendar event to an existing conversation.
    Fetches the event details and stores the calendar_event on the conversation.
    """
    await run_blocking(db_executor, _get_valid_conversation_by_id, uid, conversation_id)

    # Get Google Calendar access token
    integration = await run_blocking(db_executor, users_db.get_integration, uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")

    # Fetch the event from Google Calendar
    try:
        event = await get_google_calendar_event(access_token, request.event_id)
    except Exception as e:
        error_msg = str(e)
        # Try to refresh token if authentication failed
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    event = await get_google_calendar_event(new_token, request.event_id)
                except Exception as retry_error:
                    raise HTTPException(status_code=500, detail=f"Failed after token refresh: {str(retry_error)}")
            else:
                raise HTTPException(status_code=401, detail="Google Calendar authentication expired. Please reconnect.")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch calendar event: {error_msg}")

    # Convert to CalendarEventLink
    calendar_event = _event_to_calendar_event_link(event)
    if calendar_event is None:
        raise HTTPException(status_code=400, detail="Could not parse calendar event times")

    # Persist to Firestore
    await run_blocking(
        db_executor,
        conversations_db.update_conversation,
        uid,
        conversation_id,
        {'calendar_event': calendar_event.model_dump(mode='json')},
    )

    # Automatically write the conversation link into the calendar event description
    await write_conversation_link_to_calendar_event(uid, calendar_event.event_id, conversation_id)

    return calendar_event


@router.post(
    "/v1/conversations/{conversation_id}/calendar-event/auto-link",
    response_model=CalendarEventLink,
    tags=['conversations'],
)
async def auto_link_calendar_event(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """
    Auto-link a conversation to the best overlapping Google Calendar event.
    Uses the conversation's started_at/finished_at to find a matching event.
    Returns 404 if no overlapping event is found.
    """
    conversation = await run_blocking(db_executor, _get_valid_conversation_by_id, uid, conversation_id)

    # Get conversation times
    started_at = conversation.get('started_at')
    finished_at = conversation.get('finished_at')

    # Fall back to created_at if times are not available
    if not started_at:
        started_at = conversation.get('created_at')
    if not finished_at:
        finished_at = started_at

    if not started_at:
        raise HTTPException(status_code=400, detail="Conversation has no timestamp information")

    # Parse datetimes if they're strings. A stored timestamp that is not valid ISO (legacy or imported
    # data) would otherwise raise ValueError and surface as a 500; return a clear 400 instead, matching the
    # missing-timestamp case handled just above.
    try:
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        if isinstance(finished_at, str):
            finished_at = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Conversation has invalid timestamp information")

    # Ensure timezone-aware
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)

    # Find overlapping calendar event
    calendar_event = await get_overlapping_calendar_event(uid, started_at, finished_at)

    if calendar_event is None:
        raise HTTPException(status_code=404, detail="No overlapping calendar event found")

    # Persist to Firestore
    await run_blocking(
        db_executor,
        conversations_db.update_conversation,
        uid,
        conversation_id,
        {'calendar_event': calendar_event.model_dump(mode='json')},
    )

    # Automatically write the conversation link into the calendar event description
    await write_conversation_link_to_calendar_event(uid, calendar_event.event_id, conversation_id)

    return calendar_event


@router.patch(
    "/v1/conversations/{conversation_id}/summary", tags=['conversations'], response_model=ConversationStatusResponse
)
def patch_conversation_summary(
    conversation_id: str, data: UpdateSummaryRequest, uid: str = Depends(auth.get_current_user_uid)
):
    result = conversations_db.update_conversation_summary(uid, conversation_id, data.app_id, data.content)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail="Conversation not found")
    if result == 'app_result_not_found':
        raise HTTPException(status_code=404, detail="App summary not found for this conversation")
    return {'status': 'Ok'}


@router.patch(
    "/v1/conversations/{conversation_id}/segments/text",
    tags=['conversations'],
    response_model=ConversationStatusResponse,
)
def patch_conversation_segment_text(
    conversation_id: str, data: UpdateSegmentTextRequest, uid: str = Depends(auth.get_current_user_uid)
):
    result = conversations_db.update_conversation_segment_text(uid, conversation_id, data.segment_id, data.text)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail="Conversation not found")
    if result == 'locked':
        raise HTTPException(status_code=402, detail="Unlimited Plan Required to access this conversation.")
    if result == 'segment_not_found':
        raise HTTPException(status_code=404, detail="Segment not found")
    return {'status': 'Ok'}


@router.get(
    "/v1/conversations/{conversation_id}/photos", response_model=List[ConversationPhoto], tags=['conversations']
)
def get_conversation_photos(
    conversation_id: str, uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "frame_requests:read"))
):
    _get_valid_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_photos(uid, conversation_id)


@router.get(
    "/v1/conversations/{conversation_id}/transcripts",
    response_model=dict[str, List[TranscriptSegment]],
    tags=['conversations'],
)
def get_conversation_transcripts_by_models(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    return conversations_db.get_conversation_transcripts_by_model(uid, conversation_id)


@router.delete("/v1/conversations/{conversation_id}", response_model=StatusResponse, tags=['conversations'])
def delete_conversation(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    # TODO(Q8-gated): ratified default is cascade=true — NOT flipped; needs explicit owner sign-off
    # before changing production behavior for all users. See test_ws_j_delete_privacy.py +
    # backend/docs/memory/domain_model.md §Delete/privacy matrix.
    cascade: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    logger.info(f'delete_conversation {conversation_id} {uid} cascade={cascade}')

    if cascade:
        # Delete associated memories and action items first so partial failure cannot orphan derived data.
        db_client = getattr(db_client_module, 'db', None)
        memory_service = MemoryService(db_client=db_client)
        # Retraction is fenced with canonical intake; skip only when there is provably nothing to retract.
        # Any real memory still raises instead of being orphaned by conversation deletion.
        if not retraction_can_be_skipped(uid, conversation_id, memory_service=memory_service, db_client=db_client):
            try:
                memory_service.retract_conversation_memories(uid, conversation_id)
            except ConversationReplacementConflictError as error:
                logger.exception('cascade retraction conflicted uid=%s conversation_id=%s', uid, conversation_id)
                # Concurrent same-account memory writes kept winning the
                # account-global control CAS. Nothing has been deleted yet, so
                # fail closed with a retryable answer instead of an opaque 500;
                # the retraction is idempotent, a retried delete is safe (#11726).
                raise HTTPException(
                    status_code=503,
                    detail='Conversation memory retraction is busy, please retry',
                ) from error
            except RuntimeError as error:
                # Isolated router tests stub database/utils.other at import time.
                if type(error).__name__ != "DestructiveOperationInProgress":
                    raise
                from utils.other.account_gate_http import account_gate_busy_http_exception

                raise account_gate_busy_http_exception() from error

        action_items_db.delete_action_items_for_conversation(uid, conversation_id)
        background_tasks.add_task(delete_conversation_audio_files, uid, conversation_id)

    # Screen frames (meeting-note screenshots) are primary conversation
    # content, not cascade-only derived data, so this runs unconditionally
    # and synchronously — unlike audio_files above, a conversation typically
    # carries at most 7 of these (contract §7 cap), so the GCS fan-out here
    # is cheap. Must run before delete_conversation below: Firestore does
    # not cascade subcollection deletes, and the GCS objects have no other
    # cleanup path once the parent doc (and the frame_id it's keyed under)
    # is gone.
    delete_conversation_screen_frames(uid, conversation_id)

    delete_conversation_and_frame_evidence(uid, conversation_id)

    delete_vector(uid, conversation_id)
    delete_transcript_chunk_vectors(uid, conversation_id)

    return {"status": "Ok"}


@router.get(
    "/v1/conversations/{conversation_id}/recording",
    response_model=ConversationRecordingResponse,
    tags=['conversations'],
)
def conversation_has_audio_recording(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_valid_conversation_by_id(uid, conversation_id)
    return {'has_recording': get_conversation_recording_if_exists(uid, conversation_id) is not None}


@router.patch(
    "/v1/conversations/{conversation_id}/events", response_model=ConversationStatusResponse, tags=['conversations']
)
def set_conversation_events_state(
    conversation_id: str, data: SetConversationEventsStateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    if len(data.events_idx) != len(data.values):
        raise HTTPException(status_code=422, detail="events_idx and values must have the same length")
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)
    events = conversation.structured.events
    for i, event_idx in enumerate(data.events_idx):
        if not (0 <= event_idx < len(events)):
            continue
        events[event_idx].created = data.values[i]

    conversations_db.update_conversation_events(uid, conversation_id, [event.model_dump() for event in events])
    return {"status": "Ok"}


@router.patch(
    "/v1/conversations/{conversation_id}/action-items",
    response_model=ConversationStatusResponse,
    tags=['conversations'],
)
def set_action_item_status(
    data: SetConversationActionItemsStateRequest, conversation_id: str, uid=Depends(auth.get_current_user_uid)
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)
    action_items = conversation.structured.action_items
    for i, action_item_idx in enumerate(data.items_idx):
        if not (0 <= action_item_idx < len(action_items)):
            continue

        action_item = action_items[action_item_idx]
        new_completed_status = data.values[i]

        # Set completed status
        action_item.completed = new_completed_status

        # Handle created_at backwards compatibility
        if action_item.created_at is None:
            action_item.created_at = conversation.created_at

        # Set completed_at timestamp
        if new_completed_status:
            # Mark as completed - set completed_at to current time
            action_item.completed_at = datetime.now(timezone.utc)
        else:
            # Mark as incomplete - clear completed_at
            action_item.completed_at = None

    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.model_dump() for action_item in action_items]
    )

    # Mirror status updates to the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        # Map descriptions to item IDs for quick lookup
        description_to_ids = {}
        for ai in existing_items:
            desc = ai.get('description')
            if not desc:
                continue
            description_to_ids.setdefault(desc, []).append(ai['id'])

        for i, action_item_idx in enumerate(data.items_idx):
            if not (0 <= action_item_idx < len(action_items)):
                continue
            action_item = action_items[action_item_idx]
            new_completed_status = data.values[i]

            ids = description_to_ids.get(action_item.description, [])
            for action_item_id in ids:
                action_items_db.mark_action_item_completed(uid, action_item_id, bool(new_completed_status))
    except Exception as e:
        # Don't break conversation route if mirrored update fails
        logger.error(f'Failed to mirror action item status update: {e}')
    return {"status": "Ok"}


@router.patch(
    "/v1/conversations/{conversation_id}/action-items/{action_item_idx}",
    response_model=ConversationStatusResponse,
    tags=['conversations'],
)
def update_action_item_description(
    conversation_id: str, data: UpdateActionItemDescriptionRequest, uid=Depends(auth.get_current_user_uid)
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)
    action_items = conversation.structured.action_items

    found_item = False
    for item in action_items:
        if item.description == data.old_description:
            item.description = data.description
            found_item = True
            break

    if not found_item:
        raise HTTPException(status_code=404, detail=f"Action item with description '{data.old_description}' not found")

    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.model_dump() for action_item in action_items]
    )

    # Mirror description update in the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        for ai in existing_items:
            if ai.get('description') == data.old_description:
                action_items_db.update_action_item(uid, ai['id'], {'description': data.description})
    except Exception as e:
        logger.error(f'Failed to mirror action item description update: {e}')
    return {"status": "Ok"}


@router.delete(
    "/v1/conversations/{conversation_id}/action-items",
    response_model=ConversationStatusResponse,
    tags=['conversations'],
)
def delete_action_item(data: DeleteActionItemRequest, conversation_id: str, uid=Depends(auth.get_current_user_uid)):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)
    action_items = conversation.structured.action_items
    updated_action_items = [item for item in action_items if not (item.description == data.description)]
    conversations_db.update_conversation_action_items(
        uid, conversation_id, [action_item.model_dump() for action_item in updated_action_items]
    )

    # Mirror deletion in the standalone action_items collection
    try:
        existing_items = action_items_db.get_action_items_by_conversation(uid, conversation_id)
        for ai in existing_items:
            if ai.get('description') == data.description:
                action_items_db.delete_action_item(uid, ai['id'])
    except Exception as e:
        logger.error(f'Failed to mirror action item deletion: {e}')
    return {"status": "Ok"}


@router.patch(
    '/v1/conversations/{conversation_id}/segments/{segment_idx}/assign',
    response_model=Conversation,
    tags=['conversations'],
)
def set_assignee_conversation_segment(
    conversation_id: str,
    segment_idx: int,
    assign_type: str,
    value: Optional[str] = None,
    use_for_speech_training: bool = True,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Another complex endpoint.

    Modify the assignee of a segment in the transcript of a conversation.
    But,
    if `use_for_speech_training` is True, the corresponding audio segment will be used for speech training.

    Speech training of whom?

    If `assign_type` is 'is_user', the segment will be used for the user speech training.
    If `assign_type` is 'person_id', the segment will be used for the person with the given id speech training.

    What is required for a segment to be used for speech training?
    1. The segment must have more than 5 words.
    2. The conversation audio file shuold be already stored in the user's bucket.

    :return: The updated conversation.
    """
    logger.info(
        f'set_assignee_conversation_segment {conversation_id} {segment_idx} {assign_type} {value} {use_for_speech_training} {uid}'
    )
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)

    # Bound-check segment_idx before indexing. Same class as the events / action-items
    # handlers above (0 <= idx < len): an out-of-range idx (e.g. a stale client after
    # reprocess/merge shrank the segments) otherwise raises IndexError -> HTTP 500, and a
    # negative idx would silently mutate the wrong segment. This is a single-target route,
    # so a missing segment is a 404 rather than a skip.
    if not (0 <= segment_idx < len(conversation.transcript_segments)):
        raise HTTPException(status_code=404, detail="Segment not found")

    if value == 'null':
        value = None

    is_unassigning = value is None or value is False

    before = [_speaker_assignment(conversation.transcript_segments[segment_idx])]
    if assign_type == 'is_user':
        conversation.transcript_segments[segment_idx].is_user = bool(value) if value is not None else False
        conversation.transcript_segments[segment_idx].person_id = None
    elif assign_type == 'person_id':
        conversation.transcript_segments[segment_idx].is_user = False
        conversation.transcript_segments[segment_idx].person_id = value
    else:
        logger.info(assign_type)
        raise HTTPException(status_code=400, detail="Invalid assign type")

    conversations_db.update_conversation_segments(
        uid,
        conversation_id,
        [segment.model_dump() for segment in conversation.transcript_segments],
    )
    _drop_display_projection(conversation)
    _emit_speaker_identity_confirmed(
        uid=uid,
        conversation_id=conversation_id,
        scope='segment',
        before=before,
        after=[_speaker_assignment(conversation.transcript_segments[segment_idx])],
    )
    # thinh's note: disabled for now
    # segment_words = len(conversation.transcript_segments[segment_idx].text.split(' '))
    # # TODO: can do this async
    # if use_for_speech_training and not is_unassigning and segment_words > 5:  # some decent sample at least
    #     person_id = value if assign_type == 'person_id' else None
    #     expand_speech_profile(conversation_id, uid, segment_idx, assign_type, person_id)
    # else:
    #     path = f'{conversation_id}_segment_{segment_idx}.wav'
    #     delete_additional_profile_audio(uid, path)
    #     delete_speech_sample_for_people(uid, path)

    return conversation


@router.patch(
    '/v1/conversations/{conversation_id}/assign-speaker/{speaker_id}',
    response_model=Conversation,
    tags=['conversations'],
)
def set_assignee_conversation_segment(
    conversation_id: str,
    speaker_id: int,
    assign_type: str,
    value: Optional[str] = None,
    use_for_speech_training: bool = True,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Another complex endpoint.

    Modify the assignee of all segments in the transcript of a conversation with the given speaker_id.
    But,
    if `use_for_speech_training` is True, the corresponding audio segment will be used for speech training.

    Speech training of whom?

    If `assign_type` is 'is_user', the segment will be used for the user speech training.
    If `assign_type` is 'person_id', the segment will be used for the person with the given id speech training.

    What is required for a segment to be used for speech training?
    1. The segment must have more than 5 words.
    2. The conversation audio file should be already stored in the user's bucket.

    :return: The updated conversation.
    """
    logger.info(
        f'set_assignee_conversation_segment {conversation_id} {speaker_id} {assign_type} {value} {use_for_speech_training} {uid}'
    )
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)

    if value == 'null':
        value = None

    is_unassigning = value is None or value is False

    targeted_segments = [segment for segment in conversation.transcript_segments if segment.speaker_id == speaker_id]
    before = [_speaker_assignment(segment) for segment in targeted_segments]

    if assign_type == 'is_user':
        for segment in conversation.transcript_segments:
            if segment.speaker_id == speaker_id:
                segment.is_user = bool(value) if value is not None else False
                segment.person_id = None
    elif assign_type == 'person_id':
        for segment in conversation.transcript_segments:
            if segment.speaker_id == speaker_id:
                logger.info(f"{segment.speaker_id} {speaker_id} {value}")
                segment.is_user = False
                segment.person_id = value
    else:
        logger.info(assign_type)
        raise HTTPException(status_code=400, detail="Invalid assign type")

    conversations_db.update_conversation_segments(
        uid,
        conversation_id,
        [segment.model_dump() for segment in conversation.transcript_segments],
    )
    _drop_display_projection(conversation)
    _emit_speaker_identity_confirmed(
        uid=uid,
        conversation_id=conversation_id,
        scope='speaker',
        before=before,
        after=[_speaker_assignment(segment) for segment in targeted_segments],
    )
    # This will be used when we setup recording for conversations, not used for now
    # get the segment with the most words with the speaker_id
    # segment_idx = 0
    # segment_words = 0
    # for segment in conversation.transcript_segments:
    #     if segment.speaker == speaker_id:
    #         if len(segment.text.split(' ')) > segment_words:
    #             segment_words = len(segment.text.split(' '))
    #             if segment_words > 5:
    #                 segment_idx = segment.idx
    #
    # if use_for_speech_training and not is_unassigning and segment_words > 5:  # some decent sample at least
    #     person_id = value if assign_type == 'person_id' else None
    #     expand_speech_profile(conversation_id, uid, segment_idx, assign_type, person_id)
    # else:
    #     path = f'{conversation_id}_segment_{segment_idx}.wav'
    #     delete_additional_profile_audio(uid, path)
    #     delete_speech_sample_for_people(uid, path)

    return conversation


@router.patch(
    '/v1/conversations/{conversation_id}/segments/assign-bulk',
    response_model=Conversation,
    tags=['conversations'],
)
def assign_segments_bulk(
    conversation_id: str,
    data: BulkAssignSegmentsRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.get_current_user_uid),
):
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation)

    if data.assign_type not in {'is_user', 'person_id'}:
        raise HTTPException(status_code=400, detail="Invalid assign type")

    value = data.value
    if value == 'null':
        value = None

    segment_indices = _resolve_bulk_segment_indices(conversation, data.segment_ids)
    resolved_segment_ids = [conversation.transcript_segments[index].id for index in segment_indices]
    before = [_speaker_assignment(conversation.transcript_segments[index]) for index in segment_indices]

    for index in segment_indices:
        segment = conversation.transcript_segments[index]
        if data.assign_type == 'is_user':
            segment.is_user = bool(value) if value is not None else False
            segment.person_id = None
        else:
            segment.is_user = False
            segment.person_id = value

    conversations_db.update_conversation_segments(
        uid,
        conversation_id,
        [segment.model_dump() for segment in conversation.transcript_segments],
    )
    _drop_display_projection(conversation)
    _emit_speaker_identity_confirmed(
        uid=uid,
        conversation_id=conversation_id,
        scope='bulk',
        before=before,
        after=[_speaker_assignment(conversation.transcript_segments[index]) for index in segment_indices],
    )

    # Trigger speaker sample extraction when assigning to a person
    if data.assign_type == 'person_id' and value:
        background_tasks.add_task(
            extract_speaker_samples,
            uid=uid,
            person_id=value,
            conversation_id=conversation_id,
            segment_ids=resolved_segment_ids,
        )

    return conversation


# *********************************************
# *********** SHARING conversations ***********
# *********************************************


@router.patch(
    '/v1/conversations/{conversation_id}/visibility',
    tags=['conversations'],
    response_model=ConversationStatusResponse,
)
def set_conversation_visibility(
    conversation_id: str, value: ConversationVisibility, uid: str = Depends(auth.get_current_user_uid)
):
    logger.info(f'update_conversation_visibility {conversation_id} {value} {uid}')
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.set_conversation_visibility(uid, conversation_id, value)
    if value == ConversationVisibility.private:
        redis_db.remove_conversation_to_uid(conversation_id)
        redis_db.remove_public_conversation(conversation_id)
    else:
        redis_db.store_conversation_to_uid(conversation_id, uid)
        redis_db.add_public_conversation(conversation_id)

    return {"status": "Ok"}


class ShareRecipient(BaseModel):
    name: Optional[str] = None
    email: str


class ShareRecipientsResponse(BaseModel):
    recipients: List[ShareRecipient]


class SendShareEmailRequest(BaseModel):
    recipient_emails: List[str] = Field(min_length=1, max_length=share_email.MAX_RECIPIENTS)


class SendShareEmailResponse(BaseModel):
    sent_to: List[str]


@router.get(
    '/v1/conversations/{conversation_id}/share-recipients',
    tags=['conversations'],
    response_model=ShareRecipientsResponse,
)
def get_conversation_share_recipients(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Who the meeting summary could be sent to: calendar-detected participants minus the owner."""
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    recipients = share_email.get_share_recipients(uid, conversation)
    return {'recipients': recipients}


@router.post(
    '/v1/conversations/{conversation_id}/share-email',
    tags=['conversations'],
    response_model=SendShareEmailResponse,
)
def send_conversation_share_email(
    conversation_id: str, request: SendShareEmailRequest, uid: str = Depends(auth.get_current_user_uid)
):
    """Send the meeting summary to the addresses the owner chose.

    The card lets the owner type a recipient, so the address is theirs to pick
    rather than something we detected; detection only prefills the field. What
    keeps this from being an open relay is unchanged: the sender must own the
    conversation, the mail carries only that conversation's own summary and
    share link with the owner as reply-to, the request schema caps how many
    addresses one send may carry, and a per-owner daily quota bounds the total.
    Sending
    makes the conversation link-visible first (same contract as copying the
    share link) so the emailed link resolves.
    """
    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    requested = share_email.normalized_recipient_emails(request.recipient_emails)
    if not requested:
        raise HTTPException(status_code=400, detail='A valid recipient email is required')

    # Idempotency under concurrency: a Firestore transaction atomically claims
    # the not-yet-emailed recipients, so simultaneous duplicate requests can
    # never both dispatch to the same address. A repeat of an address that was
    # definitively sent returns success without a duplicate email; an address
    # some other request is dispatching *right now* is not reported as sent,
    # because that dispatch may still fail and release its claim.
    to_dispatch, already_sent, in_flight_elsewhere = conversations_db.reserve_share_email_recipients(
        uid, conversation_id, requested
    )
    if not to_dispatch:
        if in_flight_elsewhere:
            raise HTTPException(
                status_code=409,
                detail='That summary is already being sent to this recipient — check back in a moment',
            )
        return {'sent_to': already_sent}

    if not share_email.consume_daily_send_quota(uid, len(to_dispatch)):
        conversations_db.release_share_email_recipients(uid, conversation_id, to_dispatch)
        raise HTTPException(status_code=429, detail='Daily share-email limit reached')

    # Publish before dispatching (the emailed link must never race a private
    # conversation), and roll the publish back if the send fails so a failed
    # send cannot leave a never-shared conversation link-visible. A
    # previously-shared conversation stays shared either way.
    was_shared = conversation.get('visibility') in (
        ConversationVisibility.shared,
        ConversationVisibility.public,
        'shared',
        'public',
    )

    publish_token: Dict[str, Any] = {}

    def _publish():
        # An already link-visible conversation keeps its existing visibility
        # (never downgrade `public` to `shared`); only a still-private one is
        # flipped, atomically: the write is preconditioned on the same read
        # that observed 'private', so a concurrent share/public change voids
        # this publish instead of being overwritten. The CAS token comes from
        # the publish write's own result; when nothing was published there is
        # no token and rollback is a no-op.
        if not was_shared:
            published, update_time = conversations_db.publish_conversation_visibility_if_private(uid, conversation_id)
            if published:
                publish_token['update_time'] = update_time
        redis_db.store_conversation_to_uid(conversation_id, uid)
        redis_db.add_public_conversation(conversation_id)

    def _unpublish():
        if was_shared:
            return
        reverted = conversations_db.set_conversation_visibility_if_unchanged(
            uid, conversation_id, ConversationVisibility.private, publish_token.get('update_time')
        )
        if not reverted:
            # Ownership could not be proven (someone else wrote the doc while
            # the provider call was in flight) — their share stands.
            return
        redis_db.remove_conversation_to_uid(conversation_id)
        redis_db.remove_public_conversation(conversation_id)

    def _send():
        # The claim taken above only says "dispatching"; the sent ledger is
        # written once the provider accepted, and it is what makes a later
        # repeat a no-op. Recording it is the last step, so no failure after a
        # successful dispatch can trigger the visibility rollback (a delivered
        # email keeps a live link).
        share_email.send_summary_email(uid=uid, conversation=conversation, recipient_emails=to_dispatch)
        # Viral-loop telemetry: summary shares feed the admin K-factor. Emitted
        # only after the provider accepted, so the count is delivered shares.
        emit_posthog_event(
            uid,
            'Conversation Summary Shared',
            {'conversation_id': conversation_id, 'recipient_count': len(to_dispatch), 'channel': 'email'},
        )
        try:
            conversations_db.confirm_share_email_recipients(uid, conversation_id, to_dispatch)
        except Exception:
            # Delivery already happened; a lost ledger write can only cost a
            # duplicate on a later retry, which is strictly better than
            # reporting a failure for mail the recipient holds.
            logger.exception('share email: failed to record delivered recipients')
        return {'sent_to': sorted(set(already_sent) | set(to_dispatch))}

    def _release_reservation_and_quota():
        try:
            conversations_db.release_share_email_recipients(uid, conversation_id, to_dispatch)
        except Exception:
            logger.exception('share email: failed to release recipient reservation')
        share_email.refund_daily_send_quota(uid, len(to_dispatch))

    try:
        return share_email.publish_then_send(publish=_publish, unpublish=_unpublish, send=_send)
    except share_email.AmbiguousDeliveryError as e:
        # Delivery may have happened, so the claim is promoted to the sent
        # ledger rather than left in flight or released: a retry must not risk
        # a duplicate in the recipient's inbox, and a claim nobody ever
        # resolves would block the address until its TTL expires. Quota stands
        # and the link stays published. The caller still gets 504 — we do not
        # know that it arrived, and only the ledger pretends otherwise.
        try:
            conversations_db.confirm_share_email_recipients(uid, conversation_id, to_dispatch)
        except Exception:
            logger.exception('share email: failed to record ambiguous dispatch')
        raise HTTPException(status_code=504, detail=str(e))
    except ValueError as e:
        _release_reservation_and_quota()
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        _release_reservation_and_quota()
        raise HTTPException(status_code=502, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        # Any other pre-delivery failure (e.g. Redis raising inside the publish
        # path) is definitive: nothing was dispatched, so the reservation and
        # quota must not stay consumed or retries would falsely no-op.
        logger.exception('share email: definitive failure before delivery')
        _release_reservation_and_quota()
        raise HTTPException(status_code=502, detail='share email failed before delivery')


@router.patch(
    '/v1/conversations/{conversation_id}/starred', tags=['conversations'], response_model=ConversationMutationResponse
)
def set_conversation_starred(conversation_id: str, starred: bool, uid: str = Depends(auth.get_current_user_uid)):
    logger.info(f'update_conversation_starred {conversation_id} {starred} {uid}')
    _get_valid_conversation_by_id(uid, conversation_id)
    conversations_db.set_conversation_starred(uid, conversation_id, starred)
    return {"status": "Ok", "conversation": _get_valid_conversation_by_id(uid, conversation_id)}


@router.get(
    "/v1/conversations/{conversation_id}/shared", tags=['conversations'], response_model=SharedConversationResponse
)
def get_shared_conversation_by_id(conversation_id: str):
    uid = redis_db.get_conversation_uid(conversation_id)
    if not uid:
        raise HTTPException(status_code=404, detail="Conversation is private")

    conversation = _get_valid_conversation_by_id(uid, conversation_id)
    visibility = conversation.get('visibility', ConversationVisibility.private)
    if not visibility or visibility == ConversationVisibility.private:
        raise HTTPException(status_code=404, detail="Conversation is private")
    conversation = deserialize_conversation(conversation)

    # Fetch people data for speaker names
    person_ids = conversation.get_person_ids()
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, person_ids)
        people = [Person(**p) for p in people_data]

    # Public unauthenticated surface: return only the explicit allowlist.
    # SharedConversationResponse does not inherit Conversation and ignores extras,
    # so new Conversation fields and stored-document keys stay off this response.
    return project_shared_conversation(conversation, people)


class ConversationTopicRequest(BaseModel):
    model_config = {"extra": "forbid"}

    transcript: str = Field(..., min_length=1, max_length=100_000)


class ConversationTopicResponse(BaseModel):
    model_config = {"extra": "forbid"}

    emoji: str = ""
    title: str = ""


@router.post('/v1/conversations/topic', response_model=ConversationTopicResponse, tags=['conversations'])
async def generate_conversation_topic_endpoint(
    body: ConversationTopicRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:topic")),
):
    """Return-only emoji + short title through the managed conv_structure feature.

    Does not write Firestore. Desktop clients call this for the fast provisional title
    on a just-saved conversation instead of inventing one via Anthropic Haiku chat
    completions; full backend processing still overwrites it later.
    """
    # Deferred with the LLM helper: this router is covered by module-isolation tests that
    # build a minimal dependency graph, and utils.subscription pulls database.user_usage
    # in at import time.
    from utils.llm import conversation_topic as conversation_topic_llm
    from utils.subscription import is_trial_paywalled

    if await run_blocking(db_executor, is_trial_paywalled, uid, 'desktop'):
        raise HTTPException(status_code=402, detail='trial_expired')
    topic = await run_blocking(
        llm_executor,
        lambda: conversation_topic_llm.generate_conversation_topic(uid, body.transcript),
    )
    if topic is None:
        raise HTTPException(status_code=502, detail="conversation_topic_failed")
    return ConversationTopicResponse(emoji=topic.emoji or "", title=topic.title or "")


@router.post("/v1/conversations/search", response_model=SearchConversationsResponse, tags=['conversations'])
def search_conversations_endpoint(
    search_request: SearchRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:search")),
):
    if search_request.speaker_id and search_request.speaker_id != 'user':
        person = users_db.get_person(uid, search_request.speaker_id)
        if person is None:
            raise HTTPException(status_code=404, detail="Speaker not found")

    # Convert ISO datetime strings to Unix timestamps if provided
    start_timestamp = None
    end_timestamp = None

    if search_request.start_date:
        try:
            start_timestamp = int(datetime.fromisoformat(search_request.start_date).timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date; expected an ISO 8601 datetime string")

    if search_request.end_date:
        try:
            end_timestamp = int(datetime.fromisoformat(search_request.end_date).timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date; expected an ISO 8601 datetime string")

    exact_conversation_id = parse_exact_conversation_reference(search_request.query)
    if exact_conversation_id:
        exact_page, exact_per_page = clamp_conversation_search_pagination(search_request.page, search_request.per_page)
        conversations = conversations_db.get_conversations_by_id_without_photos(
            uid,
            [exact_conversation_id],
            include_discarded=bool(search_request.include_discarded),
        )
        conversations = [conversation for conversation in conversations if not conversation.get('is_locked')]
        conversations = [
            conversation
            for conversation in conversations
            if conversation_matches_speaker(conversation, search_request.speaker_id)
            and conversation_matches_date_range(conversation, start_timestamp, end_timestamp)
        ]
        if exact_page != 1:
            conversations = []
        redact_conversations_for_list(conversations)
        return {
            'items': conversations[:exact_per_page],
            'total_pages': 1,
            'current_page': exact_page,
            'per_page': exact_per_page,
        }

    try:
        search_results = search_conversations(
            query=search_request.query,
            page=search_request.page,
            per_page=search_request.per_page,
            uid=uid,
            include_discarded=search_request.include_discarded,
            start_date=start_timestamp,
            end_date=end_timestamp,
            speaker_id=search_request.speaker_id,
        )
    except ConversationSearchUnavailableError:
        raise HTTPException(status_code=503, detail="Search temporarily unavailable")
    typesense_ids = [item.get('id') for item in search_results.get('items', []) if item.get('id')]
    effective_page = search_results.get('current_page', 1)
    effective_per_page = search_results.get('per_page', 10)
    # Spoken-word hits (optional transcript-chunk index) are merged on page 1 only so
    # Typesense pagination stays stable. Snippets still attach for every hydrated hit.
    # Over-fetch candidates on page 1 so lock/speaker/date filters can still fill per_page
    # without permanently dropping displaced Typesense hits that lost the merge race.
    transcript_ids: List[str] = []
    merge_cap = effective_per_page
    if effective_page == 1 and (search_request.query or '').strip():
        merge_cap = min(max(effective_per_page * 3, effective_per_page), 250)
        transcript_ids = search_transcript_conversation_ids(
            uid,
            search_request.query,
            limit=merge_cap,
            starts_at=start_timestamp,
            ends_at=end_timestamp,
            search_transcript_chunks=vector_db.search_transcript_chunks,
        )
    conversation_ids = merge_typesense_page_with_transcript_hits(
        typesense_ids,
        transcript_ids,
        page=effective_page,
        per_page=merge_cap,
    )
    conversations = conversations_db.get_conversations_by_id_without_photos(
        uid,
        conversation_ids,
        include_discarded=bool(search_request.include_discarded),
    )
    # Preserve merge order (transcript-first on page 1); Firestore fetch may reshuffle.
    by_id = {c.get('id'): c for c in conversations if c.get('id')}
    conversations = [by_id[cid] for cid in conversation_ids if cid in by_id]
    # Typesense filters locked hits, but the index can lag Firestore. Re-check after hydration
    # so search never leaks that a locked conversation matched a query.
    conversations = [conversation for conversation in conversations if not conversation.get('is_locked')]
    # Speaker filtering happens here, not in Typesense: the index has no transcript_segments field, so
    # asking Typesense for one 400'd and 500'd the request. The hydrated Firestore documents do carry
    # transcript_segments, so match against those.
    # Date filter also re-applies here: transcript-chunk hits can arrive with one-sided chunk
    # metadata gaps; keep them consistent with Typesense + exact-reference paths.
    conversations = [
        conversation
        for conversation in conversations
        if conversation_matches_speaker(conversation, search_request.speaker_id)
        and conversation_matches_date_range(conversation, start_timestamp, end_timestamp)
    ]
    # Attach grep-style transcript snippets (start/end for seek-to-moment) before list redaction
    # clears segments on locked rows.
    if (search_request.query or '').strip():
        conversations = attach_match_snippets_to_conversations(conversations, search_request.query)
    conversations = conversations[:effective_per_page]
    redact_conversations_for_list(conversations)
    search_results['items'] = conversations
    # Recompute total_pages from the effective (clamped) pagination the search actually ran with, not the
    # raw request: search_request.page/per_page are optional and unbounded, so a null/0/huge value here
    # would 500 (None + 1 / len(...) >= None). search_conversations returns clamped current_page/per_page.
    search_results['total_pages'] = effective_page + 1 if len(conversations) >= effective_per_page else effective_page
    return search_results


@router.get(
    "/v1/conversations/{conversation_id}/suggested-apps",
    response_model=ConversationSuggestedAppsResponse,
    tags=['conversations'],
)
def get_conversation_suggested_apps(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    from utils.apps import get_available_app_by_id_with_reviews, get_is_user_paid_app

    conversation_data = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation_data)

    # Get suggested app models with full data (similar to /v1/apps endpoint)
    suggested_apps = []
    for app_id in conversation.suggested_summarization_apps:
        app_data = get_available_app_by_id_with_reviews(app_id, uid)
        if app_data:
            app = App(**app_data)
            # Add user-specific data
            app.is_user_paid = get_is_user_paid_app(app.id, uid)

            # Add payment link with user reference
            if app.payment_link:
                app.payment_link = f'{app.payment_link}?client_reference_id=uid_{uid}'

            # Generate thumbnail URLs if thumbnails exist
            if app.thumbnails:
                from utils.other.storage import get_app_thumbnail_url

                app.thumbnail_urls = [get_app_thumbnail_url(thumbnail_id) for thumbnail_id in app.thumbnails]

            suggested_apps.append(app)

    return {"suggested_apps": [app.model_dump() for app in suggested_apps], "conversation_id": conversation_id}


@router.get(
    "/v1/conversations/{conversation_id}/analytics", response_model=ConversationAnalytics, tags=['conversations']
)
def get_conversation_analytics(conversation_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Per-speaker analytics for a conversation (issue #4481).

    Returns each speaker's talk time, word count, and words per minute, plus the
    conversation totals. Speakers are the account owner ("You"), identified people
    (resolved to their name), and any remaining diarization speakers.
    """
    conversation_data = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation_data)
    person_ids = conversation.get_person_ids()
    people = users_db.get_people_by_ids(uid, person_ids) if person_ids else []
    names = {p['id']: p.get('name', '') for p in people}
    return build_conversation_analytics(conversation, names)


@router.post(
    "/v1/conversations/{conversation_id}/test-prompt",
    response_model=ConversationTestPromptResponse,
    tags=['conversations'],
)
def test_prompt(
    conversation_id: str,
    request: TestPromptRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "test:prompt")),
):
    conversation_data = _get_valid_conversation_by_id(uid, conversation_id)
    conversation = deserialize_conversation(conversation_data)

    full_transcript = "\n".join([seg.text for seg in conversation.transcript_segments if seg.text])

    if not full_transcript:
        raise HTTPException(status_code=400, detail="Conversation has no text content to summarize.")

    # Pass language code from conversation to match app behavior
    try:
        summary = generate_summary_with_prompt(
            full_transcript, request.prompt, language_code=conversation.language or 'en'
        )
    except SummaryProviderError as exc:
        # The provider failed on its own account, so this is an upstream failure and not a fault
        # of the request: report it as one instead of as a 500 the client cannot act on.
        logger.warning("test-prompt summary failed upstream: conversation_id=%s", conversation_id)
        raise HTTPException(
            status_code=504 if exc.timed_out else 502,
            detail='summary_provider_timeout' if exc.timed_out else 'summary_provider_unavailable',
        ) from exc

    return {"summary": summary}


# *********************************************
# *********** MERGING conversations ***********
# *********************************************


@router.post('/v1/conversations/merge', response_model=MergeConversationsResponse, tags=['conversations'])
def merge_conversations(
    request: MergeConversationsRequest,
    background_tasks: BackgroundTasks,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "conversations:merge")),
):
    """
    Merge multiple conversations into a new conversation (async).

    Flow:
    1. Validates conversations (locked? completed?)
    2. Returns immediately with 200 OK
    3. Background task creates new merged conversation
    4. Background task deletes source conversations
    5. FCM notification sent on completion

    The merged conversation will have:
    - A new ID (source conversations are deleted)
    - Merged transcript segments with adjusted timestamps
    - Copied audio chunks
    - Regenerated title, summary, action items, memories via process_conversation()
    """
    from utils.conversations.merge_conversations import validate_merge_compatibility, perform_merge_async

    # Validate minimum number of conversations
    if len(request.conversation_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 conversations required to merge")

    # Fetch all conversations
    conversations = []
    for conv_id in request.conversation_ids:
        conv = conversations_db.get_conversation(uid, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail=f"Conversation {conv_id} not found")
        conversations.append(conv)

    # Validate merge compatibility (returns warning for large gaps but doesn't reject)
    is_valid, error_message, warning_message = validate_merge_compatibility(conversations)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Set all source conversations to 'merging' status so user knows they're being processed
    for conv_id in request.conversation_ids:
        lifecycle_service.begin_merge(uid, conv_id)

    # Start background merge task
    background_tasks.add_task(
        perform_merge_async,
        uid=uid,
        conversation_ids=request.conversation_ids,
        reprocess=request.reprocess,
    )

    return MergeConversationsResponse(
        status="merging",
        message="Merge started",
        warning=warning_message,
        conversation_ids=request.conversation_ids,
    )
