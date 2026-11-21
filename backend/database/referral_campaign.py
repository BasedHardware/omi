"""Customer-plane referral authority. Every transition is a Firestore transaction.

No checkout redirect, share, client purchase assertion, or analytics event reaches
qualification. Only the verified Shopify adapter calls settle_order.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_customer_firestore_client, get_data_plane_firestore_client, run_transactional
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.fsr_read_cache import writing
from utils.referral_campaign import (
    CampaignPolicy,
    GRANT_FIELD,
    add_calendar_months,
    campaign_enabled,
    commercial_access_active,
    current_policy,
    milestone_progress,
    requeue_grant_for_paid_period,
    unlocked_months,
)
from utils.referral_billing import BillingAuthorityUnavailable, billing_allows_claim, billing_identity
from utils.referral_grant_clock import extend_grant_clock


class CampaignError(ValueError):
    pass


def key(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def _ref(client: Any, collection: str, policy: CampaignPolicy, *parts: str) -> Any:
    return client.collection('referral_' + collection).document(key(policy.campaign_id, policy.environment, *parts))


def _client(injected: Any | None = None) -> Any:
    if injected is not None:
        return injected
    customer = get_customer_firestore_client()
    deletion = get_data_plane_firestore_client()
    # Deletion admission and award must share the same transaction authority.
    # A split customer/data deployment needs a reviewed bridge before activation.
    if (customer.project, customer._database) != (deletion.project, deletion._database):
        raise CampaignError('deletion_authority_configuration_required')
    return customer


def _data(ref, transaction=None):
    return ref.get(transaction=transaction).to_dict() or {}


def _require_enabled(policy, now):
    if not campaign_enabled():
        raise CampaignError('campaign_disabled')
    if policy.expires_at is not None and now.timestamp() >= policy.expires_at:
        raise CampaignError('campaign_expired')


def _read_policy(client, transaction, policy):
    ref = _ref(client, 'campaigns', policy)
    prior = _data(ref, transaction)
    if prior and prior.get('policy_digest') != policy.digest:
        raise CampaignError('policy_version_conflict')
    return ref, bool(prior)


def _write_policy(transaction, pinned, policy):
    ref, exists = pinned
    if not exists:
        transaction.set(
            ref,
            {
                'campaign_id': policy.campaign_id,
                'environment': policy.environment,
                'policy_digest': policy.digest,
                'omi_choices': policy.choices,
            },
        )


def _user(client, transaction, uid):
    user_ref = client.collection('users').document(uid)
    user = _data(user_ref, transaction)
    marker = client.collection('account_deletions').document(uid).get(transaction=transaction)
    if not user or account_deletion_marker_blocks_access(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    ):
        raise CampaignError('account_unavailable')
    return user_ref, user


def read_campaign(uid: str, *, client=None, policy=None, preview: bool = False) -> dict:
    # Disabled requests never instantiate a Firestore client or provision a user; team preview only reads.
    if not campaign_enabled() and not preview:
        return {}
    client = _client(client)
    policy = policy or current_policy()
    return _data(_ref(client, 'accounts', policy, uid))


def attribute(uid: str, referrer_uid: str, *, client=None, policy=None, now=None) -> dict:
    policy = policy or current_policy()
    now = now or datetime.now(timezone.utc)
    _require_enabled(policy, now)
    if uid == referrer_uid:
        raise CampaignError('self_referral')
    client = _client(client)
    ref = _ref(client, 'attributions', policy, uid)

    @firestore.transactional
    def apply(transaction):
        pinned = _read_policy(client, transaction, policy)
        existing = _data(ref, transaction)
        _user(client, transaction, uid)
        _user(client, transaction, referrer_uid)
        if existing:
            if existing['referrer_uid'] != referrer_uid:
                raise CampaignError('attribution_conflict')
            return existing
        result = {
            'id': ref.id,
            'campaign_id': policy.campaign_id,
            'policy_digest': policy.digest,
            'uid': uid,
            'referrer_uid': referrer_uid,
            'attributed_at': int(now.timestamp()),
            'state': 'attributed',
        }
        _write_policy(transaction, pinned, policy)
        transaction.set(ref, result)
        return result

    return run_transactional(client, apply, transient=True)


def bind_checkout(uid: str, receipt: dict, *, client=None, policy=None, now=None) -> dict:
    """Persist a receipt from the trusted checkout provider, never from a request body."""
    policy = policy or current_policy()
    now = now or datetime.now(timezone.utc)
    _require_enabled(policy, now)
    client = _client(client)
    binding_ref = _ref(client, 'checkouts', policy, receipt['shop'], receipt['checkout_token'])
    buyer_ref = _ref(client, 'buyer_identities', policy, receipt['shop'], receipt['customer_id'])

    @firestore.transactional
    def apply(transaction):
        attribution = _data(_ref(client, 'attributions', policy, uid), transaction)
        binding = _data(binding_ref, transaction)
        buyer = _data(buyer_ref, transaction)
        _user(client, transaction, uid)
        if not attribution or receipt['attribution_id'] != attribution['id']:
            raise CampaignError('invalid_checkout_receipt')
        if binding and (binding['uid'] != uid or binding['receipt'] != receipt):
            raise CampaignError('checkout_binding_conflict')
        if buyer and buyer['uid'] != uid:
            raise CampaignError('buyer_already_bound')
        if binding:
            return binding
        result = {
            'uid': uid,
            'receipt': receipt,
            'referrer_uid': attribution['referrer_uid'],
            'attributed_at': attribution['attributed_at'],
            'created_at': int(now.timestamp()),
        }
        transaction.set(binding_ref, result)
        transaction.set(buyer_ref, {'uid': uid})
        return result

    return run_transactional(client, apply, transient=True)


def settle_order(evidence: dict, *, client=None, policy=None, now=None) -> dict:
    """Atomic business dedupe, refund tombstone, distinct buyer and five-slot cap.

    Evidence is produced only after raw-body Shopify HMAC and merchant checks.
    Refunds release unclaimed slots; already claimed access is not clawed back
    (an Omi choice). Claimed months are lifetime capped even after reversals.
    """
    policy = policy or current_policy()
    now = now or datetime.now(timezone.utc)
    _require_enabled(policy, now)
    client = _client(client)
    order_ref = _ref(client, 'orders', policy, evidence['shop'], evidence['order_id'])

    @firestore.transactional
    def apply(transaction):
        pinned = _read_policy(client, transaction, policy)
        order = _data(order_ref, transaction)
        # A refund tombstone is authoritative even if payment arrives later.
        if order.get('state') == 'reversed' or (order and evidence['kind'] == 'paid'):
            return order
        if evidence['kind'] == 'refund':
            state_ref = _ref(client, 'accounts', policy, order['referrer_uid']) if order.get('referrer_uid') else None
            state = _data(state_ref, transaction) if state_ref else {}
            result = {
                **order,
                'state': 'reversed',
                'order_id': evidence['order_id'],
                'refund_received_at': int(now.timestamp()),
            }
            if order.get('state') == 'qualified':
                entries = dict(state.get('qualified_orders', {}))
                entries.pop(order['buyer_key'], None)
                state = {**state, 'qualified_orders': entries}
            _write_policy(transaction, pinned, policy)
            transaction.set(order_ref, result)
            if state_ref and state:
                transaction.set(state_ref, state)
            return result

        binding = _data(_ref(client, 'checkouts', policy, evidence['shop'], evidence['checkout_token']), transaction)
        if not binding:
            raise CampaignError('unbound_checkout')
        receipt = binding['receipt']
        uid, referrer = binding['uid'], binding['referrer_uid']
        if (
            evidence['customer_id'] != receipt['customer_id']
            or evidence['variant_id'] != receipt['variant_id']
            or evidence['discount_code'] != receipt['discount_code']
            or evidence['paid_at'] < binding['created_at']
            or evidence['ordered_at'] < binding['attributed_at']
            or evidence['paid_at'] > now.timestamp()
            or evidence['ordered_at'] > evidence['paid_at']
            or uid == referrer
        ):
            raise CampaignError('unqualified_order')
        _user(client, transaction, uid)
        _, owner = _user(client, transaction, referrer)
        if owner.get('shopify_customer_id') == evidence['customer_id']:
            raise CampaignError('self_referral')
        state_ref = _ref(client, 'accounts', policy, referrer)
        state = _data(state_ref, transaction)
        recipient_ref = _ref(client, 'purchases', policy, 'uid', uid)
        buyer_ref = _ref(client, 'purchases', policy, 'customer', evidence['shop'], evidence['customer_id'])
        recipient = _data(recipient_ref, transaction)
        buyer = _data(buyer_ref, transaction)
        entries = dict(state.get('qualified_orders', {}))
        slots = dict(state.get('claimed_slots', {}))
        buyer_key = buyer_ref.id
        if recipient or buyer:
            outcome = 'duplicate_buyer'
        elif len(set(entries) | set(slots)) >= policy.friend_cap:
            outcome = 'cap_reached'
        else:
            outcome = 'qualified'
            entries[buyer_key] = order_ref.id
        result = {
            'state': outcome,
            'order_id': evidence['order_id'],
            'referrer_uid': referrer,
            'uid': uid,
            'buyer_key': buyer_key,
            'policy_digest': policy.digest,
            'received_at': int(now.timestamp()),
            'evidence_digest': evidence['digest'],
        }
        _write_policy(transaction, pinned, policy)
        transaction.set(order_ref, result)
        if outcome == 'qualified':
            transaction.set(
                state_ref, {**state, 'qualified_orders': entries, 'claimed_months': state.get('claimed_months', 0)}
            )
            transaction.set(recipient_ref, {'order_key': order_ref.id})
            transaction.set(buyer_ref, {'order_key': order_ref.id})
        return result

    return run_transactional(client, apply, transient=True)


def claim_months(uid: str, *, client=None, policy=None, now=None) -> tuple[dict, str | None]:
    policy = policy or current_policy()
    now = now or datetime.now(timezone.utc)
    _require_enabled(policy, now)
    client = _client(client)
    state_ref = _ref(client, 'accounts', policy, uid)
    observed_user = _data(client.collection('users').document(uid))
    observed_billing = billing_identity(observed_user)
    try:
        billing_clear = billing_allows_claim(uid, observed_user, now)
    except BillingAuthorityUnavailable as error:
        raise CampaignError('billing_authority_unavailable') from error

    @firestore.transactional
    def apply(transaction):
        pinned = _read_policy(client, transaction, policy)
        state = _data(state_ref, transaction)
        user_ref, user = _user(client, transaction, uid)
        if billing_identity(user) != observed_billing:
            raise CampaignError('billing_state_changed')
        months = unlocked_months(milestone_progress(state), policy)
        claimed = state.get('claimed_months', 0)
        if claimed not in (0, 2, 5):
            raise CampaignError('corrupt_referral_ledger')
        if months <= claimed:
            return state, None
        if not billing_clear or commercial_access_active(user.get('subscription', {}), now):
            return state, 'pending_paid_subscription'
        award_ref = _ref(client, 'awards', policy, uid, str(months))
        award = _data(award_ref, transaction)
        if award:
            raise CampaignError('corrupt_referral_ledger')
        prior = state.get('grant') or {}
        start = datetime.fromtimestamp(max(now.timestamp(), prior.get('ends_at', 0)), timezone.utc)
        grant = {
            **prior,
            'campaign_id': policy.campaign_id,
            'status': 'active',
            'starts_at': (
                prior.get('starts_at', int(now.timestamp()))
                if prior.get('ends_at', 0) > now.timestamp()
                else int(now.timestamp())
            ),
            'ends_at': int(add_calendar_months(start, months - claimed).timestamp()),
        }
        grant = extend_grant_clock(prior, grant, extension_start=int(start.timestamp()))
        consumed = dict(state.get('claimed_slots', {}))
        needed = next(count for count, reward in policy.milestones if reward == months) - len(consumed)
        available = [
            (buyer, order)
            for buyer, order in sorted(state.get('qualified_orders', {}).items())
            if buyer not in consumed
        ]
        if needed < 0 or len(available) < needed:
            raise CampaignError('corrupt_referral_ledger')
        consumed.update(available[:needed])
        result = {
            **state,
            'claimed_months': months,
            'grant': grant,
            'claimed_slots': consumed,
        }
        _write_policy(transaction, pinned, policy)
        transaction.set(
            award_ref,
            {
                'uid': uid,
                'months': months - claimed,
                'grant': grant,
                'policy_digest': policy.digest,
                'state': 'fulfilled',
            },
        )
        transaction.set(state_ref, result)
        transaction.update(user_ref, {GRANT_FIELD: grant})
        return result, None

    with writing('subscription_cache', uid):
        return run_transactional(client, apply, transient=True)


def write_commercial_subscription(uid: str, subscription: dict, *, client=None, policy=None, now=None):
    """Serialize billing installation with claims and preserve paid-overlap promo time."""
    client = _client(client)
    policy = policy or current_policy()
    now = now or datetime.now(timezone.utc)
    user_ref = client.collection('users').document(uid)
    state_ref = _ref(client, 'accounts', policy, uid)

    @firestore.transactional
    def apply(transaction):
        user = _data(user_ref, transaction)
        state = _data(state_ref, transaction)
        grant = user.get(GRANT_FIELD)
        requeued = requeue_grant_for_paid_period(grant, subscription, now=now)
        patch = {'subscription': subscription}
        if requeued is not None and requeued != grant:
            patch[GRANT_FIELD] = requeued
        transaction.update(user_ref, patch)
        if requeued is not None and requeued != grant:
            transaction.set(state_ref, {**state, 'grant': requeued})
        return requeued

    with writing('subscription_cache', uid):
        return run_transactional(client, apply, transient=True)
