import os
import random
import re
import uuid
import logging
import asyncio
from datetime import timezone, timedelta, datetime
from collections.abc import Mapping
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, cast

from fastapi import HTTPException

import database._client as db_client_module
from database import redis_db
from database.auth import get_user_name
from utils.conversations.transcript_for_llm import (
    conversation_transcript_for_action_items,
    conversation_transcript_for_llm,
    conversation_transcripts_for_llm,
)
import database.conversations as conversations_db
import database.notifications as notification_db
import database.users as users_db
import database.tasks as tasks_db
import database.action_items as action_items_db
import database.folders as folders_db
import database.calendar_meetings as calendar_db
import database.screen_activity as screen_activity_db
from database.vector_db import (
    upsert_action_item_vectors_batch,
    delete_action_item_vectors_batch,
    find_similar_action_items,
)
from database.apps import record_app_usage, get_omi_personas_by_uid_db, get_app_by_id_db
from database.vector_db import upsert_vector2, update_vector_metadata, upsert_transcript_chunk_vectors
from utils.conversations.transcript_chunks import build_transcript_chunks
from models.app import App, UsageHistoryType
from models.memories import MemoryDB, Memory, MemoryCategory, SubjectAttribution
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.memory_contracts import L1MemoryArchiveClass, deterministic_contract_id
from models.workstream_association import AssociationEvidence
from models.product_memory import MemoryTier
from models.calendar_context import CalendarMeetingContext
from models.conversation import (
    AppResult,
    Conversation,
    CreateConversation,
    ExternalIntegrationCreateConversation,
)
from models.conversation_enums import ConversationSource, ConversationStatus, ExternalIntegrationConversationSource
from utils.conversations.factory import deserialize_conversation
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.subjects import infer_subject_from_segments
from utils.memory.memory_service import MemoryService
from testing.parity_pack_v0.live_capture import SurfaceParityCapture
from utils.memory.canonical_memory_adapter import extraction_memory_id
from utils.observability.fallback import record_fallback
from utils.product_telemetry import emit_product_event
from utils.task_intelligence.workstream_association import associate_canonical_evidence
from utils.subscription import is_trial_paywalled, should_defer_desktop_processing
from models.other import Person
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from utils.notifications import send_important_conversation_message
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.notification_message import NotificationMessage
from utils.apps import get_available_app_model_by_id, get_available_apps, update_persona_prompt
from utils.executors import llm_executor, postprocess_executor, submit_with_context
from utils.llm.conversation_processing import (
    get_transcript_structure,
    get_app_result,
    should_discard_conversation,
    get_suggested_apps_for_conversation,
    get_reprocess_transcript_structure,
    extract_action_items,
    get_conversation_notes,
)
from utils.llm.conversation_prompt_prefix import ConversationPromptPrefix, build_conversation_prompt_prefix
from utils.llm.gateway_error_contract import conversation_processing_http_exception
from utils.llm.conversation_folder import assign_conversation_to_folder
from utils.analytics import record_usage
from utils.llm.usage_tracker import track_usage, Features
from models.memory_contracts import MemoryExtractionError
from utils.llm.memories import (
    extract_canonical_l1_memory_candidates,
    extract_memories_from_text,
)
from utils.llm.temporal import date_in_tz
from utils.conversations.memory_extraction_telemetry import (
    PATH_CANONICAL,
    ConversationMemoryExtractionResult,
    emit_conversation_memories_extracted,
    source_for_conversation,
)
from utils.llm.external_integrations import summarize_experience_text
from utils.llm.goals import extract_and_update_goal_progress
from utils.llm.chat import (
    retrieve_metadata_from_text,
    retrieve_metadata_from_message,
    retrieve_metadata_fields_from_transcript,
    retrieve_metadata_fields_from_structured,
    obtain_emotional_message,
)
from utils.llm.external_integrations import get_message_structure
from utils.llm.clients import generate_embedding
from utils.notifications import send_notification
from utils.other.hume import (
    get_hume,
    HumeJobCallbackModel,
    HumeJobModelPredictionResponseModel,
    HumePredictionEmotionResponseModel,
)
from utils.retrieval.rag import retrieve_rag_conversation_context
from utils.webhooks import conversation_created_webhook
from utils.notifications import send_action_item_data_message
from utils.task_sync import auto_sync_action_items_batch
from utils.task_intelligence import conversation_capture
from utils.conversations.calendar_linking import (
    get_overlapping_calendar_event,
    write_conversation_link_to_calendar_event,
)
from utils.conversations.meeting_treatment import is_meeting_treatment_eligible
from utils.conversations.meeting_context import (
    MAX_SCREEN_CONTEXT_ROWS,
    MEETING_SEARCH_TOLERANCE_MINUTES,
    context_from_calendar_link,
    context_from_screen_activity,
    resolve_meeting_context,
    select_overlapping_meeting,
)
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import (
    compute_audio_files_fingerprint,
    enqueue_conversation_artifact_build,
    precache_conversation_audio,
)

logger = logging.getLogger(__name__)


