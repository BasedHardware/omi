"""Durable LLM-gateway accounting ledger writes.

The gateway is the producer, but the backend-owned datastore is the canonical
ledger. Events are immutable and idempotent by provider-attempt ID so retries
or process restarts cannot double-count a billed attempt.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from database.store import get_document_store
from database.store.errors import AlreadyExists

ATTEMPTS_COLLECTION = 'llm_gateway_attempts'


def _store():
    return get_document_store()


def record_llm_gateway_attempt(event: Mapping[str, Any]) -> bool:
    """Create one immutable gateway attempt event.

    Returns ``True`` for a new event and ``False`` for an already-persisted
    attempt. No prompts, provider response bodies, or credentials are accepted
    in the event schema constructed by the gateway.
    """
    attempt_id = _required_string(event, 'attempt_id')
    data = dict(event)
    data['subscription_tier'] = _subscription_tier(data.get('user_uid'))
    try:
        _store().create(f'{ATTEMPTS_COLLECTION}/{attempt_id}', data)
    except AlreadyExists:
        return False
    return True


def _subscription_tier(uid: object) -> str:
    if not isinstance(uid, str) or not uid:
        return 'unattributed'
    try:
        snapshot = _store().get(f'users/{uid}', fields=['subscription'])
        if not snapshot.exists:
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
