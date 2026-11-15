"""Versioned Pocket-match amounts and explicit Omi implementation policy.

Pocket evidence establishes amounts/milestones only. Omi choices: existing accounts
are eligible, attribution precedes purchase, a refunded order cannot qualify again,
manual claim starts calendar months when commercial paid access is no longer active.
Links and unclaimed rewards have no configured expiry in this policy version.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlencode

from utils.referrals import ReferralCodeError, referral_environment
from utils.referral_grant_clock import requeue_for_paid_period

from config.referral_campaign import (
    CAMPAIGN_ID as CAMPAIGN_ID,
    GRANT_FIELD as GRANT_FIELD,
    campaign_enabled as campaign_enabled,
)

UID_PATTERN = re.compile(r'^[A-Za-z0-9:_-]{1,128}$')


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _secret(secret: bytes | None) -> bytes:
    value = secret if secret is not None else os.getenv('ENCRYPTION_SECRET', '').encode()
    if len(value) < 32:
        raise ReferralCodeError('missing_referral_signing_secret')
    return value


@dataclass(frozen=True)
class CampaignPolicy:
    campaign_id: str = CAMPAIGN_ID
    environment: str = 'prod'
    discount_percent: int = 10
    friend_cap: int = 5
    # These are immutable economics for this version, not rollout settings.
    milestones: tuple[tuple[int, int], ...] = ((2, 2), (5, 5))
    expires_at: int | None = None
    choices: str = 'post_attribution_purchase;refund_terminal;manual_calendar_month_claim;paid_deferred;no_claim_expiry'

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def current_policy() -> CampaignPolicy:
    return CampaignPolicy(environment=referral_environment())


def campaign_code(uid: str, *, policy: CampaignPolicy | None = None, secret: bytes | None = None) -> str:
    if not UID_PATTERN.fullmatch(uid):
        raise ReferralCodeError('invalid_referral_code')
    policy = policy or current_policy()
    payload = _encode(
        json.dumps(
            {'uid': uid, 'campaign': policy.campaign_id, 'env': policy.environment, 'policy': policy.digest},
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
    )
    signed = f'ref2.{payload}'
    return f'{signed}.{_encode(hmac.new(_secret(secret), signed.encode(), hashlib.sha256).digest())}'


def decode_campaign_code(
    code: str, *, policy: CampaignPolicy | None = None, secret: bytes | None = None, now: datetime | None = None
) -> str:
    policy = policy or current_policy()
    try:
        prefix, payload, signature = code.split('.')
        expected = _encode(hmac.new(_secret(secret), f'{prefix}.{payload}'.encode(), hashlib.sha256).digest())
        data = json.loads(_decode(payload))
        if (
            prefix != 'ref2'
            or not hmac.compare_digest(expected, signature)
            or data
            != {
                'uid': data.get('uid'),
                'campaign': policy.campaign_id,
                'env': policy.environment,
                'policy': policy.digest,
            }
            or not UID_PATTERN.fullmatch(data['uid'])
        ):
            raise ValueError('invalid code')
        if policy.expires_at is not None and (now or datetime.now(timezone.utc)).timestamp() >= policy.expires_at:
            raise ValueError('expired code')
        return data['uid']
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ReferralCodeError('invalid_referral_code') from error


def campaign_link(uid: str, *, policy: CampaignPolicy | None = None) -> str:
    base = (os.getenv('REFERRAL_PUBLIC_BASE_URL') or 'https://omi.me').rstrip('/')
    return f'{base}/r/{campaign_code(uid, policy=policy)}'


def hardware_landing_url(code: str, policy: CampaignPolicy) -> str:
    return 'https://app.omi.me/referral/hardware?' + urlencode({'code': code, 'environment': policy.environment})


def unlocked_months(qualified: int, policy: CampaignPolicy) -> int:
    return max((months for count, months in policy.milestones if qualified >= count), default=0)


def milestone_progress(state: Mapping[str, Any]) -> int:
    """Retain consumed milestone credit without calling refunded orders purchases."""
    return len(set(state.get('claimed_slots', {})) | set(state.get('qualified_orders', {})))


def add_calendar_months(start: datetime, months: int) -> datetime:
    absolute_month = start.year * 12 + start.month - 1 + months
    year, month = divmod(absolute_month, 12)
    return start.replace(year=year, month=month + 1, day=min(start.day, calendar.monthrange(year, month + 1)[1]))


def commercial_access_active(subscription: Any, now: datetime) -> bool:
    # Malformed commercial rows must never be overwritten or treated as Free.
    if not isinstance(subscription, Mapping):
        raise ValueError('invalid subscription')
    plan = subscription.get('plan', 'basic')
    if plan in ('basic', 'free'):
        return False
    end = subscription.get('current_period_end')
    return not isinstance(end, (int, float)) or end >= now.timestamp()


def effective_subscription_payload(
    subscription: Mapping[str, Any], grant: Mapping[str, Any] | None, *, now: datetime | None = None
) -> dict[str, Any]:
    """Compose access only; commercial subscription metadata stays stored untouched."""
    now = now or datetime.now(timezone.utc)
    original = dict(subscription)
    if not grant or commercial_access_active(subscription, now):
        return original
    if (
        grant.get('campaign_id') != CAMPAIGN_ID
        or grant.get('status') != 'active'
        or type(grant.get('starts_at')) is not int
        or type(grant.get('ends_at')) is not int
        or not grant['starts_at'] <= now.timestamp() < grant['ends_at']
    ):
        return original
    if any(interval['start'] <= now.timestamp() < interval['end'] for interval in grant.get('paid_coverage', [])):
        return original
    return {
        'plan': 'unlimited_v2',
        'status': 'active',
        'current_period_start': grant['starts_at'],
        'current_period_end': grant['ends_at'],
        'cancel_at_period_end': True,
    }


def requeue_grant_for_paid_period(
    grant: Mapping[str, Any] | None, subscription: Mapping[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    """Account paid coverage as intervals while preserving the promo obligation."""
    if not grant or grant.get('campaign_id') != CAMPAIGN_ID or grant.get('status') != 'active':
        return dict(grant) if grant else None
    if subscription.get('plan', 'basic') in ('basic', 'free'):
        return dict(grant)
    return requeue_for_paid_period(grant, subscription, now=now)


def campaign_snapshot(
    state: Mapping[str, Any] | None,
    *,
    enabled: bool,
    referral_url: str | None = None,
    reason: str | None = None,
    now: datetime | None = None,
    policy: CampaignPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or current_policy()
    state = state or {}
    qualified = len(state.get('qualified_orders', {}))
    claimed = state.get('claimed_months', 0)
    progress = milestone_progress(state)
    if not qualified <= progress <= 5 or claimed not in (0, 2, 5):
        raise ValueError('corrupt referral ledger')
    earned = max(claimed, unlocked_months(progress, policy))
    claimable = earned - claimed
    grant = state.get('grant') or {}
    epoch = (now or datetime.now(timezone.utc)).timestamp()
    pending = grant.get('starts_at', 0) > epoch or any(
        interval['start'] <= epoch < interval['end'] for interval in grant.get('paid_coverage', [])
    )
    active = not pending and grant.get('starts_at', 0) <= epoch < grant.get('ends_at', 0)
    return {
        'campaign_id': policy.campaign_id,
        'enabled': enabled,
        'referral_url': referral_url if enabled else None,
        'qualified_purchases': qualified,
        'milestone_progress': progress,
        'earned_months': earned,
        'claimed_months': claimed,
        'claimable_months': claimable if enabled else 0,
        'reward_status': (
            'disabled'
            if not enabled
            else ('pending_paid_subscription' if pending else ('active' if active else 'ready'))
        ),
        'reason': reason,
    }
