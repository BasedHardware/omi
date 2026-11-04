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


def get_questions_data() -> None:
    uids = get_users_uid()[:20]
    users_ref = db.collection("users")

    users_with_persona_messages = 0
    automatic_conversations_count = 0
    total_conversations_count = 0
    users_with_no_messages_back = 0
    conversation_lengths: List[int] = []
    conversations_per_user: Dict[str, int] = {}

    questions_their_own = 0
    questions_someone_else = 0
    popular_questions: Dict[str, int] = {}
    popular_questions_someone_else: Dict[str, Dict[str, int]] = {}

    def process_user(uid: str) -> None:
        nonlocal users_with_persona_messages, automatic_conversations_count, total_conversations_count
        nonlocal users_with_no_messages_back, questions_their_own, questions_someone_else

        messages_ref = users_ref.document(uid).collection("messages")
        messages = list(messages_ref.stream())

        has_persona_message = False
        user_messages_count = 0
        bot_messages_count = 0

        for message in messages:
            raw: object = message.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}

            sender = data.get('sender', '')
            if sender == 'user':
                user_messages_count += 1
                text = data.get('text', '').lower()
                if '?' in text:
                    # simplified logic for "own" vs "someone else's"
                    is_own = 'my' in text or 'i ' in text or 'me ' in text
                    if is_own:
                        questions_their_own += 1
                    else:
                        questions_someone_else += 1
                        target = data.get('botName', 'unknown')
                        if target not in popular_questions_someone_else:
                            popular_questions_someone_else[target] = {}
                        popular_questions_someone_else[target][text] = (
                            popular_questions_someone_else[target].get(text, 0) + 1
                        )

                    popular_questions[text] = popular_questions.get(text, 0) + 1
            else:
                bot_messages_count += 1

            if 'botName' in data:
                has_persona_message = True

        if has_persona_message:
            users_with_persona_messages += 1

        if len(messages) > 0:
            if user_messages_count == 0:
                automatic_conversations_count += 1
            if bot_messages_count == 0:
                users_with_no_messages_back += 1

        conversation_lengths.append(len(messages))
        conversations_per_user[uid] = len(messages)

    with ThreadPoolExecutor() as executor:
        executor.map(process_user, uids)

    from pathlib import Path

    total_questions = questions_their_own + questions_someone_else
    percent_own = (questions_their_own / total_questions * 100) if total_questions > 0 else 0
    percent_someone_else = (questions_someone_else / total_questions * 100) if total_questions > 0 else 0

    top_popular_questions = sorted(popular_questions.items(), key=lambda item: item[1], reverse=True)[:5]

    top_someone_else_questions = {}
    for target, questions in popular_questions_someone_else.items():
        top_someone_else_questions[target] = sorted(questions.items(), key=lambda item: item[1], reverse=True)[:3]

    no_messages_back_ratio = (users_with_no_messages_back / len(uids)) if uids else 0

    results = {
        "percent_questions_their_own": percent_own,
        "percent_questions_someone_else": percent_someone_else,
        "most_popular_questions": top_popular_questions,
        "top_3_popular_questions_someone_else_and_to_whom": top_someone_else_questions,
        "users_with_personas_messages": users_with_persona_messages,
        "automatic_conversations_count": automatic_conversations_count,
        "users_with_no_messages_back_ratio": no_messages_back_ratio,
        "conversations_length_distribution": conversation_lengths,
        "conversations_distribution_per_user": conversations_per_user,
    }

    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "questions_data.json", "w") as f:
        json.dump(results, f, default=str, indent=2)


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    get_plugin_data_by_persona_name()
    get_questions_data()
