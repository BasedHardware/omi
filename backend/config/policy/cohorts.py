"""Literal legacy env fallbacks used by the rollout cache at admission."""

import os


def batch_members():
    return os.getenv('BATCH_PIPELINE_UID_ALLOWLIST', '')


def recovery_members():
    return os.getenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '')
