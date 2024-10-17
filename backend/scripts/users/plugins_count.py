# - P3
# - Include speechmatics to the game
import json
import os
import threading
from collections import defaultdict

from dotenv import load_dotenv

from models.plugin import UsageHistoryType

load_dotenv('../../.dev.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

import firebase_admin

firebase_admin.initialize_app()

# noinspection PyUnresolvedReferences
from typing import List
from database.plugins import record_plugin_usage

# noinspection PyUnresolvedReferences
import numpy as np
# noinspection PyUnresolvedReferences
import plotly.graph_objects as go
# noinspection PyUnresolvedReferences
import umap
# noinspection PyUnresolvedReferences
from plotly.subplots import make_subplots

# noinspection PyUnresolvedReferences
from models.memory import Memory
from database.redis_db import get_enabled_plugins, set_plugin_installs_count
from database._client import get_users_uid
import database.memories as memories_db
import database.chat as chat_db


def single(uid, data):
    pids = get_enabled_plugins(uid)
    for pid in pids:
        data[pid] += 1
    return pids


def execute():
    uids = get_users_uid()
    data = defaultdict(int)

    threads = []
    for uid in uids:
        threads.append(threading.Thread(target=single, args=(uid, data,)))

    count = 20
    chunks = [threads[i:i + count] for i in range(0, len(threads), count)]
    for i, chunk in enumerate(chunks):
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]

    print(json.dumps(data, indent=2))
    for pid, count in data.items():
        set_plugin_installs_count(pid, count)


def count_memory_prompt_plugins_trigger():
    uids = get_users_uid()

    def single(uid):
        memories = memories_db.get_memories(uid, limit=1000)
        print('user', uid, 'memories', len(memories))
        for memory in memories:
            triggered = memory.get('plugins_results', [])
            created_at = memory.get('created_at')
            if triggered:
                print('memory', memory['id'], 'triggered', len(triggered), 'plugins')
            for trigger in triggered:
                record_plugin_usage(
                    uid, trigger['plugin_id'], UsageHistoryType.memory_created_prompt, memory_id=memory['id'],
                    timestamp=created_at
                )

        messages = chat_db.get_messages(uid, limit=1000)
        print('user', uid, 'messages', len(messages))
        for message in messages:
            if pid := message.get('plugin_id'):
                record_plugin_usage(
                    uid, pid, UsageHistoryType.memory_created_prompt, message_id=message['id'],
                    timestamp=message['created_at']
                )

    threads = []
    for uid in uids:
        threads.append(threading.Thread(target=single, args=(uid,)))

    count = 20
    chunks = [threads[i:i + count] for i in range(0, len(threads), count)]
    for i, chunk in enumerate(chunks):
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]


if __name__ == '__main__':
    count_memory_prompt_plugins_trigger()
