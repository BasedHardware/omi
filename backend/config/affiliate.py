"""Native affiliate program: rollout gate and GoAffPro bindings.

The affiliate program itself lives in GoAffPro. The backend holds the GoAffPro
admin and public tokens so clients never see a GoAffPro credential.
"""

import hashlib
import os

REFERRAL_SITE_URL_DEFAULT = 'https://www.omi.me'


def goaffpro_access_token() -> str:
    return os.getenv('GOAFFPRO_ACCESS_TOKEN', '').strip()


def goaffpro_public_token() -> str:
    return os.getenv('GOAFFPRO_PUBLIC_TOKEN', '').strip()


def goaffpro_stripe_method_key() -> str:
    return os.getenv('GOAFFPRO_STRIPE_METHOD_KEY', '').strip()


def goaffpro_stripe_field_key() -> str:
    return os.getenv('GOAFFPRO_STRIPE_FIELD_KEY', '').strip()


def goaffpro_configured() -> bool:
    return bool(goaffpro_access_token() and goaffpro_public_token())


def referral_site_url() -> str:
    return os.getenv('AFFILIATE_REFERRAL_SITE_URL', REFERRAL_SITE_URL_DEFAULT).strip().rstrip('/')


def native_enabled(uid: str) -> bool:
    """True when this uid gets the in-app affiliate page instead of the website."""
    if not uid or os.getenv('AFFILIATE_NATIVE_ENABLED', 'false').strip().lower() != 'true':
        return False
    if not goaffpro_configured():
        return False
    allowlist = {item.strip() for item in os.getenv('AFFILIATE_NATIVE_UID_ALLOWLIST', '').split(',') if item.strip()}
    if uid in allowlist:
        return True
    try:
        percent = float(os.getenv('AFFILIATE_NATIVE_PERCENT', '0'))
    except ValueError:
        return False
    if not 0 <= percent <= 100:
        return False
    bucket = int.from_bytes(hashlib.sha256(('affiliate-native:' + uid).encode()).digest()[:8], 'big') / 2**64
    return bucket * 100 < percent
