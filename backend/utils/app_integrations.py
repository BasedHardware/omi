import logging
import threading
from typing import List, Any
from datetime import datetime
import os
import requests
import time

from langchain_core.messages import SystemMessage, HumanMessage

import database.notifications as notification_db
from database import mem_db
from database import redis_db
from database.apps import record_app_usage
from database.chat import add_app_message, get_app_messages
from database.goals import get_user_goals
from database.redis_db import get_generic_cache, set_generic_cache
from models.app import App, ProactiveNotification, UsageHistoryType
from models.chat import Message
from models.conversation import Conversation, ConversationSource
from models.notification_message import NotificationMessage
from utils.apps import get_available_apps
from utils.notifications import send_notification
from utils.llm.clients import generate_embedding, llm_mini
from utils.llm.proactive_notification import get_proactive_message
from utils.llm.usage_tracker import track_usage, Features
from utils.llms.memory import get_prompt_memories
from database.vector_db import query_vectors_by_metadata
import database.conversations as conversations_db

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


PROACTIVE_NOTI_LIMIT_SECONDS = 30  # 1 noti / 30s


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


def _process_tools(
    uid: str, system_prompt: str, user_message: str, tools: list, confidence_threshold: float
) -> list[dict]:
    """
    Run LLM tool calling and filter results by confidence threshold.

    Args:
        uid: User ID (for logging)
        system_prompt: System prompt for the LLM
        user_message: User message with conversation context
        tools: Tool definitions (OpenAI function-calling format)
        confidence_threshold: Minimum confidence to accept a tool result

    Returns:
        List of accepted notification dicts. Empty list if no triggers apply.
    """
    if not tools:
        return []

    try:
        llm_messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]

        llm_with_tools = llm_mini.bind_tools(tools, tool_choice="auto")
        resp = llm_with_tools.invoke(llm_messages)

        if not resp.tool_calls:
            logger.info(f"proactive_tool_decision uid={uid} triggered=false")
            return []

        results = []
        for tool_call in resp.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            confidence = tool_args.get("confidence", 0)
            notification_text = tool_args.get("notification_text", "")

            logger.info(
                f"proactive_tool_decision uid={uid} triggered=true "
                f"tool={tool_name} confidence={confidence:.2f} "
                f"rationale={tool_args.get('rationale', tool_args.get('conflict_description', ''))[:100]}"
            )

            if confidence < confidence_threshold:
                logger.info(f"proactive_tool_below_threshold uid={uid} tool={tool_name} confidence={confidence:.2f}")
                continue

            if not notification_text or len(notification_text) < 5:
                logger.warning(f"proactive_tool_empty_text uid={uid} tool={tool_name}")
                continue

            results.append(
                {
                    "notification_text": notification_text,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                }
            )

        logger.info(f"proactive_tool_results uid={uid} total_calls={len(resp.tool_calls)} accepted={len(results)}")
        return results

    except Exception as e:
        logger.error(f"proactive_tool_error uid={uid} error={e}")
        return []


def _build_mentor_tool_context(uid: str, conversation_messages: list[dict]) -> tuple[str, str]:
    """Build system prompt and user message for mentor tool calling."""
    user_name, user_facts = get_prompt_memories(uid)
    goals = get_user_goals(uid)
    goals_text = (
        "\n".join(f"- {g.get('title', g.get('description', 'Unnamed goal'))}" for g in goals)
        if goals
        else "No goals set."
    )

    lines = []
    for msg in conversation_messages:
        speaker = user_name if msg.get('is_user') else "other"
        lines.append(f"[{speaker}]: {msg['text']}")
    conversation_text = "\n".join(lines)

    system_prompt = (
        f"You are {user_name}'s proactive AI mentor and trusted friend. "
        "You may call multiple tools if multiple triggers clearly apply. "
        "Call a tool ONLY when the conversation clearly matches a trigger. "
        "If no trigger applies, respond with no tool calls.\n\n"
        "IMPORTANT RULES:\n"
        "- notification_text must be <300 chars, warm, and personal — like texting a close friend\n"
        "- Reference specific details from the conversation (names, situations, feelings)\n"
        "- For arguments: validate feelings first, then offer perspective. Don't be clinical.\n"
        "- For goal misalignment: ONLY trigger when user is ACTIVELY contradicting a goal. "
        "Do NOT trigger when they are doing something aligned with or neutral to their goals.\n"
        "- For emotional support: suggest ONE concrete action they can do RIGHT NOW\n"
        "- Always end with a gentle question or suggestion, never a lecture"
    )

    user_message = (
        f"Conversation:\n{conversation_text}\n\n"
        f"What we know about {user_name}:\n{user_facts}\n\n"
        f"{user_name}'s active goals:\n{goals_text}"
    )

    return system_prompt, user_message


