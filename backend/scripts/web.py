from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, cast

from database._client import get_users_uid, db


import json


def get_plugin_data_by_persona_name() -> None:
    """Map persona plugins_data docs keyed by username (unique handle).

    Display `name` is not unique; last-write-wins on name silently dropped
    documents. Output lives under backend/scripts/data/ which is gitignored so
    an accidental `git add -A` cannot commit owner emails / prompts.
    """
    from pathlib import Path

    plugin_data_by_username: Dict[str, Dict[str, Any]] = {}
    plugins_ref = db.collection("plugins_data").stream()
    for doc in plugins_ref:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        capabilities = data.get("capabilities") or []
        if isinstance(capabilities, list) and "persona" not in capabilities:
            continue
        username = data.get("username")
        if not username:
            continue
        plugin_data_by_username.setdefault(str(username), data)

    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "plugin_data_by_persona_name.json", "w") as f:
        json.dump(plugin_data_by_username, f, default=str)


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

    from pathlib import Path

    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "user_messages_with_bot_name.json", "w") as f:
        json.dump(user_messages_with_bot_name, f, default=str)

    return uids


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    get_plugin_data_by_persona_name()
    # TODO: questions
    # -- % of people who provided their x vs someone else's, and most popular questions
    # -- If someone else, who were the top 3 most popular questions and to whom
    # - how many users have personas messages?
    # - how many conversations are just automatic messages? (no user messages)
    # - how many users have no messages back at all? ratio
    # - conversations length distribution
    # - # of conversations distribution per user
