"""Paid-start assignment, bounded product probes, and transactional recovery dedupe.

State lives below the owning user, never in a user scan. A start is admitted only
by the owner-confirmed billing projection. Background selection uses the indexed
``next_push_probe_at`` collection-group window; app-open reads only that user's
recent paid starts. Prompt claims and the local-day cap commit atomically.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, cast
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.first_value_recovery import intake_admitted, recovery_enabled
from config.plan_catalog import PlanType, resolve_stripe_price_plan
from database._client import get_firestore_client
from database.firestore_index_registry import (
    FIRST_VALUE_DUE_PUSH_QUERY,
    FIRST_VALUE_PRODUCT_SIGNALS_QUERY,
    FIRST_VALUE_RECENT_STARTS_QUERY,
)
from utils.experiments import assigned_variant, ENROLLED_EVENT
from utils.product_telemetry import emit_product_event

EXPERIMENT_ID = 'EXP-005-first-value-recovery'
SOURCE = 'direct_paid_monthly_start'
STARTS = 'first_value_starts'
PROMPTS = 'first_value_prompts'
DELIVERY_DAYS = 'first_value_delivery_days'
DEDUPE_WINDOW = timedelta(days=30)
CAPTURE_DELAY = timedelta(hours=72)
RESULT_DELAY = timedelta(hours=24)
PENDANT_RECENCY = timedelta(hours=24)
PROBE_INTERVAL = timedelta(hours=6)
MAX_PUSH_PROBES_PER_RUN = 50
MAX_PRODUCT_ROWS = 26
LOCAL_PROMPT_CAP = 1
CAPTURE = 'capture'
RESULT = 'result'
PROMPT_KINDS = (CAPTURE, RESULT)


def _client(client: Any = None) -> Any:
    return client or get_firestore_client()


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _start_ref(uid: str, start_id: str, client: Any) -> Any:
    return client.collection('users').document(uid).collection(STARTS).document(start_id)


def _start_key(uid: str, subscription_id: str, created: int) -> str:
    return f'{uid}:{subscription_id}:{created}'


def paid_start_id(uid: str, subscription_id: str, created: int) -> str:
    return hashlib.sha256(_start_key(uid, subscription_id, created).encode()).hexdigest()[:32]


def _first_price(subscription: Mapping[str, Any]) -> Mapping[str, Any]:
    items = subscription.get('items')
    data = items.get('data') if isinstance(items, Mapping) else None
    first = data[0] if isinstance(data, list) and data else None
    price = first.get('price') if isinstance(first, Mapping) else None
    return price if isinstance(price, Mapping) else {}


def verified_direct_monthly_start(kwargs: Mapping[str, Any]) -> dict[str, Any] | None:
    """Validate the same owner-bound initial activation as Billing Subscription Started."""

    uid = kwargs.get('uid')
    event_id = kwargs.get('stripe_event_id')
    event_type = kwargs.get('stripe_event_type')
    obj = kwargs.get('subscription_obj')
    previous_attributes = kwargs.get('previous_attributes') or {}
    if not uid or not event_id or not isinstance(obj, Mapping):
        return None
    subscription_id = obj.get('id')
    resulting_id = kwargs.get('resulting_paid_subscription_id')
    if not subscription_id or subscription_id != resulting_id:
        return None
    initial = not kwargs.get('previous_paid_subscription_id') or (
        event_type == 'customer.subscription.created'
        or (event_type == 'customer.subscription.updated' and previous_attributes.get('status') == 'incomplete')
    )
    if not initial or obj.get('status') == 'trialing':
        return None
    created = obj.get('created')
    current_period_end = obj.get('current_period_end')
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (created, current_period_end)):
        return None
    price = _first_price(obj)
    recurring = price.get('recurring')
    if not isinstance(recurring, Mapping) or recurring.get('interval') != 'month':
        return None
    price_id = price.get('id')
    if not isinstance(price_id, str) or not price_id:
        return None
    try:
        plan = resolve_stripe_price_plan(price_id)
    except Exception:
        return None
    if plan == PlanType.basic:
        return None
    return {
        'uid': uid,
        'subscription_id': subscription_id,
        'price_id': price_id,
        'created': int(cast(int, created)),
        'current_period_end': int(cast(int, current_period_end)),
    }


def enroll_verified_paid_start(*, firestore_client: Any = None, **projection: Any) -> bool:
    """Persist assignment before product eligibility; OFF performs no reads or writes."""

    if not recovery_enabled():
        return False
    details = verified_direct_monthly_start(projection)
    if details is None:
        return False
    key = _start_key(details['uid'], details['subscription_id'], details['created'])
    if not intake_admitted(EXPERIMENT_ID, key):
        return False
    start_at = datetime.fromtimestamp(details['created'], timezone.utc)
    start_id = paid_start_id(details['uid'], details['subscription_id'], details['created'])
    # Hashing the paid-start key, not only uid, keeps renewed/replaced starts stable
    # and gives every paid start its own permanent 50/50 assignment.
    variant = assigned_variant(EXPERIMENT_ID, key, treatment_share=0.5)
    record = {
        'schema_version': 1,
        'experiment_id': EXPERIMENT_ID,
        'uid': details['uid'],
        'variant': variant,
        'source': SOURCE,
        'paid_start_at': start_at,
        'assigned_at': start_at,
        'expires_at': start_at + DEDUPE_WINDOW,
        'subscription_id': details['subscription_id'],
        'price_id': details['price_id'],
        # Both arms get identical value probes; only treatment can claim a prompt.
        'next_push_probe_at': start_at + RESULT_DELAY,
        'signal_coverage': 'pending',
    }
    client = _client(firestore_client)
    start_ref = _start_ref(details['uid'], start_id, client)
    try:
        start_ref.create(record)
    except Exception:
        # A retry may have committed the start but died before the enrollment
        # capture. Adopt only the identical record; deterministic insert IDs
        # make this recovery emission safe without reassigning the paid start.
        try:
            snapshot = start_ref.get()
            existing = snapshot.to_dict() or {} if snapshot.exists else {}
        except Exception:
            return False
        if (
            existing.get('variant') not in {'control', 'treatment'}
            or existing.get('subscription_id') != details['subscription_id']
            or existing.get('price_id') != details['price_id']
        ):
            return False
        record = existing
    emit_product_event(
        uid=details['uid'],
        event=ENROLLED_EVENT,
        properties={
            '$insert_id': str(uuid5(NAMESPACE_URL, f'omi:first-value:{key}')),
            'experiment_id': EXPERIMENT_ID,
            'variant': variant,
            'source': SOURCE,
            'occurred_at': start_at.isoformat().replace('+00:00', 'Z'),
        },
    )
    return True


def recent_starts(uid: str, *, now: datetime, firestore_client: Any = None) -> list[dict[str, Any]]:
    client = _client(firestore_client)
    query = FIRST_VALUE_RECENT_STARTS_QUERY.build(
        client.collection('users').document(uid).collection(STARTS),
        {'start': now - DEDUPE_WINDOW},
        field_filter_factory=FieldFilter,
    )
    rows = []
    # Ordered oldest first through the spec's index; at most two monthly starts
    # normally coexist, while the explicit cap keeps corrupt history bounded.
    for snapshot in query.order_by('paid_start_at').limit(12).stream():
        rows.append({'start_id': snapshot.id, **(snapshot.to_dict() or {})})
    return rows


def due_push_starts(
    *, now: datetime, firestore_client: Any = None, limit: int = MAX_PUSH_PROBES_PER_RUN
) -> list[dict[str, Any]]:
    client = _client(firestore_client)
    query = FIRST_VALUE_DUE_PUSH_QUERY.build(
        client.collection_group(STARTS), {'due': now}, field_filter_factory=FieldFilter
    )
    return [
        {'start_id': snapshot.id, **(snapshot.to_dict() or {})}
        for snapshot in query.order_by('next_push_probe_at').limit(min(limit, MAX_PUSH_PROBES_PER_RUN)).stream()
    ]


def set_next_push_probe(uid: str, start_id: str, value: datetime | None, *, firestore_client: Any = None) -> None:
    _start_ref(uid, start_id, _client(firestore_client)).set({'next_push_probe_at': value}, merge=True)


def _probe_conversations(uid: str, paid_start_at: datetime, client: Any) -> tuple[list[dict[str, Any]], bool]:
    query = FIRST_VALUE_PRODUCT_SIGNALS_QUERY.build(
        client.collection('users').document(uid).collection('conversations'),
        {'start': paid_start_at},
        field_filter_factory=FieldFilter,
    )
    rows = [
        {'conversation_id': snapshot.id, **(snapshot.to_dict() or {})}
        for snapshot in query.order_by('created_at').limit(MAX_PRODUCT_ROWS).stream()
    ]
    return rows, len(rows) >= MAX_PRODUCT_ROWS


def _emit_value(uid: str, variant: str, kind: str, paid_start_at: datetime, value_at: datetime) -> None:
    emit_product_event(
        uid=uid,
        event='First Value Recovery Value',
        properties={
            'experiment_id': EXPERIMENT_ID,
            'variant': variant,
            'kind': kind,
            'paid_start_at': paid_start_at.isoformat().replace('+00:00', 'Z'),
            'occurred_at': value_at.isoformat().replace('+00:00', 'Z'),
        },
    )


def probe_start(
    uid: str,
    start_id: str,
    start: Mapping[str, Any],
    *,
    now: datetime,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Refresh only value evidence; entitlement and consent are fenced again at claim."""

    client = _client(firestore_client)
    paid_start_at = _aware(start.get('paid_start_at'))
    if paid_start_at is None:
        return dict(start, signal_coverage='invalid_paid_start')
    rows, truncated = _probe_conversations(uid, paid_start_at, client)
    result: dict[str, Any] = dict(start)
    saved = [row for row in rows if not row.get('discarded') and not row.get('deleted') and not row.get('is_locked')]
    saved_at = min(
        (created for row in saved if (created := _aware(row.get('created_at'))) is not None),
        default=None,
    )
    if saved_at is not None and _aware(start.get('capture_saved_at')) is None:
        result['capture_saved_at'] = saved_at
        _emit_value(uid, str(start.get('variant')), CAPTURE, paid_start_at, saved_at)
    ready_candidates = []
    for row in saved:
        ready_at = _aware(row.get('summary_completed_at'))
        if row.get('status') == 'completed' and ready_at is not None and _aware(row.get('created_at')) is not None:
            ready_candidates.append((ready_at, str(row['conversation_id'])))
    if ready_candidates and _aware(start.get('result_opened_at')) is None:
        ready_at, conversation_id = min(ready_candidates)
        result['ready_result_at'] = ready_at
        result['ready_result_conversation_id'] = conversation_id
    result['signal_coverage'] = 'complete' if not truncated else 'truncated'
    result['last_probed_at'] = now
    _start_ref(uid, start_id, client).set(
        {
            key: result[key]
            for key in (
                'capture_saved_at',
                'ready_result_at',
                'ready_result_conversation_id',
                'signal_coverage',
                'last_probed_at',
            )
            if key in result
        },
        merge=True,
    )
    return result


