import os
import random
import re
import uuid
import logging
import asyncio
from datetime import timezone, timedelta, datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

from fastapi import HTTPException

import database._client as db_client_module
from database import redis_db
from database.auth import get_user_name
import database.memories as memories_db
import database.conversations as conversations_db
import database.notifications as notification_db
import database.users as users_db
import database.tasks as tasks_db
import database.action_items as action_items_db
import database.folders as folders_db
import database.calendar_meetings as calendar_db
from database.vector_db import (
    find_similar_memories,
    upsert_memory_vector,
    delete_memory_vector,
    upsert_action_item_vectors_batch,
    delete_action_item_vectors_batch,
    find_similar_action_items,
)
from utils.llm.memories import resolve_memory_conflict
from database.apps import record_app_usage, get_omi_personas_by_uid_db, get_app_by_id_db
from database.vector_db import upsert_vector2, update_vector_metadata, upsert_transcript_chunk_vectors
from utils.conversations.transcript_chunks import build_transcript_chunks
from models.app import App, UsageHistoryType
from models.memories import MemoryDB, Memory, render_memory
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
from utils.conversations.subjects import infer_subject_from_segments
from utils.memory.canonical_activation import canonical_write_enabled
from utils.memory.memory_api_contract import MemoryApiExposure, memory_write_payload
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.memory_system_pin import memory_system_request_scope
from utils.memory.canonical_memory_adapter import extraction_memory_id
from utils.subscription import is_trial_paywalled, should_defer_desktop_processing
from models.other import Person
from models.structured import Structured
from utils.notifications import send_important_conversation_message
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps, update_persona_prompt
from utils.executors import db_executor, llm_executor, postprocess_executor, submit_with_context
from utils.llm.conversation_processing import (
    get_transcript_structure,
    get_app_result,
    should_discard_conversation,
    get_suggested_apps_for_conversation,
    get_reprocess_transcript_structure,
    extract_action_items,
)
from utils.llm.conversation_folder import assign_conversation_to_folder
from utils.analytics import record_usage
from utils.llm.usage_tracker import track_usage, Features
from utils.llm.memories import extract_memories_from_text, new_memories_extractor
from utils.llm.external_integrations import summarize_experience_text
from utils.llm.goals import extract_and_update_goal_progress
from utils.llm.knowledge_graph import extract_knowledge_from_memory
from utils.llm.chat import (
    retrieve_metadata_from_text,
    retrieve_metadata_from_message,
    retrieve_metadata_fields_from_transcript,
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
from utils.conversations.calendar_linking import (
    get_overlapping_calendar_event,
    write_conversation_link_to_calendar_event,
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


def _fetch_dedup_candidates(uid: str, structured: Structured) -> List[Dict[str, Any]]:
    """
    Fetch open action items semantically related to this conversation, active
    in the past week, for the LLM extraction prompt to consider as potential
    duplicates. Replaces the older time-windowed fetch (past 2 days, limit
    50). Returns [] if Pinecone is down or there's no overview to query —
    extraction then proceeds with no dedup context, same as for a new user.
    """
    if not structured or not structured.overview:
        return []

    try:
        similar = find_similar_action_items(uid, structured.overview, threshold=0.6, limit=10)
        if not similar:
            return []

        items = action_items_db.get_action_items_by_ids(uid, [s['action_item_id'] for s in similar])
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        eligible: List[Dict[str, Any]] = []
        for item in items:
            if item.get('completed', False):
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


def _get_structured(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    people: Optional[List[Person]] = None,
) -> Tuple[Structured, bool]:
    try:
        tz: Optional[str] = notification_db.get_user_time_zone(uid)
        tz_str: str = tz or ''
        user_language = users_db.get_user_language_preference(uid) or language_code

        # Extract calendar context from external_data
        calendar_context: Optional[CalendarMeetingContext] = None
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
                        existing_action_items=_fetch_dedup_candidates(uid, structured),
                        calendar_meeting_context=calendar_context,
                        output_language_code=user_language,
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
        user_name = get_user_name(uid, use_default=False)
        transcript_text = main_conv.get_transcript(False, people=people, user_name=user_name)  # type: ignore[reportArgumentType]  # conversation.py reverted to main; people/user_name may be Optional

        # For re-processing, we don't discard, just re-structure.
        if force_process:
            conv_started_at = cast(datetime, main_conv.started_at)
            structured_conv = cast(Conversation, main_conv)
            # reprocess endpoint
            with track_usage(uid, Features.CONVERSATION_STRUCTURE):
                structured = get_reprocess_transcript_structure(
                    transcript_text,
                    conv_started_at,
                    language_code,
                    tz_str,
                    structured_conv.structured.title,
                    photos=main_conv.photos,
                    output_language_code=user_language,
                )
            with track_usage(uid, Features.CONVERSATION_ACTION_ITEMS):
                structured.action_items = extract_action_items(
                    transcript_text,
                    conv_started_at,
                    language_code,
                    tz_str,
                    photos=main_conv.photos,
                    existing_action_items=_fetch_dedup_candidates(uid, structured),
                    output_language_code=user_language,
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
                transcript_text,
                conv_started_at,
                language_code,
                tz_str,
                photos=main_conv.photos,
                existing_action_items=_fetch_dedup_candidates(uid, structured),
                calendar_meeting_context=calendar_context,
                output_language_code=user_language,
            )
        return structured, False
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Error processing conversation, please try again later")


def _get_conversation_obj(
    uid: str,
    structured: Structured,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
) -> Conversation:
    discarded = structured.title == ''
    if isinstance(conversation, CreateConversation):
        conversation_dict = conversation.dict()
        # Store calendar context in external_data if available
        calendar_context = conversation_dict.pop('calendar_meeting_context', None)

        # Use started_at as created_at for imported conversations to preserve original timestamp
        created_at = conversation.started_at if conversation.started_at else datetime.now(timezone.utc)
        result: Conversation = Conversation(
            id=str(uuid.uuid4()),
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
            id=str(uuid.uuid4()),
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
    default_apps = get_default_conversation_summarized_apps()
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
    else:
        # Check preferred app first — skip the suggestion LLM call if user has one
        preferred_app_id = redis_db.get_user_preferred_app(uid)
        if preferred_app_id and preferred_app_id in all_apps_dict:
            app_to_run = cast(App, all_apps_dict.get(preferred_app_id))
            logger.info(f"Using user's preferred app: {app_to_run.name} (id: {preferred_app_id})")
        else:
            # Only run suggestion LLM call when no preferred app is set
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

    filtered_apps: List[App] = [app_to_run] if app_to_run else []

    if not filtered_apps:
        logger.info(f"No summarization app selected for conversation {conversation.id} {uid}")

    # Clear existing app results
    conversation.apps_results = []

    def execute_app(app: App) -> None:
        with track_usage(uid, Features.CONVERSATION_APPS):
            result = get_app_result(
                conversation.get_transcript(False, people=people), conversation.photos, app, language_code=language_code  # type: ignore[reportArgumentType]  # conversation.py reverted to main; people/user_name may be Optional
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


def _extract_memories(uid: str, conversation: Conversation) -> None:
    with track_usage(uid, Features.MEMORIES):
        _extract_memories_inner(uid, conversation)


def _extract_memories_canonical(uid: str, conversation: Conversation, *, db_client: Any) -> None:
    """Canonical-cohort extraction: extract first, then retract-and-write (Q1/Q7)."""
    memory_service = MemoryService(db_client=db_client)

    language = users_db.get_user_language_preference(uid)
    new_memories: List[Memory] = []

    if conversation.source == ConversationSource.external_integration:
        ext_data = conversation.external_data or {}
        text_content = ext_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = ext_data.get('text_source', 'other')
            new_memories = extract_memories_from_text(uid, text_content, text_source, language=language)
    else:
        new_memories = new_memories_extractor(uid, conversation.transcript_segments, language=language)

    is_locked = conversation.is_locked
    parsed_memories: List[MemoryDB] = []
    seen_norm: Set[str] = set()
    subject_entity_id, subject_attribution = infer_subject_from_segments(conversation.transcript_segments)

    for memory in new_memories:
        norm = ' '.join((memory.content or '').lower().split())
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)

        memory_db_obj = MemoryDB.from_memory(
            memory,
            uid,
            conversation.id,
            False,
            source_id=conversation.id,
            source_type="conversation",
            source_signal="transcription",
            artifact_ref=_transcript_artifact_ref(conversation),
            extractor_id="new_memories_extractor",
            subject_entity_id=subject_entity_id,
            subject_attribution=subject_attribution,
            client_device_id=getattr(conversation, "client_device_id", None),
        )
        memory_db_obj.is_locked = is_locked
        memory_db_obj.id = extraction_memory_id(uid=uid, source_id=conversation.id, content=memory_db_obj.content)
        memory_db_obj.memory_tier = MemoryTier.short_term
        parsed_memories.append(memory_db_obj)

    if len(parsed_memories) == 0:
        logger.info(f"No canonical memories extracted for conversation {conversation.id}")
        return

    memory_service.retract_conversation_memories(uid, conversation.id)

    logger.info(f"Saving {len(parsed_memories)} canonical memories for conversation {conversation.id}")
    for memory_db_obj in parsed_memories:
        memory_service.write(uid, memory_db_obj.model_dump(mode="json"))

    record_usage(uid, memories_created=len(parsed_memories))


def _extract_memories_inner(uid: str, conversation: Conversation) -> None:
    with memory_system_request_scope(uid) as memory_system:
        db_client = getattr(db_client_module, 'db', None)
        if memory_system == MemorySystem.CANONICAL and canonical_write_enabled(uid, db_client=db_client):
            _extract_memories_canonical(uid, conversation, db_client=db_client)
            return

        _extract_memories_legacy(uid, conversation)


def _extract_memories_legacy(uid: str, conversation: Conversation) -> None:
    language = users_db.get_user_language_preference(uid)
    new_memories: List[Memory] = []

    # Extract memories based on conversation source
    if conversation.source == ConversationSource.external_integration:
        ext_data = conversation.external_data or {}
        text_content = ext_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = ext_data.get('text_source', 'other')
            new_memories = extract_memories_from_text(uid, text_content, text_source, language=language)
    else:
        # For regular conversations with transcript segments
        new_memories = new_memories_extractor(uid, conversation.transcript_segments, language=language)

    is_locked = conversation.is_locked
    parsed_memories: List[MemoryDB] = []
    # (old_memory_id, new_memory_id) pairs to invalidate after the new memories are saved.
    invalidations: List[Tuple[str, str]] = []
    # Cheap exact-duplicate guard within this batch (avoids redundant conflict LLM calls).
    seen_norm: Set[str] = set()
    subject_entity_id, subject_attribution = infer_subject_from_segments(conversation.transcript_segments)

    for memory in new_memories:
        norm = ' '.join((memory.content or '').lower().split())
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)

        # Wider net (lower threshold, more candidates) than before so cross-phrasing
        # contradictions are caught — "loves ice cream" vs "hates ice cream",
        # "lives in NYC" vs "lives in LA" — then let the LLM decide what's outdated.
        similar_matches = find_similar_memories(
            uid, memory.content, threshold=0.6, limit=8, subject_entity_id=subject_entity_id
        )

        # Only compare against currently-active memories (never resurface superseded ones).
        similar_memories: List[Dict[str, Any]] = []
        for match in similar_matches:
            memory_data = memories_db.get_memory(uid, match['memory_id'])
            if memory_data and memory_data.get('invalid_at') is None:
                existing_subject = memory_data.get('subject_entity_id')
                if subject_entity_id and existing_subject and subject_entity_id != existing_subject:
                    continue
                similar_memories.append(
                    {
                        'memory_id': match['memory_id'],
                        'category': match['category'],
                        'score': match['score'],
                        'content': memory_data.get('content', ''),
                    }
                )

        supersede_ids: List[str] = []
        if similar_memories:
            resolution = resolve_memory_conflict(memory.content, similar_memories, language=language)

            if resolution.action == 'skip':
                continue

            if resolution.action == 'merge':
                if resolution.merged_predicate:
                    memory.predicate = resolution.merged_predicate
                if resolution.merged_arguments:
                    memory.arguments = resolution.merged_arguments
                if resolution.merged_qualifiers:
                    memory.qualifiers = {**memory.qualifiers, **resolution.merged_qualifiers}
                if resolution.merged_content:
                    memory.content = resolution.merged_content
                elif resolution.merged_predicate or resolution.merged_arguments:
                    memory.content = render_memory(memory)

            if resolution.action in ('update', 'merge'):
                for idx in resolution.supersedes or []:
                    if 1 <= idx <= len(similar_memories):
                        supersede_ids.append(similar_memories[idx - 1]['memory_id'])

        memory_db_obj = MemoryDB.from_memory(
            memory,
            uid,
            conversation.id,
            False,
            source_id=conversation.id,
            source_type="conversation",
            source_signal="transcription",
            artifact_ref=_transcript_artifact_ref(conversation),
            extractor_id="new_memories_extractor",
            subject_entity_id=subject_entity_id,
            subject_attribution=subject_attribution,
            client_device_id=getattr(conversation, "client_device_id", None),
        )
        memory_db_obj.is_locked = is_locked
        # Corroboration is durability: a fact that updates/merges/supersedes an
        # existing memory has now been seen more than once, so promote it out of
        # the short-term tier it was born into.
        if supersede_ids:
            memory_db_obj.memory_tier = MemoryTier.long_term
        parsed_memories.append(memory_db_obj)

        for old_id in supersede_ids:
            # Guard against superseding the very memory we're about to (re)write — the
            # merged content can hash to an existing id.
            if old_id and old_id != memory_db_obj.id:
                invalidations.append((old_id, memory_db_obj.id))

    if len(parsed_memories) == 0:
        logger.info(f"No memories extracted for conversation {conversation.id}")
        return

    # Replace conversation-scoped memories only after extraction succeeds.
    deletion_result = memories_db.delete_memories_for_conversation(uid, conversation.id)
    for memory_id in deletion_result.get('vector_delete_ids', []):
        delete_memory_vector(uid, memory_id)

    logger.info(f"Saving {len(parsed_memories)} memories for conversation {conversation.id}")
    memories_db.save_memories(uid, [memory_write_payload(fact, MemoryApiExposure.LEGACY) for fact in parsed_memories])

    for memory_db_obj in parsed_memories:
        upsert_memory_vector(
            uid,
            memory_db_obj.id,
            memory_db_obj.content,
            memory_db_obj.category.value,
            subject_entity_id=memory_db_obj.subject_entity_id,
        )

    # Invalidate (not delete) superseded memories: keep them as history but drop them from
    # every retrieval path. Removing the vector also pulls them out of semantic search.
    for old_id, new_id in invalidations:
        try:
            memories_db.invalidate_memory(uid, old_id, superseded_by=new_id)
            delete_memory_vector(uid, old_id)
            logger.info(f"Invalidated superseded memory {old_id} -> {new_id}")
        except Exception:
            logger.exception(f"Failed to invalidate superseded memory {old_id}")

    if len(parsed_memories) > 0:
        record_usage(uid, memories_created=len(parsed_memories))

        try:
            user_name = cast(str, get_user_name(uid))

            for memory_db_obj in parsed_memories:
                if memory_db_obj.kg_extracted or memory_db_obj.is_locked:
                    continue
                try:
                    result = extract_knowledge_from_memory(uid, memory_db_obj.content, memory_db_obj.id, user_name)
                    if result is not None:
                        memories_db.set_memory_kg_extracted(uid, memory_db_obj.id)
                except Exception:
                    logging.exception(f"Error extracting knowledge graph from memory_id: {memory_db_obj.id}")
        except Exception:
            logging.exception("Error extracting knowledge graph from memory.")


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
        }
        action_items_data.append(action_item_data)

    if action_items_data:
        # Delete existing action items and their vectors first (in case of reprocessing)
        old_items = action_items_db.get_action_items_by_conversation(uid, conversation.id)
        old_ids = [item['id'] for item in old_items]
        if old_ids:
            delete_action_item_vectors_batch(uid, old_ids)
        action_items_db.delete_action_items_for_conversation(uid, conversation.id)
        # Save new action items
        action_item_ids = action_items_db.create_action_items_batch(uid, action_items_data)
        logger.info(f"Saved {len(action_item_ids)} action items for conversation {conversation.id}")

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

        submit_with_context(db_executor, _run_auto_sync)

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
        # For regular conversations with transcript segments
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
    structured = _build_deferred_structured(conversation)
    conversation = _get_conversation_obj(uid, structured, conversation)
    conversation.deferred = True
    # `processing` (not completed) is the user-facing "awaiting enrichment" state. Unlike the
    # `deferred` flag it survives the desktop's local conversation cache, so the client shows a
    # processing indicator and re-fetches on open to trigger enrichment. The lazy enrich sets it
    # back to `completed`.
    conversation.status = ConversationStatus.processing
    conversations_db.upsert_conversation(uid, conversation.dict())
    logger.info("lazy: stored deferred desktop conversation uid=%s conv=%s", uid, conversation.id)
    return conversation


def process_conversation(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    is_reprocess: bool = False,
    app_id: Optional[str] = None,
) -> Conversation:
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
        return _store_deferred_conversation(uid, conversation)

    # Fetch meeting context from Firestore if meeting_id is associated with this conversation
    if isinstance(conversation, Conversation) and conversation.id:
        meeting_id = redis_db.get_conversation_meeting_id(conversation.id)
        if meeting_id:
            try:
                meeting_data = calendar_db.get_meeting(uid, meeting_id)
                if meeting_data:
                    # Add meeting context to conversation's external_data
                    if not conversation.external_data:
                        conversation.external_data = {}
                    conversation.external_data['calendar_meeting_context'] = meeting_data
                    logger.info(
                        f"Retrieved meeting context for conversation {conversation.id}: {meeting_data.get('title')}"
                    )
            except Exception as e:
                logger.error(f"Error retrieving meeting context for conversation {conversation.id}: {e}")

    person_ids = conversation.get_person_ids()
    people: List[Person] = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    structured, discarded = _get_structured(uid, language_code, conversation, force_process, people=people)
    conversation = _get_conversation_obj(uid, structured, conversation)

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
                asyncio.run(write_conversation_link_to_calendar_event(uid, calendar_event.event_id, conversation.id))
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
                with track_usage(uid, Features.CONVERSATION_FOLDER):
                    folder_id, confidence, reasoning = assign_conversation_to_folder(
                        title=conversation.structured.title or '',
                        overview=conversation.structured.overview or '',
                        category=(
                            conversation.structured.category.value if conversation.structured.category else 'other'
                        ),
                        user_folders=user_folders,
                    )
                if folder_id:
                    conversation.folder_id = folder_id
                    assigned_folder_id = folder_id
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
        if not is_reprocess:
            submit_with_context(postprocess_executor, save_structured_vector, uid, conversation)
            if TRANSCRIPT_CHUNK_INDEXING_ENABLED:
                submit_with_context(postprocess_executor, save_transcript_chunk_vectors, uid, conversation)
        submit_with_context(postprocess_executor, _extract_memories, uid, conversation)
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

    conversation.status = ConversationStatus.completed
    conversations_db.upsert_conversation(uid, conversation.dict())

    # Update folder conversation count after conversation is saved
    if assigned_folder_id:
        folders_db.update_folder_conversation_count(uid, assigned_folder_id)

    if not is_reprocess:

        def _run_webhook():
            asyncio.run(conversation_created_webhook(uid, conversation))

        submit_with_context(postprocess_executor, _run_webhook)

        # Disable important conversation for now
        # Send important conversation notification for long conversations (>30 minutes)
        # threading.Thread(
        #     target=_send_important_conversation_notification_if_needed,
        #     args=(uid, conversation),
        # ).start()

    # TODO: trigger external integrations here too

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