def _calendar_auto_link_enabled() -> bool:
    return os.getenv('GOOGLE_CALENDAR_AUTO_LINK_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _flag_enabled(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {'1', 'true', 'yes', 'on'}


class SummaryPipelineMode(str, Enum):
    """The two configurations of the summary pipeline that are actually safe to run.

    Independent booleans for "notes v2" and "apps are opt-in" describe four states, but only
    two of them are coherent. The missing pair is what makes this an enum rather than two
    flags: legacy notes + opt-in apps would take the app summary away and fall back to the
    short first-party overview, which is worse than either whole configuration — a regression
    reachable purely by flag misconfiguration.
    """

    LEGACY_APP_PRIMARY = 'legacy_app_primary'
    NOTES_V2_APPS_OPT_IN = 'notes_v2_primary_apps_opt_in'


def summary_pipeline_mode() -> SummaryPipelineMode:
    """Resolve the pipeline mode once. `CONVERSATION_NOTES_V2_ENABLED` is the only switch.

    Rollback is turning notes v2 off, which restores the previous behaviour wholesale rather
    than leaving a half-migrated combination running.
    """
    if _flag_enabled('CONVERSATION_NOTES_V2_ENABLED'):
        return SummaryPipelineMode.NOTES_V2_APPS_OPT_IN
    return SummaryPipelineMode.LEGACY_APP_PRIMARY


def _conversation_notes_v2_enabled() -> bool:
    return summary_pipeline_mode() is SummaryPipelineMode.NOTES_V2_APPS_OPT_IN


def _conversation_apps_opt_in_only() -> bool:
    # Derived, never independently configured — see SummaryPipelineMode.
    return summary_pipeline_mode() is SummaryPipelineMode.NOTES_V2_APPS_OPT_IN


def _calendar_context_read_enabled() -> bool:
    return _flag_enabled('CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED')


def _ocr_meeting_context_enabled() -> bool:
    return _flag_enabled('CONVERSATION_OCR_CONTEXT_ENABLED')


def _stored_meeting_lookup_enabled() -> bool:
    # Defaults ON: this is a bounded, read-only query of the user's own stored
    # meetings, wrapped in try/except, and it is the only identity source that
    # does not require a Google OAuth grant or a Redis mapping that may never
    # have been written. The env var exists as a kill switch.
    return _flag_enabled('CONVERSATION_STORED_MEETING_CONTEXT_ENABLED', default=True)


def _dedup_excluded_conversation_ids(conversation: Any) -> set:
    """The conversation's own id plus any merge-source ids. Items from these
    conversations must never be dedup candidates: on reprocess/merge they are
    this conversation's previous items — the LLM would suppress re-extracting
    them, and the save step then deletes them, silently losing the tasks."""
    excluded = {getattr(conversation, 'id', None)}
    external_data = getattr(conversation, 'external_data', None) or {}
    merge_metadata = external_data.get('merge_metadata') or {}
    excluded.update(merge_metadata.get('source_conversation_ids') or [])
    excluded.discard(None)
    return excluded


def _fetch_dedup_candidates_for_query(uid: str, query: str, conversation: Any = None) -> List[Dict[str, Any]]:
    if not query.strip():
        return []

    excluded_conversation_ids = _dedup_excluded_conversation_ids(conversation) if conversation else set()

    try:
        similar = find_similar_action_items(uid, query, threshold=0.6, limit=10)
        if not similar:
            return []

        items = action_items_db.get_action_items_by_ids(uid, [s['action_item_id'] for s in similar])
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        eligible: List[Dict[str, Any]] = []
        for item in items:
            if item.get('completed', False):
                continue
            if item.get('conversation_id') in excluded_conversation_ids:
                continue
            last_active = item.get('updated_at') or item.get('created_at')
            if last_active is None or last_active < cutoff:
                continue
            eligible.append(item)

        logger.info(
            f'dedup_candidates uid={uid} similar={len(similar)} '
            f'eligible={len(eligible)} top_score={similar[0]["score"]}'
        )
        return eligible
    except Exception as e:
        logger.exception(f'_fetch_dedup_candidates failed uid={uid}: {e}')
        return []


def _fetch_dedup_candidates(uid: str, structured: Structured, conversation: Any = None) -> List[Dict[str, Any]]:
    """Fetch recently active open tasks related to a generated overview."""
    if not structured or not structured.overview:
        return []
    return _fetch_dedup_candidates_for_query(uid, structured.overview, conversation)


def _get_structured(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    people: Optional[List[Person]] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[Structured, bool]:
    try:
        task_intelligence_capture = conversation_capture.capture_enabled(uid)
        tz: Optional[str] = notification_db.get_user_time_zone(uid)
        tz_str: str = tz or ''
        user_language = users_db.get_user_language_preference(uid) or language_code
        prompt_conversation_id = (
            conversation_id
            or getattr(conversation, 'id', None)
            or getattr(conversation, 'processing_conversation_id', None)
            or str(uuid.uuid4())
        )

        # Extract calendar context from external_data
        direct_calendar_context = getattr(conversation, 'calendar_meeting_context', None)
        calendar_context: Optional[CalendarMeetingContext] = (
            direct_calendar_context
            if isinstance(direct_calendar_context, CalendarMeetingContext)
            else (
                CalendarMeetingContext(**direct_calendar_context)
                if isinstance(direct_calendar_context, dict) and direct_calendar_context
                else None
            )
        )
        if hasattr(conversation, 'external_data'):
            external_data_value = cast(Optional[Dict[str, Any]], getattr(conversation, 'external_data', None))
            if external_data_value:
                calendar_data = external_data_value.get('calendar_meeting_context')
                if calendar_data:
                    calendar_context = CalendarMeetingContext(**calendar_data)

        if (
            conversation.source == ConversationSource.workflow
            or conversation.source == ConversationSource.external_integration
        ):
            ext_conv = cast(ExternalIntegrationCreateConversation, conversation)
            started_at = cast(datetime, ext_conv.started_at)
            if ext_conv.text_source == ExternalIntegrationConversationSource.audio:
                if _conversation_notes_v2_enabled():
                    prefix = build_conversation_prompt_prefix(
                        conversation_id=prompt_conversation_id,
                        transcript=ext_conv.text,
                        started_at=started_at,
                        timezone_name=tz_str,
                        language_code=language_code,
                        calendar_context=calendar_context,
                    )
                    with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                        structured = get_conversation_notes(
                            prefix,
                            started_at=started_at,
                            language_code=language_code,
                            output_language_code=user_language,
                            tz=tz_str,
                            task_intelligence_capture=task_intelligence_capture,
                            existing_action_items=_fetch_dedup_candidates_for_query(uid, ext_conv.text, conversation),
                        )
                    return structured, False
                with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                    structured = get_transcript_structure(
                        ext_conv.text,
                        started_at,
                        language_code,
                        tz_str,
                        uid,
                        calendar_meeting_context=calendar_context,
                        output_language_code=user_language,
                    )
                with track_usage(uid, Features.CONVERSATION_ACTION_ITEMS):
                    structured.action_items = extract_action_items(
                        ext_conv.text,
                        started_at,
                        language_code,
                        tz_str,
                        existing_action_items=_fetch_dedup_candidates(uid, structured, conversation),
                        calendar_meeting_context=calendar_context,
                        output_language_code=user_language,
                        task_intelligence_capture=task_intelligence_capture,
                    )
                return structured, False

            if ext_conv.text_source == ExternalIntegrationConversationSource.message:
                with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                    structured = get_message_structure(
                        ext_conv.text,
                        started_at,
                        language_code,
                        tz_str,
                        ext_conv.text_source_spec,
                        output_language_code=user_language,
                    )
                return structured, False

            if ext_conv.text_source == ExternalIntegrationConversationSource.other:
                with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                    structured = summarize_experience_text(ext_conv.text, ext_conv.text_source_spec, tz=tz)
                return structured, False

            # not supported conversation source
            raise HTTPException(status_code=400, detail=f'Invalid conversation source: {ext_conv.text_source}')

        main_conv = cast(Union[Conversation, CreateConversation], conversation)
        transcript_text, action_items_transcript = conversation_transcripts_for_llm(uid, main_conv, people)

        # For re-processing, we don't discard, just re-structure.
        if force_process:
            conv_started_at = cast(datetime, main_conv.started_at)
            if _conversation_notes_v2_enabled():
                prefix = build_conversation_prompt_prefix(
                    conversation_id=prompt_conversation_id,
                    transcript=action_items_transcript,
                    started_at=conv_started_at,
                    timezone_name=tz_str,
                    language_code=language_code,
                    calendar_context=calendar_context,
                    photos=main_conv.photos,
                )
                with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                    structured = get_conversation_notes(
                        prefix,
                        started_at=conv_started_at,
                        language_code=language_code,
                        output_language_code=user_language,
                        tz=tz_str,
                        task_intelligence_capture=task_intelligence_capture,
                        existing_action_items=_fetch_dedup_candidates_for_query(uid, transcript_text, conversation),
                    )
                return structured, False
            # reprocess endpoint
            with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                structured = get_reprocess_transcript_structure(
                    transcript_text,
                    conv_started_at,
                    language_code,
                    tz_str,
                    photos=main_conv.photos,
                    output_language_code=user_language,
                )
            with track_usage(uid, Features.CONVERSATION_ACTION_ITEMS):
                structured.action_items = extract_action_items(
                    action_items_transcript,
                    conv_started_at,
                    language_code,
                    tz_str,
                    photos=main_conv.photos,
                    existing_action_items=_fetch_dedup_candidates(uid, structured, conversation),
                    output_language_code=user_language,
                    task_intelligence_capture=task_intelligence_capture,
                )
            return structured, False

        # Compute conversation duration for discard heuristics
        duration_seconds: Optional[float] = None
        if main_conv.started_at and main_conv.finished_at:
            duration_seconds = max(0, (main_conv.finished_at - main_conv.started_at).total_seconds())

        # Determine whether to discard the conversation based on its content (transcript and/or photos).
        with track_usage(uid, Features.CONVERSATION_DISCARD):
            discarded = should_discard_conversation(transcript_text, main_conv.photos, duration_seconds)
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        # If not discarded, proceed to generate the structured summary from transcript and/or photos.
        conv_started_at = cast(datetime, main_conv.started_at)
        if _conversation_notes_v2_enabled():
            prefix = build_conversation_prompt_prefix(
                conversation_id=prompt_conversation_id,
                transcript=action_items_transcript,
                started_at=conv_started_at,
                timezone_name=tz_str,
                language_code=language_code,
                calendar_context=calendar_context,
                photos=main_conv.photos,
            )
            with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                structured = get_conversation_notes(
                    prefix,
                    started_at=conv_started_at,
                    language_code=language_code,
                    output_language_code=user_language,
                    tz=tz_str,
                    task_intelligence_capture=task_intelligence_capture,
                    existing_action_items=_fetch_dedup_candidates_for_query(uid, transcript_text, conversation),
                )
            return structured, False
        with track_usage(uid, Features.CONVERSATION_STRUCTURE):
            structured = get_transcript_structure(
                transcript_text,
                conv_started_at,
                language_code,
                tz_str,
                uid,
                photos=main_conv.photos,
                calendar_meeting_context=calendar_context,
                output_language_code=user_language,
            )
        with track_usage(uid, Features.CONVERSATION_ACTION_ITEMS):
            structured.action_items = extract_action_items(
                action_items_transcript,
                conv_started_at,
                language_code,
                tz_str,
                photos=main_conv.photos,
                existing_action_items=_fetch_dedup_candidates(uid, structured, conversation),
                calendar_meeting_context=calendar_context,
                output_language_code=user_language,
                task_intelligence_capture=task_intelligence_capture,
            )
        return structured, False
    except Exception as e:
        raise conversation_processing_http_exception(e) from e


def _get_conversation_obj(
    uid: str,
    structured: Structured,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    conversation_id: Optional[str] = None,
) -> Conversation:
    discarded = structured.title == ''
    if isinstance(conversation, CreateConversation):
        conversation_dict = conversation.dict()
        # Store calendar context in external_data if available
        calendar_context = conversation_dict.pop('calendar_meeting_context', None)

        # Use started_at as created_at for imported conversations to preserve original timestamp
        created_at = conversation.started_at if conversation.started_at else datetime.now(timezone.utc)
        result: Conversation = Conversation(
            id=conversation_id or str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            created_at=created_at,
            discarded=discarded,
            **conversation_dict,
        )

        # Add calendar metadata to external_data
        if calendar_context:
            if not result.external_data:
                result.external_data = {}
            result.external_data['calendar_meeting_context'] = calendar_context

        if result.photos:
            conversations_db.store_conversation_photos(uid, result.id, result.photos)
        return result
    elif isinstance(conversation, ExternalIntegrationCreateConversation):
        create_conversation = conversation
        # Use started_at as created_at for external integrations to preserve original timestamp
        created_at = conversation.started_at if conversation.started_at else datetime.now(timezone.utc)
        result = Conversation(
            id=conversation_id or str(uuid.uuid4()),
            **conversation.dict(),
            created_at=created_at,
            structured=structured,
            discarded=discarded,
        )
        result.external_data = create_conversation.dict()
        result.app_id = create_conversation.app_id
        return result
    else:
        main_conv = conversation
        main_conv.structured = structured
        main_conv.discarded = discarded
        return main_conv


# Function to get conversation summary apps from Redis
def get_default_conversation_summarized_apps() -> List[App]:
    """
    Get conversation summary apps from Redis.
    Falls back to environment variable if Redis is empty.
    """
    default_apps: List[App] = []

    # Try to get from Redis first
    redis_app_ids = redis_db.get_conversation_summary_app_ids()

    if redis_app_ids:
        # Use apps from Redis
        for app_id in redis_app_ids:
            app_data = get_app_by_id_db(app_id.strip())
            if app_data:
                default_apps.append(App(**app_data))
    else:
        # Fallback to environment variable for backward compatibility
        env_app_ids = os.getenv(
            'CONVERSATION_SUMMARIZED_APP_IDS', 'summary_assistant,action_item_extractor,insight_analyzer'
        ).split(',')

        for app_id in env_app_ids:
            app_data = get_app_by_id_db(app_id.strip())
            if app_data:
                default_apps.append(App(**app_data))

    return default_apps


def _trigger_apps(
    uid: str,
    conversation: Conversation,
    is_reprocess: bool = False,
    app_id: Optional[str] = None,
    language_code: str = 'en',
    people: Optional[List[Person]] = None,
) -> None:
    # Get default apps for auto-selection
    opt_in_only = _conversation_apps_opt_in_only()
    default_apps = [] if opt_in_only else get_default_conversation_summarized_apps()
    default_apps_dict = {app.id: app for app in default_apps}

    # Also get user's installed apps (only used for preferred app lookup and reprocessing)
    apps: List[App] = get_available_apps(uid)
    conversation_apps = [app for app in apps if app.works_with_memories() and app.enabled]

    # Combined dict for looking up preferred apps or specific app_id requests
    all_apps_dict = {app.id: app for app in conversation_apps}
    all_apps_dict.update(default_apps_dict)

    # Combined list for suggestions: default apps + user's installed apps (no duplicates)
    all_suggestion_apps = list(all_apps_dict.values())

    app_to_run: Optional[App] = None

    # If a specific app_id is provided (for reprocessing), find and use it.
    if app_id:
        app_to_run = all_apps_dict.get(app_id)
        if app_to_run is None:
            candidate = get_available_app_model_by_id(app_id, uid)
            if candidate and candidate.works_with_memories():
                app_to_run = candidate
    else:
        # Check preferred app first — skip the suggestion LLM call if user has one
        preferred_app_id = redis_db.get_user_preferred_app(uid)
        if preferred_app_id and preferred_app_id in all_apps_dict:
            app_to_run = cast(App, all_apps_dict.get(preferred_app_id))
            logger.info(f"Using user's preferred app: {app_to_run.name} (id: {preferred_app_id})")
        elif preferred_app_id:
            # The set-preferred route admits any app `get_available_app_by_id`
            # can see (routers/users.py); it never requires the enabled-installed
            # slice this dict is built from. A default whose enablement never
            # landed (e.g. the template create flow's enable call failed) was
            # therefore accepted by the setter and silently ignored here (#10074).
            # Resolve through the setter's own authority instead of re-deciding.
            candidate = get_available_app_model_by_id(preferred_app_id, uid)
            if candidate and candidate.works_with_memories():
                app_to_run = candidate
                logger.info(
                    f"Using user's preferred app outside the installed slice: {candidate.name} (id: {preferred_app_id})"
                )
            else:
                logger.warning(
                    f"Preferred app {preferred_app_id} is set but unusable "
                    f"(missing={candidate is None}); falling back to suggestions {uid}"
                )
        if app_to_run is None and not opt_in_only:
            # Only run suggestion LLM call when no usable preferred app is set
            if not conversation.suggested_summarization_apps:
                with track_usage(uid, Features.CONVERSATION_APPS):
                    suggested_apps, _reasoning = get_suggested_apps_for_conversation(conversation, all_suggestion_apps)
                conversation.suggested_summarization_apps = suggested_apps
                logger.info(f"Generated suggested apps for conversation {conversation.id}: {suggested_apps}")

            if conversation.suggested_summarization_apps:
                first_suggested_app_id = conversation.suggested_summarization_apps[0]
                app_to_run = all_apps_dict.get(first_suggested_app_id)
                if app_to_run:
                    logger.info(f"Using first suggested app: {app_to_run.name}")
                else:
                    logger.warning(f"First suggested app '{first_suggested_app_id}' not found in apps.")
        elif app_to_run is None:
            logger.info('Summarization apps are opt-in only; skipping automatic app selection')

    filtered_apps: List[App] = [app_to_run] if app_to_run else []

    if not filtered_apps:
        logger.info(f"No summarization app selected for conversation {conversation.id} {uid}")

    # Clear existing app results
    conversation.apps_results = []

    def execute_app(app: App) -> None:
        with track_usage(uid, Features.CONVERSATION_APPS):
            transcript = conversation_transcript_for_llm(uid, conversation, people)
            prompt_prefix = None
            if _conversation_notes_v2_enabled() and conversation.started_at:
                prompt_prefix = build_conversation_prompt_prefix(
                    conversation_id=conversation.id,
                    transcript=conversation_transcript_for_action_items(uid, conversation, people),
                    started_at=conversation.started_at,
                    timezone_name=notification_db.get_user_time_zone(uid) or '',
                    language_code=language_code,
                    calendar_context=_stored_meeting_context(conversation),
                    photos=conversation.photos,
                )
            result = get_app_result(
                transcript,
                conversation.photos,
                app,
                language_code=language_code,
                prompt_prefix=prompt_prefix,
            ).strip()
        conversation.apps_results.append(AppResult(app_id=app.id, content=result))
        if not is_reprocess:
            record_app_usage(uid, app.id, UsageHistoryType.memory_created_prompt, conversation_id=conversation.id)

    futures = [submit_with_context(llm_executor, execute_app, app) for app in filtered_apps]
    for future in futures:
        try:
            future.result()
        except Exception as e:
            logger.error(f"Error executing app: {e}")


def _update_goal_progress(uid: str, conversation: Conversation) -> None:
    """Extract and update goal progress from conversation text."""
    try:
        # Idempotency: skip if this conversation was already processed for goals
        if not redis_db.try_acquire_conversation_goal_lock(uid, conversation.id):
            logger.info(f"[GOAL] Skipping already-processed conversation {conversation.id}")
            return

        # Get conversation text
        text = ""
        if conversation.structured and conversation.structured.overview:
            text = conversation.structured.overview
        elif conversation.transcript_segments:
            text = " ".join([s.text for s in conversation.transcript_segments[:20]])

        if not text or len(text) < 10:
            return

        # Use utility function to extract and update goal progress
        with track_usage(uid, Features.GOALS):
            extract_and_update_goal_progress(uid, text)
    except Exception as e:
        logger.error(f"[GOAL] Error updating progress: {e}")


def _parity_transcript_segments(conversation: Conversation) -> list[dict[str, Any]]:
    segments = getattr(conversation, "transcript_segments", None) or []
    return [
        {
            "start": segment.start,
            "end": segment.end,
            "speaker": segment.speaker,
            "text": (segment.text or "")[:8192],
        }
        for segment in segments[:1000]
    ]


def _parity_accepted_memories(memories: List[MemoryDB]) -> list[dict[str, Any]]:
    return [
        {
            "id": memory.id,
            "content": (memory.content or "")[:8192],
            "category": memory.category.value,
            "visibility": memory.visibility,
        }
        for memory in memories[:100]
    ]


def extract_memories(uid: str, conversation: Conversation) -> None:
    """Extract one conversation's memories through the selected memory system.

    Finalization workers use this public boundary while holding their durable
    lease. Keep the private helper below for existing in-module async callers.
    """
    source = source_for_conversation(conversation)
    parity_capture = SurfaceParityCapture.from_environ(
        principal_id=uid,
        session_id=conversation.id,
        surface="conversation_finalization",
        source=f"conversation_{source}",
        provider_lane="memory",
        route_or_model="memory-extraction",
        request={
            "conversation_source": str(source),
            "segment_count": len(getattr(conversation, "transcript_segments", None) or []),
            "locked": bool(getattr(conversation, "is_locked", False)),
        },
    )
    parity_capture.observe(
        "client",
        {"type": "conversation_transcript", "segments": _parity_transcript_segments(conversation)},
    )
    try:
        with track_usage(uid, Features.MEMORIES):
            if parity_capture.enabled:
                result = _extract_memories_inner(uid, conversation, parity_capture=parity_capture)
            else:
                result = _extract_memories_inner(uid, conversation)
        parity_capture.observe(
            "inbound",
            {"type": "memory_extraction_result", "count": result.count, "path": result.path},
        )
    finally:
        parity_capture.persist()
    # Product-analytics telemetry (Conversation Memories Extracted): at most one
    # analytics success per (uid, conversation) across retries — zero-extraction
    # (count == 0) and persistence exceptions emit nothing; the durable
    # per-conversation dedup (Redis SET NX EX) is inside emit_*_memories_extracted.
    if result is not None and result.count > 0:
        emit_conversation_memories_extracted(uid, conversation.id, result)


def _extract_memories(uid: str, conversation: Conversation) -> None:
    extract_memories(uid, conversation)


def _normalized_l1_subject_label(value: Optional[str]) -> str:
    return re.sub(r"[\W_]+", " ", (value or "").casefold()).strip()


def _source_scoped_l1_subject_id(*, source_id: str, kind: str, label: str) -> str:
    digest = deterministic_contract_id(
        "canonical-l1-source-scoped-subject",
        {
            "source_id": source_id,
            "kind": kind,
            "label": _normalized_l1_subject_label(label),
        },
    )
    return f"source:{digest[:24]}"


def _l1_subject_from_matched_segments(
    *,
    source_id: str,
    matched_segments: List[Any],
) -> Tuple[Optional[str], SubjectAttribution, str]:
    resolved_subjects: Set[Tuple[str, SubjectAttribution, str]] = set()
    for segment in matched_segments:
        if bool(getattr(segment, "is_user", False)):
            resolved_subjects.add(("user", SubjectAttribution.user, "user"))
            continue
        person_id = getattr(segment, "person_id", None)
        if person_id:
            resolved_subjects.add((f"person:{person_id}", SubjectAttribution.third_party, "person"))
            continue
        raw_speaker = str(getattr(segment, "speaker", "") or "").strip()
        speaker_id = getattr(segment, "speaker_id", None)
        speaker_label = raw_speaker or (f"speaker_{speaker_id}" if speaker_id is not None else "")
        if not speaker_label:
            return None, SubjectAttribution.unknown, "unknown"
        resolved_subjects.add(
            (
                _source_scoped_l1_subject_id(
                    source_id=source_id,
                    kind="speaker",
                    label=speaker_label,
                ),
                SubjectAttribution.third_party,
                "speaker",
            )
        )
    if len(resolved_subjects) == 1:
        return next(iter(resolved_subjects))
    return None, SubjectAttribution.unknown, "unknown"


def _l1_quote_matched_segments(evidence_quotes: List[str], segments: List[Any]) -> List[Any]:
    return [
        segment
        for segment in segments
        if any(
            f" {_normalized_l1_subject_label(quote)} "
            in f" {_normalized_l1_subject_label(str(getattr(segment, 'text', '') or ''))} "
            for quote in evidence_quotes
            if _normalized_l1_subject_label(quote)
        )
    ]


def _l1_candidate_subject(
    *,
    source_id: str,
    about: str,
    speaker_label: Optional[str],
    evidence_quotes: List[str],
    user_name: Optional[str],
    segments: List[Any],
) -> Tuple[Optional[str], SubjectAttribution, str]:
    """Resolve one L1 candidate without assigning the whole conversation's subject."""
    about_norm = _normalized_l1_subject_label(about)
    speaker_norm = _normalized_l1_subject_label(speaker_label)
    user_aliases = {"user", "the user", "primary user"}
    normalized_user_name = _normalized_l1_subject_label(user_name)
    if normalized_user_name:
        user_aliases.add(normalized_user_name)

    quote_matched_segments = _l1_quote_matched_segments(evidence_quotes, segments)
    matched_segments: List[Any] = []
    source_speaker_labels: Set[str] = set()
    for segment in segments:
        raw_speaker = getattr(segment, "speaker", None)
        speaker_id = getattr(segment, "speaker_id", None)
        labels = {
            _normalized_l1_subject_label(raw_speaker),
            _normalized_l1_subject_label(f"speaker_{speaker_id}") if speaker_id is not None else "",
            _normalized_l1_subject_label(f"ent_speaker_{speaker_id}") if speaker_id is not None else "",
        }
        labels.discard("")
        source_speaker_labels.update(labels)
        if speaker_norm and speaker_norm in labels:
            matched_segments.append(segment)
            continue
        if about_norm and any(f" {label} " in f" {about_norm} " for label in labels):
            matched_segments.append(segment)

    if about_norm in user_aliases:
        if quote_matched_segments:
            # Quote-bearing source segments outrank both model-authored
            # ``about`` and ``speaker_label`` fields. This applies even when
            # the model invents a user speaker label that happens to match a
            # different segment elsewhere in the conversation.
            return _l1_subject_from_matched_segments(
                source_id=source_id,
                matched_segments=quote_matched_segments,
            )
        if speaker_norm and matched_segments:
            # A known source speaker is more authoritative than a contradictory
            # model-authored about=user label.
            return _l1_subject_from_matched_segments(
                source_id=source_id,
                matched_segments=matched_segments,
            )
        return "user", SubjectAttribution.user, "user"

    about_names_model_speaker = bool(
        about_norm and speaker_norm and (about_norm == speaker_norm or f" {speaker_norm} " in f" {about_norm} ")
    )
    if quote_matched_segments and about_names_model_speaker:
        # Identified contacts are rendered into the extraction transcript by
        # name (for example ``Sarah:``), while the source segment retains the
        # durable ``person_id``. Bind that model-visible name back to the
        # uniquely grounded source speaker instead of degrading it to a
        # source-scoped entity.
        return _l1_subject_from_matched_segments(
            source_id=source_id,
            matched_segments=quote_matched_segments,
        )

    about_names_source_speaker = any(
        label == about_norm or f" {label} " in f" {about_norm} " for label in source_speaker_labels
    )
    about_is_source_speaker = (
        not about_norm
        or about_norm in {"unknown", "unclear", "uncertain"}
        or about_names_source_speaker
        or about_norm in {"speaker", "the speaker", "unidentified non primary speaker"}
    )
    if about_is_source_speaker:
        if quote_matched_segments:
            return _l1_subject_from_matched_segments(
                source_id=source_id,
                matched_segments=quote_matched_segments,
            )
        if matched_segments:
            return _l1_subject_from_matched_segments(
                source_id=source_id,
                matched_segments=matched_segments,
            )
        return None, SubjectAttribution.unknown, "unknown"

    if about_norm and about_norm not in {"unknown", "unclear", "uncertain"}:
        return (
            _source_scoped_l1_subject_id(source_id=source_id, kind="about", label=about),
            SubjectAttribution.third_party,
            "entity",
        )
    if speaker_norm:
        return (
            _source_scoped_l1_subject_id(source_id=source_id, kind="speaker", label=speaker_label or speaker_norm),
            SubjectAttribution.third_party,
            "speaker",
        )
    return None, SubjectAttribution.unknown, "unknown"


def _l1_candidate_sensitivity_labels(candidate: Any) -> List[str]:
    labels = [
        str(label).strip().lower() for label in (getattr(candidate, "risk_flags", []) or []) if str(label).strip()
    ]
    archive_class = getattr(candidate, "archive_class", L1MemoryArchiveClass.general)
    archive_class_value = getattr(archive_class, "value", archive_class)
    if archive_class_value == L1MemoryArchiveClass.sensitive.value:
        # Fail closed when the broad extractor marks an item sensitive without
        # naming a narrower restricted risk class.
        labels.append("secret")
    return list(dict.fromkeys(labels))


def _normalized_l1_evidence_quote(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold()).strip()


def _grounded_l1_evidence_quotes(evidence_quotes: List[str], segments: List[Any]) -> List[str]:
    """Return quotes only when each has one unambiguous authoritative source segment."""
    grounded: List[str] = []
    seen: Set[str] = set()
    for raw_quote in evidence_quotes:
        quote = raw_quote.strip()
        normalized_quote = _normalized_l1_evidence_quote(quote)
        matched_segments = [
            segment
            for segment in segments
            if normalized_quote
            and f" {normalized_quote} " in f" {_normalized_l1_evidence_quote(str(getattr(segment, 'text', '') or ''))} "
        ]
        if not normalized_quote or len(matched_segments) != 1:
            return []
        if normalized_quote in seen:
            continue
        seen.add(normalized_quote)
        grounded.append(quote)
    return grounded


def _canonical_quote_ref(
    *,
    quote: str,
    source_id: str,
    segments: List[Any],
) -> Dict[str, Any]:
    normalized_quote = _normalized_l1_evidence_quote(quote)
    matched_segments = [
        segment
        for segment in segments
        if f" {normalized_quote} " in f" {_normalized_l1_evidence_quote(str(getattr(segment, 'text', '') or ''))} "
    ]
    if len(matched_segments) != 1:
        raise RuntimeError("canonical conversation quote lost its unique source binding")
    segment = matched_segments[0]
    raw_speaker = getattr(segment, "speaker", None)
    speaker_id = getattr(segment, "speaker_id", None)
    authoritative_speaker = (
        str(raw_speaker).strip()
        if isinstance(raw_speaker, str) and raw_speaker.strip()
        else f"speaker_{speaker_id}" if speaker_id is not None else None
    )
    segment_id = getattr(segment, "id", None)
    return {
        "text": quote,
        "source_id": source_id,
        **({"segment_id": str(segment_id)} if segment_id else {}),
        **({"speaker_label": authoritative_speaker, "speaker_scope": "source-local"} if authoritative_speaker else {}),
    }


def _canonical_conversation_write_payload(
    memory: MemoryDB,
    *,
    source_id: str,
    evidence_quotes: List[str],
    subject_kind: str,
    sensitivity_labels: List[str],
    segments: List[Any],
) -> Dict[str, Any]:
    payload = memory.model_dump(mode="json")
    payload["sensitivity_labels"] = sensitivity_labels
    payload["subject_kind"] = subject_kind
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list) or len(raw_evidence) != 1 or not isinstance(raw_evidence[0], dict):
        raise RuntimeError("canonical conversation capture requires exactly one source evidence item")
    evidence = cast(Dict[str, Any], raw_evidence[0])
    evidence.update(
        {
            "quote_refs": [
                _canonical_quote_ref(
                    quote=quote,
                    source_id=source_id,
                    segments=segments,
                )
                for quote in evidence_quotes
            ],
        }
    )
    return payload


def _canonical_extraction_unavailable(
    conversation: Conversation, source: Any, exc: Exception
) -> ConversationMemoryExtractionResult:
    """The extractor never produced a batch, so this run has no verdict to apply.

    ``strict=True`` exists so a provider failure cannot be mistaken for "no
    memories" and submit the empty replacement that would retract the source's
    existing memories. Skipping the replacement achieves that on its own;
    raising additionally cancels the caller's finalization, which also drops
    that conversation's action items, goal progress, audio files and created
    webhook — an outcome a timed-out LLM call has no standing to decide.
    """
    logger.warning(
        "canonical memory extraction skipped replacement: extractor unavailable conversation=%s reason=%s",
        conversation.id,
        type(exc).__name__,
    )
    record_fallback(
        component='other',
        from_mode='canonical_memory_extraction',
        to_mode='replacement_skipped',
        reason='provider_5xx',
        outcome='degraded',
    )
    return ConversationMemoryExtractionResult(count=0, source=source, path=PATH_CANONICAL)


def _extract_memories_canonical(
    uid: str, conversation: Conversation, *, db_client: Any, parity_capture: SurfaceParityCapture | None = None
) -> ConversationMemoryExtractionResult:
    """Universal canonical extraction with one atomic source replacement."""
    source = source_for_conversation(conversation)
    memory_service = MemoryService(db_client=db_client)

    language = users_db.get_user_language_preference(uid)
    capture_candidates: List[Tuple[Memory, List[str], str, List[str], bool]] = []

    # Relative dates in delayed external content must resolve against capture
    # time, not the worker's current wall clock.  Keep this date grounding on
    # the universal extractor path as well as the retired legacy path.
    content_date = None
    if conversation.started_at is not None:
        try:
            content_date = date_in_tz(conversation.started_at, notification_db.get_user_time_zone(uid))
        except Exception as exc:
            logger.warning("canonical memory extraction content_date_failed uid=%s reason=%s", uid, exc)

    if conversation.source == ConversationSource.external_integration:
        ext_data = conversation.external_data or {}
        text_content = ext_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = ext_data.get('text_source', 'other')
            try:
                extracted_memories = extract_memories_from_text(
                    uid,
                    text_content,
                    text_source,
                    language=language,
                    content_date=content_date,
                    strict=True,
                )
            except MemoryExtractionError as exc:
                return _canonical_extraction_unavailable(conversation, source, exc)
            capture_candidates = [(memory, [], "unknown", [], False) for memory in extracted_memories]
    else:
        raw_user_name = get_user_name(uid)
        user_name = raw_user_name.strip() if isinstance(raw_user_name, str) and raw_user_name.strip() else "the user"
        prompt_prefix: Optional[ConversationPromptPrefix] = None
        if _conversation_notes_v2_enabled() and conversation.started_at:
            person_ids = conversation.get_person_ids()
            people_records = users_db.get_people_by_ids(uid, list(set(person_ids))) if person_ids else []
            prompt_people = [Person(**record) for record in people_records]
            calendar_context = _stored_meeting_context(conversation)
            prompt_prefix = build_conversation_prompt_prefix(
                conversation_id=conversation.id,
                transcript=conversation_transcript_for_action_items(uid, conversation, prompt_people),
                started_at=conversation.started_at,
                timezone_name=notification_db.get_user_time_zone(uid) or '',
                language_code=conversation.language or 'en',
                calendar_context=calendar_context,
                photos=conversation.photos,
            )
        try:
            extracted_candidates = extract_canonical_l1_memory_candidates(
                uid,
                conversation.id,
                conversation.transcript_segments,
                user_name=user_name,
                language=language,
                strict=True,
                prompt_prefix=prompt_prefix,
            )
        except MemoryExtractionError as exc:
            return _canonical_extraction_unavailable(conversation, source, exc)
        ungrounded_candidates = 0
        seen_candidates = 0
        for candidate in extracted_candidates:
            seen_candidates += 1
            evidence_quotes = _grounded_l1_evidence_quotes(
                candidate.evidence_quotes,
                conversation.transcript_segments,
            )
            if not evidence_quotes:
                # A quote that binds to no single segment is a verdict on this
                # candidate, not on the run. Dropping it keeps the capture fence
                # intact — nothing unbound is written — without discarding the
                # grounded siblings and the rest of conversation finalization.
                ungrounded_candidates += 1
                continue
            subject_entity_id, subject_attribution, subject_kind = _l1_candidate_subject(
                source_id=conversation.id,
                about=candidate.about,
                speaker_label=candidate.speaker_label,
                evidence_quotes=evidence_quotes,
                user_name=user_name,
                segments=conversation.transcript_segments,
            )
            capture_candidates.append(
                (
                    Memory(
                        content=candidate.content,
                        category=(
                            MemoryCategory.system
                            if subject_attribution == SubjectAttribution.user
                            else MemoryCategory.interesting
                        ),
                        visibility="private",
                        subject_entity_id=subject_entity_id,
                        subject_attribution=subject_attribution,
                    ),
                    evidence_quotes,
                    subject_kind,
                    _l1_candidate_sensitivity_labels(candidate),
                    True,
                )
            )
        if seen_candidates and not capture_candidates:
            # Every candidate failed grounding: the run itself is untrustworthy,
            # so it must not submit the empty replacement that would retract the
            # source's existing memories. Skipping the replacement is the whole
            # verdict — it leaves prior memories intact. Raising instead would
            # abort the caller's finalization and additionally drop that
            # conversation's action items, goal progress, audio files and
            # created webhook, which this extraction has no standing to decide.
            # Count what the loop actually yielded — the extractor's return
            # value is only known to be iterable, so its truthiness is not a
            # statement about how many candidates it holds.
            logger.warning(
                "canonical memory extraction skipped replacement: all %s candidates ungrounded conversation=%s",
                seen_candidates,
                conversation.id,
            )
            record_fallback(
                component='other',
                from_mode='canonical_memory_extraction',
                to_mode='replacement_skipped',
                reason='other',
                outcome='degraded',
            )
            return ConversationMemoryExtractionResult(count=0, source=source, path=PATH_CANONICAL)
        if ungrounded_candidates:
            logger.warning(
                "canonical memory extraction dropped %s of %s ungrounded candidates conversation=%s",
                ungrounded_candidates,
                seen_candidates,
                conversation.id,
            )
            record_fallback(
                component='other',
                from_mode='canonical_memory_extraction',
                to_mode='grounded_candidates_only',
                reason='other',
                outcome='degraded',
            )

    is_locked = conversation.is_locked
    parsed_memories: List[Tuple[MemoryDB, List[str], str, List[str]]] = []
    seen_norm: Set[Tuple[str, str]] = set()
    subject_entity_id, subject_attribution = infer_subject_from_segments(conversation.transcript_segments)
    # Keep the service boundary bounded even when a provider or test double
    # bypasses the structured extractor's output cap.
    from utils.llm.working_observations import MAX_WORKING_OBSERVATION_ITEMS

    for (
        memory,
        evidence_quotes,
        subject_kind,
        sensitivity_labels,
        has_candidate_subject,
    ) in capture_candidates:
        norm = ' '.join((memory.content or '').lower().split())
        candidate_subject_entity_id = memory.subject_entity_id if has_candidate_subject else subject_entity_id
        proposition_key = (norm, candidate_subject_entity_id or "")
        if not norm or proposition_key in seen_norm:
            continue
        seen_norm.add(proposition_key)
        if len(parsed_memories) >= MAX_WORKING_OBSERVATION_ITEMS:
            break

        memory_db_obj = MemoryDB.from_memory(
            memory,
            uid,
            conversation.id,
            False,
            source_id=conversation.id,
            source_type="conversation",
            source_signal="transcription",
            artifact_ref=_transcript_artifact_ref(conversation),
            extractor_id="canonical_l1_memory_extractor" if has_candidate_subject else "new_memories_extractor",
            extractor_version="v1",
            subject_entity_id=candidate_subject_entity_id,
            subject_attribution=memory.subject_attribution if has_candidate_subject else subject_attribution,
            client_device_id=getattr(conversation, "client_device_id", None),
        )
        memory_db_obj.is_locked = is_locked
        memory_db_obj.id = extraction_memory_id(
            uid=uid,
            source_id=conversation.id,
            content=memory_db_obj.content,
            subject_entity_id=candidate_subject_entity_id,
        )
        memory_db_obj.memory_tier = MemoryTier.short_term
        parsed_memories.append((memory_db_obj, evidence_quotes, subject_kind, sensitivity_labels))

    replacement_payloads = [
        _canonical_conversation_write_payload(
            memory_db_obj,
            source_id=conversation.id,
            evidence_quotes=evidence_quotes,
            subject_kind=subject_kind,
            sensitivity_labels=sensitivity_labels,
            segments=conversation.transcript_segments,
        )
        for (
            memory_db_obj,
            evidence_quotes,
            subject_kind,
            sensitivity_labels,
        ) in parsed_memories
    ]
    memory_service.replace_conversation_memories(
        uid,
        conversation.id,
        replacement_payloads,
    )
    if len(parsed_memories) == 0:
        logger.info(f"No canonical memories extracted for conversation {conversation.id}")
        return ConversationMemoryExtractionResult(count=0, source=source, path=PATH_CANONICAL)

    logger.info(f"Saving {len(parsed_memories)} canonical memories for conversation {conversation.id}")
    if parity_capture is not None:
        parity_capture.observe(
            "inbound",
            {
                "type": "accepted_memories",
                "memories": _parity_accepted_memories([memory for memory, *_ in parsed_memories]),
            },
        )

    if not is_locked:
        memory_refs = [
            EvidenceRef(
                kind=EvidenceKind.memory_item,
                id=cast(str, memory_db_obj.id),
                scope=EvidenceScope.canonical,
            )
            for memory_db_obj, _, _, _ in parsed_memories[:49]
        ]
        evidence_summary = '\n'.join(
            memory.content.strip() for memory, _, _, _ in parsed_memories if memory.content.strip()
        )[:2000]
        try:
            associate_canonical_evidence(
                uid,
                AssociationEvidence(
                    evidence_id=conversation.id,
                    summary=evidence_summary,
                    evidence_refs=[
                        EvidenceRef(
                            kind=EvidenceKind.conversation,
                            id=conversation.id,
                            scope=EvidenceScope.canonical,
                        ),
                        *memory_refs,
                    ],
                ),
                firestore_client=db_client,
            )
        except Exception:
            record_fallback(
                component='other',
                from_mode='canonical_memory_workflow_association',
                to_mode='memory_write_only',
                reason='other',
                outcome='degraded',
            )

    record_usage(uid, memories_created=len(parsed_memories))
    return ConversationMemoryExtractionResult(count=len(parsed_memories), source=source, path=PATH_CANONICAL)


def _extract_memories_inner(
    uid: str, conversation: Conversation, *, parity_capture: SurfaceParityCapture | None = None
) -> ConversationMemoryExtractionResult:
    db_client = getattr(db_client_module, 'db', None)
    memory_service = MemoryService(db_client=db_client)
    memory_service.ensure_canonical_mutation_ready(uid)
    return _extract_memories_canonical(uid, conversation, db_client=db_client, parity_capture=parity_capture)


def _transcript_artifact_ref(conversation: Conversation) -> Dict[str, Any]:
    segments = conversation.transcript_segments or []
    return {
        "kind": "transcript_segments",
        "conversation_id": conversation.id,
        "segment_ids": [segment.id for segment in segments if segment.id],
        "start": min((segment.start for segment in segments), default=None),
        "end": max((segment.end for segment in segments), default=None),
    }


def send_new_memories_notification(user_id: str, memories: List[MemoryDB]) -> None:
    memories_str = ", ".join([memory.content for memory in memories])
    message = f"New memories {memories_str}"
    ai_message = NotificationMessage(
        text=message,
        from_integration='false',
        type='text',
        notification_type='new_fact',
        navigate_to="/facts",
    )

    send_notification(user_id, "omi" + ' says', message, NotificationMessage.get_message_as_dict(ai_message))


def _save_action_items(uid: str, conversation: Conversation):
    """
    Save action items from a conversation to the dedicated action_items collection.
    This runs in addition to storing them in the conversation for backward compatibility.
    """
    if not conversation.structured or not conversation.structured.action_items:
        return

    is_locked = conversation.is_locked
    if conversation_capture.process_conversation_before_legacy(uid, conversation):
        emit_product_event(
            uid=uid,
            event='Task Extracted',
            properties={
                'task_count': len(conversation.structured.action_items),
                'conversation_id': conversation.id,
                'task_source': 'transcript',
                'persistence_path': 'canonical_candidate',
            },
        )
        return

    action_items_data: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for action_item in conversation.structured.action_items:
        action_item_data = {
            'description': action_item.description,
            'completed': action_item.completed,
            'created_at': action_item.created_at or now,
            'updated_at': action_item.updated_at or now,
            'due_at': action_item.due_at,
            'completed_at': action_item.completed_at,
            'conversation_id': conversation.id,
            'is_locked': is_locked,
            **conversation_capture.canonical_conversation_fields(action_item, conversation),
        }
        action_items_data.append(action_item_data)

    if action_items_data:
        # Delete existing action items and their vectors first (in case of reprocessing)
        old_items = action_items_db.get_action_items_by_conversation(uid, conversation.id)
        old_ids = [item['id'] for item in old_items]
        if old_ids:
            delete_action_item_vectors_batch(uid, old_ids)
        document_ids = conversation_capture.legacy_document_ids(
            uid,
            conversation.id,
            conversation.structured.action_items,
        )
        if document_ids is None:
            action_items_db.delete_action_items_for_conversation(uid, conversation.id)
        else:
            action_items_db.retire_action_items_for_conversation(
                uid,
                conversation.id,
                active_ids=document_ids,
                replacements=conversation_capture.legacy_replacement_map(
                    old_items,
                    conversation.structured.action_items,
                    document_ids,
                ),
            )
        # Save new action items
        action_item_ids = action_items_db.create_action_items_batch(
            uid,
            action_items_data,
            document_ids=document_ids,
        )
        logger.info(f"Saved {len(action_item_ids)} action items for conversation {conversation.id}")

        conversation_capture.reconcile_after_legacy(
            uid,
            conversation.id,
            conversation.structured.action_items,
            action_item_ids,
        )
        emit_product_event(
            uid=uid,
            event='Task Extracted',
            properties={
                'task_count': len(action_item_ids),
                'conversation_id': conversation.id,
                'task_source': 'transcript',
                'persistence_path': 'legacy_projection',
            },
        )

        # Send FCM data messages for action items with due dates
        for idx, action_item in enumerate(conversation.structured.action_items):
            if action_item.due_at and idx < len(action_item_ids):
                action_item_id = action_item_ids[idx]
                send_action_item_data_message(
                    user_id=uid,
                    action_item_id=action_item_id,
                    description=action_item.description,
                    due_at=action_item.due_at.isoformat(),
                )

        # Auto-sync to task integration — submit before vector ops so it always runs
        created_items = [{"id": aid, **data} for aid, data in zip(action_item_ids, action_items_data)]

        def _run_auto_sync():
            asyncio.run(auto_sync_action_items_batch(uid, created_items))

        submit_with_context(postprocess_executor, _run_auto_sync)

        upsert_action_item_vectors_batch(
            uid,
            [
                {'action_item_id': aid, 'description': data['description']}
                for aid, data in zip(action_item_ids, action_items_data)
            ],
        )


# Verbatim transcript-chunk indexing (ns_tchunks). Off by default: enables semantic
# retrieval over raw transcript text, which the summary-only conversation vectors miss.
TRANSCRIPT_CHUNK_INDEXING_ENABLED = os.getenv('TRANSCRIPT_CHUNK_INDEXING_ENABLED', 'false').lower() == 'true'


def save_transcript_chunk_vectors(uid: str, conversation: Conversation):
    segments: List[Any] = [s.dict() if hasattr(s, 'dict') else s for s in (conversation.transcript_segments or [])]
    chunks = build_transcript_chunks(
        cast(List[Dict[str, Any]], segments), conversation.started_at or conversation.created_at
    )
    if chunks:
        upsert_transcript_chunk_vectors(uid, conversation.id, chunks)


def save_structured_vector(uid: str, conversation: Conversation, update_only: bool = False) -> None:
    vector = generate_embedding(str(conversation.structured)) if not update_only else None
    tz = notification_db.get_user_time_zone(uid) or ''

    metadata: Dict[str, Any] = {}

    # Extract metadata based on conversation source
    if conversation.source == ConversationSource.external_integration:
        ext_data: Dict[str, Any] = conversation.external_data or {}
        text_source = ext_data.get('text_source')
        text_content = ext_data.get('text')
        if text_content and len(text_content) > 0 and text_content and len(text_content) > 0:
            text_source_spec = ext_data.get('text_source_spec') or ''
            if text_source == ExternalIntegrationConversationSource.message.value:
                metadata = retrieve_metadata_from_message(
                    uid, conversation.created_at, text_content, tz, text_source_spec
                )
            elif text_source == ExternalIntegrationConversationSource.other.value:
                metadata = retrieve_metadata_from_text(uid, conversation.created_at, text_content, tz, text_source_spec)
    else:
        if _conversation_notes_v2_enabled():
            metadata = retrieve_metadata_fields_from_structured(
                uid, conversation.created_at, conversation.structured, tz
            )
        else:
            # Legacy path extracts filters from the raw transcript and photos.
            segments: List[Dict[str, Any]] = [t.dict() for t in conversation.transcript_segments]
            metadata = retrieve_metadata_fields_from_transcript(
                uid, conversation.created_at, segments, tz, photos=conversation.photos
            )

    metadata['created_at'] = int(conversation.created_at.timestamp())

    if not update_only:
        logger.info('save_structured_vector creating vector')
        upsert_vector2(uid, conversation.id, cast(List[float], vector), metadata)
    else:
        logger.info('save_structured_vector updating metadata')
        update_vector_metadata(uid, conversation.id, metadata)


def _update_personas_async(uid: str):  # type: ignore[reportUnusedFunction]  # referenced in tests
    logger.info(f"[PERSONAS] Starting persona updates in background thread for uid={uid}")
    personas = get_omi_personas_by_uid_db(uid)
    if personas:

        async def _batch():
            await asyncio.gather(*[update_persona_prompt(persona) for persona in personas])

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_batch())
        finally:
            loop.close()
        logger.info(f"[PERSONAS] Finished persona updates in background thread for uid={uid}")


