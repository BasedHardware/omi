"""Durable LLM-gateway accounting ledger writes.

The gateway is the producer, but Firestore is the canonical backend-owned
ledger. Events are immutable and idempotent by provider-attempt ID so retries
or process restarts cannot double-count a billed attempt.

Every newly persisted attempt also increments a fail-open hashed per-user-day
rollup (``llm_gateway_user_days``) so the finops daily pull can read one
document per user-day instead of paging every attempt document.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from database._client import get_firestore_client
from database.llm_usage import resolve_usage_plan_id

ATTEMPTS_COLLECTION = 'llm_gateway_attempts'
USER_DAYS_COLLECTION = 'llm_gateway_user_days'

_UNATTRIBUTED = 'unattributed'
_ANONYMOUS_UID_HASH = 'anonymous'
_PROVIDER_COST_FIELDS = {'openai': 'cost_openai', 'gemini': 'cost_gemini'}
_OTHER_PROVIDER_COST_FIELD = 'cost_other_provider'

logger = logging.getLogger(__name__)


def record_llm_gateway_attempt(
    event: Mapping[str, Any],
    *,
    firestore_client: Any | None = None,
) -> bool:
    """Create one immutable gateway attempt event.

    Returns ``True`` for a new event and ``False`` for an already-persisted
    attempt. No prompts, provider response bodies, or credentials are accepted
    in the event schema constructed by the gateway.
    """
    attempt_id = _required_string(event, 'attempt_id')
    client = firestore_client or get_firestore_client()
    data = dict(event)
    data['subscription_tier'] = _subscription_tier(client, data.get('user_uid'))
    plan_id = resolve_usage_plan_id(data.get('user_uid', ''), firestore_client=client)
    data['plan_id'] = plan_id
    data['plan_attribution_status'] = 'complete' if plan_id is not None else 'missing'
    payer = data.get('payer')
    if payer == 'byok':
        data['cost_attribution_status'] = 'excluded'
        data['cost_exclusion'] = 'byok_provider_cost'
    elif data.get('estimated_cost_micro_usd') is not None and data.get('cost_status') not in {'not_omi_cost'}:
        data['cost_attribution_status'] = 'complete'
    elif data.get('cost_status') == 'not_omi_cost':
        data['cost_attribution_status'] = 'excluded'
        data['cost_exclusion'] = 'provider_not_omi_cost'
    else:
        data['cost_attribution_status'] = 'missing'
    try:
        client.collection(ATTEMPTS_COLLECTION).document(attempt_id).create(data)
    except AlreadyExists:
        return False
    _record_user_day_rollup(client, data)
    return True


def _subscription_tier(client: Any, uid: object) -> str:
    if not isinstance(uid, str) or not uid:
        return 'unattributed'
    try:
        snapshot = client.collection('users').document(uid).get(['subscription'])
        if not getattr(snapshot, 'exists', False):
            return 'basic'
        raw = snapshot.to_dict()
        if not isinstance(raw, Mapping):
            return 'unknown'
        subscription = raw.get('subscription')
        if not isinstance(subscription, Mapping):
            return 'basic'
        plan = subscription.get('plan')
        if not isinstance(plan, str) or not plan.strip():
            return 'basic'
        # `free` was migrated to the current internal basic-plan identifier.
        return 'basic' if plan.strip() == 'free' else plan.strip()
    except Exception:
        # A plan lookup must not discard a confirmed provider-usage event. The
        # event remains attributable by UID and is auditable as tier unknown.
        return 'unknown'


def _required_string(event: Mapping[str, Any], key: str) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f'gateway accounting event requires {key}')
    return value


def _record_user_day_rollup(client: Any, data: Mapping[str, Any]) -> None:
    """Increment the hashed per-user-day rollup for one newly stored attempt.

    Fail-open by contract: the immutable attempt document already carries the
    canonical record, so a rollup failure is logged and never propagates. The
    document id and fields hold only the finops ``sha256(uid)[:16]`` hash —
    never a raw Firebase uid — and the ``date`` field keeps the per-day pull on
    Firestore's automatic single-field index (no composite index required).
    """
    uid_hash: str | None = None
    try:
        date = data.get('date')
        if not isinstance(date, str) or not date:
            logger.warning('user-day rollup skipped: accounting event without a date')
            return
        uid_hash = _hashed_uid(data.get('user_uid'))
        cost = _micro_usd(data.get('estimated_cost_micro_usd'))
        update: dict[str, Any] = {
            'date': date,
            'uid_hash': uid_hash,
            'attempts': firestore.Increment(1),
            # Last-seen attribution: plain fields overwrite via set(..., merge=True).
            'app_platform': _platform(data.get('app_platform')),
            'subscription_tier': data.get('subscription_tier'),
            'plan_id': data.get('plan_id'),
        }
        if cost:
            update['cost_micro_usd_sum'] = firestore.Increment(cost)
            update[_provider_cost_field(data.get('provider'))] = firestore.Increment(cost)
            update[f'fc_{_feature_class(data.get("feature"))}'] = firestore.Increment(cost)
        if data.get('cost_status') != 'estimated':
            update['attempts_unpriced'] = firestore.Increment(1)
        client.collection(USER_DAYS_COLLECTION).document(f'{date}_{uid_hash}').set(update, merge=True)
    except Exception:
        # The attempt ledger write already succeeded; losing one rollup
        # increment is recoverable from the attempts collection itself.
        logger.exception('user-day rollup failed (date=%s uid_hash=%s)', data.get('date'), uid_hash)


def _hashed_uid(uid: object) -> str:
    """The finops ledger uid convention: sha256 prefix, or anonymous when absent."""
    if isinstance(uid, str) and uid:
        return hashlib.sha256(uid.encode()).hexdigest()[:16]
    return _ANONYMOUS_UID_HASH


def _micro_usd(value: object) -> int:
    return value if isinstance(value, int) else 0


def _platform(value: object) -> str:
    return value if isinstance(value, str) and value else _UNATTRIBUTED


def _provider_cost_field(provider: object) -> str:
    return _PROVIDER_COST_FIELDS.get(provider if isinstance(provider, str) else '', _OTHER_PROVIDER_COST_FIELD)


def _feature_class(feature: object) -> str:
    """Mirror the finops ledger puller's per-user feature bucketing."""
    if not isinstance(feature, str) or not feature:
        return 'extraction'
    if feature.startswith('desktop_'):
        return 'desktop'
    if feature == 'proactive_notification':
        return 'proactive_notification'
    if feature.startswith('chat') or feature.startswith('persona'):
        return 'chat'
    if feature == 'translation':
        return 'translation'
    if 'embedding' in feature:
        return 'embeddings'
    return 'extraction'
