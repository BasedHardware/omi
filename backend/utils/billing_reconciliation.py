"""Read-only subscription drift classification; no provider/storage dependencies."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping

DRIFT_CATEGORIES = (
    'paid_in_stripe_basic_in_firestore',
    'trial_in_stripe_basic_in_firestore',
    'paid_in_firestore_no_stripe_entitlement',
    'wrong_plan',
    'wrong_price',
    'missing_price_identity',
    'stale_period',
    'subscription_id_mismatch',
    'multiple_entitled_subscriptions',
    'unknown_price',
    'unmapped_owner',
)


@dataclass(frozen=True)
class DriftReport:
    counts: dict[str, int]
    compared_users: int
    stripe_subscriptions: int


def _price_id(sub: Mapping[str, Any]) -> str | None:
    items = sub.get('items', {}).get('data', [])
    return items[0].get('price', {}).get('id') if items else None


def reconcile(
    subscriptions: list[dict], users: list[dict], price_plans: Mapping[str, str], *, as_of: int
) -> DriftReport:
    """Compare complete snapshots; keep ambiguous matches visible, never repair.

    active and trialing are entitlements, but trials are reported separately
    from paid-plan drift. An active Stripe status is not proof of collected cash.
    No amount/currency arithmetic is used. Caller must certify complete input.
    """
    counts = Counter({category: 0 for category in DRIFT_CATEGORIES})
    by_uid = {u['uid']: u for u in users}
    customers = defaultdict(list)
    for user in users:
        if user.get('stripe_customer_id'):
            customers[user['stripe_customer_id']].append(user['uid'])
    entitled = defaultdict(list)
    for sub in subscriptions:
        metadata = sub.get('metadata') or {}
        if metadata.get('app_id'):
            continue  # Creator-app billing is a separate entitlement domain.
        if sub.get('status') not in ('active', 'trialing'):
            continue
        uid = metadata.get('uid')
        if not uid:
            owners = customers.get(sub.get('customer'), [])
            uid = owners[0] if len(owners) == 1 else None
        if uid not in by_uid:
            counts['unmapped_owner'] += 1
            continue
        entitled[uid].append(sub)
    for uid, user in by_uid.items():
        stored = user.get('subscription') or {}
        all_candidates = entitled.get(uid, [])
        unknown = [s for s in all_candidates if _price_id(s) not in price_plans]
        counts['unknown_price'] += len(unknown)
        candidates = [s for s in all_candidates if _price_id(s) in price_plans]
        if unknown and not candidates:
            continue  # Unknown price cannot prove either access or lack of access.
        if len(all_candidates) > 1:
            counts['multiple_entitled_subscriptions'] += 1
        stored_paid = (
            stored.get('plan', 'basic') not in ('basic', 'free')
            and stored.get('status', 'active') == 'active'
            and bool(stored.get('current_period_end'))
            and stored['current_period_end'] >= as_of
        )
        if not candidates:
            if stored_paid:
                counts['paid_in_firestore_no_stripe_entitlement'] += 1
            continue
        if not stored_paid:
            category = (
                'paid_in_stripe_basic_in_firestore'
                if any(s['status'] == 'active' for s in candidates)
                else 'trial_in_stripe_basic_in_firestore'
            )
            counts[category] += 1
        matching = [s for s in candidates if s['id'] == stored.get('stripe_subscription_id')]
        if matching:
            chosen = matching[0]
        elif len(all_candidates) == 1:
            chosen = candidates[0]
            counts['subscription_id_mismatch'] += 1
        else:
            # No authoritative choice among multiple paid subscriptions.
            continue
        price_id = _price_id(chosen)
        plan = price_plans.get(price_id) if price_id else None
        if stored.get('plan', 'basic') != plan:
            counts['wrong_plan'] += 1
        if not stored.get('current_price_id'):
            # Raw webhooks historically omit this: do not pretend missing is a wrong price.
            counts['missing_price_identity'] += 1
        elif stored['current_price_id'] != price_id:
            counts['wrong_price'] += 1
        if (
            any(stored.get(field) != chosen.get(field) for field in ('current_period_start', 'current_period_end'))
            or not chosen.get('current_period_end')
            or chosen['current_period_end'] < as_of
        ):
            counts['stale_period'] += 1
    return DriftReport(dict(counts), len(users), len(subscriptions))
