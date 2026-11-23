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


def min_play_build(environ: Optional[Mapping[str, str]] = None) -> Optional[int]:
    raw = (_env(environ).get(MIN_BUILD_ENV) or '').strip()
    if not raw.isdigit() or int(raw) <= 0:
        return None
    return int(raw)


def user_in_play_cohort(uid: Optional[str], environ: Optional[Mapping[str, str]] = None) -> bool:
    if not isinstance(uid, str) or not rollout_cohorts.valid_uid(uid):
        return False
    if rollout_cohorts.cohort_admits(uid, _env(environ).get(COHORT_ENV)):
        return True
    try:
        return rollout_cohorts.in_rollout_cohort(uid, ROLLOUT_COHORT)
    except Exception:
        # Unknown membership keeps today's Stripe flow.
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
    minimum = min_play_build(environ)
    build = app_build.strip() if isinstance(app_build, str) else ''
    if minimum is None or not build.isdigit() or int(build) < minimum:
        return False
    return android_billing_mode(environ) == 'play' or user_in_play_cohort(uid, environ)


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


def obfuscated_account_id(uid: str) -> str:
    """Stable 64-char id the app passes to Play; Google echoes it on the purchase."""
    return hashlib.sha256(f'omi-play-account:{uid}'.encode('utf-8')).hexdigest()


def client_config_payload(uid: str, environ: Optional[Mapping[str, str]] = None) -> dict:
    """The ``play_billing`` block of the subscription response."""
    return {
        'product_id': product_id(environ),
        'base_plans': [{'id': plan_id, 'interval': interval} for plan_id, interval in base_plans(environ).items()],
        'trial_offer_id': trial_offer_id(environ),
        'obfuscated_account_id': obfuscated_account_id(uid),
    }
