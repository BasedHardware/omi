"""Gross/credits/net and settlement-window reconciliation. No live BigQuery."""

from datetime import date
from decimal import Decimal

from scripts.finops.gcp_cost_reconciliation import (
    AGGREGATE_CATALOG,
    CURRENT_BILLING_TABLE,
    DIRECT_CONSUMERS,
    PREDECESSOR_BILLING_TABLE,
    apply_date_replacement,
    net_cost,
    partition_bounds,
    recompute_settlement_window,
    settlement_window,
    sum_export_rows,
    window_net,
)

TODAY = date(2026, 10, 12)


def _row(day: date, gross: str, credits: str) -> dict[str, Decimal]:
    return {"gross": Decimal(gross), "credits": Decimal(credits), "net": net_cost(gross, credits)}


def test_net_is_gross_plus_signed_credits_and_predecessor_is_excluded():
    assert net_cost("10.00", "-2.50") == Decimal("7.50")
    assert net_cost("10.00", "1.25") == Decimal("11.25")
    totals = sum_export_rows(
        [
            {"table": CURRENT_BILLING_TABLE, "gross": "10.00", "credits": "-2.50"},
            {"table": CURRENT_BILLING_TABLE, "gross": "4.00", "credits": "0.50"},
            {"table": PREDECESSOR_BILLING_TABLE, "gross": "999.00", "credits": "-100.00"},
        ]
    )
    assert totals == {
        "gross": Decimal("14.00"),
        "credits": Decimal("-2.00"),
        "net": Decimal("12.00"),
    }
    assert totals["net"] == totals["gross"] + totals["credits"]


def test_settlement_window_replaces_three_dates_and_preserves_older_ones():
    older = TODAY.fromordinal(TODAY.toordinal() - 5)
    stored = {
        older: _row(older, "3.00", "-0.25"),
        TODAY.fromordinal(TODAY.toordinal() - 2): _row(TODAY, "1.00", "0"),
        TODAY.fromordinal(TODAY.toordinal() - 1): _row(TODAY, "1.00", "0"),
        TODAY: _row(TODAY, "1.00", "0"),
    }
    window = settlement_window(TODAY)
    assert window == (
        date(2026, 10, 10),
        date(2026, 10, 11),
        date(2026, 10, 12),
    )
    replacement = {
        window[0]: {"gross": "8.00", "credits": "-1.00"},
        window[1]: {"gross": "6.00", "credits": "-0.50"},
        window[2]: {"gross": "5.00", "credits": "-0.25"},
    }
    first = recompute_settlement_window(stored, replacement, TODAY)
    second = recompute_settlement_window(first, replacement, TODAY)
    assert first == second
    assert first[older] == stored[older]
    assert first[window[0]]["net"] == Decimal("7.00")
    assert first[window[1]]["net"] == Decimal("5.50")
    assert first[window[2]]["net"] == Decimal("4.75")
    assert window_net(first, TODAY) == Decimal("17.25")
    assert window_net(first, TODAY) == sum(first[day]["net"] for day in window)


def test_explicit_range_applies_a_late_credit_without_rewriting_neighbors():
    day = date(2026, 9, 1)
    neighbor = date(2026, 9, 2)
    stored = {
        day: _row(day, "20.00", "0"),
        neighbor: _row(neighbor, "9.00", "-1.00"),
    }
    updated = apply_date_replacement(
        stored,
        {day: {"gross": "20.00", "credits": "-3.75"}},
        [day],
    )
    assert updated[day]["credits"] == Decimal("-3.75")
    assert updated[day]["net"] == Decimal("16.25")
    assert updated[neighbor] == stored[neighbor]
    again = apply_date_replacement(updated, {day: {"gross": "20.00", "credits": "-3.75"}}, [day])
    assert again == updated


def test_partition_window_and_catalog_match_the_existing_loaders():
    assert partition_bounds(date(2026, 10, 1), date(2026, 10, 7)) == (date(2026, 9, 29), date(2026, 10, 10))
    assert AGGREGATE_CATALOG["unit_cost_daily"]["partition_expiry"] is None
    assert AGGREGATE_CATALOG["unit_cost_daily"]["grain"] == [
        "date",
        "segment_type",
        "segment",
        "component",
        "method",
    ]
    assert AGGREGATE_CATALOG["unit_cost_user_day"]["cluster"] == ["cohort", "plan"]
    assert all(item["needs_posthog_copy"] is False for item in DIRECT_CONSUMERS)
    assert len(DIRECT_CONSUMERS) == 3
