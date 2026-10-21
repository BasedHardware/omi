from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

from models.users import PlanType

REFERRAL_COOKIE_NAME = 'omi_desktop_referral'
REFERRAL_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
REFERRAL_TRIAL_DAYS = 30
REFERRAL_SIGNUP_URL = 'https://app.omi.me/login'
REFERRAL_NEW_USER_WINDOW_SECONDS = 15 * 60
REFERRAL_PROGRAM = 'desktop_operator_month_v1'

_CODE_PREFIX = 'ref1'
_UID_PATTERN = re.compile(r'^[A-Za-z0-9:_-]{1,128}$')
_PAID_PLAN_VALUES = {
    PlanType.unlimited.value,
    PlanType.architect.value,
    PlanType.operator.value,
    PlanType.plus.value,
    PlanType.unlimited_v2.value,
    'pro',
}


class ReferralCodeError(ValueError):
    pass


def _secret(secret: Optional[bytes] = None) -> bytes:
    if secret is not None:
        return secret
    value = os.getenv('ENCRYPTION_SECRET', '')
    if len(value) < 32:
        raise ReferralCodeError('missing_referral_signing_secret')
    return value.encode('utf-8')


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + ('=' * (-len(value) % 4)))
    except (ValueError, TypeError) as error:
        raise ReferralCodeError('malformed_referral_code') from error


def create_referral_code(uid: str, *, secret: Optional[bytes] = None) -> str:
    if not _UID_PATTERN.fullmatch(uid):
        raise ReferralCodeError('invalid_referrer_uid')
    payload = _encode(uid.encode('utf-8'))
    signed_value = f'{_CODE_PREFIX}.{payload}'
    signature = _encode(
        hmac.new(_secret(secret), f'omi-desktop-referral:{signed_value}'.encode('ascii'), hashlib.sha256).digest()
    )
    return f'{signed_value}.{signature}'


def referrer_uid_from_code(code: str, *, secret: Optional[bytes] = None) -> str:
    parts = code.split('.') if code else []
    if len(parts) != 3 or parts[0] != _CODE_PREFIX:
        raise ReferralCodeError('malformed_referral_code')
    signed_value = f'{parts[0]}.{parts[1]}'
    expected_signature = _encode(
        hmac.new(_secret(secret), f'omi-desktop-referral:{signed_value}'.encode('ascii'), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_signature, parts[2]):
        raise ReferralCodeError('invalid_referral_signature')
    try:
        uid = _decode(parts[1]).decode('utf-8')
    except UnicodeDecodeError as error:
        raise ReferralCodeError('malformed_referrer_uid') from error
    if not _UID_PATTERN.fullmatch(uid):
        raise ReferralCodeError('invalid_referrer_uid')
    return uid


def referral_link(uid: str, *, secret: Optional[bytes] = None, public_base_url: Optional[str] = None) -> str:
    base_url = (public_base_url or os.getenv('REFERRAL_PUBLIC_BASE_URL') or 'https://omi.me').rstrip('/')
    return f'{base_url}/r/{create_referral_code(uid, secret=secret)}'


def referral_environment(public_base_url: Optional[str] = None) -> str:
    base_url = public_base_url or os.getenv('REFERRAL_PUBLIC_BASE_URL') or 'https://omi.me'
    return 'dev' if urlparse(base_url).hostname == 'api.omiapi.com' else 'prod'


def referral_signup_url(code: str, *, public_base_url: Optional[str] = None) -> str:
    query = urlencode({'referral': code, 'environment': referral_environment(public_base_url)})
    return f'{REFERRAL_SIGNUP_URL}?{query}'


def is_new_referral_account(
    creation_timestamp_ms: Optional[int],
    *,
    now: Optional[datetime] = None,
) -> bool:
    if creation_timestamp_ms is None:
        return False
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    age_seconds = current_time.timestamp() - (creation_timestamp_ms / 1000)
    return 0 <= age_seconds <= REFERRAL_NEW_USER_WINDOW_SECONDS


def referral_claim_patch(
    *,
    referred_uid: str,
    referrer_uid: str,
    is_new_user: bool,
    user_data: Optional[dict[str, Any]],
    now: Optional[datetime] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Return the referral entitlement patch and its privacy-safe outcome reason."""
    if not is_new_user:
        return None, 'existing_account'
    if referred_uid == referrer_uid:
        return None, 'self_refer'

    existing = user_data or {}
    if existing.get('referral'):
        return None, 'already_claimed'

    subscription = existing.get('subscription')
    if isinstance(subscription, dict) and subscription.get('plan') in _PAID_PLAN_VALUES:
        return None, 'paid'

    started_at = now or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    started_epoch = int(started_at.timestamp())
    ends_epoch = int((started_at + timedelta(days=REFERRAL_TRIAL_DAYS)).timestamp())
    return {
        'subscription': {
            'plan': PlanType.operator.value,
            'status': 'active',
            'current_period_start': started_epoch,
            'current_period_end': ends_epoch,
            'cancel_at_period_end': True,
        },
        'referral': {
            'program': REFERRAL_PROGRAM,
            'referrer_uid': referrer_uid,
            'claimed_at': started_epoch,
            'trial_ends_at': ends_epoch,
        },
    }, 'granted'
