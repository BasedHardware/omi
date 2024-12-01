from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
from tabulate import tabulate

from database._client import get_users_uid, db
from database.chat import get_messages


import json

def get_user_messages_with_bot_name():
    user_messages_with_bot_name = {}
    uids = get_users_uid()[:1000]
    users_ref = db.collection("users")
    print(len(uids))

    def process_user(uid):
        messages_ref = users_ref.document(uid).collection("messages")
        messages = messages_ref.stream()
        filtered_messages = [message.to_dict() for message in messages if 'botName' in message.to_dict()]
        print(uid, "has personas messages", len(filtered_messages))
        if filtered_messages:
            user_messages_with_bot_name[uid] = filtered_messages

    with ThreadPoolExecutor() as executor:
        executor.map(process_user, uids)

    with open('user_messages_with_bot_name.json', 'w') as f:
        json.dump(user_messages_with_bot_name, f)

    return uids


if __name__ == "__main__":
    get_user_messages_with_bot_name()
