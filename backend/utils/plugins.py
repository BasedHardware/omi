import threading
from typing import List, Optional
import os
import requests

import database.notifications as notification_db
from database.apps import get_private_apps_db, get_public_apps_db
from database.chat import add_plugin_message
from database.plugins import record_plugin_usage
from database.redis_db import get_enabled_plugins, get_plugin_reviews, get_plugin_installs_count, get_generic_cache, \
    set_generic_cache
from models.app import App
from models.memory import Memory, MemorySource
from models.notification_message import NotificationMessage
from models.plugin import Plugin, UsageHistoryType
from utils.apps import get_available_apps, weighted_rating
from utils.notifications import send_notification
from utils.other.endpoints import timeit
from utils.llm import (
    generate_embedding,
    get_proactive_message
)
from database.vector_db import query_vectors_by_metadata
import database.memories as memories_db


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

@timeit
def get_plugin_by_id(plugin_id: str) -> Optional[Plugin]:
    if not plugin_id or plugin_id == 'null':
        return None
    plugins = get_plugins_data('', include_reviews=False)
    return next((p for p in plugins if p.id == plugin_id), None)


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
    plugins = []
    for plugin in all_plugins:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        plugin_dict['installs'] = get_plugin_installs_count(plugin['id'])
        if include_reviews:
            reviews = get_plugin_reviews(plugin['id'])
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
    plugins = []
    for plugin in data:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        plugin_dict['installs'] = get_plugin_installs_count(plugin['id'])
        if include_reviews:
            reviews = get_plugin_reviews(plugin['id'])
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

    plugins: List[App] = get_available_apps(uid)
    filtered_plugins = [plugin for plugin in plugins if
                        plugin.triggers_on_memory_creation() and plugin.enabled and not plugin.deleted]
    if not filtered_plugins:
        return []

    threads = []
    results = {}

    def _single(plugin: App):
        if not plugin.external_integration.webhook_url:
            return

        memory_dict = memory.as_dict_cleaned_dates()

        # Ignore external data on workflow
        if memory.source == MemorySource.workflow and 'external_data' in memory_dict:
            memory_dict['external_data'] = None

        url = plugin.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            response = requests.post(url, json=memory_dict, timeout=30, )  # TODO: failing?
            if response.status_code != 200:
                print('Plugin integration failed', plugin.id, 'result:', response.content)
                return

            record_plugin_usage(uid, plugin.id, UsageHistoryType.memory_created_external_integration,
                                memory_id=memory.id)

            # print('response', response.json())
            if message := response.json().get('message', ''):
                results[plugin.id] = message
        except Exception as e:
            print(f"Plugin integration error: {e}")
            return

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=_single, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]

    messages = []
    for key, message in results.items():
        if not message:
            continue
        messages.append(add_plugin_message(message, key, uid, memory.id))
    return messages


async def trigger_realtime_integrations(uid: str, segments: list[dict]):
    """REALTIME STREAMING"""
    # TODO: don't retrieve token before knowing if to notify
    token = notification_db.get_token_only(uid)
    _trigger_realtime_integrations(uid, token, segments)


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


def _process_proactive_notification(uid: str, token: str, plugin: App, data):
    if not plugin.has_capability("proactive_notification") or not data:
        print(f"Plugins {plugin.id} is not proactive_notification or data invalid", uid)
        return None

    max_prompt_char_limit = 8000
    min_message_char_limit = 5

    prompt = data.get('prompt', '')
    if len(prompt) > max_prompt_char_limit:
        send_plugin_notification(token, plugin.name, plugin.id, f"Prompt too long: {len(prompt)}/{max_prompt_char_limit} characters. Please shorten.")
        print(f"Plugin {plugin.id}, prompt too long, length: {len(prompt)}/{max_prompt_char_limit}", uid)
        return None

    filter_scopes = plugin.filter_proactive_notification_scopes(data.get('params', []))

    # context
    context = None
    if 'user_context' in filter_scopes:
        memories = _retrieve_contextual_memories(uid, data.get('context', {}))
        if len(memories) > 0:
            context = Memory.memories_to_string(memories, True)

    print(f'_process_proactive_notification context {context[:100] if context else "empty"}')

    # retrive message
    message = get_proactive_message(uid, prompt, filter_scopes, context)
    if not message or len(message) < min_message_char_limit:
        print(f"Plugins {plugin.id}, message too short", uid)
        return None

    # send notification
    send_plugin_notification(token, plugin.name, plugin.id, message)
    return message


def _trigger_realtime_integrations(uid: str, token: str, segments: List[dict]) -> dict:
    plugins: List[App] = get_available_apps(uid)
    filtered_plugins = [
        plugin for plugin in plugins if
        plugin.triggers_realtime() and plugin.enabled and not plugin.deleted
    ]
    if not filtered_plugins:
        return {}

    threads = []
    results = {}

    def _single(plugin: App):
        if not plugin.external_integration.webhook_url:
            return

        url = plugin.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            response = requests.post(url, json={"session_id": uid, "segments": segments}, timeout=30)
            if response.status_code != 200:
                print('trigger_realtime_integrations', plugin.id, 'result:', response.content)
                return

            response_data = response.json()
            if not response_data:
                return

            # message
            message = response_data.get('message', '')
            print('Plugin', plugin.id, 'response message:', message)
            if message and len(message) > 5:
                send_plugin_notification(token, plugin.name, plugin.id, message)
                results[plugin.id] = message

            # proactive_notification
            noti = response_data.get('notification', None)
            print('Plugin', plugin.id, 'response notification:', noti)
            if plugin.has_capability("proactive_notification"):
                message = _process_proactive_notification(uid, token, plugin, noti)
                if message:
                    results[plugin.id] = message

        except Exception as e:
            print(f"Plugin integration error: {e}")
            return

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=_single, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]
    messages = []
    for key, message in results.items():
        if not message:
            continue
        messages.append(add_plugin_message(message, key, uid))

    return messages


def send_plugin_notification(token: str, plugin_name: str, plugin_id: str, message: str):
    ai_message = NotificationMessage(
        text=message,
        plugin_id=plugin_id,
        from_integration='true',
        type='text',
        notification_type='plugin',
    )

    send_notification(token, plugin_name + ' says', message, NotificationMessage.get_message_as_dict(ai_message))
