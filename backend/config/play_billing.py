"""Google Play Billing switch for new Android subscription purchases. Pure module: stdlib only.

``ANDROID_BILLING`` selects how a NEW Android purchase is started: ``stripe`` (default, today's
flow) or ``play`` (everyone). With ``stripe``, a user still buys through Play when admitted by
``ANDROID_PLAY_BILLING_COHORT`` (``uid:<uid>,pct:<n>`` or ``all``) or the ``android-play-billing``
rollout cohort document. Either way only an Android build at or above
``ANDROID_PLAY_BILLING_MIN_BUILD`` (the first Play version code with the Play code) qualifies;
unset means none does. Env is read at call time.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Mapping, Optional

from config import rollout_cohorts

ANDROID_BILLING_ENV = 'ANDROID_BILLING'
MIN_BUILD_ENV = 'ANDROID_PLAY_BILLING_MIN_BUILD'
COHORT_ENV = 'ANDROID_PLAY_BILLING_COHORT'
ROLLOUT_COHORT = 'android-play-billing'

DEFAULT_PACKAGE_NAME = 'com.friend.ios'
DEFAULT_PRODUCT_ID = 'omi_pro'
DEFAULT_MONTHLY_BASE_PLAN = 'monthly'
DEFAULT_YEARLY_BASE_PLAN = 'yearly'
DEFAULT_TRIAL_OFFER = 'trial-7d'
# Retired Play products, closed to new subscribers: never offered, never granted.
LEGACY_PRODUCT_IDS = frozenset({'com.omi.app.lite', 'com.omi.app.plus', 'com.omi.app.unlimited_v2'})


def _env(environ: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def _value(name: str, default: str, environ: Optional[Mapping[str, str]]) -> str:
    return (_env(environ).get(name) or '').strip() or default


def android_billing_mode(environ: Optional[Mapping[str, str]] = None) -> str:
    """``play`` only when explicitly set; any other value keeps Stripe."""
    return 'play' if (_env(environ).get(ANDROID_BILLING_ENV) or '').strip().lower() == 'play' else 'stripe'


# Android version codes fit in 9 digits; longer input is malformed (and int() refuses over 4300 digits).
_MAX_BUILD_DIGITS = 9


def _build_number(value: Optional[str]) -> Optional[int]:
    """ASCII digits only: ``str.isdigit()`` also accepts digits ``int()`` cannot parse (e.g. superscripts)."""
    raw = value.strip() if isinstance(value, str) else ''
    if not raw or len(raw) > _MAX_BUILD_DIGITS or not raw.isascii() or not raw.isdigit():
        return None
    return int(raw)


def min_play_build(environ: Optional[Mapping[str, str]] = None) -> Optional[int]:
    minimum = _build_number(_env(environ).get(MIN_BUILD_ENV))
    return minimum if minimum else None


def user_in_play_cohort(uid: Optional[str], environ: Optional[Mapping[str, str]] = None) -> bool:
    try:
        if not isinstance(uid, str) or not rollout_cohorts.valid_uid(uid):
            return False
        if rollout_cohorts.cohort_admits(uid, _env(environ).get(COHORT_ENV)):
            return True
        return bool(rollout_cohorts.in_rollout_cohort(uid, ROLLOUT_COHORT))
    except Exception:
        # Unknown membership keeps today's Stripe flow; it can never fail the request.
        return False


def client_uses_play(
    platform: Optional[str],
    app_build: Optional[str],
    uid: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """True when this client must start new purchases through Google Play Billing."""
    if not isinstance(platform, str) or platform.strip().lower() != 'android':
        return False
    if account_id_key(environ) is None:
        return False  # without the account-id secret no purchase could be bound safely
    minimum = min_play_build(environ)
    build = _build_number(app_build)
    if minimum is None or build is None or build < minimum:
        return False
    return android_billing_mode(environ) == 'play' or user_in_play_cohort(uid, environ)


# Refusal for a new Stripe charge from a client that must buy through Google Play.
USE_GOOGLE_PLAY = 'use_google_play'
USE_GOOGLE_PLAY_MESSAGE = 'Subscribe with Google Play in the app.'


def package_name(environ: Optional[Mapping[str, str]] = None) -> str:
    return _value('PLAY_PACKAGE_NAME', DEFAULT_PACKAGE_NAME, environ)


def product_id(environ: Optional[Mapping[str, str]] = None) -> str:
    return _value('PLAY_SUBSCRIPTION_PRODUCT_ID', DEFAULT_PRODUCT_ID, environ)


def base_plans(environ: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Base plan id -> billing interval."""
    return {
        _value('PLAY_MONTHLY_BASE_PLAN_ID', DEFAULT_MONTHLY_BASE_PLAN, environ): 'month',
        _value('PLAY_YEARLY_BASE_PLAN_ID', DEFAULT_YEARLY_BASE_PLAN, environ): 'year',
    }


def trial_offer_id(environ: Optional[Mapping[str, str]] = None) -> str:
    return _value('PLAY_TRIAL_OFFER_ID', DEFAULT_TRIAL_OFFER, environ)


def rtdn_audience(environ: Optional[Mapping[str, str]] = None) -> str:
    return (_env(environ).get('PLAY_RTDN_OIDC_AUDIENCE') or '').strip()


def rtdn_invoker_sa(environ: Optional[Mapping[str, str]] = None) -> str:
    return (_env(environ).get('PLAY_RTDN_PUSH_SA') or '').strip()


def reconcile_audience(environ: Optional[Mapping[str, str]] = None) -> str:
    return (_env(environ).get('PLAY_RECONCILE_OIDC_AUDIENCE') or '').strip()


def reconcile_invoker_sa(environ: Optional[Mapping[str, str]] = None) -> str:
    return (_env(environ).get('PLAY_RECONCILE_INVOKER_SA') or '').strip()


ACCOUNT_ID_KEY_ENV = 'PLAY_ACCOUNT_ID_HMAC_KEY'


class AccountIdKeyMissing(RuntimeError):
    """The server secret for Play account ids is not configured; Play Billing stays off."""


def account_id_key(environ: Optional[Mapping[str, str]] = None) -> Optional[bytes]:
    raw = (_env(environ).get(ACCOUNT_ID_KEY_ENV) or '').strip()
    return raw.encode('utf-8') if len(raw) >= 32 else None


def obfuscated_account_id(uid: str, environ: Optional[Mapping[str, str]] = None) -> str:
    """64-hex id the app passes to Play; Google echoes it on the purchase.

    HMAC-SHA256 of the uid under a server secret (Secret Manager), so nobody can compute another
    user's id from their uid.
    """
    key = account_id_key(environ)
    if key is None:
        raise AccountIdKeyMissing(ACCOUNT_ID_KEY_ENV)
    return hmac.new(key, f'omi-play-account:{uid}'.encode('utf-8'), hashlib.sha256).hexdigest()


def client_config_payload(uid: str, environ: Optional[Mapping[str, str]] = None) -> dict:
    """The ``play_billing`` block of the subscription response."""
    return {
        'product_id': product_id(environ),
        'base_plans': [{'id': plan_id, 'interval': interval} for plan_id, interval in base_plans(environ).items()],
        'trial_offer_id': trial_offer_id(environ),
        'obfuscated_account_id': obfuscated_account_id(uid),
    }


def manage_subscription_url(environ: Optional[Mapping[str, str]] = None) -> str:
    """Google Play's subscription center for Omi Pro."""
    return (
        'https://play.google.com/store/account/subscriptions'
        f'?sku={product_id(environ)}&package={package_name(environ)}'
    )