def _build_deferred_structured(
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
) -> Structured:
    """A cheap, no-LLM placeholder Structured for a lazily-deferred conversation. The title is
    the first few words of the transcript so the conversation list stays usable until the user
    opens it (which triggers the real enrichment). A non-empty title is required — an empty one
    marks the conversation discarded in `_get_conversation_obj`."""
    text = ''
    for seg in list(getattr(conversation, 'transcript_segments', None) or []):
        seg_text = (getattr(seg, 'text', '') or '').strip()
        if seg_text:
            text = seg_text
            break
    words = text.split()
    title = ' '.join(words[:8]).strip() if words else ''
    return Structured(title=title or 'Recording')


def _store_deferred_conversation(
    uid: str, conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]
) -> Conversation:
    """Persist a desktop conversation with a cheap (no-LLM) title and `deferred=True`, skipping
    all enrichment. Mirrors the tail of process_conversation's persistence (cheap structured →
    `_get_conversation_obj` → upsert) without any LLM / Pinecone / app work. The enrichment runs
    later via the lazy trigger in `get_conversation_by_id`."""
    is_initial_creation = isinstance(conversation, (CreateConversation, ExternalIntegrationCreateConversation))
    structured = _build_deferred_structured(conversation)
    conversation = _get_conversation_obj(uid, structured, conversation)
    conversation.deferred = True
    # `processing` (not completed) is the user-facing "awaiting enrichment" state. Unlike the
    # `deferred` flag it survives the desktop's local conversation cache, so the client shows a
    # processing indicator and re-fetches on open to trigger enrichment. The lazy enrich sets it
    # back to `completed`.
    conversation.status = ConversationStatus.processing
    if is_initial_creation:
        persisted = lifecycle_service.create_processing_conversation(uid, conversation.dict(), idempotent=True)
    else:
        persisted = lifecycle_service.persist_processed_conversation(uid, conversation.dict())
    if not persisted:
        logger.info('lazy: deferred conversation creation fenced uid=%s conv=%s', uid, conversation.id)
        return conversation
    logger.info("lazy: stored deferred desktop conversation uid=%s conv=%s", uid, conversation.id)
    return conversation


