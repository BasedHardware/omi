"""
LLM Usage Database Operations.

Stores and queries LLM token usage by feature in Firestore.
Schema: users/{uid}/llm_usage/{date} -> {feature -> {model -> {input_tokens, output_tokens}}}
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore

from ._client import db

transactional = getattr(firestore, 'transactional', lambda fn: fn)  # pyright: ignore[reportUnknownMemberType]


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


def record_llm_usage(
    uid: str,
    feature: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
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
    if not model:
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

    update_data: Dict[str, Any] = {
        f"{feature}.{safe_model}.input_tokens": firestore.Increment(input_tokens),
        f"{feature}.{safe_model}.output_tokens": firestore.Increment(output_tokens),
        f"{feature}.{safe_model}.call_count": firestore.Increment(1),
        "date": doc_id,  # Store date as a field for collection-group queries
        "last_updated": datetime.now(timezone.utc),
    }

    usage_ref.set(update_data, merge=True)


@transactional  # pyright: ignore[reportUntypedFunctionDecorator]
def _record_chat_quota_question_transaction(
    transaction: Any,
    usage_ref: Any,
    event_ref: Any,
    event_data: Dict[str, Any],
    doc_id: str,
) -> bool:
    event_snapshot = event_ref.get(transaction=transaction)
    if getattr(event_snapshot, "exists", False):
        return False

    now = datetime.now(timezone.utc)
    transaction.set(event_ref, event_data)
    transaction.set(
        usage_ref,
        {
            'backend_chat.quota_questions': firestore.Increment(1),
            'date': doc_id,
            'last_updated': now,
        },
        merge=True,
    )
    return True


def record_chat_quota_question(
    uid: str,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
) -> bool:
    """Record one accepted visible backend chat question exactly once.

    This is the product-boundary quota counter for mobile/backend chat. It is
    intentionally separate from ``chat.*.call_count``, which is LLM telemetry
    and can vary with implementation details.
    """
    if not idempotency_key:
        raise ValueError('idempotency_key is required')

    now = datetime.now(timezone.utc)
    doc_id = now.strftime('%Y-%m-%d')
    event_id = hashlib.sha256(f'{uid}:{idempotency_key}'.encode('utf-8')).hexdigest()

    user_ref = db.collection('users').document(uid)
    usage_ref = user_ref.collection('llm_usage').document(doc_id)
    event_ref = user_ref.collection('chat_quota_events').document(event_id)
    event_data: Dict[str, Any] = {
        'idempotency_key': idempotency_key,
        'source': source,
        'message_id': message_id,
        'chat_session_id': chat_session_id,
        'platform': platform,
        'created_at': now,
        'date': doc_id,
    }

    transaction = db.transaction()
    return _record_chat_quota_question_transaction(transaction, usage_ref, event_ref, event_data, doc_id)


def get_daily_usage(uid: str, date: Optional[datetime] = None) -> Dict[str, Any]:
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
    if getattr(doc, "exists", False):
        return _typed_doc(doc)
    return {}


def _aggregate_summary(data: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for feature, models in data.items():
        if feature in ("last_updated",):
            continue
        if not isinstance(models, dict):
            continue

        if feature not in summary:
            summary[feature] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}

        models_dict: Dict[str, Any] = cast(Dict[str, Any], models)
        for _, tokens in models_dict.items():
            if isinstance(tokens, dict):
                token_dict: Dict[str, Any] = cast(Dict[str, Any], tokens)
                summary[feature]["input_tokens"] += int(token_dict.get("input_tokens", 0) or 0)
                summary[feature]["output_tokens"] += int(token_dict.get("output_tokens", 0) or 0)
                summary[feature]["call_count"] += int(token_dict.get("call_count", 0) or 0)
    return summary


def get_usage_summary(uid: str, days: int = 30) -> Dict[str, Dict[str, int]]:
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
        data = _typed_doc(doc)
        partial = _aggregate_summary(data)
        for feature, tokens in partial.items():
            if feature not in summary:
                summary[feature] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}
            summary[feature]["input_tokens"] += tokens["input_tokens"]
            summary[feature]["output_tokens"] += tokens["output_tokens"]
            summary[feature]["call_count"] += tokens["call_count"]

    return summary


def _features_from_summary(summary: Dict[str, Dict[str, int]], limit: int) -> List[Dict[str, Any]]:
    features: List[Dict[str, Any]] = []
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


def get_top_features(uid: str, days: int = 30, limit: int = 3) -> List[Dict[str, Any]]:
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
    return _features_from_summary(summary, limit)


def get_global_top_features(days: int = 30, limit: int = 3) -> List[Dict[str, Any]]:
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
        data = _typed_doc(doc)
        partial = _aggregate_summary(data)
        for feature, tokens in partial.items():
            if feature not in global_summary:
                global_summary[feature] = {"input_tokens": 0, "output_tokens": 0, "call_count": 0}
            global_summary[feature]["input_tokens"] += tokens["input_tokens"]
            global_summary[feature]["output_tokens"] += tokens["output_tokens"]
            global_summary[feature]["call_count"] += tokens["call_count"]

    return _features_from_summary(global_summary, limit)


# ============================================================================
# BUCKET-BASED LLM USAGE
#
# Flat key scheme ("desktop_chat" / "desktop_chat_{account}") with fields:
# input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
# total_tokens, cost_usd, call_count.
#
# This differs from the {feature}.{model} nesting above.  Both schemas
# coexist in the same date-keyed documents using Firestore's schemaless design.
# ============================================================================


def record_llm_usage_bucket(
    uid: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    bucket: str = 'desktop_chat',
    account: str = 'omi',
) -> None:
    """Record LLM token usage into a flat bucket with atomic increments.

    Dual-writes to both the primary bucket and a per-account alias
    (``{bucket}_{account}``) for per-account breakdown.
    """
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = db.collection("users").document(uid).collection("llm_usage").document(today)

    acct_key = f'{bucket}_{account}'
    update: Dict[str, Any] = {
        f'{bucket}.input_tokens': firestore.Increment(input_tokens),
        f'{bucket}.output_tokens': firestore.Increment(output_tokens),
        f'{bucket}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{bucket}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{bucket}.total_tokens': firestore.Increment(total_tokens),
        f'{bucket}.cost_usd': firestore.Increment(cost_usd),
        f'{bucket}.call_count': firestore.Increment(1),
        f'{acct_key}.input_tokens': firestore.Increment(input_tokens),
        f'{acct_key}.output_tokens': firestore.Increment(output_tokens),
        f'{acct_key}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{acct_key}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{acct_key}.total_tokens': firestore.Increment(total_tokens),
        f'{acct_key}.cost_usd': firestore.Increment(cost_usd),
        f'{acct_key}.call_count': firestore.Increment(1),
        'date': today,
        'last_updated': datetime.now(timezone.utc),
    }
    ref.set(update, merge=True)


def get_total_llm_cost(uid: str, bucket: str = 'desktop_chat') -> float:
    """Sum cost_usd from the given bucket.

    When the bucket dual-writes to both ``{bucket}`` and ``{bucket}_{account}``,
    this reads only the primary bucket to avoid double-counting.
    """
    col = db.collection("users").document(uid).collection("llm_usage")
    total = 0.0
    for doc in col.stream():
        data = _typed_doc(doc)
        dc = data.get(bucket)
        if isinstance(dc, dict):
            dc_dict: Dict[str, Any] = cast(Dict[str, Any], dc)
            total += float(dc_dict.get('cost_usd', 0.0) or 0.0)
    return round(total, 6)
