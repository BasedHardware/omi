"""Flagged admission on the durable usage projection; legacy accounts bypass it."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from config import ladder_v1 as policy
from config.plan_catalog import ENTITLEMENT_VERSIONS
from utils.observability.fallback import record_fallback
from utils.observability.ladder_v1 import record_coverage

_UNRESOLVED = object()


def account(uid: str, subscription: Any = _UNRESOLVED, *, firestore_client: Any = None):
    if subscription is _UNRESOLVED:
        from database import users as users_db

        subscription = users_db.get_user_valid_subscription(uid, firestore_client=firestore_client, provision=False)
    return policy.entitlements(subscription)


def usage_snapshot(uid: str, subscription: Any = _UNRESOLVED, *, firestore_client: Any = None) -> dict | None:
    entitlement = account(uid, subscription, firestore_client=firestore_client)
    if entitlement is None:
        return None
    from database import usage_units

    now = datetime.now(timezone.utc)
    snapshot = usage_units.get_usage_units(uid, now, firestore_client=firestore_client, entitlements=entitlement)
    if policy.budget_enforcement_enabled():
        record_coverage(snapshot.get('completeness', {}))
    reset = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    budget = snapshot['budget_units']
    if not budget or budget <= 0:
        raise ValueError('Invalid ladder usage budget')
    return dict(
        snapshot,
        budget_percent=100 * snapshot['used_units'] / budget,
        reset_at=int(reset.timestamp()),
        period_id=now.strftime('%Y-%m'),
        plan_id=entitlement['plan_id'],
    )


def budget_snapshot(uid: str, subscription: Any = _UNRESOLVED, *, firestore_client: Any = None):
    if not policy.budget_enforcement_enabled():
        return None
    snapshot = usage_snapshot(uid, subscription, firestore_client=firestore_client)
    coverage = (snapshot or {}).get('completeness', {})
    if any(
        coverage.get(key, 0) > 0
        for key in ('ambiguous_priced_transcription_seconds', 'ambiguous_priced_gateway_attempts')
    ):
        # Original mixed-status quantities cannot be reconstructed without
        # double pricing. Funded STT catches this transient denial and retains
        # audio; other paid work retries instead of treating an unknown cap as
        # available. A new UTC month or repaired attribution clears the guard.
        raise HTTPException(status_code=503, detail={'error': 'usage_budget_coverage_unavailable'})
    return snapshot


def limit_detail(snapshot: dict) -> dict:
    return {
        'error': 'usage_budget_exhausted',
        'trigger': 'usage_budget',
        'reset_at': snapshot['reset_at'],
        'period_id': snapshot['period_id'],
        'plan_type': snapshot['plan_id'],
        'state': 'held_pending_choice',
        'choices': ['on_device', 'upgrade'],
    }


def enforce_budget(uid: str, *, firestore_client: Any = None) -> bool:
    snapshot = budget_snapshot(uid, firestore_client=firestore_client)
    if snapshot is None:
        return False
    if snapshot['budget_percent'] >= 100:
        raise HTTPException(status_code=402, detail=limit_detail(snapshot))
    return True


def enforce_chat_budget(uid: str, *, firestore_client: Any = None) -> bool:
    snapshot = budget_snapshot(uid, firestore_client=firestore_client)
    if snapshot is None:
        return False
    if snapshot['budget_percent'] >= 100:
        from utils.storefront_copy import chat_at_cap

        raise HTTPException(
            status_code=402,
            detail={
                'error': 'usage_budget_exhausted',
                'trigger': 'usage_budget',
                'chat_at_cap': chat_at_cap(snapshot['plan_id'], snapshot['reset_at']),
            },
        )
    return True


def feature_allowed(uid: str, feature: str, subscription: Any = _UNRESOLVED) -> bool | None:
    if not policy.enabled('LADDER_V1_PRO_GATES_ENABLED'):
        return None
    entitlement = account(uid, subscription)
    if entitlement is None:
        return None
    if policy.pro_trigger(feature):
        return entitlement['plan_id'] in ('operator', 'architect')
    return True


def enforce_daily_cap(uid: str) -> dict | None:
    if not policy.mcp_daily_caps_enabled():
        return None
    entitlement = account(uid)
    if entitlement is None:
        return None
    cap = ENTITLEMENT_VERSIONS['ladder_v1']['mcp_daily_caps'][entitlement['plan_id']]
    try:
        from database.ladder_v1 import reserve_daily_request

        result = reserve_daily_request(uid, cap)
    except Exception:
        record_fallback(
            component='other',
            from_mode='ladder_daily_cap',
            to_mode='unavailable',
            reason='provider_error',
            outcome='degraded',
        )
        raise HTTPException(status_code=503, detail='usage_unavailable', headers={'Retry-After': '30'})
    if not result['allowed']:
        raise HTTPException(
            status_code=429,
            detail={
                'error': 'mcp_daily_cap',
                'trigger': 'mcp_daily_cap',
                **result,
                'upgrade_plan': (
                    'plus'
                    if entitlement['plan_id'] == 'basic'
                    else 'operator' if entitlement['plan_id'] == 'plus' else None
                ),
            },
            headers={'Retry-After': str(max(1, result['reset_at'] - int(datetime.now(timezone.utc).timestamp())))},
        )
    return result
