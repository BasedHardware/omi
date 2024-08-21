import random
import datetime
import threading
import uuid
from typing import Union

import asyncio

from fastapi import HTTPException

import database.memories as memories_db
from database.vector_db import upsert_vector
import database.tasks as tasks_db
import database.notifications as notification_db
from models.memory import *
from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
from models.plugin import Plugin
from utils.llm import summarize_open_glass, get_transcript_structure, generate_embedding, \
    get_plugin_result, should_discard_memory, summarize_experience_text
from utils.plugins import get_plugins_data
from utils.notifications import send_notification
from utils.other.hume import get_hume, HumeJobCallbackModel

from utils.llm import qa_emotional_rag
from utils.retrieval.rag import retrieve_rag_memory_context


def _get_structured(
        uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
        force_process: bool = False, retries: int = 1
) -> Structured:
    try:
        if memory.source == MemorySource.workflow:
            if memory.text_source == WorkflowMemorySource.audio:
                structured = get_transcript_structure(memory.text, memory.started_at, language_code)
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
            return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code), False

        discarded = should_discard_memory(memory.get_transcript(False))
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code), False
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
            created_at=datetime.utcnow(),
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
            created_at=datetime.utcnow(),
            deleted=False,
            structured=structured,
            discarded=discarded,
        )
        memory.external_data = create_memory.dict()
    else:
        memory.structured = structured
        memory.discarded = discarded

    return memory


def _trigger_plugins(uid: str, transcript: str, memory: Memory):
    plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
    filtered_plugins = [plugin for plugin in plugins if plugin.works_with_memories() and plugin.enabled]
    threads = []

    def execute_plugin(plugin):
        if result := get_plugin_result(transcript, plugin).strip():
            memory.plugins_results.append(PluginResult(plugin_id=plugin.id, content=result))

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=execute_plugin, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def process_memory(uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
                   force_process: bool = False):
    structured, discarded = _get_structured(uid, language_code, memory, force_process)
    memory = _get_memory_obj(uid, structured, memory)

    if not discarded:
        vector = generate_embedding(str(structured))
        upsert_vector(uid, memory, vector)
        _trigger_plugins(uid, memory.get_transcript(False), memory)  # async

    memories_db.upsert_memory(uid, memory.dict())
    print('process_memory memory.id=', memory.id)

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

    # Get prediction
    uid = task.user_uid
    predictions = callback.predictions
    if len(predictions) == 0 or len(predictions[0].emotions) == 0:
        print(f"Can not predict user's expression. Uid: {uid}")
        return

    # Top emotion
    emotion_filters = []
    prediction = callback.predictions[0]
    emotions = prediction.get_top_emotion_names(1, 0.5)
    if len(emotion_filters) > 0:
        emotions = filter(lambda emotion: emotion in emotion_filters, emotions)
    if len(emotions) == 0:
        print(f"Can not extract users emmotion. uid: {uid}")
        return

    emotion = ','.join(emotions)
    print(f"Emotion Uid: {uid} {emotion}")

    # Ask llms about notification content
    title = "Omi"
    memory_data = memories_db.get_memory(uid, task.memory_id)
    if memory_data is None:
        print(f"Memory is not found. Uid: {uid}. Memory: {task.memory_id}")
        return

    memory = Memory(**memory_data)

    context_str, memories = retrieve_rag_memory_context(uid, memory)
    response: str = qa_emotional_rag(context_str, memories, emotion)
    message = response
    if message is None or len(message) == 0:
        print(f"Message is too short. Uid: {uid}. Message: {message}")
        return

    print(title)
    print(message)

    # Send the notification
    token = notification_db.get_token_only(uid)
    if token is None:
        print(f"User token is none. Uid: {uid}")
        return

    send_notification(token, title, message, None)

    return
