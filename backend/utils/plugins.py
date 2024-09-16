import threading
from datetime import datetime
from typing import List, Optional

import requests

from database.chat import add_plugin_message
from database.redis_db import get_enabled_plugins, get_plugin_reviews
from models.memory import Memory, MemorySource
from models.notification_message import NotificationMessage
from models.plugin import Plugin
from utils.notifications import send_notification


def get_plugin_by_id(plugin_id: str) -> Optional[Plugin]:
    if not plugin_id:
        return None
    plugins = get_plugins_data('', include_reviews=False)
    return next((p for p in plugins if p.id == plugin_id), None)


def weighted_rating(plugin):
    C = 3.0  # Assume 3.0 is the mean rating across all plugins
    m = 5  # Minimum number of ratings required to be considered
    R = plugin.rating_avg or 0
    v = plugin.rating_count or 0
    return (v / (v + m) * R) + (m / (v + m) * C)


def get_plugins_data(uid: str, include_reviews: bool = False) -> List[Plugin]:
    # print('get_plugins_data', uid, include_reviews)
    response = requests.get('https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json')
    if response.status_code != 200:
        return []
    user_enabled = set(get_enabled_plugins(uid))
    # print('get_plugins_data, user_enabled', user_enabled)
    data = response.json()
    plugins = []
    for plugin in data:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
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


def trigger_external_integrations(uid: str, memory: Memory) -> list:
    plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
    filtered_plugins = [plugin for plugin in plugins if
                        plugin.triggers_on_memory_creation() and plugin.enabled and not plugin.deleted]
    if not filtered_plugins:
        return []

    threads = []
    results = {}

    def _single(plugin: Plugin):
        if not plugin.external_integration.webhook_url:
            return

        memory_dict = memory.dict()
        memory_dict['created_at'] = memory_dict['created_at'].isoformat()
        memory_dict['started_at'] = memory_dict['started_at'].isoformat() if memory_dict['started_at'] else None
        memory_dict['finished_at'] = memory_dict['finished_at'].isoformat() if memory_dict['finished_at'] else None

        # Ignore external data on workflow
        if memory.source == MemorySource.workflow and 'external_data' in memory_dict:
            memory_dict['external_data'] = None

        url = plugin.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        response = requests.post(url, json=memory_dict)  # TODO: failing?
        if response.status_code != 200:
            print('Plugin integration failed', plugin.id, 'result:', response.content)
            return

        print('response', response.json())
        if message := response.json().get('message', ''):
            results[plugin.id] = message

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


def trigger_realtime_integrations(uid: str, token: str, segments: List[dict]) -> dict:
    plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
    filtered_plugins = [plugin for plugin in plugins if
                        plugin.triggers_realtime() and plugin.enabled and not plugin.deleted]
    if not filtered_plugins:
        return {}

    threads = []
    results = {}

    def _single(plugin: Plugin):
        if not plugin.external_integration.webhook_url:
            return

        url = plugin.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        try:
            response = requests.post(url, json={"session_id": uid, "segments": segments})
            if response.status_code != 200:
                print('trigger_realtime_integrations', plugin.id, 'result:', response.content)
                return

            response_data = response.json()
            if not response_data:
                return
            message = response_data.get('message', '')
            print('Plugin', plugin.id, 'response:', message)
            if message and len(message) > 5:
                send_plugin_notification(token, plugin.name, plugin.id, message)
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