def _stored_meeting_context(conversation: Any) -> Optional[CalendarMeetingContext]:
    direct = getattr(conversation, 'calendar_meeting_context', None)
    if isinstance(direct, CalendarMeetingContext):
        return direct
    if isinstance(direct, dict) and direct:
        return CalendarMeetingContext(**direct)
    raw_external_data = getattr(conversation, 'external_data', None)
    external_data = raw_external_data if isinstance(raw_external_data, dict) else {}
    raw = external_data.get('calendar_meeting_context')
    if isinstance(raw, CalendarMeetingContext):
        return raw
    if isinstance(raw, dict) and raw:
        return CalendarMeetingContext(**raw)
    return None


def _store_meeting_context(conversation: Any, context: CalendarMeetingContext) -> None:
    if isinstance(conversation, CreateConversation):
        conversation.calendar_meeting_context = context
        return
    external_data = dict(getattr(conversation, 'external_data', None) or {})
    external_data['calendar_meeting_context'] = context.model_dump(mode='json')
    conversation.external_data = external_data


def _meeting_context_from_redis_mapping(uid: str, conversation: Any) -> Optional[CalendarMeetingContext]:
    """Exact conversation->meeting association, when one was recorded.

    `redis_db.set_conversation_meeting_id` is written in exactly one place
    (`routers/listen/conversations.py`, at desktop conversation creation) and only
    when a stored meeting already overlaps that instant, so this is frequently
    absent. It is an optimization, never the only path.
    """
    conversation_id = getattr(conversation, 'id', None)
    if not isinstance(conversation, Conversation) or not conversation_id:
        return None
    try:
        meeting_id = redis_db.get_conversation_meeting_id(conversation_id)
        if not meeting_id:
            return None
        meeting_data = calendar_db.get_meeting(uid, meeting_id)
        if not meeting_data:
            return None
        parsed = CalendarMeetingContext.from_records([meeting_data])
        return parsed[0] if parsed else None
    except Exception as exc:
        logger.error('Error retrieving mapped meeting context for conversation %s: %s', conversation_id, exc)
        return None