def prompt_kind(start: Mapping[str, Any], kind: str, *, now: datetime) -> bool:
    paid_start_at = _aware(start.get('paid_start_at'))
    expires_at = _aware(start.get('expires_at'))
    if start.get('variant') != 'treatment' or paid_start_at is None or expires_at is None or now >= expires_at:
        return False
    if start.get('signal_coverage') != 'complete':
        return False
    if kind == CAPTURE:
        return now >= paid_start_at + CAPTURE_DELAY and _aware(start.get('capture_saved_at')) is None
    ready_at = _aware(start.get('ready_result_at'))
    return (
        kind == RESULT
        and ready_at is not None
        and now >= ready_at + RESULT_DELAY
        and _aware(start.get('result_opened_at')) is None
    )


def route_for(kind: str, start: Mapping[str, Any]) -> str:
    if kind == CAPTURE:
        return '/settings/device'
    conversation_id = start.get('ready_result_conversation_id')
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError('ready result has no route')
    return f'/conversation/{quote(conversation_id, safe="")}'


def push_access(uid: str, *, now: datetime, firestore_client: Any = None) -> dict[str, Any]:
    """Resolve actual token/timezone coverage before a push claim."""

    client = _client(firestore_client)
    user_ref = client.collection('users').document(uid)
    snapshot = user_ref.get()
    user = snapshot.to_dict() or {} if snapshot.exists else {}
    token_docs = list(user_ref.collection('fcm_tokens').limit(1).stream())
    has_token = bool(user.get('fcm_token') or token_docs)
    return {
        'notifications_authorized': has_token and user.get('notifications_enabled') is not False,
        'time_zone_covered': isinstance(user.get('time_zone'), str) and bool(user.get('time_zone')),
        'recent_pendant': (
            (pendant_at := _aware(user.get('first_value_pendant_connected_at'))) is not None
            and timedelta(0) <= now - pendant_at <= PENDANT_RECENCY
        ),
    }


