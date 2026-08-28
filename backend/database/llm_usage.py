"""
LLM Usage Database Operations.

Stores and queries LLM token usage by feature in Firestore.
Schema: users/{uid}/llm_usage/{date} -> {feature -> {model -> {input_tokens, output_tokens}}}
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore

from config.plan_catalog import PlanType, WIRE_PLAN_ALIASES
from ._client import db

transactional = getattr(firestore, 'transactional', lambda fn: fn)  # pyright: ignore[reportUnknownMemberType]


def _usage_client(firestore_client: Any | None) -> Any:
    return firestore_client if firestore_client is not None else db


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


_UNATTRIBUTED_PLAN = '_unattributed'
_COST_STATUSES = {'complete', 'partial', 'missing', 'excluded'}


def _canonical_plan_id(value: object) -> str | None:
    """Return a catalog plan id, or ``None`` for an unknown wire value."""
    raw = value.value if isinstance(value, PlanType) else value
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw == 'free':
        raw = PlanType.basic.value
    try:
        return PlanType(raw).value
    except ValueError:
        alias = WIRE_PLAN_ALIASES.get(raw)
        return alias.value if alias is not None else None


def resolve_usage_plan_id(uid: str, *, firestore_client: Any | None = None) -> str | None:
    """Resolve the server-owned catalog plan used for a usage event.

    A missing or unreadable subscription is deliberately returned as ``None``.
    It must become an explicitly unattributed report row, never an assumed
    ``basic`` row: otherwise a read failure would move paid cost into the free
    plan and make the resulting COGS report look complete.
    """
    if not uid:
        return None
    client = _usage_client(firestore_client)
    try:
        snapshot = client.collection('users').document(uid).get(['subscription'])
    except TypeError:
        # Small test doubles and older Firestore adapters do not accept a field
        # projection. The full read remains bounded to this one user document.
        try:
            snapshot = client.collection('users').document(uid).get()
        except Exception:
            return None
    except Exception:
        return None
    if not getattr(snapshot, 'exists', False):
        return None
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        return None
    subscription = raw.get('subscription')
    if not isinstance(subscription, dict):
        return None
    return _canonical_plan_id(subscription.get('plan'))


def _plan_key(uid: str, firestore_client: Any | None) -> str:
    return resolve_usage_plan_id(uid, firestore_client=firestore_client) or _UNATTRIBUTED_PLAN


def _nested(update: Dict[str, Any]) -> Dict[str, Any]:
    """Expand dotted field paths into nested maps, for writes that use ``set(..., merge=True)``.

    Firestore treats a dot as a field PATH in ``update()`` but as a literal character in ``set()``. These
    usage documents are written with ``set(merge=True)`` because they must be created on first use, so a
    key like ``chat.gpt-4o.input_tokens`` lands as ONE top-level field whose name contains dots — the
    counter still increments correctly, but nothing is nested, and every reader that walks
    ``feature -> model -> counter`` (``get_usage_summary``, ``_aggregate_summary``,
    ``get_plan_usage_report``) skips it and reports empty usage.

    Every dot in these keys is a separator by construction: the model name, the cost-exclusion label and
    the plan id are each sanitised of ``.`` before being interpolated, and the remaining segments are
    literals in this module.
    """
    nested: Dict[str, Any] = {}
    for path, value in update.items():
        if '.' not in path:
            nested[path] = value
            continue
        cursor = nested
        *parents, leaf = path.split('.')
        for segment in parents:
            branch = cursor.get(segment)
            if not isinstance(branch, dict):
                branch = {}
                cursor[segment] = branch
            cursor = branch
        cursor[leaf] = value
    return nested


def _record_plan_metadata(
    update: Dict[str, Any],
    plan_key: str,
    *,
    cost_status: str,
    cost_exclusion: str | None = None,
) -> None:
    """Add auditable status counters without fabricating a cost value."""
    status = cost_status if cost_status in _COST_STATUSES else 'missing'
    if cost_exclusion is None and status in {'missing', 'partial'}:
        cost_exclusion = 'provider_cost_not_recorded'
    root = f'plan_usage.{plan_key}._metadata'
    update[f'{root}.cost_status_counts.{status}'] = firestore.Increment(1)
    update[f'{root}.last_cost_status'] = status
    if cost_exclusion:
        safe_exclusion = (
            cost_exclusion.replace('.', '_')
            .replace('/', '_')
            .replace('~', '_')
            .replace('*', '_')
            .replace('[', '_')
            .replace(']', '_')
            .replace('`', '_')
        )
        update[f'{root}.cost_exclusions.{safe_exclusion}'] = firestore.Increment(1)


def _record_plan_bucket(
    update: Dict[str, Any],
    plan_key: str,
    bucket: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int = 0,
    quota_questions: int = 0,
    cost_usd: float | None = None,
    count_call: bool = True,
) -> None:
    prefix = f'plan_usage.{plan_key}.{bucket}'
    for field, value in (
        ('input_tokens', input_tokens),
        ('output_tokens', output_tokens),
        ('cache_read_tokens', cache_read_tokens),
        ('cache_write_tokens', cache_write_tokens),
        ('total_tokens', total_tokens),
        ('quota_questions', quota_questions),
    ):
        if value:
            update[f'{prefix}.{field}'] = firestore.Increment(value)
    if cost_usd is not None:
        update[f'{prefix}.cost_usd'] = firestore.Increment(cost_usd)
    if count_call:
        update[f'{prefix}.call_count'] = firestore.Increment(1)


def record_llm_usage(
    uid: str,
    feature: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cost_usd: float | None = None,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    firestore_client: Any | None = None,
) -> None:
    """
    Record LLM token usage for a user and feature.

    Uses Firestore atomic increments for safe concurrent updates.

    Args:
        uid: User ID
        feature: Feature name (e.g., "chat", "rag", "conversation_processing")
        model: Model name (e.g., "gpt-5.6-luna", "gpt-5-nano")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
    """
    if input_tokens == 0 and output_tokens == 0:
        return
    if cost_status == 'complete' and cost_usd is None:
        raise ValueError('complete cost attribution requires cost_usd')

    now = datetime.now(timezone.utc)
    doc_id = f"{now.year}-{now.month:02d}-{now.day:02d}"

    client = _usage_client(firestore_client)
    user_ref = client.collection("users").document(uid)
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

    plan_key = _plan_key(uid, firestore_client)
    plan_prefix = f'plan_usage.{plan_key}.{feature}.{safe_model}'
    update_data[f'{plan_prefix}.input_tokens'] = firestore.Increment(input_tokens)
    update_data[f'{plan_prefix}.output_tokens'] = firestore.Increment(output_tokens)
    update_data[f'{plan_prefix}.call_count'] = firestore.Increment(1)
    if cost_usd is not None:
        update_data[f'{plan_prefix}.cost_usd'] = firestore.Increment(cost_usd)
    _record_plan_metadata(
        update_data,
        plan_key,
        cost_status=cost_status,
        cost_exclusion=cost_exclusion,
    )

    usage_ref.set(_nested(update_data), merge=True)


@transactional  # pyright: ignore[reportUntypedFunctionDecorator]
def _record_chat_quota_question_transaction(
    transaction: Any,
    usage_ref: Any,
    event_ref: Any,
    event_data: Dict[str, Any],
    doc_id: str,
    plan_key: str,
) -> bool:
    event_snapshot = event_ref.get(transaction=transaction)
    if getattr(event_snapshot, "exists", False):
        return False

    now = datetime.now(timezone.utc)
    transaction.set(event_ref, event_data)
    update: Dict[str, Any] = {
        'backend_chat.quota_questions': firestore.Increment(1),
        'date': doc_id,
        'last_updated': now,
    }
    _record_plan_bucket(update, plan_key, 'backend_chat', quota_questions=1)
    _record_plan_metadata(update, plan_key, cost_status='missing', cost_exclusion='chat_token_cost_not_recorded')
    transaction.set(usage_ref, _nested(update), merge=True)
    return True


def record_chat_quota_question(
    uid: str,
    idempotency_key: str,
    source: str,
    message_id: Optional[str] = None,
    chat_session_id: Optional[str] = None,
    platform: Optional[str] = None,
    *,
    firestore_client: Any | None = None,
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

    client = _usage_client(firestore_client)
    plan_key = _plan_key(uid, firestore_client)
    plan_id = None if plan_key == _UNATTRIBUTED_PLAN else plan_key
    user_ref = client.collection('users').document(uid)
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
        'plan_id': plan_id,
        'plan_attribution_status': 'complete' if plan_id is not None else 'missing',
    }

    transaction = client.transaction()
    return _record_chat_quota_question_transaction(transaction, usage_ref, event_ref, event_data, doc_id, plan_key)


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

    # The value of a `__name__` filter must be a Key, not a string: Firestore answers
    # `400 __key__ filter value must be a Key` otherwise, so this raised on every call.
    docs = usage_collection.where("__name__", ">=", usage_collection.document(cutoff_id)).stream()

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
    cost_usd: float | None = None,
    bucket: str = 'desktop_chat',
    account: str = 'omi',
    *,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    quota_questions: int = 0,
    count_call: bool = True,
    firestore_client: Any | None = None,
) -> None:
    """Record LLM token usage into a flat bucket with atomic increments.

    Dual-writes to both the primary bucket and a per-account alias
    (``{bucket}_{account}``) for per-account breakdown.
    """
    if cost_status == 'complete' and cost_usd is None:
        raise ValueError('complete cost attribution requires cost_usd')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = _usage_client(firestore_client).collection("users").document(uid).collection("llm_usage").document(today)

    acct_key = f'{bucket}_{account}'
    update: Dict[str, Any] = {
        f'{bucket}.input_tokens': firestore.Increment(input_tokens),
        f'{bucket}.output_tokens': firestore.Increment(output_tokens),
        f'{bucket}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{bucket}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{bucket}.total_tokens': firestore.Increment(total_tokens),
        f'{acct_key}.input_tokens': firestore.Increment(input_tokens),
        f'{acct_key}.output_tokens': firestore.Increment(output_tokens),
        f'{acct_key}.cache_read_tokens': firestore.Increment(cache_read_tokens),
        f'{acct_key}.cache_write_tokens': firestore.Increment(cache_write_tokens),
        f'{acct_key}.total_tokens': firestore.Increment(total_tokens),
        'date': today,
        'last_updated': datetime.now(timezone.utc),
    }
    if cost_usd is not None:
        update[f'{bucket}.cost_usd'] = firestore.Increment(cost_usd)
        update[f'{acct_key}.cost_usd'] = firestore.Increment(cost_usd)
    if count_call:
        update[f'{bucket}.call_count'] = firestore.Increment(1)
        update[f'{acct_key}.call_count'] = firestore.Increment(1)
    if quota_questions:
        update[f'{bucket}.quota_questions'] = firestore.Increment(quota_questions)
        update[f'{acct_key}.quota_questions'] = firestore.Increment(quota_questions)

    plan_key = _plan_key(uid, firestore_client)
    _record_plan_bucket(
        update,
        plan_key,
        bucket,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        total_tokens=total_tokens,
        quota_questions=quota_questions,
        cost_usd=cost_usd,
        count_call=count_call,
    )
    _record_plan_metadata(update, plan_key, cost_status=cost_status, cost_exclusion=cost_exclusion)
    ref.set(_nested(update), merge=True)


def record_llm_cost_exclusion(
    uid: str,
    *,
    bucket: str = 'desktop_chat',
    account: str = 'omi',
    cost_exclusion: str,
    firestore_client: Any | None = None,
) -> None:
    """Record a non-OMI or otherwise excluded cost without fake usage/cost."""
    if not cost_exclusion:
        raise ValueError('cost_exclusion is required')
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    ref = _usage_client(firestore_client).collection('users').document(uid).collection('llm_usage').document(today)
    plan_key = _plan_key(uid, firestore_client)
    update: Dict[str, Any] = {'date': today, 'last_updated': datetime.now(timezone.utc)}
    _record_plan_metadata(update, plan_key, cost_status='excluded', cost_exclusion=cost_exclusion)
    ref.set(_nested(update), merge=True)


def _merge_cost_status(existing: str | None, observed: str) -> str:
    statuses = {existing, observed} - {None}
    if statuses == {'complete'} or (statuses and statuses <= {'complete', 'excluded'} and 'complete' in statuses):
        return 'complete'
    if statuses == {'excluded'}:
        return 'excluded'
    if 'partial' in statuses:
        return 'partial'
    if 'missing' in statuses:
        return 'missing'
    return observed


def _accumulate_plan_data(row: Dict[str, Any], value: Dict[str, Any]) -> None:
    """Collect metrics from both bucket and feature/model plan layouts."""
    for key, child in value.items():
        if key == '_metadata':
            continue
        if isinstance(child, dict):
            _accumulate_plan_data(row, child)
            continue
        if key == 'input_tokens':
            row['input_tokens'] += int(child or 0)
        elif key == 'output_tokens':
            row['output_tokens'] += int(child or 0)
        elif key == 'total_tokens':
            row['total_tokens'] += int(child or 0)
        elif key == 'quota_questions':
            row['questions'] += int(child or 0)
        elif key == 'cost_usd':
            row['cost_usd'] = (row['cost_usd'] or 0.0) + float(child or 0.0)


def get_plan_usage_report(uid: str, days: int = 30) -> Dict[str, Dict[str, Any]]:
    """Return usage/cost rows keyed by catalog plan without zero-filling cost.

    Legacy rows that predate plan attribution are retained under
    ``_unattributed``. A missing cost field is represented by ``None`` and a
    status, so a real zero and an unmeasured cost cannot be confused.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_id = f'{cutoff.year}-{cutoff.month:02d}-{cutoff.day:02d}'
    usage_collection = db.collection('users').document(uid).collection('llm_usage')
    report: Dict[str, Dict[str, Any]] = {}

    # A `__name__` filter takes a Key, not a string (see get_usage_summary above).
    for doc in usage_collection.where('__name__', '>=', usage_collection.document(cutoff_id)).stream():
        data = _typed_doc(doc)
        plan_usage = data.get('plan_usage')
        if isinstance(plan_usage, dict):
            for plan_key, plan_data in plan_usage.items():
                if not isinstance(plan_data, dict):
                    continue
                row = report.setdefault(
                    str(plan_key),
                    {
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'total_tokens': 0,
                        'questions': 0,
                        'cost_usd': None,
                        'cost_status': None,
                        'cost_exclusions': {},
                    },
                )
                metadata = plan_data.get('_metadata')
                if isinstance(metadata, dict):
                    counts = metadata.get('cost_status_counts')
                    if isinstance(counts, dict):
                        for status, count in counts.items():
                            if int(count or 0) > 0:
                                row['cost_status'] = _merge_cost_status(row['cost_status'], str(status))
                    exclusions = metadata.get('cost_exclusions')
                    if isinstance(exclusions, dict):
                        for exclusion, count in exclusions.items():
                            row['cost_exclusions'][str(exclusion)] = row['cost_exclusions'].get(
                                str(exclusion), 0
                            ) + int(count or 0)
                _accumulate_plan_data(row, plan_data)

        # A document with only legacy fields cannot be safely joined to a
        # catalog plan. Mark that fact explicitly rather than assigning basic.
        if not isinstance(plan_usage, dict) and any(
            key == 'desktop_chat' or key.startswith('desktop_chat.') or key.startswith('chat.') for key in data
        ):
            row = report.setdefault(
                _UNATTRIBUTED_PLAN,
                {
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'total_tokens': 0,
                    'questions': 0,
                    'cost_usd': None,
                    'cost_status': 'missing',
                    'cost_exclusions': {},
                },
            )
            for key, value in data.items():
                if isinstance(value, dict) and (key == 'desktop_chat' or key.startswith('chat')):
                    _accumulate_plan_data(row, value)
                elif isinstance(value, (int, float)):
                    if key.endswith('.quota_questions') or (key.startswith('chat.') and key.endswith('.call_count')):
                        row['questions'] += int(value)
            row['cost_exclusions']['plan_snapshot_missing'] = row['cost_exclusions'].get('plan_snapshot_missing', 0) + 1
            row['cost_status'] = 'missing'

    for row in report.values():
        row['cost_status'] = row['cost_status'] or 'missing'
    return report


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
