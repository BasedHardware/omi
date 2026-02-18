import logging
import threading
from typing import List, Any
from datetime import datetime
import os
import requests
import time

import database.notifications as notification_db
from database import mem_db
from database import redis_db
from database.apps import record_app_usage
from database.chat import add_app_message, get_app_messages
from database.goals import get_user_goals
from database.redis_db import get_generic_cache, set_generic_cache
from models.app import App, UsageHistoryType
from models.chat import Message
from models.conversation import Conversation, ConversationSource
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps
from utils.notifications import send_notification
from utils.llm.clients import generate_embedding
from utils.llm.proactive_notification import (
    evaluate_proactive_notification,
    get_proactive_message,
    FREQUENCY_TO_BASE_THRESHOLD,
    MAX_DAILY_NOTIFICATIONS,
)
from utils.llm.usage_tracker import track_usage, Features
from utils.llms.memory import get_prompt_memories
from database.vector_db import query_vectors_by_metadata
import database.conversations as conversations_db
from utils.mentor_notifications import process_mentor_notification

logger = logging.getLogger(__name__)


def _json_serialize_datetime(obj: Any) -> Any:
    """Helper function to recursively convert datetime objects to ISO format strings for JSON serialization"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _json_serialize_datetime(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_json_serialize_datetime(item) for item in obj]
    else:
        return obj


PROACTIVE_NOTI_LIMIT_SECONDS = 30  # 1 noti / 30s for external apps
MENTOR_NOTI_LIMIT_SECONDS = 300  # 5 min gap for mentor notifications


def get_github_docs_content(repo="BasedHardware/omi", path="docs/doc"):
    """
    Recursively retrieves content from GitHub docs folder and subfolders using GitHub API.
    Returns a dict mapping file paths to their raw content.

    If cached, returns cached content. (24 hours)
    So any changes to the docs will take 24 hours to be reflected.
    """
    if cached := get_generic_cache(f'get_github_docs_content_{repo}_{path}'):
        return cached
    docs_content = {}
    headers = {"Authorization": f"token {os.getenv('GITHUB_TOKEN')}"}

    def get_contents(path):
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Failed to fetch contents for {path}: {response.status_code}")
            return

        contents = response.json()

        if not isinstance(contents, list):
            return

        for item in contents:
            if item["type"] == "file" and (item["name"].endswith(".md") or item["name"].endswith(".mdx")):
                # Get raw content for documentation files
                raw_response = requests.get(item["download_url"], headers=headers)
                if raw_response.status_code == 200:
                    docs_content[item["path"]] = raw_response.text

            elif item["type"] == "dir":
                # Recursively process subfolders
                get_contents(item["path"])

    get_contents(path)
    set_generic_cache(f'get_github_docs_content_{repo}_{path}', docs_content, 60 * 24 * 7)
    return docs_content


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************


def trigger_external_integrations(uid: str, conversation: Conversation) -> list:
    """ON CONVERSATION CREATED"""
    if not conversation or conversation.discarded:
        return []

    apps: List[App] = get_available_apps(uid)
    filtered_apps = [app for app in apps if app.triggers_on_conversation_creation() and app.enabled]
    if not filtered_apps:
        return []

    threads = []
    results = {}

    def _single(app: App):
        if not app.external_integration.webhook_url:
            return

        conversation_dict = conversation.as_dict_cleaned_dates()

        # Ignore external data on workflow
        if conversation.source == ConversationSource.workflow and 'external_data' in conversation_dict:
            conversation_dict['external_data'] = None

        url = app.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            payload = _json_serialize_datetime(conversation_dict)
            response = requests.post(
                url,
                json=payload,
                timeout=30,
            )  # TODO: failing?
            if response.status_code != 200:
                print('App integration failed', app.id, 'status:', response.status_code, 'result:', response.text[:100])
                return

            if app.uid is not None:
                if app.uid != uid:
                    record_app_usage(
                        uid,
                        app.id,
                        UsageHistoryType.memory_created_external_integration,
                        conversation_id=conversation.id,
                    )
            else:
                record_app_usage(
                    uid, app.id, UsageHistoryType.memory_created_external_integration, conversation_id=conversation.id
                )

            # print('response', response.json())
            if message := response.json().get('message', ''):
                results[app.id] = message
        except Exception as e:
            print(f"Plugin integration error: {e}")
            return

    for app in filtered_apps:
        threads.append(threading.Thread(target=_single, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]

    messages = []
    for key, message in results.items():
        if not message:
            continue
        messages.append(add_app_message(message, key, uid, conversation.id))
    return messages


async def trigger_realtime_integrations(uid: str, segments: list[dict], conversation_id: str | None):
    print("trigger_realtime_integrations", uid)
    """REALTIME STREAMING"""
    _trigger_realtime_integrations(uid, segments, conversation_id)


async def trigger_realtime_audio_bytes(uid: str, sample_rate: int, data: bytearray):
    print("trigger_realtime_audio_bytes", uid)
    """REALTIME AUDIO STREAMING"""
    _trigger_realtime_audio_bytes(uid, sample_rate, data)


# proactive notification
def _retrieve_contextual_memories(uid: str, user_context):
    vector = generate_embedding(user_context.get('question', '')) if user_context.get('question') else [0] * 3072
    print("query_vectors vector:", vector[:5])

    date_filters = {}  # not support yet
    filters = user_context.get('filters', {})
    memories_id = query_vectors_by_metadata(
        uid,
        vector,
        dates_filter=[date_filters.get("start"), date_filters.get("end")],
        people=filters.get("people", []),
        topics=filters.get("topics", []),
        entities=filters.get("entities", []),
        dates=filters.get("dates", []),
    )
    return conversations_db.get_conversations_by_id(uid, memories_id)


def _hit_proactive_notification_rate_limits(uid: str, app: App):
    sent_at = mem_db.get_proactive_noti_sent_at(uid, app.id)
    if sent_at and time.time() - sent_at < PROACTIVE_NOTI_LIMIT_SECONDS:
        return True

    # remote
    sent_at = redis_db.get_proactive_noti_sent_at(uid, app.id)
    if not sent_at:
        return False
    ttl = redis_db.get_proactive_noti_sent_at_ttl(uid, app.id)
    if ttl > 0:
        mem_db.set_proactive_noti_sent_at(uid, app.id, int(time.time() + ttl), ttl=ttl)

    return time.time() - sent_at < PROACTIVE_NOTI_LIMIT_SECONDS


def _set_proactive_noti_sent_at(uid: str, app: App):
    ts = time.time()
    mem_db.set_proactive_noti_sent_at(uid, app, int(ts), ttl=PROACTIVE_NOTI_LIMIT_SECONDS)
    redis_db.set_proactive_noti_sent_at(uid, app.id, int(ts), ttl=PROACTIVE_NOTI_LIMIT_SECONDS)


def _process_mentor_proactive_notification(uid: str, conversation_messages: List[dict]):
    """
    Evaluate and send a mentor proactive notification using rich context.

    Gathers user facts, goals, relevant past conversations, recent notification history,
    and the current conversation, then makes a single structured LLM call to decide
    whether to send a notification.

    Args:
        uid: User ID
        conversation_messages: List of message dicts with 'text', 'timestamp', 'is_user'
    """
    # 1. Get frequency setting
    frequency = notification_db.get_mentor_notification_frequency(uid)
    if frequency == 0:
        return None

    base_threshold = FREQUENCY_TO_BASE_THRESHOLD.get(frequency)
    if base_threshold is None:
        return None

    # 2. Rate limit check (5 min gap)
    mentor_sent_at = mem_db.get_proactive_noti_sent_at(uid, 'mentor')
    if mentor_sent_at and time.time() - mentor_sent_at < MENTOR_NOTI_LIMIT_SECONDS:
        logger.info(f"Mentor notification rate limited for user {uid}")
        return None
    if not mentor_sent_at:
        redis_sent_at = redis_db.get_proactive_noti_sent_at(uid, 'mentor')
        if redis_sent_at and time.time() - redis_sent_at < MENTOR_NOTI_LIMIT_SECONDS:
            logger.info(f"Mentor notification rate limited for user {uid}")
            return None

    # 3. Daily cap check
    daily_count = redis_db.get_daily_notification_count(uid)
    if daily_count >= MAX_DAILY_NOTIFICATIONS:
        logger.info(f"Mentor notification daily cap reached for user {uid} ({daily_count}/{MAX_DAILY_NOTIFICATIONS})")
        return None

    # 4. Gather rich context
    user_name, user_facts = get_prompt_memories(uid)

    # Active goals
    try:
        goals = get_user_goals(uid, limit=3)
    except Exception as e:
        logger.error(f"Failed to fetch goals for user {uid}: {e}")
        goals = []

    # Format current conversation with speaker labels
    lines = []
    for msg in conversation_messages:
        speaker = user_name if msg.get('is_user') else "other"
        lines.append(f"[{speaker}]: {msg['text']}")
    current_conversation = "\n".join(lines)

    # Vector search for relevant past conversations
    past_conversations_text = ""
    try:
        if current_conversation:
            vector = generate_embedding(current_conversation[:1000])
            memory_ids = query_vectors_by_metadata(uid, vector, [], [], [], [], [])
            if memory_ids:
                past_convos = conversations_db.get_conversations_by_id(uid, memory_ids)
                if past_convos:
                    past_conversations_text = Conversation.conversations_to_string(past_convos)
    except Exception as e:
        logger.error(f"Failed to retrieve past conversations for user {uid}: {e}")

    # Recent notifications (for LLM self-regulation)
    recent_notifications_text = ""
    try:
        recent_notis = get_app_messages(uid, 'mentor', limit=20)
        if recent_notis:
            noti_lines = []
            for noti in reversed(recent_notis):
                created = noti.get('created_at', '')
                text = noti.get('text', '')
                if text:
                    noti_lines.append(f"[{created}] {text}")
            recent_notifications_text = "\n".join(noti_lines)
    except Exception as e:
        logger.error(f"Failed to fetch recent notifications for user {uid}: {e}")

    # 5. Single LLM call with structured output
    try:
        result = evaluate_proactive_notification(
            user_name=user_name,
            user_facts=user_facts,
            goals=goals,
            past_conversations=past_conversations_text,
            current_conversation=current_conversation,
            recent_notifications=recent_notifications_text,
            frequency=frequency,
        )
    except Exception as e:
        logger.error(f"Failed to evaluate proactive notification for user {uid}: {e}")
        return None

    # 6. Confidence gate
    if not result.has_advice or not result.advice:
        logger.info(f"Mentor notification: no advice for user {uid}")
        return None

    if result.advice.confidence < base_threshold:
        logger.info(
            f"Mentor notification below threshold for user {uid}: "
            f"{result.advice.confidence:.2f} < {base_threshold:.2f}"
        )
        return None

    notification_text = result.advice.notification_text
    if not notification_text or len(notification_text) < 5:
        return None
    if len(notification_text) > 300:
        notification_text = notification_text[:300]

    # 7. Send notification, increment daily count, set rate limit
    send_app_notification(uid, 'Omi', 'mentor', notification_text)

    redis_db.incr_daily_notification_count(uid)

    ts = time.time()
    mem_db.set_proactive_noti_sent_at(uid, 'mentor', int(ts), ttl=MENTOR_NOTI_LIMIT_SECONDS)
    redis_db.set_proactive_noti_sent_at(uid, 'mentor', int(ts), ttl=MENTOR_NOTI_LIMIT_SECONDS)

    logger.info(
        f"Mentor notification sent to user {uid}: "
        f"confidence={result.advice.confidence:.2f} category={result.advice.category}"
    )
    return notification_text


def _process_proactive_notification(uid: str, app: App, data):
    """Process proactive notifications for external/third-party apps."""
    if not app.has_capability("proactive_notification") or not data:
        print(f"App {app.id} is not proactive_notification or data invalid", uid)
        return None

    # rate limits
    if _hit_proactive_notification_rate_limits(uid, app):
        print(f"App {app.id} is reach rate limits 1 noti per user per {PROACTIVE_NOTI_LIMIT_SECONDS}s", uid)
        return None

    max_prompt_char_limit = 128000
    min_message_char_limit = 5

    prompt = data.get('prompt', '')
    if len(prompt) > max_prompt_char_limit:
        send_app_notification(
            uid,
            app.name,
            app.id,
            f"Prompt too long: {len(prompt)}/{max_prompt_char_limit} characters. Please shorten.",
        )
        print(f"App {app.id}, prompt too long, length: {len(prompt)}/{max_prompt_char_limit}", uid)
        return None

    filter_scopes = app.filter_proactive_notification_scopes(data.get('params', []))

    user_name, user_facts = get_prompt_memories(uid)

    context = None
    if 'user_context' in filter_scopes:
        memories = _retrieve_contextual_memories(uid, data.get('context', {}))
        if len(memories) > 0:
            context = Conversation.conversations_to_string(memories)

    chat_messages = []
    if 'user_chat' in filter_scopes:
        chat_messages = list(reversed([Message(**msg) for msg in get_app_messages(uid, app.id, limit=10)]))

    message = get_proactive_message(uid, prompt, filter_scopes, context, chat_messages, user_name, user_facts)
    if not message or len(message) < min_message_char_limit:
        print(f"Plugins {app.id}, message too short", uid)
        return None

    send_app_notification(uid, app.name, app.id, message)

    _set_proactive_noti_sent_at(uid, app)
    return message


def _trigger_realtime_audio_bytes(uid: str, sample_rate: int, data: bytearray):
    apps: List[App] = get_available_apps(uid)
    filtered_apps = [app for app in apps if app.triggers_realtime_audio_bytes() and app.enabled]
    if not filtered_apps:
        return {}

    threads = []
    results = {}

    def _single(app: App):
        if not app.external_integration.webhook_url:
            return

        url = app.external_integration.webhook_url
        url += f'?sample_rate={sample_rate}&uid={uid}'
        try:
            response = requests.post(url, data=data, headers={'Content-Type': 'application/octet-stream'}, timeout=15)
            print('trigger_realtime_audio_bytes', app.id, 'status:', response.status_code)
        except Exception as e:
            print(f"Plugin integration error: {e}")
            return

    for app in filtered_apps:
        threads.append(threading.Thread(target=_single, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]

    return results


def _trigger_realtime_integrations(uid: str, segments: List[dict], conversation_id: str | None) -> dict:
    # Process mentor notification first (built-in feature)
    mentor_results = {}
    conversation_messages = process_mentor_notification(uid, segments)
    if conversation_messages:
        with track_usage(uid, Features.REALTIME_INTEGRATIONS):
            mentor_message = _process_mentor_proactive_notification(uid, conversation_messages)
        if mentor_message:
            mentor_results['mentor'] = mentor_message

    apps: List[App] = get_available_apps(uid)
    filtered_apps = [app for app in apps if app.triggers_realtime() and app.enabled]
    if not filtered_apps:
        # Return mentor results if any, even if no external apps
        if mentor_results:
            messages = []
            for key, message in mentor_results.items():
                messages.append(add_app_message(message, key, uid))
            return messages
        return {}

    threads = []
    results = {}

    def _single(app: App):
        if not app.external_integration.webhook_url:
            return

        url = app.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            response = requests.post(url, json={"session_id": uid, "segments": segments}, timeout=10)
            if response.status_code != 200:
                print(
                    'trigger_realtime_integrations',
                    app.id,
                    'status: ',
                    response.status_code,
                    'results:',
                    response.text[:100],
                )
                return

            if (app.uid is None or app.uid != uid) and conversation_id is not None:
                record_app_usage(
                    uid,
                    app.id,
                    UsageHistoryType.transcript_processed_external_integration,
                    conversation_id=conversation_id,
                )

            response_data = response.json()
            if not response_data:
                return

            # message
            message = response_data.get('message', '')
            # print('Plugin', plugin.id, 'response message:', message)
            if message and len(message) > 5:
                send_app_notification(uid, app.name, app.id, message)
                results[app.id] = message

            # proactive_notification
            noti = response_data.get('notification', None)
            # print('Plugin', plugin.id, 'response notification:', noti)
            if app.has_capability("proactive_notification"):
                with track_usage(uid, Features.REALTIME_INTEGRATIONS):
                    message = _process_proactive_notification(uid, app, noti)
                if message:
                    results[app.id] = message

        except Exception as e:
            print(f"App integration error: {e}")
            return

    for app in filtered_apps:
        threads.append(threading.Thread(target=_single, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]

    # Merge mentor results with app results
    all_results = {**mentor_results, **results}

    messages = []
    for key, message in all_results.items():
        if not message:
            continue
        messages.append(add_app_message(message, key, uid))

    return messages


def send_app_notification(user_id: str, app_name: str, app_id: str, message: str, target: str = 'app'):
    navigate_to = '/chat/omi' if target == 'main' else f'/chat/{app_id}'
    ai_message = NotificationMessage(
        text=message,
        app_id=app_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
        navigate_to=navigate_to,
    )

    send_notification(user_id, app_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
