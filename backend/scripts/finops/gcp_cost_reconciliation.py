"""Gross, signed credits and net reconciliation for the existing GCP export.

This module does not query BigQuery and does not create a PostHog aggregate.
It preserves the rules already implemented by ``pull_gcp.py`` and
``load_bigquery.py``:

- net = gross + credits, and credits stay signed
- the predecessor billing-account export is never summed
- a usage day is recomputed across the three UTC dates that are still
  settling (today and the prior two); older dates stay put
- an older correction is an explicit date-range replacement, not a
  wholesale reload
- ``omi_finops`` tables are partitioned by date with no partition expiry
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

CURRENT_BILLING_TABLE = "based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256"
PREDECESSOR_BILLING_TABLE = "based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B896_918303_539138"
SETTLEMENT_WINDOW_DAYS = 3
PARTITION_LOOKBACK_DAYS = 2
PARTITION_LOOKAHEAD_DAYS = 3

# Grains of the tables ``load_bigquery.py`` already loads. No partition expiry.
AGGREGATE_CATALOG = {
    "unit_cost_daily": {
        "partition": "date",
        "partition_expiry": None,
        "cluster": ["segment_type", "segment", "component"],
        "grain": ["date", "segment_type", "segment", "component", "method"],
    },
    "unit_cost_reconciliation": {
        "partition": "date",
        "partition_expiry": None,
        "cluster": ["pool"],
        "grain": ["date", "pool"],
    },
    "plan_revenue_daily": {
        "partition": "date",
        "partition_expiry": None,
        "cluster": ["plan"],
        "grain": ["date", "plan", "snapshot_date"],
    },
    "unit_cost_user_day": {
        "partition": "date",
        "partition_expiry": None,
        "cluster": ["cohort", "plan"],
        "grain": ["date", "uid_hash", "cohort", "plan"],
    },
}

DIRECT_CONSUMERS = (
    {
        "path": "backend/scripts/finops/pull_gcp.py",
        "reads": CURRENT_BILLING_TABLE,
        "needs_posthog_copy": False,
    },
    {
        "path": "web/admin/lib/services/gcp-billing.ts",
        "reads": CURRENT_BILLING_TABLE,
        "needs_posthog_copy": False,
    },
    {
        "path": "web/admin/lib/services/plan-economics.ts",
        "reads": "based-hardware.omi_finops.unit_cost_daily, plan_revenue_daily, unit_cost_reconciliation",
        "needs_posthog_copy": False,
    },
)


def money(value: Any) -> Decimal:
    return Decimal(str(value))


def net_cost(gross: Any, credits: Any) -> Decimal:
    """Credits are signed. A credit reduces net only when it is negative."""
    return money(gross) + money(credits)


def partition_bounds(start: date, end: date) -> tuple[date, date]:
    """Return the ``[lo, hi)`` partition dates ``pull_gcp.py`` already opens."""
    return start - timedelta(days=PARTITION_LOOKBACK_DAYS), end + timedelta(days=PARTITION_LOOKAHEAD_DAYS)


def settlement_window(today: date) -> tuple[date, date, date]:
    """Today and the prior two UTC dates, oldest first."""
    return today - timedelta(days=2), today - timedelta(days=1), today


def sum_export_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Decimal]:
    """Sum current-account rows. The predecessor table contributes nothing."""
    gross = Decimal("0")
    credits = Decimal("0")
    for row in rows:
        if row.get("table") == PREDECESSOR_BILLING_TABLE:
            continue
        if row.get("table") not in (None, CURRENT_BILLING_TABLE):
            continue
        gross += money(row.get("gross", 0))
        credits += money(row.get("credits", 0))
    return {"gross": gross, "credits": credits, "net": gross + credits}


def apply_date_replacement(
    stored: dict[date, dict[str, Decimal]],
    replacement: dict[date, dict[str, Decimal]],
    dates: Iterable[date],
) -> dict[date, dict[str, Decimal]]:
    """Replace only ``dates``. Every other stored date is preserved."""
    updated = {day: dict(totals) for day, totals in stored.items()}
    for day in dates:
        updated.pop(day, None)
        if day in replacement:
            updated[day] = {
                "gross": money(replacement[day]["gross"]),
                "credits": money(replacement[day]["credits"]),
                "net": net_cost(replacement[day]["gross"], replacement[day]["credits"]),
            }
    return updated


def recompute_settlement_window(
    stored: dict[date, dict[str, Decimal]],
    replacement: dict[date, dict[str, Decimal]],
    today: date,
) -> dict[date, dict[str, Decimal]]:
    """Idempotently replace today and the prior two UTC dates."""
    return apply_date_replacement(stored, replacement, settlement_window(today))


def window_net(totals: dict[date, dict[str, Decimal]], today: date) -> Decimal:
    return sum((totals[day]["net"] for day in settlement_window(today) if day in totals), Decimal("0"))
