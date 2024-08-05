import threading
from datetime import datetime
from typing import List, Optional

import requests

from models.memory import Memory
from models.plugin import Plugin
from utils.redis_utils import get_enabled_plugins, get_plugin_reviews


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
    response = requests.get('https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json')
    if response.status_code != 200:
        return []
    user_enabled = set(get_enabled_plugins(uid))
    print('get_plugins_data, user_enabled', user_enabled)
    data = response.json()
    plugins = []
    for plugin in data:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        if include_reviews:
            reviews = get_plugin_reviews(plugin['id'])
            sorted_reviews = sorted(reviews.values(), key=lambda x: datetime.fromisoformat(x['rated_at']), reverse=True)
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if sorted_reviews else None
            plugin_dict['reviews'] = []
            plugin_dict['user_review'] = reviews.get(uid)
            plugin_dict['rating_avg'] = rating_avg
            plugin_dict['rating_count'] = len(sorted_reviews)
        plugins.append(Plugin(**plugin_dict))
    if include_reviews:
        plugins = sorted(plugins, key=weighted_rating, reverse=True)

    return plugins


def trigger_external_integrations(uid: str, memory: Memory):
    plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
    filtered_plugins = [
        plugin for plugin in plugins if plugin.triggers_on_memory_creation() and plugin.enabled
    ]
    if not filtered_plugins:
        return {}

    threads = []
    results = {}

    def _single(plugin: Plugin):
        if not plugin.external_integration.webhook_url:
            return

        memory_dict = memory.dict()
        memory_dict['created_at'] = memory_dict['created_at'].isoformat()
        memory_dict['started_at'] = memory_dict['started_at'].isoformat() if memory_dict['started_at'] else None
        memory_dict['finished_at'] = memory_dict['finished_at'].isoformat() if memory_dict['finished_at'] else None
        url = plugin.external_integration.webhook_url
        if '?' in url:
            url += '&uid=' + uid
        else:
            url += '?uid=' + uid

        response = requests.post(url, json=memory_dict)
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
    return results
