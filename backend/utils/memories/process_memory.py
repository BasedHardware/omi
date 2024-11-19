import datetime
import random
import threading
import uuid
from datetime import timezone
from typing import Union, Tuple

from fastapi import HTTPException

import database.facts as facts_db
import database.memories as memories_db
import database.notifications as notification_db
import database.tasks as tasks_db
import database.trends as trends_db
from database.plugins import record_plugin_usage
from database.vector_db import upsert_vector2, update_vector_metadata
from models.app import App
from models.facts import FactDB
from models.memory import *
from models.plugin import Plugin, UsageHistoryType
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.trend import Trend
from utils.apps import get_available_apps
from utils.llm import obtain_emotional_message, retrieve_metadata_fields_from_transcript
from utils.llm import summarize_open_glass, get_transcript_structure, generate_embedding, \
    get_plugin_result, should_discard_memory, summarize_experience_text, new_facts_extractor, \
    trends_extractor
from utils.notifications import send_notification
from utils.other.hume import get_hume, HumeJobCallbackModel, HumeJobModelPredictionResponseModel
from utils.plugins import get_plugins_data, get_plugins_data_from_db
from utils.retrieval.rag import retrieve_rag_memory_context
from utils.webhooks import memory_created_webhook


def _get_structured(
        uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
        force_process: bool = False, retries: int = 1
) -> Tuple[Structured, bool]:
    try:
        tz = notification_db.get_user_time_zone(uid)
        if memory.source == MemorySource.workflow:
            if memory.text_source == WorkflowMemorySource.audio:
                structured = get_transcript_structure(memory.text, memory.started_at, language_code, tz)
                return structured, False

            if memory.text_source == WorkflowMemorySource.other:
                structured = summarize_experience_text(memory.text)
                return structured, False

            # not workflow memory source support
            raise HTTPException(status_code=400, detail='Invalid workflow memory source')

        # from OpenGlass
        if memory.photos:
            return summarize_open_glass(memory.photos), False

        # from Friend
        if force_process:
            # reprocess endpoint
            return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code, tz), False

        discarded = should_discard_memory(memory.get_transcript(False))
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code, tz), False
    except Exception as e:
        print(e)
        if retries == 2:
            raise HTTPException(status_code=500, detail="Error processing memory, please try again later")
        return _get_structured(uid, language_code, memory, force_process, retries + 1)


def _get_memory_obj(uid: str, structured: Structured, memory: Union[Memory, CreateMemory, WorkflowCreateMemory]):
    discarded = structured.title == ''
    if isinstance(memory, CreateMemory):
        memory = Memory(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            **memory.dict(),
            created_at=datetime.now(timezone.utc),
            discarded=discarded,
            deleted=False,
        )
        if memory.photos:
            memories_db.store_memory_photos(uid, memory.id, memory.photos)
    elif isinstance(memory, WorkflowCreateMemory):
        create_memory = memory
        memory = Memory(
            id=str(uuid.uuid4()),
            **memory.dict(),
            created_at=datetime.now(timezone.utc),
            deleted=False,
            structured=structured,
            discarded=discarded,
        )
        memory.external_data = create_memory.dict()
    else:
        memory.structured = structured
        memory.discarded = discarded

    return memory


def _trigger_plugins(uid: str, memory: Memory, is_reprocess: bool = False):
    plugins: List[App] = get_available_apps(uid)
    filtered_plugins = [plugin for plugin in plugins if plugin.works_with_memories() and plugin.enabled]
    memory.plugins_results = []
    threads = []

    def execute_plugin(plugin):
        if result := get_plugin_result(memory.get_transcript(False), plugin).strip():
            memory.plugins_results.append(PluginResult(plugin_id=plugin.id, content=result))
            if not is_reprocess:
                record_plugin_usage(uid, plugin.id, UsageHistoryType.memory_created_prompt, memory_id=memory.id)

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=execute_plugin, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def _extract_facts(uid: str, memory: Memory):
    # TODO: maybe instead (once they can edit them) we should not tie it this hard
    facts_db.delete_facts_for_memory(uid, memory.id)
    new_facts = new_facts_extractor(uid, memory.transcript_segments)
    parsed_facts = []
    for fact in new_facts:
        parsed_facts.append(FactDB.from_fact(fact, uid, memory.id, memory.structured.category))
        print('_extract_facts:', fact.category.value.upper(), '|', fact.content)
    facts_db.save_facts(uid, [fact.dict() for fact in parsed_facts])


def _extract_trends(memory: Memory):
    extracted_items = trends_extractor(memory)
    parsed = [Trend(category=item.category, topics=[item.topic], type=item.type) for item in extracted_items]
    trends_db.save_trends(memory, parsed)


def save_structured_vector(uid: str, memory: Memory, update_only: bool = False):
    vector = generate_embedding(str(memory.structured)) if not update_only else None

    segments = [t.dict() for t in memory.transcript_segments]
    metadata = retrieve_metadata_fields_from_transcript(uid, memory.created_at, segments)
    metadata['created_at'] = int(memory.created_at.timestamp())
    if not update_only:
        print('save_structured_vector creating vector')
        upsert_vector2(uid, memory, vector, metadata)
    else:
        print('save_structured_vector updating metadata')
        update_vector_metadata(uid, memory.id, metadata)


def process_memory(
        uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
        force_process: bool = False, is_reprocess: bool = False
) -> Memory:
    structured, discarded = _get_structured(uid, language_code, memory, force_process)
    memory = _get_memory_obj(uid, structured, memory)

    if not discarded:
        _trigger_plugins(uid, memory, is_reprocess=is_reprocess)
        threading.Thread(target=save_structured_vector, args=(uid, memory,)).start() if not is_reprocess else None
        threading.Thread(target=_extract_facts, args=(uid, memory)).start()

    memory.status = MemoryStatus.completed
    memories_db.upsert_memory(uid, memory.dict())

    if not is_reprocess:
        threading.Thread(target=memory_created_webhook, args=(uid, memory,)).start()

    # TODO: trigger external integrations here too

    print('process_memory completed memory.id=', memory.id)
    return memory


def process_user_emotion(uid: str, language_code: str, memory: Memory, urls: [str]):
    print('process_user_emotion memory.id=', memory.id)

    # save task
    now = datetime.now()
    task = Task(
        id=str(uuid.uuid4()),
        action=TaskAction.HUME_MERSURE_USER_EXPRESSION,
        user_uid=uid,
        memory_id=memory.id,
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
        memories_db.store_model_emotion_predictions_result(task.user_uid, task.memory_id, provider,
                                                           callback.predictions)

    # Memory
    memory_data = memories_db.get_memory(uid, task.memory_id)
    if memory_data is None:
        print(f"Memory is not found. Uid: {uid}. Memory: {task.memory_id}")
        return

    memory = Memory(**memory_data)

    # Get prediction
    predictions = callback.predictions
    print(predictions)
    if len(predictions) == 0 or len(predictions[0].emotions) == 0:
        print(f"Can not predict user's expression. Uid: {uid}")
        return

    # Filter users emotions only
    users_frames = []
    for seg in filter(lambda seg: seg.is_user and 0 <= seg.start < seg.end, memory.transcript_segments):
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
    title = "Omi"
    context_str, _ = retrieve_rag_memory_context(uid, memory)

    response: str = obtain_emotional_message(uid, memory, context_str, emotion)
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