def _meeting_context_from_time_overlap(
    uid: str, started_at: Optional[datetime], finished_at: Optional[datetime]
) -> Optional[CalendarMeetingContext]:
    """Time-overlap lookup against the user's stored meetings.

    Independent of the Redis mapping and of any OAuth grant: it reads the same
    `users/{uid}/meetings` collection that `POST /v1/calendar/meetings` writes.
    """
    if started_at is None or finished_at is None:
        return None
    try:
        tolerance = timedelta(minutes=MEETING_SEARCH_TOLERANCE_MINUTES)
        records = calendar_db.get_meetings_in_time_range(uid, started_at - tolerance, finished_at + tolerance)
        return select_overlapping_meeting(records, started_at=started_at, finished_at=finished_at)
    except Exception as exc:
        logger.error('Error reading stored meetings by time range for uid %s: %s', uid, exc)
        return None


def _is_desktop_meeting_role(conversation: Any) -> bool:
    """Whether the finalization-time meeting policy is the authority for this conversation.

    Only desktop conversations opened in the meeting role are covered by
    `is_meeting_treatment_eligible`; every other source keeps its prior enrichment behaviour.
    """
    source = getattr(conversation, 'source', None)
    if getattr(source, 'value', source) != 'desktop':
        return False
    external_data = getattr(conversation, 'external_data', None) or {}
    if not isinstance(external_data, Mapping):
        return False
    return external_data.get('conversation_role') == 'meeting'


