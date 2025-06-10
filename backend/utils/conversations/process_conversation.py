import os
import datetime
import random
import threading
import uuid
from datetime import timezone
from typing import Union, Tuple, List, Optional

from fastapi import HTTPException

from database import redis_db
import database.memories as memories_db
import database.conversations as conversations_db
import database.notifications as notification_db
import database.tasks as tasks_db
import database.trends as trends_db
from database.apps import record_app_usage, get_omi_personas_by_uid_db, get_app_by_id_db
from database.redis_db import get_user_preferred_app
from database.vector_db import upsert_vector2, update_vector_metadata
from models.app import App, UsageHistoryType
from models.memories import MemoryDB, Memory
from models.conversation import *
from models.conversation import ExternalIntegrationCreateConversation, Conversation, CreateConversation, ConversationSource
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.trend import Trend
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps, update_personas_async, sync_update_persona_prompt
from utils.llm.conversation_processing import get_transcript_structure, \
    get_app_result, should_discard_conversation, select_best_app_for_conversation, \
    get_reprocess_transcript_structure, get_combined_transcript_and_photos_structure
from utils.llm.memories import extract_memories_from_text, new_memories_extractor
from utils.llm.external_integrations import summarize_experience_text
from utils.llm.openglass import summarize_open_glass
from utils.llm.trends import trends_extractor
from utils.llm.chat import retrieve_metadata_from_text, retrieve_metadata_from_message, retrieve_metadata_fields_from_transcript, obtain_emotional_message
from utils.llm.external_integrations import get_message_structure
from utils.llm.clients import generate_embedding
from utils.notifications import send_notification
from utils.other.hume import get_hume, HumeJobCallbackModel, HumeJobModelPredictionResponseModel
from utils.retrieval.rag import retrieve_rag_conversation_context
from utils.webhooks import conversation_created_webhook


def _get_structured(
        uid: str, language_code: str, conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
        force_process: bool = False
) -> Tuple[Structured, bool]:
    try:
        tz = notification_db.get_user_time_zone(uid)
        if conversation.source == ConversationSource.workflow or conversation.source == ConversationSource.external_integration:
            if conversation.text_source == ExternalIntegrationConversationSource.audio:
                structured = get_transcript_structure(conversation.text, conversation.started_at, language_code, tz)
                return structured, False

            if conversation.text_source == ExternalIntegrationConversationSource.message:
                structured = get_message_structure(conversation.text, conversation.started_at, language_code, tz,
                                                   conversation.text_source_spec)
                return structured, False

            if conversation.text_source == ExternalIntegrationConversationSource.other:
                structured = summarize_experience_text(conversation.text, conversation.text_source_spec)
                return structured, False

            # not supported conversation source
            raise HTTPException(status_code=400, detail=f'Invalid conversation source: {conversation.text_source}')

        # ELEGANT: Handle photo conversations properly - check photos BEFORE OpenGlass source check
        # This ensures photo conversations get proper titles from photo descriptions
        if conversation.photos:
            # Check if this is a combined conversation (has both transcript and photos)
            transcript = conversation.get_transcript(False) if hasattr(conversation, 'get_transcript') else ""
            
            if transcript and transcript.strip():
                # Combined conversation: transcript + photos (audio+photo)
                structured = get_combined_transcript_and_photos_structure(
                    transcript, conversation.photos, conversation.started_at, language_code, tz
                )
                
                # Never discard conversations with photos - visual content is always valuable
                return structured, False
            else:
                # Photos-only conversation - use specialized OpenGlass processing for proper titles
                from utils.llm.openglass import summarize_open_glass
                structured = summarize_open_glass(conversation.photos)
                
                # Never discard photo conversations - they have valuable visual content
                return structured, False

        # ELEGANT: Only use generic OpenGlass fallback when NO photos exist
        if conversation.source == ConversationSource.openglass:
            # This ensures empty OpenGlass conversations are never marked as discarded
            # But only used when no photos are available for proper processing
            
            # Create basic structured data for OpenGlass conversations without photos
            basic_structure = get_transcript_structure("Visual experience captured via OpenGlass", conversation.started_at, language_code, tz)
            return basic_structure, False  # Never discard OpenGlass conversations

        # from Omi
        if force_process:
            # reprocess endpoint
            return get_reprocess_transcript_structure(conversation.get_transcript(False), conversation.started_at, language_code, tz, conversation.structured.title), False

        discarded = should_discard_conversation(conversation.get_transcript(False))
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        return get_transcript_structure(conversation.get_transcript(False), conversation.started_at, language_code, tz), False
    except Exception as e:
        # Keep error logging for debugging
        import traceback
        traceback.print_exc()
        if retries == 2:
            raise HTTPException(status_code=500, detail="Error processing conversation, please try again later")
        return _get_structured(uid, language_code, conversation, force_process, retries + 1)


