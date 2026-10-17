"""Affiliate ref-code validation, ported from the affiliate dashboard.

Ref codes appear in public links (omi.me/?ref=<code>), so they must not pass
for an Omi-issued discount, impersonate the brand, or carry abusive words.
"""

import re
from dataclasses import dataclass
from typing import Literal, Optional

REF_CODE_MIN_LENGTH = 3
REF_CODE_MAX_LENGTH = 32

_FORMAT = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{2,31}$')

DISCOUNT_TERMS = (
    'save', 'saving', 'savings', 'off', 'deal', 'deals', 'sale', 'sales', 'promo', 'promos', 'promotion',
    'promocode', 'code', 'codes', 'coupon', 'coupons', 'discount', 'discounts', 'free', 'offer', 'offers',
    'bargain', 'cheap', 'clearance', 'special', 'specials', 'holiday', 'blackfriday', 'cybermonday',
    'christmas', 'claim', 'gift', 'voucher', 'rebate', 'cashback',
)  # fmt: skip
BRAND_TERMS = (
    'omi', 'omiapp', 'omiglass', 'omihq', 'omime', 'friend', 'based', 'basedhardware', 'official', 'support',
    'team', 'staff', 'admin', 'help', 'contact', 'hello', 'info', 'sales', 'marketing', 'founder', 'founders',
    'ceo', 'store', 'shop', 'billing', 'refund', 'refunds',
)  # fmt: skip
RESERVED_TERMS = ('scam', 'hack', 'fraud', 'fake', 'test', 'demo', 'null', 'undefined', 'unknown')
PROFANITY_TERMS = (
    'fuck', 'shit', 'bitch', 'cunt', 'dick', 'cock', 'pussy', 'asshole', 'bastard', 'nigger', 'nigga',
    'faggot', 'retard', 'porn', 'sex', 'xxx', 'nazi', 'rape',
)  # fmt: skip

_BLOCKED = frozenset(DISCOUNT_TERMS + BRAND_TERMS + RESERVED_TERMS + PROFANITY_TERMS)
_DISCOUNT_WITH_NUMBER = tuple(re.compile(rf'^{term}\d+$') for term in DISCOUNT_TERMS)
_IMPERSONATION_SUFFIXES = frozenset(
    ('team', 'support', 'help', 'official', 'staff', 'admin', 'store', 'shop', 'info', 'sales')
)

Reason = Literal['length', 'format', 'blocked']


@dataclass(frozen=True)
class RefCodeValidation:
    ok: bool
    normalized: Optional[str] = None
    reason: Optional[Reason] = None
    error: Optional[str] = None


def _rejected(reason: Reason, error: str) -> RefCodeValidation:
    return RefCodeValidation(ok=False, reason=reason, error=error)


def validate_ref_code(value: str) -> RefCodeValidation:
    trimmed = (value or '').strip()
    if len(trimmed) < REF_CODE_MIN_LENGTH:
        return _rejected('length', f'Must be at least {REF_CODE_MIN_LENGTH} characters.')
    if len(trimmed) > REF_CODE_MAX_LENGTH:
        return _rejected('length', f'Must be {REF_CODE_MAX_LENGTH} characters or fewer.')
    if not _FORMAT.match(trimmed):
        return _rejected('format', 'Use only letters, numbers, hyphens, and underscores. Must start with a letter.')

    lower = trimmed.lower()
    if lower in _BLOCKED:
        return _rejected(
            'blocked',
            'That word is reserved. Pick something that identifies your brand, not a discount or Omi itself.',
        )
    if any(pattern.match(lower) for pattern in _DISCOUNT_WITH_NUMBER):
        return _rejected('blocked', 'Looks like a generic discount code. Pick something that identifies your brand.')
    for brand in ('omi', 'friend', 'based'):
        if lower == brand:
            continue
        if lower.startswith(f'{brand}-') or lower.startswith(f'{brand}_') or re.match(rf'^{brand}[a-z]+$', lower):
            suffix = re.sub(r'^[-_]', '', lower[len(brand) :])
            if suffix in _IMPERSONATION_SUFFIXES:
                return _rejected('blocked', 'Reserved — looks like an official Omi handle.')
    return RefCodeValidation(ok=True, normalized=lower)
