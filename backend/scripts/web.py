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


def get_questions_stats() -> None:
    import threading

    uids = get_users_uid()
    users_ref = db.collection("users")

    users_with_personas_messages = 0
    conversations_just_automatic = 0
    users_no_messages_back = 0
    total_users_with_conversations = 0
    conversation_lengths: List[int] = []
    conversations_per_user: List[int] = []

    own_vs_someone_else = {"own": 0, "someone_else": 0}
    popular_questions: Dict[str, int] = {}
    someone_else_questions: Dict[str, int] = {}
    someone_else_to_whom: Dict[str, int] = {}

    stats_lock = threading.Lock()

    def process_user(uid: str) -> None:
        nonlocal users_with_personas_messages, conversations_just_automatic
        nonlocal users_no_messages_back, total_users_with_conversations
        nonlocal conversation_lengths, conversations_per_user
        nonlocal own_vs_someone_else, popular_questions, someone_else_questions, someone_else_to_whom

        messages_ref = users_ref.document(uid).collection("messages")
        messages = messages_ref.stream()

        has_persona_message = False
        sessions: Dict[str, Dict[str, Any]] = {}

        local_popular_questions = {}
        local_someone_else_questions = {}
        local_someone_else_to_whom = {}
        local_own = 0
        local_someone_else = 0

        for message in messages:
            raw = message.to_dict()
            data = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}

            if 'botName' in data:
                has_persona_message = True

            session_id = data.get('chat_session_id') or data.get('session_id') or 'default'
            if session_id not in sessions:
                sessions[session_id] = {'user_messages': 0, 'ai_messages': 0, 'messages': []}

            role = data.get('sender', '')
            if role in ('user', 'human'):
                sessions[session_id]['user_messages'] += 1
                text = data.get('text', '')
                if text and '?' in text:
                    q = text.strip()
                    local_popular_questions[q] = local_popular_questions.get(q, 0) + 1

                    # Heuristic for someone else vs own
                    if 'my' in q.lower() or ' i ' in f" {q.lower()} " or q.lower().startswith('i '):
                        local_own += 1
                    else:
                        local_someone_else += 1
                        local_someone_else_questions[q] = local_someone_else_questions.get(q, 0) + 1
                        # We could extract 'to whom' but without a model it's hard, fallback to botName
                        bot_name = data.get('botName', 'unknown')
                        local_someone_else_to_whom[bot_name] = local_someone_else_to_whom.get(bot_name, 0) + 1

            elif role in ('ai', 'assistant', 'bot'):
                sessions[session_id]['ai_messages'] += 1

            sessions[session_id]['messages'].append(data)

        local_conversations_just_automatic = 0
        local_has_ai_reply_overall = False
        local_conversation_lengths = []
        local_conversations_per_user = 0

        if sessions:
            local_conversations_per_user = len(sessions)
            for s_id, s_data in sessions.items():
                local_conversation_lengths.append(len(s_data['messages']))
                if s_data['user_messages'] == 0 and s_data['ai_messages'] > 0:
                    local_conversations_just_automatic += 1
                if s_data['ai_messages'] > 0:
                    local_has_ai_reply_overall = True

        with stats_lock:
            if has_persona_message:
                users_with_personas_messages += 1
            if sessions:
                total_users_with_conversations += 1
                conversations_per_user.append(local_conversations_per_user)
                conversation_lengths.extend(local_conversation_lengths)
                conversations_just_automatic += local_conversations_just_automatic
                if not local_has_ai_reply_overall:
                    users_no_messages_back += 1

            own_vs_someone_else['own'] += local_own
            own_vs_someone_else['someone_else'] += local_someone_else

            for q, count in local_popular_questions.items():
                popular_questions[q] = popular_questions.get(q, 0) + count
            for q, count in local_someone_else_questions.items():
                someone_else_questions[q] = someone_else_questions.get(q, 0) + count
            for b, count in local_someone_else_to_whom.items():
                someone_else_to_whom[b] = someone_else_to_whom.get(b, 0) + count

    with ThreadPoolExecutor() as executor:
        executor.map(process_user, uids)

    print(f"Total Users Checked: {len(uids)}")
    print(f"Users with persona messages: {users_with_personas_messages}")
    print(f"Conversations just automatic messages: {conversations_just_automatic}")

    no_reply_ratio = (
        users_no_messages_back / total_users_with_conversations if total_users_with_conversations > 0 else 0
    )
    print(f"Users with no messages back: {users_no_messages_back} (ratio: {no_reply_ratio:.2f})")

    if conversation_lengths:
        print(f"Avg conversation length: {sum(conversation_lengths) / len(conversation_lengths):.2f}")
    if conversations_per_user:
        print(f"Avg conversations per user: {sum(conversations_per_user) / len(conversations_per_user):.2f}")

    print(f"Own vs Someone Else: {own_vs_someone_else}")

    top_questions = sorted(popular_questions.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"Top popular questions overall: {top_questions}")

    top_someone_else_q = sorted(someone_else_questions.items(), key=lambda x: x[1], reverse=True)[:3]
    print(f"Top 3 someone else questions: {top_someone_else_q}")

    top_whom = sorted(someone_else_to_whom.items(), key=lambda x: x[1], reverse=True)[:3]
    print(f"Top 3 to whom (botName): {top_whom}")


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    get_plugin_data_by_persona_name()
    get_questions_stats()
