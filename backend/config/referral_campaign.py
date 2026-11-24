"""Dependency-free campaign gate and storage identity, safe below business logic."""

import os

CAMPAIGN_ID = 'omi_pocket_match_v1'
GRANT_FIELD = 'referral_campaign_grant'


def campaign_enabled() -> bool:
    return os.getenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'false').lower() == 'true'


def campaign_preview_uid(uid: str) -> bool:
    """Team preview: listed uids see the real read-only snapshot; money paths stay gated."""
    raw = os.getenv('OMI_REFERRAL_CAMPAIGN_PREVIEW_UIDS', '')
    return bool(uid) and uid in {item.strip() for item in raw.split(',') if item.strip()}