def _get_conversation_obj(uid: str, structured: Structured,
                          conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]):
    # ELEGANT: Never discard photo conversations - they have valuable visual content
    # Only discard based on empty title for non-photo conversations
    has_photos = False
    if hasattr(conversation, 'photos') and conversation.photos:
        has_photos = True
    
    discarded = structured.title == '' and not has_photos  # Don't discard if has photos
    if isinstance(conversation, CreateConversation):
        conversation = Conversation(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            **conversation.dict(),
            created_at=datetime.now(timezone.utc),
            discarded=discarded,
        )
        if conversation.photos:
            conversations_db.store_conversation_photos(uid, conversation.id, conversation.photos)
    elif isinstance(conversation, ExternalIntegrationCreateConversation):
        create_conversation = conversation
        conversation = Conversation(
            id=str(uuid.uuid4()),
            **conversation.dict(),
            created_at=datetime.now(timezone.utc),
            structured=structured,
            discarded=discarded,
        )
        conversation.external_data = create_conversation.dict()
        conversation.app_id = create_conversation.app_id
    else:
        conversation.structured = structured
        conversation.discarded = discarded

    return conversation


# Get default conversation summary app IDs from environment variable
CONVERSATION_SUMMARIZED_APP_IDS = os.getenv('CONVERSATION_SUMMARIZED_APP_IDS', 'summary_assistant,action_item_extractor,insight_analyzer').split(',')

# Function to get default memory apps
def get_default_conversation_summarized_apps():
    default_apps = []
    for app_id in CONVERSATION_SUMMARIZED_APP_IDS:
        app_data = get_app_by_id_db(app_id.strip())
        if app_data:
            default_apps.append(App(**app_data))

    return default_apps