def _process_proactive_notification(uid: str, app: App, tools_data, tools: list = None, tool_uses: bool = False):
    if not app.has_capability("proactive_notification") or not tools_data:
        print(f"App {app.id} is not proactive_notification or data invalid", uid)
        return None

    # rate limits
    if _hit_proactive_notification_rate_limits(uid, app):
        print(f"App {app.id} is reach rate limits 1 noti per user per {PROACTIVE_NOTI_LIMIT_SECONDS}s", uid)
        return None

    # Tool-based proactive notifications.
    # All tool notifications from one analysis cycle are sent together (up to 3,
    # one per tool type). The rate limit above blocks the NEXT cycle (30s cooldown),
    # not individual notifications within one cycle. Per CTO request.
    if tool_uses and tools and tools_data.get('messages'):
        from utils.mentor_notifications import PROACTIVE_CONFIDENCE_THRESHOLD

        system_prompt, user_message = _build_mentor_tool_context(uid, tools_data['messages'])
        tool_results = _process_tools(uid, system_prompt, user_message, tools, PROACTIVE_CONFIDENCE_THRESHOLD)
        if tool_results:
            messages_sent = []
            for noti in tool_results:
                send_app_notification(uid, app.name, app.id, noti['notification_text'])
                logger.info(f"Sent proactive tool notification to user {uid} (tool: {noti.get('tool_name')})")
                messages_sent.append(noti['notification_text'])
            _set_proactive_noti_sent_at(uid, app)
            return "\n\n".join(messages_sent)
        # Tools didn't fire — fall through to prompt-based path

    max_prompt_char_limit = 128000
    min_message_char_limit = 5

    prompt = tools_data.get('prompt', '')
    if len(prompt) > max_prompt_char_limit:
        send_app_notification(
            uid,
            app.name,
            app.id,
            f"Prompt too long: {len(prompt)}/{max_prompt_char_limit} characters. Please shorten.",
        )
        print(f"App {app.id}, prompt too long, length: {len(prompt)}/{max_prompt_char_limit}", uid)
        return None

    filter_scopes = app.filter_proactive_notification_scopes(tools_data.get('params', []))

    # context
    context = None
    if 'user_context' in filter_scopes:
        memories = _retrieve_contextual_memories(uid, tools_data.get('context', {}))
        if len(memories) > 0:
            context = Conversation.conversations_to_string(memories)

    # messages
    messages = []
    if 'user_chat' in filter_scopes:
        messages = list(reversed([Message(**msg) for msg in get_app_messages(uid, app.id, limit=10)]))

    # retrive message
    message = get_proactive_message(uid, prompt, filter_scopes, context, messages)
    if not message or len(message) < min_message_char_limit:
        print(f"Plugins {app.id}, message too short", uid)
        return None

    # send notification
    send_app_notification(uid, app.name, app.id, message)

    # set rate
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
    from utils.mentor_notifications import process_mentor_notification

    mentor_results = {}
    mentor_notification = process_mentor_notification(uid, segments)
    if mentor_notification:
        # Create a virtual "Omi" app for processing
        mentor_app = App(
            id='mentor',
            name='Omi',
            category='productivity',
            author='Omi',
            description='AI providing real-time guidance during conversations',
            image='https://raw.githubusercontent.com/BasedHardware/Omi/main/assets/images/app_logo.png',
            capabilities={'proactive_notification'},
            enabled=True,
            proactive_notification=ProactiveNotification(
                scopes={'user_name', 'user_facts', 'user_context', 'user_chat'}
            ),
        )
        with track_usage(uid, Features.REALTIME_INTEGRATIONS):
            mentor_message = _process_proactive_notification(
                uid,
                mentor_app,
                mentor_notification,
                tools=mentor_notification.get('tools'),
                tool_uses=True,
            )
        if mentor_message:
            mentor_results['mentor'] = mentor_message
            print(f"Sent mentor notification to user {uid}")

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


def send_app_notification(user_id: str, app_name: str, app_id: str, message: str):
    ai_message = NotificationMessage(
        text=message,
        app_id=app_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
        navigate_to=f'/chat/{app_id}',
    )

    send_notification(user_id, app_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