def _enrich_meeting_context(uid: str, conversation: Any) -> None:
    """Read identity context before summarization without mutating calendar providers.

    Sources, best first — each merges only the participants the better sources did
    not already supply, and any failure degrades to the next source rather than
    failing the conversation:
      1. stored calendar-backed meeting (exact Redis mapping, else time overlap)
      2. `calendar_meeting_context` sent directly on the create request
      3. Google Calendar event overlapping the conversation window (read-only)
      4. stored on-device screen-derived meeting identity
      5. conferencing-window OCR already synced to the server (legacy fallback)
    """
    started_at = getattr(conversation, 'started_at', None)
    finished_at = getattr(conversation, 'finished_at', None)
    has_window = bool(started_at and finished_at)

    # conversation_role is open-time identity, not the treatment decision (#11832). A short or
    # mostly-silent call still opens as a meeting, so gating enrichment on the role alone would
    # spend a Google Calendar read and a screen-activity query on conversations that the
    # authoritative finalization policy has already ruled out. Defer to that policy where it
    # applies — desktop meeting-role conversations — and leave every other source untouched.
    if _is_desktop_meeting_role(conversation) and not is_meeting_treatment_eligible(conversation):
        logger.info(
            'Skipping meeting-context enrichment for conversation %s: not meeting-treatment eligible',
            getattr(conversation, 'id', None),
        )
        return

    def _stored() -> Optional[CalendarMeetingContext]:
        mapped = _meeting_context_from_redis_mapping(uid, conversation)
        if mapped is not None:
            return mapped
        return _meeting_context_from_time_overlap(uid, started_at, finished_at)

    def _calendar() -> Optional[CalendarMeetingContext]:
        linked = asyncio.run(get_overlapping_calendar_event(uid, started_at, finished_at))
        return context_from_calendar_link(linked) if linked else None

    def _screen() -> Optional[CalendarMeetingContext]:
        rows = screen_activity_db.get_screen_activity(
            uid,
            start_date=started_at,
            end_date=finished_at,
            limit=MAX_SCREEN_CONTEXT_ROWS,
        )
        return context_from_screen_activity(rows, started_at=started_at, finished_at=finished_at)

    context = resolve_meeting_context(
        direct=_stored_meeting_context(conversation),
        stored=_stored if _stored_meeting_lookup_enabled() else None,
        calendar=_calendar if has_window and _calendar_context_read_enabled() else None,
        screen=_screen if has_window and _ocr_meeting_context_enabled() else None,
        on_error=lambda source, exc: logger.error(
            'Error reading %s meeting context before summarization: %s', source, exc
        ),
    )
    if context:
        _store_meeting_context(conversation, context)