def _current_suppression(user: Mapping[str, Any], start: Mapping[str, Any], *, now: datetime) -> str | None:
    subscription = user.get('subscription')
    if not isinstance(subscription, Mapping):
        return 'paid_coverage_missing'
    if subscription.get('status') == 'inactive':
        return 'paid_ended'
    if subscription.get('stripe_subscription_id') != start.get('subscription_id'):
        return 'paid_changed'
    if subscription.get('current_price_id') != start.get('price_id'):
        return 'paid_changed'
    if subscription.get('cancel_at_period_end') is True:
        return 'cancelled'
    period_end = subscription.get('current_period_end')
    if isinstance(period_end, bool) or not isinstance(period_end, (int, float)):
        return 'paid_coverage_missing'
    if period_end <= now.timestamp():
        return 'paid_ended'
    return None


def _local_date_or_suppression(user: Mapping[str, Any], now: datetime) -> tuple[str | None, str | None]:
    try:
        local = now.astimezone(ZoneInfo(str(user['time_zone'])))
    except (KeyError, TypeError, ZoneInfoNotFoundError):
        return None, 'timezone_missing'
    if user.get('notifications_enabled') is False:
        return None, 'opted_out'
    if local.hour < 8 or local.hour >= 22:
        return None, 'quiet_hours'
    return local.date().isoformat(), None


