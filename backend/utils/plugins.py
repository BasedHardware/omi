import threading
from datetime import datetime
from typing import List

import requests

from models.memory import Memory
from models.plugin import Plugin
from utils.redis_utils import get_enabled_plugins, get_plugin_reviews


def get_plugins_data(uid: str, include_reviews: bool = False) -> List[Plugin]:
    # print('get_plugins_data', uid, include_reviews)
    response = requests.get('https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json')
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
            sorted_reviews = sorted(reviews.values(), key=lambda x: datetime.fromisoformat(x['rated_at']), reverse=True)
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if sorted_reviews else None
            plugin_dict['reviews'] = []
            plugin_dict['user_review'] = reviews.get(uid)
            plugin_dict['rating_avg'] = rating_avg
            plugin_dict['rating_count'] = len(sorted_reviews)
        plugins.append(Plugin(**plugin_dict))
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
        print('response', response.json())
        if message := response.json().get('message', ''):
            results[plugin.id] = message

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=_single, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]
    return results
