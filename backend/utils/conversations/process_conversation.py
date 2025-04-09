import datetime
import random
import threading
import uuid
from datetime import timezone
from typing import Union, Tuple, List

from fastapi import HTTPException

from database import redis_db
import database.memories as memories_db
import database.conversations as conversations_db
import database.notifications as notification_db
import database.tasks as tasks_db
import database.trends as trends_db
from database.apps import record_app_usage, get_omi_personas_by_uid_db
from database.vector_db import upsert_vector2, update_vector_metadata
from models.app import App, UsageHistoryType
from models.memories import MemoryDB, Memory
from models.conversation import *
from models.conversation import ExternalIntegrationCreateConversation, Conversation, CreateConversation, ConversationSource
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.trend import Trend
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps, update_personas_async, sync_update_persona_prompt
from utils.llm import obtain_emotional_message, retrieve_metadata_fields_from_transcript, \
    summarize_open_glass, get_transcript_structure, generate_embedding, \
    get_app_result, should_discard_conversation, summarize_experience_text, new_memories_extractor, \
    trends_extractor, get_email_structure, get_post_structure, get_message_structure, \
    retrieve_metadata_from_email, retrieve_metadata_from_post, retrieve_metadata_from_message, \
    retrieve_metadata_from_text, \
    extract_memories_from_text
from utils.notifications import send_notification
from utils.other.hume import get_hume, HumeJobCallbackModel, HumeJobModelPredictionResponseModel
from utils.retrieval.rag import retrieve_rag_conversation_context
from utils.webhooks import conversation_created_webhook


def _get_structured(
        uid: str, language_code: str, conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
        force_process: bool = False, retries: int = 1
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

        # from OpenGlass
        if conversation.photos:
            return summarize_open_glass(conversation.photos), False

        # from Omi
        if force_process:
            # reprocess endpoint
            return get_transcript_structure(conversation.get_transcript(False), conversation.started_at, language_code, tz), False

        discarded = should_discard_conversation(conversation.get_transcript(False))
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        return get_transcript_structure(conversation.get_transcript(False), conversation.started_at, language_code, tz), False
    except Exception as e:
        print(e)
        if retries == 2:
            raise HTTPException(status_code=500, detail="Error processing conversation, please try again later")
        return _get_structured(uid, language_code, conversation, force_process, retries + 1)


def _get_conversation_obj(uid: str, structured: Structured,
                          conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation]):
    discarded = structured.title == ''
    if isinstance(conversation, CreateConversation):
        conversation = Conversation(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            **conversation.dict(),
            created_at=datetime.now(timezone.utc),
            discarded=discarded,
            deleted=False,
        )
        if conversation.photos:
            conversations_db.store_conversation_photos(uid, conversation.id, conversation.photos)
    elif isinstance(conversation, ExternalIntegrationCreateConversation):
        create_conversation = conversation
        conversation = Conversation(
            id=str(uuid.uuid4()),
            **conversation.dict(),
            created_at=datetime.now(timezone.utc),
            deleted=False,
            structured=structured,
            discarded=discarded,
        )
        conversation.external_data = create_conversation.dict()
        conversation.app_id = create_conversation.app_id
    else:
        conversation.structured = structured
        conversation.discarded = discarded

    return conversation


def _trigger_apps(uid: str, conversation: Conversation, is_reprocess: bool = False):
    apps: List[App] = get_available_apps(uid)
    filtered_apps = [app for app in apps if app.works_with_memories() and app.enabled]
    conversation.apps_results = []
    threads = []

    def execute_app(app):
        if result := get_app_result(conversation.get_transcript(False), app).strip():
            conversation.apps_results.append(AppResult(app_id=app.id, content=result))
            if not is_reprocess:
                record_app_usage(uid, app.id, UsageHistoryType.memory_created_prompt, conversation_id=conversation.id)

    for app in filtered_apps:
        threads.append(threading.Thread(target=execute_app, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def _extract_facts(uid: str, conversation: Conversation):
    # TODO: maybe instead (once they can edit them) we should not tie it this hard
    memories_db.delete_memories_for_conversation(uid, conversation.id)

    new_facts: List[Memory] = []

    # Extract facts based on conversation source
    if conversation.source == ConversationSource.external_integration:
        text_content = conversation.external_data.get('text')
        if text_content and len(text_content) > 0:
            text_source = conversation.external_data.get('text_source', 'other')
            new_facts = extract_memories_from_text(uid, text_content, text_source)
    else:
        # For regular conversations with transcript segments
        new_facts = new_memories_extractor(uid, conversation.transcript_segments)

    parsed_facts = []
    for fact in new_facts:
        parsed_facts.append(MemoryDB.from_memory(fact, uid, conversation.id, conversation.structured.category, False))
        print('_extract_facts:', fact.category.value.upper(), '|', fact.content)

    if len(parsed_facts) == 0:
        print(f"No facts extracted for conversation {conversation.id}")
        return

    print(f"Saving {len(parsed_facts)} facts for conversation {conversation.id}")
    memories_db.save_memories(uid, [fact.dict() for fact in parsed_facts])


def send_new_facts_notification(token: str, facts: [MemoryDB]):
    facts_str = ", ".join([fact.content for fact in facts])
    message = f"New facts {facts_str}"
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
        uid: str, language_code: str, conversation: Union[Conversation, CreateConversation, ExternalIntegrationCreateConversation],
        force_process: bool = False, is_reprocess: bool = False
) -> Conversation:
    structured, discarded = _get_structured(uid, language_code, conversation, force_process)
    conversation = _get_conversation_obj(uid, structured, conversation)

    if not discarded:
        _trigger_apps(uid, conversation, is_reprocess=is_reprocess)
        threading.Thread(target=save_structured_vector, args=(uid, conversation,)).start() if not is_reprocess else None
        threading.Thread(target=_extract_facts, args=(uid, conversation)).start()

    conversation.status = ConversationStatus.completed
    conversations_db.upsert_conversation(uid, conversation.dict())

    if not is_reprocess:
        threading.Thread(target=conversation_created_webhook, args=(uid, conversation,)).start()
        # Update persona prompts with new conversation
        threading.Thread(target=update_personas_async, args=(uid,)).start()

    # TODO: trigger external integrations here too

    print('process_conversation completed conversation.id=', conversation.id)
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
    return existing
