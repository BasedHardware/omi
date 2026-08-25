from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple, cast

from database._client import get_firestore_client, get_users_uid, db
from pathlib import Path

import json
import os

USER_BATCH_SIZE = 20
EXPORT_FILE_MODE = 0o600


def clear_export_artifacts() -> None:
    Path("user_messages_with_bot_name.json").unlink(missing_ok=True)
    Path("plugin_data_by_persona_name.json").unlink(missing_ok=True)


def _owner_only_open(path: str):
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, EXPORT_FILE_MODE)
    try:
        os.fchmod(fd, EXPORT_FILE_MODE)
        return os.fdopen(fd, "w")
    except Exception:
        os.close(fd)
        raise


def get_user_messages_with_bot_name() -> List[str]:
    uids = get_users_uid()
    users_ref = db.collection("users")
    print(len(uids))

    def process_user(uid: str) -> Tuple[str, List[Dict[str, Any]]]:
        messages_ref = users_ref.document(uid).collection("messages")
        messages = messages_ref.stream()
        filtered_messages: List[Dict[str, Any]] = []
        for message in messages:
            raw: object = message.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            if 'botName' in data:
                filtered_messages.append(data)
        return uid, filtered_messages

    tmp_path = "user_messages_with_bot_name.json.tmp"
    try:
        wrote_any = False
        with _owner_only_open(tmp_path) as f:
            f.write("{")
            for start in range(0, len(uids), USER_BATCH_SIZE):
                with ThreadPoolExecutor(max_workers=USER_BATCH_SIZE) as executor:
                    results = list(executor.map(process_user, uids[start : start + USER_BATCH_SIZE]))
                for uid, filtered_messages in results:
                    if not filtered_messages:
                        continue
                    if wrote_any:
                        f.write(",")
                    f.write(json.dumps(uid))
                    f.write(":")
                    f.write(json.dumps(filtered_messages, default=str))
                    wrote_any = True
                f.flush()
            f.write("}")
        os.replace(tmp_path, "user_messages_with_bot_name.json")
        os.chmod("user_messages_with_bot_name.json", EXPORT_FILE_MODE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    return uids


def map_plugin_data_by_persona_name(*, firestore_client: Any = None) -> None:
    try:
        with open("user_messages_with_bot_name.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("user_messages_with_bot_name.json not found. Run get_user_messages_with_bot_name() first.")
        Path("plugin_data_by_persona_name.json").unlink(missing_ok=True)
        return

    persona_uids: Dict[str, set[str]] = {}
    bot_name_only_messages: Dict[str, List[Dict[str, Any]]] = {}

    for uid, messages in data.items():
        for message in messages:
            plugin_id = message.get("pluginId")
            if plugin_id:
                persona_uids.setdefault(plugin_id, set()).add(uid)
            elif message.get("botName"):
                # Legacy messages carry botName without a stable pluginId; keep them
                # under their botName so they are not silently dropped from the export.
                bot_name_only_messages.setdefault(uid, []).append(message)

    client = firestore_client if firestore_client is not None else get_firestore_client()
    plugin_data_by_persona: Dict[str, List[Dict[str, Any]]] = {}
    for plugin_document in client.collection("plugins_data").stream():
        raw: object = plugin_document.to_dict()
        plugin_data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        plugin_id = plugin_data.get("id")
        if not isinstance(plugin_id, str) or plugin_id not in persona_uids:
            continue
        for uid in sorted(persona_uids[plugin_id]):
            # Keep the plugin owner's uid and record the chatting user separately
            plugin_data_with_uid = plugin_data.copy()
            plugin_data_with_uid["user_uid"] = uid
            integration = plugin_data_with_uid.get("external_integration")
            if isinstance(integration, dict) and "mcp_oauth_tokens" in integration:
                plugin_data_with_uid["external_integration"] = {
                    key: value for key, value in integration.items() if key != "mcp_oauth_tokens"
                }
            plugin_data_by_persona.setdefault(plugin_id, []).append(plugin_data_with_uid)

    if bot_name_only_messages:
        plugin_data_by_persona["_bot_name_only"] = [
            {"uid": uid, "bot_name": message["botName"], "message": message}
            for uid, messages in sorted(bot_name_only_messages.items())
            for message in messages
        ]

    with _owner_only_open("plugin_data_by_persona_name.json") as f:
        json.dump(plugin_data_by_persona, f, indent=2, default=str)

    print(f"Mapped {len(plugin_data_by_persona)} personas to plugin_data_by_persona_name.json")


if __name__ == "__main__":
    clear_export_artifacts()
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
