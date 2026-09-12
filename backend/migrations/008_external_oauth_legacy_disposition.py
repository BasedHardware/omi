"""Pure planner for legacy OAuth records; intentionally performs no database I/O.

The safe migration is explicit re-consent into separate grants. This helper lets
an approved inventory job classify record shapes without copying credentials or
user content. It is not imported by application runtime and cannot mutate data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class LegacyDisposition(str, Enum):
    NO_CREDENTIAL = 'no_credential'
    REVOKE_AND_RECONSENT = 'revoke_and_reconsent'
    VAULT_ONLY_QUARANTINE = 'vault_only_legacy_quarantine'
    UNKNOWN_REVIEW_REQUIRED = 'unknown_review_required'


SECRET_FIELDS = frozenset({'access_token', 'refresh_token', 'token', 'credentials'})


@dataclass(frozen=True)
class LegacyGrantClassification:
    integration_key: str
    has_credential: bool
    has_calendar_scope: bool
    has_gmail_scope: bool
    disposition: LegacyDisposition


def classify_legacy_grant(integration_key: str, record: Mapping[str, object]) -> LegacyGrantClassification:
    scopes = record.get('granted_scopes')
    normalized_scopes = set(scopes) if isinstance(scopes, (list, tuple, set, frozenset)) else set()
    has_credential = any(bool(record.get(field)) for field in SECRET_FIELDS)
    has_calendar = any('calendar' in str(scope) for scope in normalized_scopes)
    has_gmail = any('gmail.' in str(scope) for scope in normalized_scopes)
    if not has_credential:
        disposition = LegacyDisposition.NO_CREDENTIAL
    elif integration_key == 'google_calendar':
        # Never copy this plaintext/broad credential into the new grant family.
        disposition = LegacyDisposition.REVOKE_AND_RECONSENT
    else:
        disposition = LegacyDisposition.UNKNOWN_REVIEW_REQUIRED
    return LegacyGrantClassification(
        integration_key=integration_key,
        has_credential=has_credential,
        has_calendar_scope=has_calendar,
        has_gmail_scope=has_gmail,
        disposition=disposition,
    )


def public_inventory_row(classification: LegacyGrantClassification) -> dict[str, object]:
    """Content-free output safe for aggregate inventory reports."""
    return {
        'integration_key': classification.integration_key,
        'has_credential': classification.has_credential,
        'has_calendar_scope': classification.has_calendar_scope,
        'has_gmail_scope': classification.has_gmail_scope,
        'disposition': classification.disposition.value,
    }
