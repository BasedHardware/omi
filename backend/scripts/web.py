from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, cast

from database._client import get_users_uid, db


import json


def map_plugin_data_by_persona_name() -> None:
    plugin_data_by_persona_name: Dict[str, Dict[str, Any]] = {}
    plugins_ref = db.collection("plugins_data")
    plugins = plugins_ref.stream()

    for plugin in plugins:
        raw: object = plugin.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        persona_name = data.get("persona_name")
        if persona_name:
            plugin_data_by_persona_name[persona_name] = data

    with open("plugin_data_by_persona_name.json", "w") as f:
        json.dump(plugin_data_by_persona_name, f, default=str)


def get_user_messages_with_bot_name() -> List[str]:
    user_messages_with_bot_name: Dict[str, List[Dict[str, Any]]] = {}
    uids = get_users_uid()[:20]
    users_ref = db.collection("users")
    print(len(uids))

    def process_user(uid: str) -> None:
        messages_ref = users_ref.document(uid).collection("messages")
        messages = messages_ref.stream()
        filtered_messages: List[Dict[str, Any]] = []
        for message in messages:
            raw: object = message.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            if 'botName' in data:
                filtered_messages.append(data)
        print(uid, "has personas messages", len(filtered_messages))
        if filtered_messages:
            user_messages_with_bot_name[uid] = filtered_messages

    with ThreadPoolExecutor() as executor:
        executor.map(process_user, uids)

    with open("user_messages_with_bot_name.json", "w") as f:
        json.dump(user_messages_with_bot_name, f, default=str)

    return uids


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    map_plugin_data_by_persona_name()
    # TODO: questions
    # -- % of people who provided their x vs someone else's, and most popular questions
    # -- If someone else, who were the top 3 most popular questions and to whom
    # - how many users have personas messages?
    # - how many conversations are just automatic messages? (no user messages)
    # - how many users have no messages back at all? ratio
    # - conversations length distribution
    # - # of conversations distribution per user