def process_conversation(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    is_reprocess: bool = False,
    app_id: Optional[str] = None,
    persistence_observer: Callable[[bool], None] | None = None,
    defer_memory_extraction: bool = False,
    defer_derived_effects: bool = False,
    derived_effects_observer: Callable[[Callable[[], None]], None] | None = None,
) -> Conversation:
    def report_persistence(current: bool) -> None:
        if persistence_observer is not None:
            persistence_observer(current)

    is_initial_creation = isinstance(conversation, (CreateConversation, ExternalIntegrationCreateConversation))
    # Trial paywall: skip ALL post-processing (summaries, memories, action
    # items, embeddings, app integrations) for paywalled desktop users.
    # Without this, any segments that did get through before the trial gate
    # (e.g. buffered transcripts, retroactive `/v1/conversations` create) still
    # trigger expensive LLM + Pinecone work.
    #
    # `conversation.source` carries the originating client (desktop / omi / etc).
    # Non-desktop sources flow through untouched — paywall is desktop-only.
    if (
        hasattr(conversation, 'source')
        and conversation.source == ConversationSource.desktop
        and is_trial_paywalled(uid, 'macos')
    ):
        logger.info(
            "trial paywall: skipping post-processing for uid=%s conv=%s source=desktop",
            uid,
            getattr(conversation, 'id', '?'),
        )
        # Return the conversation as-is with no LLM work performed. If it has
        # a status field, mark it processed so the client doesn't show a stuck
        # "processing" state forever.
        if isinstance(conversation, Conversation):
            try:
                conversation.status = ConversationStatus.completed
            except Exception:
                pass
        report_persistence(False)
        return cast(Conversation, conversation)

    # Lazy desktop processing (freemium cost cut): desktop users without a desktop-entitled
    # paid plan (basic / Neo) get ONLY the raw transcript on capture. The expensive LLM
    # enrichment (summary, action items, memories, embeddings, app results) is deferred until
    # they first OPEN the conversation (get_conversation_by_id reprocesses it with
    # force_process=True). Paid desktop plans (Operator / Architect), BYOK users, and all
    # non-desktop sources are processed normally here. force_process / is_reprocess — the lazy
    # trigger and manual reprocess — bypass this so the enrichment actually runs.
    if (
        not force_process
        and not is_reprocess
        and hasattr(conversation, 'source')
        and conversation.source == ConversationSource.desktop
        and should_defer_desktop_processing(uid)
    ):
        deferred = _store_deferred_conversation(uid, conversation)
        report_persistence(False)
        return deferred

    _enrich_meeting_context(uid, conversation)

    person_ids = conversation.get_person_ids()
    people: List[Person] = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    generated_conversation_id = (
        str(uuid.uuid4())
        if isinstance(conversation, (CreateConversation, ExternalIntegrationCreateConversation))
        else None
    )
    structured, discarded = _get_structured(
        uid,
        language_code,
        conversation,
        force_process,
        people=people,
        conversation_id=generated_conversation_id,
    )
    conversation = _get_conversation_obj(uid, structured, conversation, conversation_id=generated_conversation_id)

    # Persist the completed generation before it can trigger any derived work.
    # A discard or replacement that wins this transaction must not create
    # integrations, vectors, memories, action items, audio artifacts, folders,
    # calendar links, usage, or webhooks from a stale in-memory snapshot.
    conversation.status = ConversationStatus.completed
    if is_initial_creation:
        persisted = lifecycle_service.create_completed_conversation(uid, conversation.dict(), idempotent=True)
    else:
        persisted = lifecycle_service.persist_processed_conversation(uid, conversation.dict())
    report_persistence(persisted)
    if not persisted:
        logger.info(
            'processing result fenced before completion side effects uid=%s conversation=%s', uid, conversation.id
        )
        return conversation

    # Wrap every post-persistence derived effect so the durable finalizer can
    # defer the bundle until it transactionally claims ownership (#10468 r5).
    def _emit_derived_effects() -> None:
        # Calendar auto-linking calls and mutates a user's Google Calendar during generic
        # conversation processing. Keep it opt-in so normal sync/reprocess jobs do not
        # fan out provider traffic for every connected user.
        if (
            _calendar_auto_link_enabled()
            and not discarded
            and conversation.started_at
            and conversation.finished_at
            and conversation.calendar_event is None
        ):
            try:
                calendar_event = asyncio.run(
                    get_overlapping_calendar_event(
                        uid,
                        conversation.started_at,
                        conversation.finished_at,
                    )
                )
                if calendar_event:
                    conversation.calendar_event = calendar_event
                    asyncio.run(
                        write_conversation_link_to_calendar_event(uid, calendar_event.event_id, conversation.id)
                    )
                    conversations_db.update_conversation(
                        uid,
                        conversation.id,
                        {'calendar_event': calendar_event.model_dump(mode='json')},
                    )
            except Exception as e:
                logger.error(f"Error during calendar event linking: {e}")
                pass

        # AI-based folder assignment
        assigned_folder_id = None
        if not discarded and not is_reprocess and not conversation.folder_id:
            try:
                # Get user's folders
                user_folders = folders_db.get_folders(uid)
                if not user_folders:
                    user_folders = folders_db.initialize_system_folders(uid)

                if user_folders and conversation.structured:
                    cat = conversation.structured.category.value if conversation.structured.category else 'other'
                    with track_usage(uid, Features.CONVERSATION_FOLDER):
                        folder_id, confidence, reasoning = assign_conversation_to_folder(
                            title=conversation.structured.title or '',
                            overview=conversation.structured.overview or '',
                            category=cat,
                            user_folders=user_folders,
                            category_folder_id=folders_db.resolve_category_folder_id(cat, user_folders),
                        )
                    if folder_id:
                        conversation.folder_id = folder_id
                        assigned_folder_id = folder_id
                        conversations_db.update_conversation(uid, conversation.id, {'folder_id': folder_id})
                        logger.info(
                            f"AI assigned conversation {conversation.id} to folder {folder_id} (confidence: {confidence:.2f}): {reasoning}"
                        )
            except Exception as e:
                logger.error(f"Error during folder assignment for conversation {conversation.id}: {e}")

        if not discarded:
            # Analytics tracking
            insights_gained = 0
            if conversation.structured:
                # Count sentences with more than 5 words from title and overview
                for text in [conversation.structured.title, conversation.structured.overview]:
                    if text:
                        sentences = re.split(r'[.!?]+', text)
                        for sentence in sentences:
                            if len(sentence.split()) > 5:
                                insights_gained += 1

                # Count number of action items and events
                insights_gained += len(conversation.structured.action_items)
                insights_gained += len(conversation.structured.events)

            # Count sentences with more than 5 words from app results
            for app_result in conversation.apps_results:
                if app_result.content:
                    sentences = re.split(r'[.!?]+', app_result.content)
                    for sentence in sentences:
                        if len(sentence.split()) > 5:
                            insights_gained += 1

            if insights_gained > 0:
                record_usage(uid, insights_gained=insights_gained)

            _trigger_apps(
                uid, conversation, is_reprocess=is_reprocess, app_id=app_id, language_code=language_code, people=people
            )
            # _trigger_apps only mutates the in-memory conversation and the durable write above already
            # happened, so persist its output the same way the calendar_event/folder_id/audio_files
            # write-backs do. Otherwise the app summary the LLM just produced is discarded.
            if (
                _conversation_apps_opt_in_only()
                or conversation.apps_results
                or conversation.suggested_summarization_apps
            ):
                app_updates = {
                    'apps_results': [result.dict() for result in conversation.apps_results],
                    'suggested_summarization_apps': conversation.suggested_summarization_apps,
                }
                conversations_db.update_conversation(uid, conversation.id, app_updates)
            if not is_reprocess:
                submit_with_context(postprocess_executor, save_structured_vector, uid, conversation)
                if TRANSCRIPT_CHUNK_INDEXING_ENABLED:
                    submit_with_context(postprocess_executor, save_transcript_chunk_vectors, uid, conversation)
            if not defer_memory_extraction:
                # Canonical source replacement is universal and intentionally
                # fail-closed. Do not hide a retryable apply/store failure in an
                # unobserved future while reporting finalization as successful.
                _extract_memories(uid, conversation)
            submit_with_context(postprocess_executor, _save_action_items, uid, conversation)
            submit_with_context(postprocess_executor, _update_goal_progress, uid, conversation)

        # Create audio files from chunks if private cloud sync was enabled
        if not is_reprocess and conversation.private_cloud_sync_enabled:
            try:
                audio_files = conversations_db.create_audio_files_from_chunks(uid, conversation.id)
                if audio_files:
                    conversation.audio_files = audio_files
                    files_payload = [af.dict() for af in audio_files]
                    conversations_db.update_conversation(uid, conversation.id, {'audio_files': files_payload})
                    # Pre-cache audio files in background
                    precache_conversation_audio(uid, conversation.id, files_payload)
                    # Build the conversation-level playback artifact (dense MP3 + spans)
                    if is_audio_merge_dispatch_enabled():
                        enqueue_conversation_artifact_build(
                            uid,
                            conversation.id,
                            compute_audio_files_fingerprint(files_payload),
                            caller='process_conversation',
                        )
            except Exception as e:
                logger.error(f"Error creating audio files: {e}")

        # Update folder conversation count after conversation is saved
        if assigned_folder_id:
            folders_db.update_folder_conversation_count(uid, assigned_folder_id)

        if not is_reprocess:

            def _run_webhook():
                asyncio.run(conversation_created_webhook(uid, conversation))

            submit_with_context(postprocess_executor, _run_webhook)

    if defer_derived_effects:
        if derived_effects_observer is not None:
            derived_effects_observer(_emit_derived_effects)
        return conversation
    _emit_derived_effects()
    logger.info(f'process_conversation completed conversation.id= {conversation.id}')
    return conversation


