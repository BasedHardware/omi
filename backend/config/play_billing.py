"""Google Play Billing switch for new Android subscription purchases. Pure module: stdlib only.

``ANDROID_BILLING`` selects how a NEW Android purchase is started: ``stripe`` (default, today's
flow) or ``play``. ``play`` reaches a client only when it is an Android build at or above
``ANDROID_PLAY_BILLING_MIN_BUILD`` (the Play version code that first ships the Play code); unset
means no build qualifies. Env is read at call time so a config change needs no code change.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

ANDROID_BILLING_ENV = 'ANDROID_BILLING'
MIN_BUILD_ENV = 'ANDROID_PLAY_BILLING_MIN_BUILD'

DEFAULT_PACKAGE_NAME = 'com.friend.ios'
DEFAULT_PRODUCT_ID = 'omi_pro'
DEFAULT_MONTHLY_BASE_PLAN = 'monthly'
DEFAULT_YEARLY_BASE_PLAN = 'yearly'
DEFAULT_TRIAL_OFFER = 'free-trial-7d'


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


def client_uses_play(
    platform: Optional[str], app_build: Optional[str], environ: Optional[Mapping[str, str]] = None
) -> bool:
    """True when this client must start new purchases through Google Play Billing."""
    if android_billing_mode(environ) != 'play':
        return False
    if not isinstance(platform, str) or platform.strip().lower() != 'android':
        return False
    minimum = min_play_build(environ)
    build = app_build.strip() if isinstance(app_build, str) else ''
    return minimum is not None and build.isdigit() and int(build) >= minimum


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
