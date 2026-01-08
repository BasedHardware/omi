import os
import random
import re
import threading
import uuid
import logging
from datetime import timezone, timedelta, datetime
from typing import Union, Tuple, List, Optional

from fastapi import HTTPException

from database import redis_db
import database.memories as memories_db
import database.conversations as conversations_db
import database.notifications as notification_db
import database.users as users_db
import database.tasks as tasks_db
import database.trends as trends_db
import database.action_items as action_items_db
import database.folders as folders_db
import database.calendar_meetings as calendar_db
from database.apps import record_app_usage, get_omi_personas_by_uid_db, get_app_by_id_db
from database.vector_db import upsert_vector2, update_vector_metadata
from models.app import App, UsageHistoryType
from models.memories import MemoryDB, Memory
from models.conversation import *
from models.conversation import (
    ExternalIntegrationCreateConversation,
    Conversation,
    CreateConversation,
    ConversationSource,
)
from utils.notifications import send_important_conversation_message
from models.conversation import CalendarMeetingContext
from models.other import Person
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.trend import Trend
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps, update_personas_async, sync_update_persona_prompt
from utils.llm.conversation_processing import (
    get_transcript_structure,
    get_app_result,
    should_discard_conversation,
    select_best_app_for_conversation,
    get_suggested_apps_for_conversation,
    get_reprocess_transcript_structure,
    assign_conversation_to_folder,
)
from utils.analytics import record_usage
from utils.llm.memories import extract_memories_from_text, new_memories_extractor
from utils.llm.external_integrations import summarize_experience_text
from utils.llm.trends import trends_extractor
from utils.llm.goals import extract_and_update_goal_progress
from utils.llm.chat import (
    retrieve_metadata_from_text,
    retrieve_metadata_from_message,
    retrieve_metadata_fields_from_transcript,
    obtain_emotional_message,
)
from utils.llm.external_integrations import get_message_structure
from utils.llm.clients import generate_embedding
from utils.notifications import send_notification
from utils.other.hume import get_hume, HumeJobCallbackModel, HumeJobModelPredictionResponseModel
from utils.retrieval.rag import retrieve_rag_conversation_context
from utils.webhooks import conversation_created_webhook
from utils.notifications import send_action_item_data_message
from utils.other.storage import precache_conversation_audio


