"""Durable LLM-gateway accounting ledger writes.

The gateway is the producer, but Firestore is the canonical backend-owned
ledger. Events are immutable and idempotent by provider-attempt ID so retries
or process restarts cannot double-count a billed attempt.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.api_core.exceptions import AlreadyExists

from database._client import get_firestore_client
from database.llm_usage import resolve_usage_plan_id

ATTEMPTS_COLLECTION = 'llm_gateway_attempts'


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
