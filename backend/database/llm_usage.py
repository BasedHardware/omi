"""
LLM Usage Database Operations.

Stores and queries LLM token usage by feature in Firestore.
Schema: users/{uid}/llm_usage/{date} -> {feature -> {model -> {input_tokens, output_tokens}}}
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from google.cloud import firestore

from ._client import db


def record_llm_usage(
    uid: str,
    feature: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
):
    """
    Record LLM token usage for a user and feature.

    Uses Firestore atomic increments for safe concurrent updates.

    Args:
        uid: User ID
        feature: Feature name (e.g., "chat", "rag", "conversation_processing")
        model: Model name (e.g., "gpt-4.1-mini", "o4-mini")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
    """
    if input_tokens == 0 and output_tokens == 0:
        return

    now = datetime.now(timezone.utc)
    doc_id = f"{now.year}-{now.month:02d}-{now.day:02d}"

    user_ref = db.collection("users").document(uid)
    usage_ref = user_ref.collection("llm_usage").document(doc_id)

    # Use nested field paths for atomic increments
    # Structure: {feature}.{model}.{input_tokens|output_tokens}
    # Firestore doesn't allow '.', '/', '[', ']', '*', '`', '~' in field names
    if not isinstance(model, str) or not model:
        model = "unknown"

    safe_model = (
        model.replace(".", "_")
        .replace("/", "_")
        .replace("~", "_")
        .replace("*", "_")
        .replace("[", "_")
        .replace("]", "_")
        .replace("`", "_")
    )

    update_data = {
        f"{feature}.{safe_model}.input_tokens": firestore.Increment(input_tokens),
        f"{feature}.{safe_model}.output_tokens": firestore.Increment(output_tokens),
        f"{feature}.{safe_model}.call_count": firestore.Increment(1),
        "date": doc_id,  # Store date as a field for collection-group queries
        "last_updated": datetime.now(timezone.utc),
    }

    usage_ref.set(update_data, merge=True)


def get_daily_usage(uid: str, date: Optional[datetime] = None) -> Dict:
    """
    Get LLM usage for a specific day.

    Args:
        uid: User ID
        date: Date to query (defaults to today)

    Returns:
        Dict with usage data by feature and model
    """
    if date is None:
        date = datetime.now(timezone.utc)

    doc_id = f"{date.year}-{date.month:02d}-{date.day:02d}"
    user_ref = db.collection("users").document(uid)
    usage_ref = user_ref.collection("llm_usage").document(doc_id)

    doc = usage_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {}


def get_usage_summary(uid: str, days: int = 30) -> Dict:
    """
    Get aggregated LLM usage summary for the last N days.

    Args:
        uid: User ID
        days: Number of days to aggregate

    Returns:
        Dict with total usage by feature
    """
    user_ref = db.collection("users").document(uid)
    usage_collection = user_ref.collection("llm_usage")

    # Query last N days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_id = f"{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}"

    docs = usage_collection.where("__name__", ">=", cutoff_id).stream()

    # Aggregate by feature
    summary: Dict[str, Dict[str, int]] = {}

    for doc in docs:
        data = doc.to_dict()
        for feature, models in data.items():
            if feature in ("last_updated",):
                continue
            if not isinstance(models, dict):
                continue

            if feature not in summary:
                summary[feature] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}

            for model, tokens in models.items():
                if isinstance(tokens, dict):
                    summary[feature]["input_tokens"] += tokens.get("input_tokens", 0)
                    summary[feature]["output_tokens"] += tokens.get("output_tokens", 0)
                    summary[feature]["call_count"] += tokens.get("call_count", 0)

    return summary


def get_top_features(uid: str, days: int = 30, limit: int = 3) -> List[Dict]:
    """
    Get top features by total token usage.

    Args:
        uid: User ID
        days: Number of days to aggregate
        limit: Number of top features to return

    Returns:
        List of dicts with feature name and total tokens, sorted by usage
    """
    summary = get_usage_summary(uid, days)

    features = []
    for feature, tokens in summary.items():
        total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
        features.append(
            {
                "feature": feature,
                "input_tokens": tokens.get("input_tokens", 0),
                "output_tokens": tokens.get("output_tokens", 0),
                "total_tokens": total,
                "call_count": tokens.get("call_count", 0),
            }
        )

    features.sort(key=lambda x: x["total_tokens"], reverse=True)
    return features[:limit]


def get_global_top_features(days: int = 30, limit: int = 3) -> List[Dict]:
    """
    Get top features across all users by total token usage.

    Args:
        days: Number of days to aggregate
        limit: Number of top features to return

    Returns:
        List of dicts with feature name and total tokens
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_id = f"{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}"

    # Query all users' llm_usage subcollections
    # Note: This is a collection group query; use 'date' field instead of __name__
    # since __name__ comparisons don't work reliably for collection-group queries
    usage_query = db.collection_group("llm_usage").where("date", ">=", cutoff_id)

    global_summary: Dict[str, Dict[str, int]] = {}

    for doc in usage_query.stream():
        data = doc.to_dict()
        for feature, models in data.items():
            if feature in ("last_updated",):
                continue
            if not isinstance(models, dict):
                continue

            if feature not in global_summary:
                global_summary[feature] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}

            for model, tokens in models.items():
                if isinstance(tokens, dict):
                    global_summary[feature]["input_tokens"] += tokens.get("input_tokens", 0)
                    global_summary[feature]["output_tokens"] += tokens.get("output_tokens", 0)
                    global_summary[feature]["call_count"] += tokens.get("call_count", 0)

    features = []
    for feature, tokens in global_summary.items():
        total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
        features.append(
            {
                "feature": feature,
                "input_tokens": tokens.get("input_tokens", 0),
                "output_tokens": tokens.get("output_tokens", 0),
                "total_tokens": total,
                "call_count": tokens.get("call_count", 0),
            }
        )

    features.sort(key=lambda x: x["total_tokens"], reverse=True)
    return features[:limit]