def _get_structured(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    people: List[Person] = None,
) -> Tuple[Structured, bool]:
    try:
        tz = notification_db.get_user_time_zone(uid)

        # Fetch existing action items from past 2 days for deduplication
        existing_action_items = None
        try:
            two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
            existing_action_items = action_items_db.get_action_items(uid=uid, start_date=two_days_ago, limit=50)
        except Exception as e:
            print(f"Error fetching existing action items for deduplication: {e}")

        # Extract calendar context from external_data
        calendar_context = None
        if hasattr(conversation, 'external_data') and conversation.external_data:
            calendar_data = conversation.external_data.get('calendar_meeting_context')
            if calendar_data:
                calendar_context = CalendarMeetingContext(**calendar_data)

        if (
            conversation.source == ConversationSource.workflow
            or conversation.source == ConversationSource.external_integration
        ):
            if conversation.text_source == ExternalIntegrationConversationSource.audio:
                structured = get_transcript_structure(
                    conversation.text,
                    conversation.started_at,
                    language_code,
                    tz,
                    existing_action_items=existing_action_items,
                    calendar_meeting_context=calendar_context,
                )
                return structured, False

            if conversation.text_source == ExternalIntegrationConversationSource.message:
                structured = get_message_structure(
                    conversation.text, conversation.started_at, language_code, tz, conversation.text_source_spec
                )
                return structured, False

            if conversation.text_source == ExternalIntegrationConversationSource.other:
                structured = summarize_experience_text(conversation.text, conversation.text_source_spec)
                return structured, False

            # not supported conversation source
            raise HTTPException(status_code=400, detail=f'Invalid conversation source: {conversation.text_source}')

        transcript_text = conversation.get_transcript(False, people=people)

        # For re-processing, we don't discard, just re-structure.
        if force_process:
            # reprocess endpoint
            return (
                get_reprocess_transcript_structure(
                    transcript_text,
                    conversation.started_at,
                    language_code,
                    tz,
                    conversation.structured.title,
                    photos=conversation.photos,
                    existing_action_items=existing_action_items,
                ),
                False,
            )

        # Determine whether to discard the conversation based on its content (transcript and/or photos).
        discarded = should_discard_conversation(transcript_text, conversation.photos)
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        # If not discarded, proceed to generate the structured summary from transcript and/or photos.
        return (
            get_transcript_structure(
                transcript_text,
                conversation.started_at,
                language_code,
                tz,
                photos=conversation.photos,
                existing_action_items=existing_action_items,
                calendar_meeting_context=calendar_context,
            ),
            False,
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Error processing conversation, please try again later")


def _get_conversation_obj(
    uid: str,
    structured: Structured,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
):
    discarded = structured.title == ''
    if isinstance(conversation, CreateConversation):
        conversation_dict = conversation.dict()
        # Store calendar context in external_data if available
        calendar_context = conversation_dict.pop('calendar_meeting_context', None)

        # Use started_at as created_at for imported conversations to preserve original timestamp
        created_at = conversation.started_at if conversation.started_at else datetime.now(timezone.utc)
        conversation = Conversation(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            created_at=created_at,
            discarded=discarded,
            **conversation_dict,
        )

        # Add calendar metadata to external_data
        if calendar_context:
            if not conversation.external_data:
                conversation.external_data = {}
            conversation.external_data['calendar_meeting_context'] = calendar_context

        if conversation.photos:
            conversations_db.store_conversation_photos(uid, conversation.id, conversation.photos)
    elif isinstance(conversation, ExternalIntegrationCreateConversation):
        create_conversation = conversation
        # Use started_at as created_at for external integrations to preserve original timestamp
        created_at = conversation.started_at if conversation.started_at else datetime.now(timezone.utc)
        conversation = Conversation(
            id=str(uuid.uuid4()),
            **conversation.dict(),
            created_at=created_at,
            structured=structured,
            discarded=discarded,
        )
        conversation.external_data = create_conversation.dict()
        conversation.app_id = create_conversation.app_id
    else:
        conversation.structured = structured
        conversation.discarded = discarded

    return conversation


# Function to get conversation summary apps from Redis
def get_default_conversation_summarized_apps():
    """
    Get conversation summary apps from Redis.
    Falls back to environment variable if Redis is empty.
    """
    default_apps = []

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
    people: List[Person] = None,
):
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

    app_to_run = None

    # Always generate/update suggestions if not already set (even during reprocessing)
    if not conversation.suggested_summarization_apps:
        suggested_apps, reasoning = get_suggested_apps_for_conversation(conversation, all_suggestion_apps)
        conversation.suggested_summarization_apps = suggested_apps
        print(f"Generated suggested apps for conversation {conversation.id}: {suggested_apps}")

    # If a specific app_id is provided (for reprocessing), find and use it.
    if app_id:
        app_to_run = all_apps_dict.get(app_id)
    else:
        # Check if user has a preferred app set
        preferred_app_id = redis_db.get_user_preferred_app(uid)
        if preferred_app_id and preferred_app_id in all_apps_dict:
            app_to_run = all_apps_dict.get(preferred_app_id)
            print(f"Using user's preferred app: {app_to_run.name} (id: {preferred_app_id})")
        elif conversation.suggested_summarization_apps:
            # Use the first suggested app if available
            first_suggested_app_id = conversation.suggested_summarization_apps[0]
            app_to_run = all_apps_dict.get(first_suggested_app_id)
            if app_to_run:
                print(f"Using first suggested app: {app_to_run.name}")
            else:
                print(f"First suggested app '{first_suggested_app_id}' not found in apps.")

    filtered_apps = [app_to_run] if app_to_run else []

    if not filtered_apps:
        print(f"No summarization app selected for conversation {conversation.id}", uid)

    # Clear existing app results
    conversation.apps_results = []

    threads = []

    def execute_app(app):
        result = get_app_result(
            conversation.get_transcript(False, people=people), conversation.photos, app, language_code=language_code
        ).strip()
        conversation.apps_results.append(AppResult(app_id=app.id, content=result))
        if not is_reprocess:
            record_app_usage(uid, app.id, UsageHistoryType.memory_created_prompt, conversation_id=conversation.id)

    for app in filtered_apps:
        threads.append(threading.Thread(target=execute_app, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def _update_goal_progress(uid: str, conversation: Conversation):
    """Extract and update goal progress from conversation text."""
    try:
        # Get conversation text
        text = ""
        if conversation.structured and conversation.structured.overview:
            text = conversation.structured.overview
        elif conversation.transcript_segments:
            text = " ".join([s.text for s in conversation.transcript_segments[:20]])

        if not text or len(text) < 10:
            return

        # Use utility function to extract and update goal progress
        extract_and_update_goal_progress(uid, text)
    except Exception as e:
        print(f"[GOAL] Error updating progress: {e}")


def _extract_memories(uid: str, conversation: Conversation):
    # TODO: maybe instead (once they can edit them) we should not tie it this hard
    memories_db.delete_memories_for_conversation(uid, conversation.id)

    new_memories: List[Memory] = []

    # Extract memories based on conversation source
    if conversation.source == ConversationSource.external_integration:
        text_content = conversation.external_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = conversation.external_data.get('text_source', 'other')
            new_memories = extract_memories_from_text(uid, text_content, text_source)
    else:
        # For regular conversations with transcript segments
        new_memories = new_memories_extractor(uid, conversation.transcript_segments)

    is_locked = conversation.is_locked
    parsed_memories = []
    for memory in new_memories:
        memory_db_obj = MemoryDB.from_memory(memory, uid, conversation.id, False)
        memory_db_obj.is_locked = is_locked
        parsed_memories.append(memory_db_obj)
        # print('_extract_memories:', memory.category.value.upper(), '|', memory.content)

    if len(parsed_memories) == 0:
        print(f"No memories extracted for conversation {conversation.id}")
        return

    print(f"Saving {len(parsed_memories)} memories for conversation {conversation.id}")
    memories_db.save_memories(uid, [fact.dict() for fact in parsed_memories])

    if len(parsed_memories) > 0:
        record_usage(uid, memories_created=len(parsed_memories))

        try:
            from utils.llm.knowledge_graph import extract_knowledge_from_memory
            from database import users as users_db

            user = users_db.get_user_store_recording_permission(uid)
            user_name = user.get('name', 'User') if user else 'User'

            from database.memories import set_memory_kg_extracted

            for memory_db_obj in parsed_memories:
                if memory_db_obj.kg_extracted:
                    continue
                extract_knowledge_from_memory(uid, memory_db_obj.content, memory_db_obj.id, user_name)
                set_memory_kg_extracted(uid, memory_db_obj.id)
        except Exception:
            logging.exception("Error extracting knowledge graph from memory.")


def send_new_memories_notification(user_id: str, memories: [MemoryDB]):
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


def _extract_trends(uid: str, conversation: Conversation):
    extracted_items = trends_extractor(uid, conversation)
    parsed = [Trend(category=item.category, topics=[item.topic], type=item.type) for item in extracted_items]
    trends_db.save_trends(conversation, parsed)


def _save_action_items(uid: str, conversation: Conversation):
    """
    Save action items from a conversation to the dedicated action_items collection.
    This runs in addition to storing them in the conversation for backward compatibility.
    """
    if not conversation.structured or not conversation.structured.action_items:
        return

    is_locked = conversation.is_locked
    action_items_data = []
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
        # Delete existing action items for this conversation first (in case of reprocessing)
        action_items_db.delete_action_items_for_conversation(uid, conversation.id)
        # Save new action items
        action_item_ids = action_items_db.create_action_items_batch(uid, action_items_data)
        print(f"Saved {len(action_item_ids)} action items for conversation {conversation.id}")

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


def save_structured_vector(uid: str, conversation: Conversation, update_only: bool = False):
    vector = generate_embedding(str(conversation.structured)) if not update_only else None
    tz = notification_db.get_user_time_zone(uid)

    metadata = {}

    # Extract metadata based on conversation source
    if conversation.source == ConversationSource.external_integration:
        text_source = conversation.external_data.get('text_source')
        text_content = conversation.external_data.get('text')
        if text_content and len(text_content) > 0 and text_content and len(text_content) > 0:
            text_source_spec = conversation.external_data.get('text_source_spec')
            if text_source == ExternalIntegrationConversationSource.message.value:
                metadata = retrieve_metadata_from_message(
                    uid, conversation.created_at, text_content, tz, text_source_spec
                )
            elif text_source == ExternalIntegrationConversationSource.other.value:
                metadata = retrieve_metadata_from_text(uid, conversation.created_at, text_content, tz, text_source_spec)
    else:
        # For regular conversations with transcript segments
        segments = [t.dict() for t in conversation.transcript_segments]
        metadata = retrieve_metadata_fields_from_transcript(
            uid, conversation.created_at, segments, tz, photos=conversation.photos
        )

    metadata['created_at'] = int(conversation.created_at.timestamp())

    if not update_only:
        print('save_structured_vector creating vector')
        upsert_vector2(uid, conversation, vector, metadata)
    else:
        print('save_structured_vector updating metadata')
        update_vector_metadata(uid, conversation.id, metadata)


def _update_personas_async(uid: str):
    print(f"[PERSONAS] Starting persona updates in background thread for uid={uid}")
    personas = get_omi_personas_by_uid_db(uid)
    if personas:
        threads = []
        for persona in personas:
            threads.append(threading.Thread(target=sync_update_persona_prompt, args=(persona,)))

        [t.start() for t in threads]
        [t.join() for t in threads]
        print(f"[PERSONAS] Finished persona updates in background thread for uid={uid}")


def process_conversation(
    uid: str,
    language_code: str,
    conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
    force_process: bool = False,
    is_reprocess: bool = False,
    app_id: Optional[str] = None,
) -> Conversation:
    # Fetch meeting context from Firestore if meeting_id is associated with this conversation
    if hasattr(conversation, 'id') and conversation.id:
        meeting_id = redis_db.get_conversation_meeting_id(conversation.id)
        if meeting_id:
            try:
                meeting_data = calendar_db.get_meeting(uid, meeting_id)
                if meeting_data:
                    # Add meeting context to conversation's external_data
                    if not hasattr(conversation, 'external_data') or not conversation.external_data:
                        conversation.external_data = {}
                    conversation.external_data['calendar_meeting_context'] = meeting_data
                    print(f"Retrieved meeting context for conversation {conversation.id}: {meeting_data.get('title')}")
            except Exception as e:
                print(f"Error retrieving meeting context for conversation {conversation.id}: {e}")

    person_ids = conversation.get_person_ids()
    people = []
    if person_ids:
        people_data = users_db.get_people_by_ids(uid, list(set(person_ids)))
        people = [Person(**p) for p in people_data]

    structured, discarded = _get_structured(uid, language_code, conversation, force_process, people=people)
    conversation = _get_conversation_obj(uid, structured, conversation)

    # AI-based folder assignment
    assigned_folder_id = None
    if not discarded and not is_reprocess and not conversation.folder_id:
        try:
            # Get user's folders
            user_folders = folders_db.get_folders(uid)
            if not user_folders:
                user_folders = folders_db.initialize_system_folders(uid)

            if user_folders and conversation.structured:
                folder_id, confidence, reasoning = assign_conversation_to_folder(
                    transcript=(
                        conversation.get_transcript(False, people=people)
                        if hasattr(conversation, 'get_transcript')
                        else ''
                    ),
                    title=conversation.structured.title or '',
                    overview=conversation.structured.overview or '',
                    category=conversation.structured.category.value if conversation.structured.category else 'other',
                    user_folders=user_folders,
                )
                if folder_id:
                    conversation.folder_id = folder_id
                    assigned_folder_id = folder_id
                    print(
                        f"AI assigned conversation {conversation.id} to folder {folder_id} (confidence: {confidence:.2f}): {reasoning}"
                    )
        except Exception as e:
            print(f"Error during folder assignment for conversation {conversation.id}: {e}")

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
        (
            threading.Thread(
                target=save_structured_vector,
                args=(
                    uid,
                    conversation,
                ),
            ).start()
            if not is_reprocess
            else None
        )
        threading.Thread(target=_extract_memories, args=(uid, conversation)).start()
        threading.Thread(target=_extract_trends, args=(uid, conversation)).start()
        threading.Thread(target=_save_action_items, args=(uid, conversation)).start()
        threading.Thread(target=_update_goal_progress, args=(uid, conversation)).start()

    # Create audio files from chunks if private cloud sync was enabled
    if not is_reprocess and conversation.private_cloud_sync_enabled:
        try:
            audio_files = conversations_db.create_audio_files_from_chunks(uid, conversation.id)
            if audio_files:
                conversation.audio_files = audio_files
                conversations_db.update_conversation(
                    uid, conversation.id, {'audio_files': [af.dict() for af in audio_files]}
                )
                # Pre-cache audio files in background
                precache_conversation_audio(uid, conversation.id, [af.dict() for af in audio_files])
        except Exception as e:
            print(f"Error creating audio files: {e}")

    conversation.status = ConversationStatus.completed
    conversations_db.upsert_conversation(uid, conversation.dict())

    # Update folder conversation count after conversation is saved
    if assigned_folder_id:
        folders_db.update_folder_conversation_count(uid, assigned_folder_id)

    if not is_reprocess:
        threading.Thread(
            target=conversation_created_webhook,
            args=(
                uid,
                conversation,
            ),
        ).start()
        # Update persona prompts with new conversation
        threading.Thread(target=update_personas_async, args=(uid,)).start()

        # Send important conversation notification for long conversations (>30 minutes)
        threading.Thread(
            target=_send_important_conversation_notification_if_needed,
            args=(uid, conversation),
        ).start()

    # TODO: trigger external integrations here too

    print('process_conversation completed conversation.id=', conversation.id)
    return conversation


def _send_important_conversation_notification_if_needed(uid: str, conversation: Conversation):
    """
    Send notification for long conversations (>30 minutes) that just completed.
    Only sends once per conversation using Redis deduplication.
    """

    # Skip if conversation is discarded
    if conversation.discarded:
        return

    # Check if we have valid timestamps to compute duration
    if not conversation.started_at or not conversation.finished_at:
        print(f"Cannot compute duration for conversation {conversation.id}: missing timestamps")
        return

    # Calculate duration in seconds
    duration_seconds = (conversation.finished_at - conversation.started_at).total_seconds()

    # Only notify for conversations longer than 30 minutes (1800 seconds)
    if duration_seconds < 1800:
        return

    # Check if notification was already sent for this conversation
    if redis_db.has_important_conversation_notification_been_sent(uid, conversation.id):
        print(f"Important conversation notification already sent for {conversation.id}")
        return

    # Mark as sent before sending to prevent duplicates
    redis_db.set_important_conversation_notification_sent(uid, conversation.id)

    # Send the notification
    print(
        f"Sending important conversation notification for {conversation.id} (duration: {duration_seconds/60:.1f} mins)"
    )
    send_important_conversation_message(uid, conversation.id)


def process_user_emotion(uid: str, language_code: str, conversation: Conversation, urls: [str]):
    print('process_user_emotion conversation.id=', conversation.id)

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
        print(err)
        return
    job = ok["result"]
    request_id = job.id
    if not request_id or len(request_id) == 0:
        print(f"Can not request users feeling. uid: {uid}")
        return

    # update task
    task.request_id = request_id
    task.updated_at = datetime.now()
    tasks_db.update(task.id, task.dict())

    return


def process_user_expression_measurement_callback(provider: str, request_id: str, callback: HumeJobCallbackModel):
    support_providers = [TaskActionProvider.HUME]
    if provider not in support_providers:
        print(f"Provider is not supported. {provider}")
        return

    # Get task
    task_action = ""
    if provider == TaskActionProvider.HUME:
        task_action = TaskAction.HUME_MERSURE_USER_EXPRESSION
    if len(task_action) == 0:
        print("Task action is empty")
        return

    task_data = tasks_db.get_task_by_action_request(task_action, request_id)
    if task_data is None:
        print(f"Task not found. Action: {task_action}, Request ID: {request_id}")
        return

    task = Task(**task_data)

    # Update
    task_status = task.status
    if callback.status == "COMPLETED":
        task_status = TaskStatus.DONE
    elif callback.status == "FAILED":
        task_status = TaskStatus.ERROR
    else:
        print(f"Not support status {callback.status}")
        return

    # Not changed
    if task_status == task.status:
        print("Task status are synced")
        return

    task.status = task_status
    task.updated_at = datetime.now()
    tasks_db.update(task.id, task.dict())

    # done or not
    if task.status != TaskStatus.DONE:
        print(f"Task is not done yet. Uid: {task.user_uid}, task_id: {task.id}, status: {task.status}")
        return

    uid = task.user_uid

    # Save predictions
    if len(callback.predictions) > 0:
        conversations_db.store_model_emotion_predictions_result(
            task.user_uid, task.memory_id, provider, callback.predictions
        )

    # Conversation
    conversation_data = conversations_db.get_conversation(uid, task.memory_id)
    if conversation_data is None:
        print(f"Conversation is not found. Uid: {uid}. Conversation: {task.memory_id}")
        return

    conversation = Conversation(**conversation_data)

    # Get prediction
    predictions = callback.predictions
    print(predictions)
    if len(predictions) == 0 or len(predictions[0].emotions) == 0:
        print(f"Can not predict user's expression. Uid: {uid}")
        return

    # Filter users emotions only
    users_frames = []
    for seg in filter(lambda seg: seg.is_user and 0 <= seg.start < seg.end, conversation.transcript_segments):
        users_frames.append((seg.start, seg.end))
    # print(users_frames)

    if len(users_frames) == 0:
        print(f"User time frames are empty. Uid: {uid}")
        return

    users_predictions = []
    for prediction in predictions:
        for uf in users_frames:
            print(uf, prediction.time)
            if uf[0] <= prediction.time[0] and prediction.time[1] <= uf[1]:
                users_predictions.append(prediction)
                break
    if len(users_predictions) == 0:
        print(f"Predictions are filtered by user transcript segments. Uid: {uid}")
        return

    # Top emotions
    emotion_filters = []
    user_emotions = []
    for up in users_predictions:
        user_emotions += up.emotions
    emotions = HumeJobModelPredictionResponseModel.get_top_emotion_names(user_emotions, 1, 0.5)
    # print(emotions)
    if len(emotion_filters) > 0:
        emotions = filter(lambda emotion: emotion in emotion_filters, emotions)
    if len(emotions) == 0:
        print(f"Can not extract users emmotion. uid: {uid}")
        return

    emotion = ','.join(emotions)
    print(f"Emotion Uid: {uid} {emotion}")

    # Ask llms about notification content
    title = "omi"
    context_str, _ = retrieve_rag_conversation_context(uid, conversation)

    response: str = obtain_emotional_message(uid, conversation, context_str, emotion)
    message = response

    # Send the notification
    send_notification(uid, title, message, None)

    return


def retrieve_in_progress_conversation(uid):
    conversation_id = redis_db.get_in_progress_conversation_id(uid)
    existing = None

    if conversation_id:
        existing = conversations_db.get_conversation(uid, conversation_id)
        if existing and existing['status'] != 'in_progress':
            existing = None

    if not existing:
        existing = conversations_db.get_in_progress_conversation(uid)
    return existing
