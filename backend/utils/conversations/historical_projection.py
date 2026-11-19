"""Read-time ``summary_on_open`` projection for historical-tier (T1+) rows.

Import-light on purpose: list and detail reads load it with the router, while the
generating path (``historical_summary``) is imported only by the handlers that run it.
"""

from __future__ import annotations

from typing import Any, Mapping

from config import historical_tier
from utils.conversations.summary_delivery import present


def summary_on_open(row: Mapping[str, Any]) -> bool:
    return bool(
        historical_tier.is_historical(dict(row))
        and not present(row.get('structured'))
        and not row.get('is_locked')
        and not row.get('discarded')
        and historical_tier.open_enabled()
    )


def project(row: dict[str, Any]) -> dict[str, Any]:
    """Wire copy advertising ``summary_on_open``; nothing is stored."""
    return {**row, 'summary_on_open': True} if summary_on_open(row) else row
