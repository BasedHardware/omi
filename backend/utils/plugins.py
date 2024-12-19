import threading
from typing import List, Optional
import os
import requests
import time

import database.notifications as notification_db
from database import mem_db
from database import redis_db
from database.apps import get_private_apps_db, get_public_apps_db, record_app_usage
from database.chat import add_plugin_message, get_plugin_messages
from database.redis_db import get_enabled_plugins, get_generic_cache, \
    set_generic_cache, get_plugins_reviews, get_plugins_installs_count
from models.app import App
from models.chat import Message
from models.memory import Memory, MemorySource
from models.notification_message import NotificationMessage
from models.plugin import Plugin, UsageHistoryType
from utils.apps import get_available_apps, weighted_rating
from utils.notifications import send_notification
from utils.llm import (
    generate_embedding,
    get_proactive_message
)
from database.vector_db import query_vectors_by_metadata
import database.memories as memories_db

PROACTIVE_NOTI_LIMIT_SECONDS = 30  # 1 noti / 30s


def get_github_docs_content(repo="BasedHardware/omi", path="docs/docs"):
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


# ***********************************
# ************* BASICS **************
# ***********************************


def get_plugins_data_from_db(uid: str, include_reviews: bool = False) -> List[Plugin]:
    private_data = []
    public_data = []
    all_plugins = []
    # if cachedPlugins := get_generic_cache('get_public_plugins_data'):
    #     print('get_public_plugins_data from cache')
    #     public_data = cachedPlugins
    #     private_data = get_private_plugins_db(uid)
    #     pass
    # else:
    private_data = get_private_apps_db(uid)
    public_data = get_public_apps_db(uid)
    # set_generic_cache('get_public_plugins_data', public_data, 60 * 10)  # 10 minutes cached
    user_enabled = set(get_enabled_plugins(uid))
    all_plugins = private_data + public_data

    plugin_ids = [plugin['id'] for plugin in all_plugins]
    plugins_install = get_plugins_installs_count(plugin_ids)
    plugins_review = get_plugins_reviews(plugin_ids) if include_reviews else {}

    plugins = []
    for plugin in all_plugins:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        plugin_dict['installs'] = plugins_install.get(plugin['id'], 0)
        if include_reviews:
            reviews = plugins_review.get(plugin['id'], {})
            sorted_reviews = reviews.values()
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
            plugin_dict['reviews'] = []
            plugin_dict['user_review'] = reviews.get(uid)
            plugin_dict['rating_avg'] = rating_avg
            plugin_dict['rating_count'] = len(sorted_reviews)
        plugins.append(Plugin(**plugin_dict))
    if include_reviews:
        plugins = sorted(plugins, key=weighted_rating, reverse=True)
    return plugins


def get_plugins_data(uid: str, include_reviews: bool = False) -> List[Plugin]:
    # print('get_plugins_data', uid, include_reviews)
    if data := get_generic_cache('get_plugins_data'):
        print('get_plugins_data from cache')
        pass
    else:
        response = requests.get('https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json')
        if response.status_code != 200:
            return []
        data = response.json()
        set_generic_cache('get_plugins_data', data, 60 * 10)  # 10 minutes cached

    user_enabled = set(get_enabled_plugins(uid)) if uid else []
    # print('get_plugins_data, user_enabled', user_enabled)

    plugin_ids = [plugin['id'] for plugin in data]
    plugins_install = get_plugins_installs_count(plugin_ids)
    plugins_review = get_plugins_reviews(plugin_ids) if include_reviews else {}

    plugins = []
    for plugin in data:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        plugin_dict['installs'] = plugins_install.get(plugin['id'], 0)
        if include_reviews:
            reviews = plugins_review.get(plugin['id'], {})
            sorted_reviews = reviews.values()

            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
            plugin_dict['reviews'] = []
            plugin_dict['user_review'] = reviews.get(uid)
            plugin_dict['rating_avg'] = rating_avg
            plugin_dict['rating_count'] = len(sorted_reviews)
        plugins.append(Plugin(**plugin_dict))
    if include_reviews:
        plugins = sorted(plugins, key=weighted_rating, reverse=True)

    return plugins


# **************************************************
# ************* EXTERNAL INTEGRATIONS **************
# **************************************************

def trigger_external_integrations(uid: str, memory: Memory) -> list:
    """ON MEMORY CREATED"""
    if not memory or memory.discarded:
        return []

    apps: List[App] = get_available_apps(uid)
    filtered_apps = [app for app in apps if
                     app.triggers_on_memory_creation() and app.enabled and not app.deleted]
    if not filtered_apps:
        return []

    threads = []
    results = {}

    def _single(app: App):
        if not app.external_integration.webhook_url:
            return

        memory_dict = memory.as_dict_cleaned_dates()

        # Ignore external data on workflow
        if memory.source == MemorySource.workflow and 'external_data' in memory_dict:
            memory_dict['external_data'] = None

        url = app.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            response = requests.post(url, json=memory_dict, timeout=30, )  # TODO: failing?
            if response.status_code != 200:
                print('App integration failed', app.id, 'status:', response.status_code, 'result:', response.text[:100])
                return

            if app.uid is not None:
                if app.uid != uid:
                    record_app_usage(uid, app.id, UsageHistoryType.memory_created_external_integration,
                                     memory_id=memory.id)
            else:
                record_app_usage(uid, app.id, UsageHistoryType.memory_created_external_integration,
                                 memory_id=memory.id)

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
        messages.append(add_plugin_message(message, key, uid, memory.id))
    return messages


