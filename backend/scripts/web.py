from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, cast
import json
from pathlib import Path
from collections import defaultdict
import statistics
import re

from database._client import get_users_uid, db


def get_plugin_data_by_persona_name() -> None:
    """Map persona plugins_data docs keyed by username (unique handle)."""
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

    out_dir = Path(__file__).resolve().parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "user_messages_with_bot_name.json", "w") as f:
        json.dump(user_messages_with_bot_name, f, default=str)

    return uids


def run_questions_analysis() -> None:
    uids = get_users_uid()
    users_ref = db.collection("users")

    total_users = len(uids)

    # Use lists or dictionaries to safely collect data from threads, or return data
    results = []

    def analyze_user(uid: str) -> Dict[str, Any]:
        messages_ref = users_ref.document(uid).collection("messages")
        messages = list(messages_ref.stream())

        has_persona = False
        user_messages_count = 0
        bot_messages_count = 0
        provided_self = 0
        provided_other = 0
        questions = []
        o_questions = []
        targets = []

        for msg in messages:
            data = msg.to_dict() or {}
            if "botName" in data:
                has_persona = True
                bot_messages_count += 1
            if data.get("sender") == "user":
                user_messages_count += 1

            original_text = data.get("text", "")
            text = original_text.lower()
            if "?" in text:
                questions.append(original_text)
                words = re.findall(r"\b\w+\b", text)
                if any(pronoun in words for pronoun in ["he", "she", "they", "him", "her", "them", "someone", "name"]):
                    provided_other += 1
                    o_questions.append(original_text)

                    orig_words = re.findall(r"\b[A-Z][a-z]*\b", original_text)
                    for word in orig_words:
                        if word not in [
                            "I",
                            "You",
                            "He",
                            "She",
                            "They",
                            "We",
                            "What",
                            "How",
                            "Why",
                            "When",
                            "Where",
                            "Who",
                        ]:
                            targets.append(word)
                else:
                    provided_self += 1

        is_automatic_only = len(messages) > 0 and user_messages_count == 0
        no_replies = len(messages) > 0 and bot_messages_count == 0

        return {
            "has_persona": has_persona,
            "has_conversations": len(messages) > 0,
            "is_automatic_only": is_automatic_only,
            "no_replies": no_replies,
            "conversation_length": len(messages),
            "provided_self": provided_self,
            "provided_other": provided_other,
            "questions": questions,
            "other_questions": o_questions,
            "targets": targets,
        }

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(analyze_user, uids))

    users_with_personas = sum(1 for r in results if r["has_persona"])
    automatic_only_conversations = sum(1 for r in results if r["is_automatic_only"])
    total_conversations = sum(1 for r in results if r["has_conversations"])
    users_with_no_replies = sum(1 for r in results if r["no_replies"])

    provided_for_self = sum(r["provided_self"] for r in results)
    provided_for_other = sum(r["provided_other"] for r in results)

    all_questions = []
    other_questions = []
    other_targets = []
    conversation_lengths = []
    conversations_per_user = []

    for r in results:
        all_questions.extend(r["questions"])
        other_questions.extend(r["other_questions"])
        other_targets.extend(r["targets"])
        conversation_lengths.append(r["conversation_length"])
        conversations_per_user.append(1 if r["has_conversations"] else 0)

    print("--- Questions Analysis ---")

    # 1. % of people who provided their x vs someone else's, and most popular questions
    total_provided = provided_for_self + provided_for_other
    if total_provided > 0:
        self_pct = (provided_for_self / total_provided) * 100
        other_pct = (provided_for_other / total_provided) * 100
        print(f"Provided for self: {self_pct:.2f}%")
        print(f"Provided for someone else: {other_pct:.2f}%")

    def get_top_k(items: List[str], k: int) -> List[tuple]:
        counts = defaultdict(int)
        for item in items:
            counts[item] += 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:k]

    print(f"Top 3 most popular questions overall: {get_top_k(all_questions, 3)}")

    # 2. If someone else, who were the top 3 most popular questions and to whom
    print(f"Top 3 most popular questions for someone else: {get_top_k(other_questions, 3)}")
    print(f"Top 3 most popular targets (to whom): {get_top_k(other_targets, 3)}")

    # 3. how many users have personas messages?
    print(f"Users with personas messages: {users_with_personas}")

    # 4. how many conversations are just automatic messages? (no user messages)
    if total_conversations > 0:
        print(
            f"Conversations that are just automatic messages: {automatic_only_conversations} "
            f"({(automatic_only_conversations/total_conversations)*100:.2f}%)"
        )

    # 5. how many users have no messages back at all? ratio
    if total_users > 0:
        print(f"Users with no messages back at all (ratio): {users_with_no_replies/total_users:.2f}")

    def percentile(data, p):
        if not data:
            return 0
        s = sorted(data)
        k = (len(s) - 1) * (p / 100.0)
        f = int(k)
        c = int(k + 0.5)
        if f == c:
            return s[int(k)]
        d0 = s[f] * (c - k)
        d1 = s[c] * (k - f)
        return d0 + d1

    # 6. conversations length distribution
    if conversation_lengths:
        mean_len = statistics.mean(conversation_lengths)
        p50 = percentile(conversation_lengths, 50)
        p90 = percentile(conversation_lengths, 90)
        print(f"Conversation length distribution: mean={mean_len:.2f}, p50={p50:.2f}, p90={p90:.2f}")

    # 7. # of conversations distribution per user
    if conversations_per_user:
        mean_conv = statistics.mean(conversations_per_user)
        print(f"# of conversations distribution per user: mean={mean_conv:.2f}")


if __name__ == "__main__":
    get_user_messages_with_bot_name()
    get_plugin_data_by_persona_name()
    run_questions_analysis()