def _trigger_apps(uid: str, conversation: Conversation, is_reprocess: bool = False, app_id: Optional[str] = None, language_code: str = 'en'):
    apps: List[App] = get_available_apps(uid)
    conversation_apps = [app for app in apps if app.works_with_memories() and app.enabled]
    filtered_apps = []

    if app_id:
        # single app reprocess
        filtered_apps = [app for app in conversation_apps if app.id == app_id]
    else:
        filtered_apps = conversation_apps

        # Extend with default apps (only if they exist)
        default_apps = get_default_conversation_summarized_apps()
        filtered_apps.extend(default_apps)

        if filtered_apps and len(filtered_apps) > 0:
            # Check if the user has a preferred app
            preferred_app_id = get_user_preferred_app(uid)
            if preferred_app_id is None:
                best_app = select_best_app_for_conversation(conversation, filtered_apps)
            else:
                best_app = next((app for app in filtered_apps if app.id == preferred_app_id), None)

            if best_app:
                print(f"Selected best app for conversation: {best_app.name}")

                user_enabled = set(redis_db.get_enabled_apps(uid))
                if best_app.id not in user_enabled:
                    redis_db.enable_app(uid, best_app.id)

                filtered_apps = [best_app]  # Use only the best app
        # auto plugins. For segments > 90 and language is not Spanish or Japanese, find the best one.
        # if len(conversation.transcript_segments) >= 90 and conversation.language not in ["ja", "es"]:
        #     best_app = select_best_app_for_conversation(conversation, conversation_apps)
        #     if best_app is None:
        #         pass
        #     else:
        #         filtered_apps.insert(0, best_app)
        #
        #         # enabled
        #         user_enabled = set(redis_db.get_enabled_apps(uid))
        #         if best_app.id not in user_enabled:
        #             redis_db.enable_app(uid, best_app.id)
        #
        # filtered_apps = list(set(filtered_apps))

    if len(filtered_apps) == 0:
        # Remove debug message - fallback handling works regardless
        
        # Generate basic summary when no apps are available
        try:
            from utils.llm.conversation_processing import get_transcript_structure, get_combined_transcript_and_photos_structure
            import database.notifications as notification_db
            
            transcript = conversation.get_transcript(False)
            
            # Handle combined conversations (transcript + photos) in fallback
            if conversation.photos and transcript.strip():
                # Combined conversation: use the same logic as _get_structured
                tz = notification_db.get_user_time_zone(uid)
                
                basic_summary = get_combined_transcript_and_photos_structure(
                    transcript, conversation.photos, conversation.started_at, 'en', tz
                )
                
                # Create a fallback app result that includes both transcript and photo context
                fallback_result = AppResult(
                    app_id='fallback_combined_summary',
                    content=f"**Summary:** {basic_summary.overview}\n\n**Key Points:** Generated from combined conversation and visual analysis."
                )
                
                conversation.apps_results = [fallback_result]
                return
                
            elif transcript.strip():  # Only transcript, no photos
                # Get user timezone for proper processing
                tz = notification_db.get_user_time_zone(uid)
                
                # Generate basic summary using existing LLM structure
                # This ensures consistent formatting with other summaries
                basic_summary = get_transcript_structure(transcript, conversation.started_at, 'en', tz)
                
                # Create a fallback app result
                fallback_result = AppResult(
                    app_id='fallback_summary',
                    content=f"**Summary:** {basic_summary.overview}\n\n**Key Points:** Generated from conversation analysis."
                )
                
                conversation.apps_results = [fallback_result]
                return
            
            elif conversation.photos:
                # Photos-only conversation fallback with full structured processing
                
                # Create pseudo-transcript from photo descriptions for full processing
                photos_as_transcript = "Visual Experience Description:\n" + "\n".join([
                    f"Scene {i+1}: {photo.description}" for i, photo in enumerate(conversation.photos)
                ])
                
                # Get user timezone for proper processing
                tz = notification_db.get_user_time_zone(uid)
                
                # Use full transcript structure processing to extract action items, events, etc.
                basic_summary = get_transcript_structure(photos_as_transcript, conversation.started_at, 'en', tz)
                
                # Create a fallback app result for photos-only with full structured content
                fallback_result = AppResult(
                    app_id='fallback_photos_structured_summary',
                    content=f"**Summary:** {basic_summary.overview}\n\n**Key Points:** Generated from visual analysis with action items and events extracted."
                )
                
                conversation.apps_results = [fallback_result]
                return
        except Exception as e:
            # Keep error logging for fallback failures - this is important for debugging
            print(f"Error generating fallback summary: {e}")

        # If fallback fails, ensure empty results
        conversation.apps_results = []
        return

    # Clear existing app results
    conversation.apps_results = []

    threads = []

    def execute_app(app):
        # Handle both transcript and photo descriptions
        transcript = conversation.get_transcript(False)
        
        # Determine what content to pass to the app
        if transcript.strip():
            # Has transcript (with or without photos)
            if conversation.photos:
                # Combined: transcript + photo descriptions
                photos_text = "\n\nVisual Context:\n" + "\n".join([f"- {photo.description}" for photo in conversation.photos])
                content_for_app = transcript + photos_text
            else:
                # Transcript only
                content_for_app = transcript
        elif conversation.photos:
            # Photos only - create text from photo descriptions
            content_for_app = "Visual Descriptions:\n" + "\n".join([f"- {photo.description}" for photo in conversation.photos])
        else:
            # No content
            content_for_app = ""
        
        result = get_app_result(content_for_app, app).strip()

        conversation.apps_results.append(AppResult(app_id=app.id, content=result))
        if not is_reprocess:
            record_app_usage(uid, app.id, UsageHistoryType.memory_created_prompt, conversation_id=conversation.id)

    for app in filtered_apps:
        threads.append(threading.Thread(target=execute_app, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def _extract_memories(uid: str, conversation: Conversation):
    # TODO: maybe instead (once they can edit them) we should not tie it this hard
    memories_db.delete_memories_for_conversation(uid, conversation.id)

    new_memories: List[Memory] = []

    # Extract memories based on conversation source and content
    if conversation.source == ConversationSource.external_integration:
        text_content = conversation.external_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = conversation.external_data.get('text_source', 'other')
            new_memories = extract_memories_from_text(uid, text_content, text_source)
    else:
        # For regular conversations - handle transcript, photos, or both
        transcript = conversation.get_transcript(False) if hasattr(conversation, 'get_transcript') else ""
        
        # Support image-only and combined conversations
        if conversation.photos and len(conversation.photos) > 0:
            # Create text content from photo descriptions for memory extraction
            photos_text = "Visual Experience Analysis:\n" + "\n".join([
                f"Scene {i+1}: {photo.description}" for i, photo in enumerate(conversation.photos) 
                if photo.description and photo.description.strip()
            ])
            
            if transcript.strip():
                # Combined conversation: transcript + photos
                
                # Extract memories from transcript segments (traditional way)
                transcript_memories = new_memories_extractor(uid, conversation.transcript_segments)
                
                # Extract additional memories from photo descriptions
                photo_memories = extract_memories_from_text(uid, photos_text, "visual_experience")
                
                # Combine both sources
                new_memories = transcript_memories + photo_memories
                
            else:
                # Photos-only conversation
                new_memories = extract_memories_from_text(uid, photos_text, "visual_experience")
        else:
            # Transcript-only conversation (traditional)
            new_memories = new_memories_extractor(uid, conversation.transcript_segments)

    parsed_memories = []
    for memory in new_memories:
        parsed_memories.append(MemoryDB.from_memory(memory, uid, conversation.id, False))

    if len(parsed_memories) == 0:
        # Remove debug message - not critical for production
        return

    # Remove debug message - not critical for production
    memories_db.save_memories(uid, [fact.dict() for fact in parsed_memories])


def send_new_memories_notification(token: str, memories: [MemoryDB]):
    memories_str = ", ".join([memory.content for memory in memories])
    message = f"New memories {memories_str}"
    ai_message = NotificationMessage(
        text=message,
        from_integration='false',
        type='text',
        notification_type='new_fact',
        navigate_to="/facts",
    )

    send_notification(token, "omi" + ' says', message, NotificationMessage.get_message_as_dict(ai_message))


def _extract_trends(conversation: Conversation):
    extracted_items = trends_extractor(conversation)
    parsed = [Trend(category=item.category, topics=[item.topic], type=item.type) for item in extracted_items]
    trends_db.save_trends(conversation, parsed)


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
                metadata = retrieve_metadata_from_message(uid, conversation.created_at, text_content, tz, text_source_spec)
            elif text_source == ExternalIntegrationConversationSource.other.value:
                metadata = retrieve_metadata_from_text(uid, conversation.created_at, text_content, tz, text_source_spec)
    else:
        # For regular conversations with transcript segments
        segments = [t.dict() for t in conversation.transcript_segments]
        metadata = retrieve_metadata_fields_from_transcript(uid, conversation.created_at, segments, tz)

    metadata['created_at'] = int(conversation.created_at.timestamp())

    if not update_only:
        # Remove debug message - not critical for production
        upsert_vector2(uid, conversation, vector, metadata)
    else:
        # Remove debug message - not critical for production
        update_vector_metadata(uid, conversation.id, metadata)


def _update_personas_async(uid: str):
    # Remove debug messages - not critical for production
    personas = get_omi_personas_by_uid_db(uid)
    if personas:
        threads = []
        for persona in personas:
            threads.append(threading.Thread(target=sync_update_persona_prompt, args=(persona,)))

        [t.start() for t in threads]
        [t.join() for t in threads]


def process_conversation(
        uid: str, language_code: str, conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
        force_process: bool = False, is_reprocess: bool = False, app_id: Optional[str] = None
) -> Conversation:
    structured, discarded = _get_structured(uid, language_code, conversation, force_process)
    conversation = _get_conversation_obj(uid, structured, conversation)

    if not discarded:
        _trigger_apps(uid, conversation, is_reprocess=is_reprocess, app_id=app_id, language_code=language_code)
        threading.Thread(target=save_structured_vector, args=(uid, conversation,)).start() if not is_reprocess else None
        threading.Thread(target=_extract_memories, args=(uid, conversation)).start()

    conversation.status = ConversationStatus.completed
    conversations_db.upsert_conversation(uid, conversation.dict())

    # Notify WebSocket clients to clear live images for this completed conversation
    try:
        import json
        from database.redis_db import r
        
        # Store clear_live_images message in Redis for active WebSocket sessions to pick up
        clear_message = {
            "type": "clear_live_images",
            "data": {
                "conversation_id": conversation.id,
                "reason": "conversation_created",
                "processed_image_count": len(conversation.photos) if conversation.photos else 0
            }
        }
        
        # Store message with TTL of 60 seconds
        clear_images_key = f"clear_live_images:{uid}"
        r.setex(clear_images_key, 60, json.dumps(clear_message))
        
        # Remove debug message - not critical for production
        
    except Exception as e:
        # Keep error logging - this is important for debugging WebSocket issues
        print(f'Error storing clear_live_images message: {e}')

    if not is_reprocess:
        threading.Thread(target=conversation_created_webhook, args=(uid, conversation,)).start()
        # Update persona prompts with new conversation
        threading.Thread(target=update_personas_async, args=(uid,)).start()

    # TODO: trigger external integrations here too

    return conversation


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
        conversations_db.store_model_emotion_predictions_result(task.user_uid, task.memory_id, provider,
                                                                callback.predictions)

    # Conversation
    conversation_data = conversations_db.get_conversation(uid, task.memory_id)
    if conversation_data is None:
        print(f"Conversation is not found. Uid: {uid}. Conversation: {task.memory_id}")
        return

    # Ensure all required fields are present before creating Conversation object
    from datetime import datetime, timezone
    
    # Add finished_at if missing
    if 'finished_at' not in conversation_data or conversation_data['finished_at'] is None:
        conversation_data['finished_at'] = datetime.now(timezone.utc)
    
    # Add other required fields if missing
    if 'created_at' not in conversation_data or conversation_data['created_at'] is None:
        conversation_data['created_at'] = datetime.now(timezone.utc)
    
    if 'started_at' not in conversation_data or conversation_data['started_at'] is None:
        conversation_data['started_at'] = datetime.now(timezone.utc)
    
    # Ensure status is set
    if 'status' not in conversation_data:
        conversation_data['status'] = ConversationStatus.completed

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

    print(title)
    print(message)

    # Send the notification
    token = notification_db.get_token_only(uid)
    if token is None:
        print(f"User token is none. Uid: {uid}")
        return

    send_notification(token, title, message, None)

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
    
    # Check for active WebSocket recording sessions
    if not existing:
        # Check if user has an active transcription WebSocket session
        active_session_key = f"active_transcription_session:{uid}"
        session_data = redis_db.r.get(active_session_key)
        
        if session_data:
            # User has active recording session, create a temporary conversation object
            # This will be used to signal that images should be held for the active session
            import json
            try:
                session_info = json.loads(session_data)
                
                # Return a temporary conversation object to indicate active session
                # The actual conversation will be created when recording stops
                from datetime import datetime, timezone
                from models.conversation import Structured, ConversationStatus
                import uuid
                
                now = datetime.now(timezone.utc)
                started_at = session_info.get('started_at', now.isoformat())
                if isinstance(started_at, str):
                    started_at_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                else:
                    started_at_dt = started_at
                
                existing = {
                    'id': f'active_session_{uid}',
                    'uid': uid,
                    'status': ConversationStatus.in_progress.value,  # Convert enum to string value
                    'is_active_session': True,  # Flag to indicate this is a live session
                    'started_at': started_at_dt.isoformat(),  # Store as ISO string
                    'created_at': started_at_dt.isoformat(),  # Store as ISO string
                    'finished_at': now.isoformat(),  # Store as ISO string
                    'structured': Structured().dict(),
                    'language': session_info.get('language', 'en'),
                    'transcript_segments': [],
                    'geolocation': None,
                    'photos': [],
                    'plugins_results': [],
                    'discarded': False,
                    'processing_memory_id': None,
                    'visibility': 'private'
                }
                return existing
            except Exception as e:
                print(f"Error parsing active session data: {e}")
                # Fall through to normal conversation retrieval
    
    return existing
