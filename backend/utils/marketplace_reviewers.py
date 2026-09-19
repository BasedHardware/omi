"""Marketplace reviewer configuration parsing and validation."""

from __future__ import annotations

import os
from typing import List, Optional


def parse_marketplace_reviewers(raw: Optional[str] = None) -> List[str]:
    """Parse MARKETPLACE_APP_REVIEWERS into a list of non-empty, trimmed UIDs.

    Drops blank entries, trims surrounding whitespace and newlines, and preserves order.
    """
    if raw is None:
        raw = os.getenv("MARKETPLACE_APP_REVIEWERS", "")
    if not raw:
        return []
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def is_marketplace_reviewer(uid: str, raw: Optional[str] = None) -> bool:
    """Check whether a given uid is a configured marketplace reviewer."""
    if not uid:
        return False
    return uid.strip() in parse_marketplace_reviewers(raw)
