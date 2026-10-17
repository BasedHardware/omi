"""Native affiliate program: links an Omi account to its GoAffPro affiliate and
serves that affiliate's data, mirroring the affiliate dashboard's API routes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional
from urllib.parse import urljoin

import firebase_admin.auth
import stripe

from config import affiliate as affiliate_config
from database import affiliates as affiliates_db
from models.affiliate import (
    AffiliateCommission,
    AffiliateEarningsResponse,
    AffiliateOrder,
    AffiliateOrdersResponse,
    AffiliatePayout,
    AffiliatePayoutAccountStatusResponse,
    AffiliatePayoutsResponse,
    AffiliateProfile,
    AffiliateRefCodeAvailabilityResponse,
    AffiliateRefCodeUpdateResponse,
    AffiliateStatsResponse,
    AffiliateStatusResponse,
    AffiliateTransaction,
    LinkMethod,
)
from utils import stripe as stripe_utils
from utils.affiliates import goaffpro
from utils.affiliates.ref_code import validate_ref_code

logger = logging.getLogger(__name__)

# Stripe rejects every Express + recipient variant a US platform can build for
# these countries; Standard Connect is the only path (see the affiliate dashboard).
STANDARD_ONLY_COUNTRIES = frozenset({'BR'})
_TRANSFER_ID = re.compile(r'tr_\w+')


class AffiliateUnavailable(Exception):
    """Native affiliate page is off for this uid, or GoAffPro is not configured."""


class AffiliateNotLinked(Exception):
    pass


class AffiliateBlocked(Exception):
    pass


class AffiliateLinkRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OmiIdentity:
    email: Optional[str]
    email_verified: bool
    name: str


def _identity(uid: str) -> OmiIdentity:
    user = firebase_admin.auth.get_user(uid)
    email = (user.email or '').strip().lower() or None
    name = (user.display_name or '').strip() or (email.split('@')[0] if email else 'Omi user')
    return OmiIdentity(email=email, email_verified=bool(user.email_verified), name=name)


def _require_enabled(uid: str) -> None:
    if not affiliate_config.native_enabled(uid):
        raise AffiliateUnavailable()


def _require_affiliate(uid: str) -> str:
    _require_enabled(uid)
    affiliate_id = affiliates_db.get_linked_affiliate_id(uid)
    if not affiliate_id:
        raise AffiliateNotLinked()
    affiliate = goaffpro.get_affiliate(affiliate_id, fields='id,status')
    if not affiliate:
        raise AffiliateNotLinked()
    if goaffpro.is_blocked(affiliate.get('status')):
        raise AffiliateBlocked()
    return affiliate_id


def _float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None and value != '' else None
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> Optional[str]:
    return str(value) if value is not None and value != '' else None


def referral_url(ref_code: Optional[str]) -> Optional[str]:
    return f'{affiliate_config.referral_site_url()}/?ref={ref_code}' if ref_code else None


def _profile(affiliate: dict[str, Any]) -> AffiliateProfile:
    ref_code = _str(affiliate.get('ref_code'))
    return AffiliateProfile(
        affiliate_id=str(affiliate.get('id')),
        name=_str(affiliate.get('name')),
        email=_str(affiliate.get('email')),
        ref_code=ref_code,
        coupon=_str(affiliate.get('coupon')),
        referral_url=referral_url(ref_code),
    )


def _matchable_affiliate(identity: OmiIdentity) -> Optional[dict[str, Any]]:
    if not identity.email or not identity.email_verified:
        return None
    return goaffpro.find_affiliate_by_email(identity.email)


# ----------------------------------------------------------------------------- status and linking


def status(uid: str) -> AffiliateStatusResponse:
    if not affiliate_config.native_enabled(uid):
        return AffiliateStatusResponse(native_enabled=False, state='unavailable')
    affiliate_id = affiliates_db.get_linked_affiliate_id(uid)
    if affiliate_id:
        affiliate = goaffpro.get_affiliate(affiliate_id)
        if affiliate:
            if goaffpro.is_blocked(affiliate.get('status')):
                return AffiliateStatusResponse(native_enabled=True, state='blocked')
            return AffiliateStatusResponse(native_enabled=True, state='linked', profile=_profile(affiliate))
        logger.warning('affiliate link points at a missing GoAffPro affiliate')
    match = _matchable_affiliate(_identity(uid))
    return AffiliateStatusResponse(
        native_enabled=True,
        state='not_linked',
        email_match_available=bool(match and not goaffpro.is_blocked(match.get('status'))),
    )


def _link(uid: str, affiliate: dict[str, Any], method: LinkMethod) -> None:
    if goaffpro.is_blocked(affiliate.get('status')):
        raise AffiliateBlocked()
    outcome = affiliates_db.link_affiliate(uid, str(affiliate['id']), method)
    if outcome in ('affiliate_taken', 'account_has_other'):
        raise AffiliateLinkRejected(outcome)


def link_by_email(uid: str) -> None:
    _require_enabled(uid)
    match = _matchable_affiliate(_identity(uid))
    if not match:
        raise AffiliateLinkRejected('no_email_match')
    _link(uid, match, 'email_match')


def link_by_credentials(uid: str, email: str, password: str) -> None:
    _require_enabled(uid)
    email = email.strip().lower()
    if not goaffpro.verify_credentials(email, password):
        raise AffiliateLinkRejected('invalid_credentials')
    affiliate = goaffpro.find_affiliate_by_email(email)
    if not affiliate:
        raise AffiliateLinkRejected('invalid_credentials')
    _link(uid, affiliate, 'affiliate_login')


def join(uid: str) -> None:
    _require_enabled(uid)
    if affiliates_db.get_linked_affiliate_id(uid):
        raise AffiliateLinkRejected('account_has_other')
    identity = _identity(uid)
    if not identity.email or not identity.email_verified:
        raise AffiliateLinkRejected('email_not_verified')
    existing = goaffpro.find_affiliate_by_email(identity.email)
    if existing:
        # The email already has an affiliate account; joining would duplicate it.
        _link(uid, existing, 'email_match')
        return
    affiliate_id = goaffpro.create_affiliate(identity.name, identity.email)
    _link(uid, {'id': affiliate_id, 'status': 'approved'}, 'joined')


# ----------------------------------------------------------------------------- dashboard data


def stats(uid: str) -> AffiliateStatsResponse:
    affiliate_id = _require_affiliate(uid)
    body = goaffpro.user_get(
        affiliate_id,
        '/sdk/user/stats/aggregate',
        {'fields': 'total_sales,sale_commission_earned,revenue_generated,commission_paid,other_commission_earned'},
    )
    data = body.get('data')
    raw = data[0] if isinstance(data, list) and data else data
    if not isinstance(raw, dict):
        raw = {}
    total_commission = (_float(raw.get('sale_commission_earned')) or 0.0) + (
        _float(raw.get('other_commission_earned')) or 0.0
    )
    paid = _float(raw.get('commission_paid')) or 0.0
    clicks = 0
    try:
        clicks = int(
            goaffpro.user_get(affiliate_id, '/sdk/user/feed/traffic', {'limit': 1, 'offset': 0}).get('count') or 0
        )
    except goaffpro.GoAffProError:
        pass
    return AffiliateStatsResponse(
        total_sales=_float(raw.get('revenue_generated')) or 0.0,
        total_commission=total_commission,
        total_clicks=clicks,
        total_orders=int(_float(raw.get('total_sales')) or 0),
        paid_commission=paid,
        unpaid_commission=total_commission - paid,
    )


def orders(uid: str, limit: int, offset: int) -> AffiliateOrdersResponse:
    affiliate_id = _require_affiliate(uid)
    body = goaffpro.user_get(affiliate_id, '/sdk/user/feed/orders', {'limit': limit, 'offset': offset})
    items = []
    for order in body.get('orders') or []:
        order_id = _str(order.get('id'))
        if not order_id:
            continue
        number = _str(order.get('number')) or f"#{order.get('order_number') or order_id}"
        items.append(
            AffiliateOrder(
                id=order_id,
                number=number,
                created_at=_str(order.get('created_at')),
                total=_float(order.get('total') or order.get('amount')),
                commission=_float(order.get('commission')),
                currency=_str(order.get('currency')),
                status=_str(order.get('status')),
            )
        )
    return AffiliateOrdersResponse(orders=items, count=body.get('count'))


def _commissions(raw: Any) -> list[AffiliateCommission]:
    data = raw.get('commissions') or raw.get('data') or raw if isinstance(raw, dict) else raw
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return []
    result = []
    standard = data.get('standard')
    if isinstance(standard, dict):
        result.append(
            AffiliateCommission(
                name=None,
                commission_type=_str(standard.get('commission_type')),
                commission_value=_float(standard.get('commission_value')),
                commission_on=_str(standard.get('commission_on')),
                standard=True,
            )
        )
    for special in data.get('special') or []:
        if isinstance(special, dict):
            result.append(
                AffiliateCommission(
                    name=_str(special.get('name')),
                    commission_type=_str(special.get('commission_type')),
                    commission_value=_float(special.get('commission_value')),
                )
            )
    return result


def earnings(uid: str) -> AffiliateEarningsResponse:
    affiliate_id = _require_affiliate(uid)
    commissions = _commissions(goaffpro.user_get(affiliate_id, '/sdk/user/commissions'))
    body = goaffpro.user_get(affiliate_id, '/sdk/user/feed/transactions')
    transactions = []
    for tx in body.get('transactions') or body.get('data') or []:
        if not isinstance(tx, dict) or tx.get('entity_type') == 'payouts' or not _str(tx.get('id')):
            continue
        metadata = tx.get('metadata')
        if not isinstance(metadata, dict):
            metadata = {}
        transactions.append(
            AffiliateTransaction(
                id=str(tx['id']),
                created_at=_str(tx.get('created_at')),
                amount=_float(tx.get('amount')),
                currency=_str(tx.get('currency')),
                entity_type=_str(tx.get('entity_type')),
                event_type=_str(tx.get('event_type')),
                order_number=_str(metadata.get('order_number')),
                status=_str(metadata.get('status')),
            )
        )
    return AffiliateEarningsResponse(commissions=commissions, transactions=transactions)


def _payout_status(transfer_id: Optional[str]) -> str:
    if not transfer_id:
        return 'completed'
    try:
        transfer = stripe.Transfer.retrieve(transfer_id)  # type: ignore[reportUnknownMemberType]  # stripe Transfer.retrieve partially typed
    except stripe.StripeError:
        return 'completed'
    return 'reversed' if transfer.reversed else 'transferred'


def payouts(uid: str, limit: int, offset: int) -> AffiliatePayoutsResponse:
    affiliate_id = _require_affiliate(uid)
    body = goaffpro.user_get(affiliate_id, '/sdk/user/feed/payouts', {'limit': limit, 'offset': offset})
    raw = [p for p in body.get('payouts') or [] if isinstance(p, dict) and _str(p.get('id'))]
    notes: dict[str, str] = {}
    try:
        notes = goaffpro.payment_admin_notes([str(p['id']) for p in raw])
    except goaffpro.GoAffProError:
        pass
    items = []
    for payout in raw:
        match = _TRANSFER_ID.search(notes.get(str(payout['id']), ''))
        items.append(
            AffiliatePayout(
                id=str(payout['id']),
                date=_str(payout.get('payout_date') or payout.get('date')),
                amount=_float(payout.get('amount')),
                currency=_str(payout.get('currency')),
                payment_method=_str(payout.get('payment_method')),
                status=_payout_status(match.group(0) if match else None),  # type: ignore[arg-type]
            )
        )
    return AffiliatePayoutsResponse(payouts=items, count=body.get('count'))


# ----------------------------------------------------------------------------- ref code


def ref_code_availability(uid: str, candidate: str) -> AffiliateRefCodeAvailabilityResponse:
    affiliate_id = _require_affiliate(uid)
    validation = validate_ref_code(candidate)
    if not validation.ok or not validation.normalized:
        return AffiliateRefCodeAvailabilityResponse(available=False, error=validation.error)
    current = _str((goaffpro.get_affiliate(affiliate_id, fields='id,ref_code') or {}).get('ref_code'))
    if current and current.lower() == validation.normalized:
        return AffiliateRefCodeAvailabilityResponse(available=True, current=True)
    taken = goaffpro.ref_code_taken_by_other(validation.normalized, affiliate_id)
    return AffiliateRefCodeAvailabilityResponse(
        available=not taken, error='That code is already taken.' if taken else None
    )


class RefCodeRejected(Exception):
    def __init__(self, message: str, *, conflict: bool = False):
        super().__init__(message)
        self.message = message
        self.conflict = conflict


def update_ref_code(uid: str, candidate: str) -> AffiliateRefCodeUpdateResponse:
    affiliate_id = _require_affiliate(uid)
    validation = validate_ref_code(candidate)
    if not validation.ok or not validation.normalized:
        raise RefCodeRejected(validation.error or 'Invalid code.')
    current = _str((goaffpro.get_affiliate(affiliate_id, fields='id,ref_code') or {}).get('ref_code'))
    if current and current.lower() == validation.normalized:
        return AffiliateRefCodeUpdateResponse(
            ref_code=current, referral_url=referral_url(current) or '', unchanged=True
        )
    if goaffpro.ref_code_taken_by_other(validation.normalized, affiliate_id):
        raise RefCodeRejected('That code is already taken.', conflict=True)
    goaffpro.update_affiliate(affiliate_id, {'ref_code': validation.normalized})
    # GoAffPro canonicalizes the stored case, so re-read it.
    stored = _str((goaffpro.get_affiliate(affiliate_id, fields='id,ref_code') or {}).get('ref_code'))
    ref_code = stored or validation.normalized
    return AffiliateRefCodeUpdateResponse(ref_code=ref_code, referral_url=referral_url(ref_code) or '')


# ----------------------------------------------------------------------------- Stripe Connect payouts


def _stored_stripe_account(affiliate_id: str) -> Optional[str]:
    user = goaffpro.user_get(affiliate_id, '/sdk/user')
    details = (user.get('user') or user).get('payment_details')
    if isinstance(details, dict):
        for value in details.values():
            if isinstance(value, str) and value.startswith('acct_'):
                return value
    return None


def _save_stripe_account(affiliate_id: str, account_id: str) -> None:
    method_key = affiliate_config.goaffpro_stripe_method_key()
    field_key = affiliate_config.goaffpro_stripe_field_key()
    if not method_key or not field_key:
        logger.warning('affiliate stripe account not saved to GoAffPro: payment method keys unset')
        return
    goaffpro.user_post(
        affiliate_id, '/sdk/user', {'payment_method': method_key, 'payment_details': {field_key: account_id}}
    )


def _return_urls() -> tuple[str, str]:
    base = stripe_utils.base_url or ''
    return urljoin(base, '/v1/affiliate/payouts/stripe-refresh'), urljoin(base, '/v1/affiliate/payouts/stripe-return')


def _account_link(
    account_id: str, link_type: Literal['account_onboarding', 'account_update'] = 'account_onboarding'
) -> str:
    refresh_url, return_url = _return_urls()
    link = stripe.AccountLink.create(account=account_id, refresh_url=refresh_url, return_url=return_url, type=link_type)
    return link.url


def _create_connect_account(country: str, affiliate_id: str) -> str:
    if country in STANDARD_ONLY_COUNTRIES:
        account = stripe.Account.create(
            type='standard',
            country=country,
            capabilities={'transfers': {'requested': True}, 'card_payments': {'requested': True}},
            metadata={'affiliate_id': affiliate_id},
        )
    else:
        account = stripe.Account.create(
            controller={
                'stripe_dashboard': {'type': 'express'},
                'fees': {'payer': 'application'},
                'losses': {'payments': 'application'},
            },
            country=country,
            tos_acceptance={'service_agreement': 'recipient'},
            capabilities={'transfers': {'requested': True}},
            metadata={'affiliate_id': affiliate_id},
            settings={'payouts': {'schedule': {'interval': 'daily', 'delay_days': 7}}},
        )
    return account.id


class PayoutSetupRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def payout_setup_link(uid: str, country: Optional[str]) -> str:
    """Stripe-hosted onboarding (or update) link for this affiliate's payout account."""
    affiliate_id = _require_affiliate(uid)
    account_id = _stored_stripe_account(affiliate_id)
    if account_id:
        account = stripe.Account.retrieve(account_id)  # type: ignore[reportUnknownMemberType]  # stripe Account.retrieve partially typed
        if account.details_submitted:
            return _account_link(account_id, 'account_update')
        return _account_link(account_id)
    if not country:
        raise PayoutSetupRejected('country_required')
    account_id = _create_connect_account(country.upper(), affiliate_id)
    # Saved before onboarding finishes, as the dashboard does, so a retry reuses it.
    try:
        _save_stripe_account(affiliate_id, account_id)
    except goaffpro.GoAffProError:
        logger.warning('affiliate stripe account save failed; webhook will retry')
    return _account_link(account_id)