async def trigger_realtime_integrations(uid: str, segments: list[dict], memory_id: str | None):
    """REALTIME STREAMING"""
    # TODO: don't retrieve token before knowing if to notify
    token = notification_db.get_token_only(uid)
    _trigger_realtime_integrations(uid, token, segments, memory_id)


# proactive notification
def _retrieve_contextual_memories(uid: str, user_context):
    vector = (
        generate_embedding(user_context.get('question', ''))
        if user_context.get('question')
        else [0] * 3072
    )
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
    return memories_db.get_memories_by_id(uid, memories_id)


def _hit_proactive_notification_rate_limits(uid: str, plugin: App):
    sent_at = mem_db.get_proactive_noti_sent_at(uid, plugin.id)
    if sent_at and time.time() - sent_at < PROACTIVE_NOTI_LIMIT_SECONDS:
        return True

    # remote
    sent_at = redis_db.get_proactive_noti_sent_at(uid, plugin.id)
    if not sent_at:
        return False
    ttl = redis_db.get_proactive_noti_sent_at_ttl(uid, plugin.id)
    if ttl > 0:
        mem_db.set_proactive_noti_sent_at(uid, plugin.id, int(time.time() + ttl), ttl=ttl)

    return time.time() - sent_at < PROACTIVE_NOTI_LIMIT_SECONDS


def _set_proactive_noti_sent_at(uid: str, plugin: App):
    ts = time.time()
    mem_db.set_proactive_noti_sent_at(uid, plugin, int(ts), ttl=PROACTIVE_NOTI_LIMIT_SECONDS)
    redis_db.set_proactive_noti_sent_at(uid, plugin.id, int(ts), ttl=PROACTIVE_NOTI_LIMIT_SECONDS)


def _process_proactive_notification(uid: str, token: str, plugin: App, data):
    if not plugin.has_capability("proactive_notification") or not data:
        print(f"Plugins {plugin.id} is not proactive_notification or data invalid", uid)
        return None

    # rate limits
    if _hit_proactive_notification_rate_limits(uid, plugin):
        print(f"Plugins {plugin.id} is reach rate limits 1 noti per user per {PROACTIVE_NOTI_LIMIT_SECONDS}s", uid)
        return None

    max_prompt_char_limit = 128000
    min_message_char_limit = 5

    prompt = data.get('prompt', '')
    if len(prompt) > max_prompt_char_limit:
        send_plugin_notification(token, plugin.name, plugin.id,
                                 f"Prompt too long: {len(prompt)}/{max_prompt_char_limit} characters. Please shorten.")
        print(f"Plugin {plugin.id}, prompt too long, length: {len(prompt)}/{max_prompt_char_limit}", uid)
        return None

    filter_scopes = plugin.filter_proactive_notification_scopes(data.get('params', []))

    # context
    context = None
    if 'user_context' in filter_scopes:
        memories = _retrieve_contextual_memories(uid, data.get('context', {}))
        if len(memories) > 0:
            context = Memory.memories_to_string(memories, True)

    # messages
    messages = []
    if 'user_chat' in filter_scopes:
        messages = list(reversed([Message(**msg) for msg in get_plugin_messages(uid, plugin.id, limit=10)]))

    # print(f'_process_proactive_notification context {context[:100] if context else "empty"}')

    # retrive message
    message = get_proactive_message(uid, prompt, filter_scopes, context, messages)
    if not message or len(message) < min_message_char_limit:
        print(f"Plugins {plugin.id}, message too short", uid)
        return None

    # send notification
    send_plugin_notification(token, plugin.name, plugin.id, message)

    # set rate
    _set_proactive_noti_sent_at(uid, plugin)
    return message


def _trigger_realtime_integrations(uid: str, token: str, segments: List[dict], memory_id: str | None) -> dict:
    apps: List[App] = get_available_apps(uid)
    filtered_apps = [
        app for app in apps if
        app.triggers_realtime() and app.enabled and not app.deleted
    ]
    if not filtered_apps:
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
            response = requests.post(url, json={"session_id": uid, "segments": segments, "aid": app.id}, timeout=30)
            if response.status_code != 200:
                print('trigger_realtime_integrations', app.id, 'status: ', response.status_code, 'results:',
                      response.text[:100])
                return

            if (app.uid is None or app.uid != uid) and memory_id is not None:
                record_app_usage(uid, app.id, UsageHistoryType.transcript_processed_external_integration, memory_id=memory_id)

            response_data = response.json()
            if not response_data:
                return

            # message
            message = response_data.get('message', '')
            # print('Plugin', plugin.id, 'response message:', message)
            if message and len(message) > 5:
                send_plugin_notification(token, app.name, app.id, message)
                results[app.id] = message

            # proactive_notification
            noti = response_data.get('notification', None)
            # print('Plugin', plugin.id, 'response notification:', noti)
            if app.has_capability("proactive_notification"):
                message = _process_proactive_notification(uid, token, app, noti)
                if message:
                    results[app.id] = message

        except Exception as e:
            print(f"App integration error: {e}")
            return

    for app in filtered_apps:
        threads.append(threading.Thread(target=_single, args=(app,)))

    [t.start() for t in threads]
    [t.join() for t in threads]
    messages = []
    for key, message in results.items():
        if not message:
            continue
        messages.append(add_plugin_message(message, key, uid))

    return messages


def send_plugin_notification(token: str, app_name: str, app_id: str, message: str):
    ai_message = NotificationMessage(
        text=message,
        plugin_id=app_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
        navigate_to=f'/chat/{app_id}',
    )

    send_notification(token, app_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
