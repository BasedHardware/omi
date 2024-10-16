# - P3
# - Include speechmatics to the game
import json
import os
import threading
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv('../../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

import firebase_admin

firebase_admin.initialize_app()

# noinspection PyUnresolvedReferences
from typing import List

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


def execute2():
    uids = get_users_uid()
    data = defaultdict(int)

    threads = []
    for uid in uids:
        # - get memories of all
        # - count plugins count on memories
        # - redis store triggers counter (memory_creation ~ , chat_message ~ personality)
        # - then do for messages
        threads.append(threading.Thread(target=single, args=(uid, data,)))

    count = 20
    chunks = [threads[i:i + count] for i in range(0, len(threads), count)]
    for i, chunk in enumerate(chunks):
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]

    print(json.dumps(data, indent=2))
    for pid, count in data.items():
        set_plugin_installs_count(pid, count)


if __name__ == '__main__':
    execute()
