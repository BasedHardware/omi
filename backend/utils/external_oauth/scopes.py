"""Exact capability-to-provider-scope registry and canonicalization."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping

from utils.external_oauth.contracts import Capability, Connector, ExternalOAuthError, ProviderErrorKind

SCOPE_REGISTRY_REVISION = 'google-read-v1'
OPENID = 'openid'
EMAIL = 'email'
CALENDAR_EVENTS_READONLY = 'https://www.googleapis.com/auth/calendar.events.readonly'
GMAIL_READONLY = 'https://www.googleapis.com/auth/gmail.readonly'


@dataclass(frozen=True)
class GrantFamily:
    connector: Connector
    client_alias: str
    grant_family: str
    capability: Capability
    scopes: frozenset[str]


GRANT_FAMILIES: Mapping[Connector, GrantFamily] = {
    Connector.GOOGLE_CALENDAR: GrantFamily(
        connector=Connector.GOOGLE_CALENDAR,
        client_alias='google_calendar_prod',
        grant_family='google_calendar_read',
        capability=Capability.CALENDAR_EVENTS_READ,
        scopes=frozenset({OPENID, EMAIL, CALENDAR_EVENTS_READONLY}),
    ),
    Connector.GMAIL: GrantFamily(
        connector=Connector.GMAIL,
        client_alias='google_gmail_prod',
        grant_family='google_gmail_read',
        capability=Capability.MAIL_MESSAGES_READ,
        scopes=frozenset({OPENID, EMAIL, GMAIL_READONLY}),
    ),
}

# Google can return canonical URLs or documented aliases. Unknown additions are
# never ignored: they fail activation so scope expansion cannot happen silently.
PROVIDER_SCOPE_ALIASES: Mapping[str, str] = {
    OPENID: OPENID,
    EMAIL: EMAIL,
    CALENDAR_EVENTS_READONLY: CALENDAR_EVENTS_READONLY,
    GMAIL_READONLY: GMAIL_READONLY,
    'https://www.googleapis.com/auth/userinfo.email': EMAIL,
}


def canonicalize_scopes(scopes: Iterable[str]) -> frozenset[str]:
    canonical: set[str] = set()
    unknown: list[str] = []
    for scope in scopes:
        normalized = scope.strip()
        if not normalized:
            continue
        mapped = PROVIDER_SCOPE_ALIASES.get(normalized)
        if mapped is None:
            unknown.append(normalized)
        else:
            canonical.add(mapped)
    if unknown:
        raise ExternalOAuthError(ProviderErrorKind.SCOPE_MISMATCH, 'provider_returned_unknown_scope')
    return frozenset(canonical)


def require_exact_scopes(connector: Connector, scopes: Iterable[str]) -> frozenset[str]:
    effective = canonicalize_scopes(scopes)
    expected = GRANT_FAMILIES[connector].scopes
    if effective != expected:
        raise ExternalOAuthError(ProviderErrorKind.SCOPE_MISMATCH, 'provider_scope_set_mismatch')
    return effective


def scope_digest(scopes: Iterable[str]) -> str:
    canonical = sorted(canonicalize_scopes(scopes))
    return hashlib.sha256('\n'.join(canonical).encode()).hexdigest()
