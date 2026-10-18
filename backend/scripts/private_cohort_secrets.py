"""Private deployment selectors; validate payloads without exposing their members."""

from __future__ import annotations

import json

from config.messaging import validate_channel_policy

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


def pinned_secret_version(version: object) -> bool:
    return isinstance(version, str) and version.isascii() and version.isdigit() and not version.startswith('0')


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
        if not isinstance(policy, dict) or not policy:
            return False
        try:
            for channel, row in policy.items():
                validate_channel_policy(channel, row)
        except (ValueError, TypeError, AttributeError):
            return False
        return True
    members = [member.strip() for member in payload.split(',') if member.strip()]
    if name == 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST':
        return bool(members) and all('/' not in member and len(member.encode('utf-8')) <= 256 for member in members)
    return bool(members)