def _ready_result_available(row: Mapping[str, Any], start: Mapping[str, Any]) -> bool:
    return (
        row.get('status') == 'completed'
        and not row.get('discarded')
        and not row.get('deleted')
        and not row.get('is_locked')
        and _aware(row.get('summary_completed_at')) is not None
        and _aware(row.get('summary_completed_at')) == _aware(start.get('ready_result_at'))
    )


def claim_prompt(
    uid: str,
    start_id: str,
    start: Mapping[str, Any],
    kind: str,
    channel: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Atomically enforce entitlement, opt-out, quiet hours, daily cap and 30-day dedupe."""

    if kind not in PROMPT_KINDS or channel not in {'in_app', 'push'} or not prompt_kind(start, kind, now=now):
        return None
    client = _client(firestore_client)
    user_ref = client.collection('users').document(uid)
    start_ref = _start_ref(uid, start_id, client)
    prompt_ref = start_ref.collection(PROMPTS).document(kind)
    local_date, suppression = _local_date_or_suppression((user_ref.get().to_dict() or {}), now)
    if suppression:
        return None
    day_ref = user_ref.collection(DELIVERY_DAYS).document(local_date)
    ready_ref = None
    if kind == RESULT:
        ready_ref = user_ref.collection('conversations').document(str(start['ready_result_conversation_id']))

    @firestore.transactional
    def claim(transaction: Any) -> dict[str, Any] | None:
        # Every read precedes every write; cancellation/paid-end/value additions
        # racing this transaction fence the claim instead of producing a send.
        user_snapshot = user_ref.get(transaction=transaction)
        start_snapshot = start_ref.get(transaction=transaction)
        prompt_snapshot = prompt_ref.get(transaction=transaction)
        day_snapshot = day_ref.get(transaction=transaction)
        ready_snapshot = ready_ref.get(transaction=transaction) if ready_ref is not None else None
        user = user_snapshot.to_dict() or {} if user_snapshot.exists else {}
        current = start_snapshot.to_dict() or {} if start_snapshot.exists else {}
        if not current or prompt_snapshot.exists or not prompt_kind(current, kind, now=now):
            return None
        if ready_ref is not None:
            ready = ready_snapshot.to_dict() or {} if ready_snapshot is not None and ready_snapshot.exists else {}
            if not _ready_result_available(ready, current):
                return None
        if _current_suppression(user, current, now=now) is not None:
            return None
        current_date, current_suppression = _local_date_or_suppression(user, now)
        if current_suppression or current_date != local_date:
            return None
        day = day_snapshot.to_dict() or {} if day_snapshot.exists else {}
        if int(day.get('prompt_count', 0)) >= LOCAL_PROMPT_CAP:
            return None
        route = route_for(kind, current)
        claimed_at = now
        transaction.create(
            prompt_ref,
            {'kind': kind, 'channel': channel, 'claimed_at': claimed_at, 'expires_at': current['expires_at']},
        )
        transaction.set(day_ref, {'prompt_count': int(day.get('prompt_count', 0)) + 1, 'local_date': local_date})
        return {'kind': kind, 'channel': channel, 'route': route, 'claimed_at': claimed_at}

    return claim(client.transaction())


def resolve_push_navigation(
    uid: str,
    start_id: str,
    start: Mapping[str, Any],
    kind: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """A push tap reuses its existing claim; it never creates a second prompt."""

    if kind != RESULT or not prompt_kind(start, kind, now=now):
        return None
    client = _client(firestore_client)
    user_snapshot = client.collection('users').document(uid).get()
    user = user_snapshot.to_dict() or {} if user_snapshot.exists else {}
    if _current_suppression(user, start, now=now) is not None:
        return None
    prompt = _start_ref(uid, start_id, client).collection(PROMPTS).document(kind).get()
    data = prompt.to_dict() or {} if prompt.exists else {}
    if data.get('channel') != 'push':
        return None
    ready = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .document(str(start['ready_result_conversation_id']))
        .get()
    )
    if not _ready_result_available(ready.to_dict() or {} if ready.exists else {}, start):
        return None
    return {'kind': kind, 'channel': 'push_navigation', 'route': route_for(kind, start)}


def record_result_open(uid: str, conversation_id: str, *, now: datetime, firestore_client: Any = None) -> int:
    """Validate the owned ready result, then record the value event in every arm."""

    if not recovery_enabled() or not conversation_id or '/' in conversation_id:
        return 0
    client = _client(firestore_client)
    snapshot = client.collection('users').document(uid).collection('conversations').document(conversation_id).get()
    row = snapshot.to_dict() or {} if snapshot.exists else {}
    ready_at = _aware(row.get('summary_completed_at'))
    if (
        row.get('status') != 'completed'
        or ready_at is None
        or ready_at > now
        or row.get('discarded')
        or row.get('deleted')
        or row.get('is_locked')
    ):
        return 0
    updated = 0
    for start in recent_starts(uid, now=now, firestore_client=client):
        paid_start_at = _aware(start.get('paid_start_at'))
        if paid_start_at is None or ready_at < paid_start_at or _aware(start.get('result_opened_at')) is not None:
            continue
        if ready_at < now and start.get('ready_result_conversation_id') not in {None, conversation_id}:
            continue
        _start_ref(uid, start['start_id'], client).set(
            {'result_opened_at': now, 'ready_result_conversation_id': conversation_id, 'next_push_probe_at': None},
            merge=True,
        )
        _emit_value(uid, str(start.get('variant')), 'result_open', paid_start_at, now)
        updated += 1
    return updated


def record_pendant_connection(uid: str, *, now: datetime, firestore_client: Any = None) -> bool:
    if not recovery_enabled():
        return False
    _client(firestore_client).collection('users').document(uid).set(
        {'first_value_pendant_connected_at': now}, merge=True
    )
    return True


def mark_delivery(
    uid: str,
    start_id: str,
    kind: str,
    outcome: str,
    *,
    now: datetime,
    firestore_client: Any = None,
) -> None:
    _start_ref(uid, start_id, _client(firestore_client)).collection(PROMPTS).document(kind).set(
        {'delivery_outcome': outcome, 'delivery_recorded_at': now}, merge=True
    )


def iter_candidate_kinds(start: Mapping[str, Any], *, now: datetime) -> Iterable[str]:
    for kind in PROMPT_KINDS:
        if prompt_kind(start, kind, now=now):
            yield kind