def payout_dashboard_link(uid: str) -> str:
    affiliate_id = _require_affiliate(uid)
    account_id = _stored_stripe_account(affiliate_id)
    if not account_id:
        raise PayoutSetupRejected('no_account')
    account = stripe.Account.retrieve(account_id)  # type: ignore[reportUnknownMemberType]  # stripe Account.retrieve partially typed
    if account.type == 'standard':
        return 'https://dashboard.stripe.com/'
    return stripe.Account.create_login_link(account_id).url  # type: ignore[reportUnknownMemberType]  # stripe partially typed


def payout_account_status(uid: str) -> AffiliatePayoutAccountStatusResponse:
    affiliate_id = _require_affiliate(uid)
    account_id = _stored_stripe_account(affiliate_id)
    if not account_id:
        return AffiliatePayoutAccountStatusResponse(connected=False, has_account=False)
    account = stripe.Account.retrieve(account_id)  # type: ignore[reportUnknownMemberType]  # stripe Account.retrieve partially typed
    requirements = account.requirements
    past_due = list(requirements.past_due or []) if requirements else []
    currently_due = list(requirements.currently_due or []) if requirements else []
    disabled_reason = requirements.disabled_reason if requirements else None
    payouts_enabled = bool(account.payouts_enabled)
    submitted = bool(account.details_submitted)
    complete = bool(account.charges_enabled) and payouts_enabled and submitted
    has_issues = submitted and (not payouts_enabled or bool(past_due) or disabled_reason is not None)
    return AffiliatePayoutAccountStatusResponse(
        connected=complete,
        has_account=True,
        payouts_enabled=payouts_enabled,
        details_submitted=submitted,
        has_issues=has_issues,
        currently_due=currently_due,
    )
