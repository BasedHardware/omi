"""Dependency-free campaign gate and storage identity, safe below business logic."""

import os

CAMPAIGN_ID = 'omi_pocket_match_v1'
GRANT_FIELD = 'referral_campaign_grant'


def campaign_enabled() -> bool:
    return os.getenv('OMI_REFERRAL_CAMPAIGN_ENABLED', 'false').lower() == 'true'
