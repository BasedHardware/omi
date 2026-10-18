"""Private deployment selectors; validate payloads without exposing their members."""

from __future__ import annotations

import json

PRIVATE_COHORT_ENV_NAMES = frozenset(
    {
        'BATCH_PIPELINE_UID_ALLOWLIST',
        'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST',
        'FIRST_SUMMARY_UID_ALLOWLIST',
        'DREAM_AGENT_UID_ALLOWLIST',
        'SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST',
        'STT_LIVE_DEMAND_UID_ALLOWLIST',
        'SYNC_LEGACY_FRESH_UID_ALLOWLIST',
        'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST',
        'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST',
        'TRANSCRIPTION_SHADOW_UID_ALLOWLIST',
        'MOBILE_STANDARD_BATCH_UIDS',
        'OMI_MESSAGING_CHANNELS_UIDS',
        'OMI_MESSAGING_CHANNEL_POLICY',
    }
)


def valid_private_cohort_payload(name: str, payload: str | bytes) -> bool:
    if isinstance(payload, bytes):
        try:
            payload = payload.decode('utf-8')
        except UnicodeError:
            return False
    if name == 'OMI_MESSAGING_CHANNEL_POLICY':
        try:
            policy = json.loads(payload)
        except (ValueError, TypeError):
            return False
        return isinstance(policy, dict) and bool(policy)
    return any(member.strip() for member in payload.split(','))
