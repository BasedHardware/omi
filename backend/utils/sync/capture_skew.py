"""Shared capture-time clock-skew bound for Offline Sync uploads."""

from __future__ import annotations

import os


def maximum_future_skew_seconds() -> int:
    """Mild client clock skew allowed on sync capture timestamps (default 300s)."""
    return max(0, int(os.getenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', '300')))