def _send_important_conversation_notification_if_needed(uid: str, conversation: Conversation) -> None:  # type: ignore[reportUnusedFunction]  # reserved for re-enablement
    """
    Send notification for long conversations (>30 minutes) that just completed.
    Only sends once per conversation using Redis deduplication.
    """

    # Skip if conversation is discarded
    if conversation.discarded:
        return

    # Check if we have valid timestamps to compute duration
    if not conversation.started_at or not conversation.finished_at:
        logger.error(f"Cannot compute duration for conversation {conversation.id}: missing timestamps")
        return

    # Calculate duration in seconds
    duration_seconds = (conversation.finished_at - conversation.started_at).total_seconds()

    # Only notify for conversations longer than 30 minutes (1800 seconds)
    if duration_seconds < 1800:
        return

    # Check if notification was already sent for this conversation
    if redis_db.has_important_conversation_notification_been_sent(uid, conversation.id):
        logger.info(f"Important conversation notification already sent for {conversation.id}")
        return

    # Mark as sent before sending to prevent duplicates
    redis_db.set_important_conversation_notification_sent(uid, conversation.id)

    # Send the notification
    logger.info(
        f"Sending important conversation notification for {conversation.id} (duration: {duration_seconds/60:.1f} mins)"
    )
    send_important_conversation_message(uid, conversation.id)


def process_user_emotion(uid: str, language_code: str, conversation: Conversation, urls: List[str]) -> None:
    logger.info(f'process_user_emotion conversation.id= {conversation.id}')

    # save task
    now = datetime.now()
    task = Task(
        id=str(uuid.uuid4()),
        action=TaskAction.HUME_MERSURE_USER_EXPRESSION,
        user_uid=uid,
        memory_id=conversation.id,
        created_at=now,
        status=TaskStatus.PROCESSING,
    )
    tasks_db.create(task.dict())

    # emotion
    ok = get_hume().request_user_expression_mersurement(urls)
    if "error" in ok:
        err = ok["error"]
        logger.error(err)
        return
    job = ok["result"]
    request_id = job.id
    if not request_id or len(request_id) == 0:
        logger.info(f"Can not request users feeling. uid: {uid}")
        return

    # update task
    task.request_id = request_id
    task.updated_at = datetime.now()
    tasks_db.update(task.id, task.dict())

    return


def process_user_expression_measurement_callback(
    provider: str, request_id: str, callback: HumeJobCallbackModel
) -> None:
    support_providers = [TaskActionProvider.HUME]
    if provider not in support_providers:
        logger.info(f"Provider is not supported. {provider}")
        return

    # Get task
    task_action = ""
    if provider == TaskActionProvider.HUME:
        task_action = TaskAction.HUME_MERSURE_USER_EXPRESSION
    if len(task_action) == 0:
        logger.info("Task action is empty")
        return

    task_data = tasks_db.get_task_by_action_request(task_action, request_id)
    if task_data is None:
        logger.warning(f"Task not found. Action: {task_action}, Request ID: {request_id}")
        return

    task = Task(**task_data)

    # Update
    task_status = task.status
    if callback.status == "COMPLETED":
        task_status = TaskStatus.DONE
    elif callback.status == "FAILED":
        task_status = TaskStatus.ERROR
    else:
        logger.info(f"Not support status {callback.status}")
        return

    # Not changed
    if task_status == task.status:
        logger.info("Task status are synced")
        return

    task.status = task_status
    task.updated_at = datetime.now()
    tasks_db.update(task.id, task.dict())

    # done or not
    if task.status != TaskStatus.DONE:
        logger.info(f"Task is not done yet. Uid: {task.user_uid}, task_id: {task.id}, status: {task.status}")
        return

    uid = cast(str, task.user_uid)
    memory_id = cast(str, task.memory_id)

    # Save predictions
    if len(callback.predictions) > 0:
        conversations_db.store_model_emotion_predictions_result(uid, memory_id, provider, callback.predictions)

    # Conversation
    conversation_data = conversations_db.get_conversation(uid, memory_id)
    if conversation_data is None:
        logger.warning(f"Conversation is not found. Uid: {uid}. Conversation: {memory_id}")
        return

    conversation = deserialize_conversation(conversation_data)

    # Get prediction
    predictions = callback.predictions
    logger.info(predictions)
    if len(predictions) == 0 or len(predictions[0].emotions) == 0:
        logger.info(f"Can not predict user's expression. Uid: {uid}")
        return

    # Filter users emotions only
    users_frames: List[Tuple[float, float]] = []
    for seg in filter(lambda seg: seg.is_user and 0 <= seg.start < seg.end, conversation.transcript_segments):
        users_frames.append((seg.start, seg.end))
    # print(users_frames)

    if len(users_frames) == 0:
        logger.info(f"User time frames are empty. Uid: {uid}")
        return

    users_predictions: List[HumeJobModelPredictionResponseModel] = []
    for prediction in predictions:
        for uf in users_frames:
            logger.info(f"{uf} {prediction.time}")
            if uf[0] <= prediction.time[0] and prediction.time[1] <= uf[1]:
                users_predictions.append(prediction)
                break
    if len(users_predictions) == 0:
        logger.info(f"Predictions are filtered by user transcript segments. Uid: {uid}")
        return

    # Top emotions
    emotion_filters: List[str] = []
    user_emotions: List[HumePredictionEmotionResponseModel] = []
    for up in users_predictions:
        user_emotions += up.emotions
    emotions = HumeJobModelPredictionResponseModel.get_top_emotion_names(user_emotions, 1, 0.5)
    # print(emotions)
    if len(emotion_filters) > 0:
        emotions = list(filter(lambda emotion: emotion in emotion_filters, emotions))
    if len(emotions) == 0:
        logger.info(f"Can not extract users emmotion. uid: {uid}")
        return

    emotion = ','.join(emotions)
    logger.info(f"Emotion Uid: {uid} {emotion}")

    # Ask llms about notification content
    title = "omi"
    context_str, _ = retrieve_rag_conversation_context(uid, conversation)

    response: str = obtain_emotional_message(
        uid, conversation.transcript_segments, conversation.get_person_ids(), context_str, emotion
    )
    message = response

    # Send the notification
    send_notification(uid, title, message, None)

    return


def retrieve_in_progress_conversation(uid: str) -> Optional[Dict[str, Any]]:
    conversation_id = redis_db.get_in_progress_conversation_id(uid)
    existing: Optional[Dict[str, Any]] = None

    if conversation_id:
        existing = conversations_db.get_conversation(uid, conversation_id)
        if existing and existing['status'] != 'in_progress':
            existing = None

    if not existing:
        existing = conversations_db.get_in_progress_conversation(uid)
    return existing
