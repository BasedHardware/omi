import json
import os
import threading
from collections import defaultdict

from dotenv import load_dotenv

from models.app import UsageHistoryType

load_dotenv('../../.env')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '../../' + os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')

import firebase_admin

firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

from typing import Dict, List
from database.apps import record_app_usage


from database.redis_db import get_enabled_apps, set_app_installs_count
from database._client import get_users_uid
import database.conversations as conversations_db
import database.chat as chat_db


def single(uid: str, data: Dict[str, int]) -> List[str]:
    pids = get_enabled_apps(uid)
    for pid in pids:
        data[pid] += 1
    return pids


def execute() -> None:
    uids = get_users_uid()
    data: Dict[str, int] = defaultdict(int)

    threads: List[threading.Thread] = []
    for uid in uids:
        threads.append(
            threading.Thread(
                target=single,
                args=(
                    uid,
                    data,
                ),
            )
        )

    count = 20
    chunks = [threads[i : i + count] for i in range(0, len(threads), count)]
    for chunk in chunks:
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]

    print(json.dumps(data, indent=2))
    for pid, count in data.items():
        set_app_installs_count(pid, count)


def count_memory_prompt_plugins_trigger() -> None:
    uids = get_users_uid()

    def single(uid: str) -> None:
        memories = conversations_db.get_conversations(uid, limit=1000)
        print('user', uid, 'conversations', len(memories))
        for memory in memories:
            triggered = memory.get('plugins_results', [])
            created_at = memory.get('created_at')
            if triggered:
                print('memory', memory['id'], 'triggered', len(triggered), 'plugins')
            for trigger in triggered:
                record_app_usage(
                    uid,
                    trigger['plugin_id'],
                    UsageHistoryType.memory_created_prompt,
                    conversation_id=memory['id'],
                    timestamp=created_at,
                )

        messages = chat_db.get_messages(uid, limit=1000)
        print('user', uid, 'messages', len(messages))
        for message in messages:
            if pid := message.get('plugin_id'):
                record_app_usage(
                    uid,
                    pid,
                    UsageHistoryType.chat_message_sent,
                    message_id=message['id'],
                    timestamp=message['created_at'],
                )

    threads: List[threading.Thread] = []
    for uid in uids:
        threads.append(threading.Thread(target=single, args=(uid,)))

    count = 20
    chunks = [threads[i : i + count] for i in range(0, len(threads), count)]
    for chunk in chunks:
        [thread.start() for thread in chunk]
        [thread.join() for thread in chunk]


if __name__ == '__main__':
    count_memory_prompt_plugins_trigger()
