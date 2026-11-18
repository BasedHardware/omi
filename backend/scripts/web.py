from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, cast
import json
from pathlib import Path
import threading
from collections import Counter

from database._client import get_users_uid, db


def get_plugin_data_by_persona_name() -> None:
    """Map persona plugins_data docs keyed by username (unique handle).

    Display `name` is not unique; last-write-wins on name silently dropped
    documents. Output lives under backend/scripts/data/ which is gitignored so
    an accidental `git add -A` cannot commit owner emails / prompts.
    """
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
    print(f"Total uids: {len(uids)}")

    def process_user(uid: str) -> None:
        messages_ref = users_ref.document(uid).collection("messages")
        messages = messages_ref.stream()
        filtered_messages: List[Dict[str, Any]] = []
        for message in messages:
            raw: object = message.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            if "botName" in data:
                filtered_messages.append(data)
        print(f"{uid} has personas messages: {len(filtered_messages)}")
        if filtered_messages:
            user_messages_with_bot_name[uid] = filtered_messages

    with ThreadPoolExecutor() as executor:
        executor.map(process_user, uids)

    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "user_messages_with_bot_name.json", "w") as f:
        json.dump(user_messages_with_bot_name, f, default=str)

    return uids


def print_question_stats() -> None:
    uids = get_users_uid()
    users_ref = db.collection("users")

    users_with_personas_messages = 0
    total_conversations = 0
    automatic_conversations = 0
    users_with_no_messages_back = 0
    conversation_lengths: List[int] = []
    conversations_per_user: Dict[str, int] = {}

    own_questions = 0
    someone_else_questions = 0
    own_question_topics = Counter()
    someone_else_question_topics = Counter()
    someone_else_recipients = Counter()

    stats_lock = threading.Lock()

    def process_user_stats(uid: str) -> None:
        nonlocal users_with_personas_messages
        nonlocal total_conversations
        nonlocal automatic_conversations
        nonlocal users_with_no_messages_back
        nonlocal own_questions
        nonlocal someone_else_questions

        messages_ref = users_ref.document(uid).collection("messages")
        messages = list(messages_ref.stream())

        has_persona = False
        has_user_message = False
        has_bot_message = False

        with stats_lock:
            conversation_lengths.append(len(messages))
            conversations_per_user[uid] = len(messages)

        for message in messages:
            raw: object = message.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            if "botName" in data:
                has_persona = True
            if data.get("role") == "user":
                has_user_message = True
                text = str(data.get("text", "")).lower()

                # Basic heuristic for checking if it's about someone else
                if any(word in text for word in ["he ", "she ", "they ", "him", "her", "their"]):
                    with stats_lock:
                        someone_else_questions += 1
                        someone_else_question_topics[text] += 1

                        # Very simple heuristic to extract a recipient/subject name if present after preposition
                        words = text.split()
                        for i, w in enumerate(words):
                            if w in ["about", "to", "for", "with"] and i + 1 < len(words):
                                recipient = words[i + 1].strip("?,.")
                                if recipient not in ["him", "her", "them", "me", "us"]:
                                    someone_else_recipients[recipient] += 1
                else:
                    with stats_lock:
                        own_questions += 1
                        own_question_topics[text] += 1

            if data.get("role") == "ai":
                has_bot_message = True

        with stats_lock:
            if has_persona:
                users_with_personas_messages += 1

            if len(messages) > 0:
                total_conversations += 1
                if not has_user_message:
                    automatic_conversations += 1

            if len(messages) > 0 and not has_bot_message:
                users_with_no_messages_back += 1

    with ThreadPoolExecutor() as executor:
        executor.map(process_user_stats, uids)

    print("--- Question Stats ---")
    total_questions = own_questions + someone_else_questions
    if total_questions > 0:
        own_pct = (own_questions / total_questions) * 100
        else_pct = (someone_else_questions / total_questions) * 100
        print(f"% provided their own x vs someone else's: {own_pct:.1f}% own / {else_pct:.1f}% someone else's")

        print("\nMost popular questions (own):")
        for q, count in own_question_topics.most_common(5):
            print(f"  - {q}: {count}")

        if someone_else_questions > 0:
            print("\nIf someone else, top 3 most popular questions:")
            for q, count in someone_else_question_topics.most_common(3):
                print(f"  - {q}: {count}")

            print("\nIf someone else, to whom (top 3):")
            for recipient, count in someone_else_recipients.most_common(3):
                print(f"  - {recipient}: {count}")

    print("\n--- Conversation Stats ---")
    print(f"Users with personas messages: {users_with_personas_messages}")
    print(f"Automatic conversations (no user messages): {automatic_conversations}")
    if total_conversations > 0:
        ratio = users_with_no_messages_back / len(uids)
        print(f"Users with no messages back ratio: {ratio:.2f}")

    print(f"Conversation length distribution: {conversation_lengths}")
    print(f"Conversations per user distribution: {conversations_per_user}")


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    get_plugin_data_by_persona_name()
    print_question_stats()
