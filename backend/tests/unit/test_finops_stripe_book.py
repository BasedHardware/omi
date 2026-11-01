"""Hermetic Stripe subscription-book tests. Synthetic API shapes only: no
account reads, identifiers, network or credentials. Covers the currency and
counting contracts the wall depends on:

  * zero-decimal currencies (JPY, KRW, ...) are never divided by 100
    (docs.stripe.com/currencies#zero-decimal; three-decimal ÷1000);
  * `mrr_usd` is USD only — a non-USD price keeps its payer counted, its native
    amount reported per currency, and is never booked as dollars;
  * a customer counts once per plan and once overall, never per item;
  * the loader carries `paying_customers`/`non_usd_paying_subs` (nullable) and
    old artifacts load them as NULL (live-table reconcile:
    test_finops_schema_reconcile.py).
"""

import importlib.util
import json
import pathlib

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"


def load(name):
    spec = importlib.util.spec_from_file_location("test_" + name, FINOPS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stripe(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    return load("pull_stripe")


def price(currency="usd", unit_amount=1999, interval="month", count=1):
    return {
        "id": "price_%s_%s" % (currency, unit_amount),
        "currency": currency,
        "unit_amount": unit_amount,
        "recurring": {"interval": interval, "interval_count": count},
    }


def sub(customer, prices, status="active", **extra):
    return {
        "id": "sub_%s" % customer,
        "customer": "cus_%s" % customer,
        "status": status,
        "metadata": {},
        "items": {"data": [{"price": p, "quantity": 1} for p in prices]},
        **extra,
    }


def plan_map(*prices, plan="unlimited"):
    return {p["id"]: plan for p in prices}


def test_zero_decimal_currency_is_not_divided_by_100(stripe):
    assert stripe.monthly_amount(price(currency="jpy", unit_amount=1200), 1) == 1200.0
    # KRW is zero-decimal too: ₩9,900 stays 9900 (÷100 would book ₩99).
    assert stripe.monthly_amount(price(currency="krw", unit_amount=9900), 1) == 9900.0
    assert stripe.monthly_amount(price(currency="usd", unit_amount=1999), 1) == 19.99
    assert stripe.monthly_amount(price(currency="vnd", unit_amount=150000), 1) == 150000.0


def test_three_decimal_currency_uses_thousandths(stripe):
    assert stripe.monthly_amount(price(currency="kwd", unit_amount=1500), 1) == 1.5


def test_backward_compat_currencies_stay_two_decimal(stripe):
    # Stripe's "Special cases" table (docs.stripe.com/currencies#special-cases):
    # "UGX transitioned to a zero-decimal currency, but backwards compatibility
    # requires you to represent it as a two-decimal value, where the decimal
    # amount is always `00`. For example, to charge 5 UGX, provide an `amount`
    # value of `500`." — same rule for ISK. Dividing by 1 would report a UGX
    # 500 price as native UGX 500 instead of UGX 5 (100x, Luna r2 P2).
    assert stripe.currency_divisor("ugx") == 100
    assert stripe.monthly_amount(price(currency="ugx", unit_amount=500), 1) == 5.0
    assert stripe.currency_divisor("isk") == 100
    assert stripe.monthly_amount(price(currency="isk", unit_amount=500), 1) == 5.0
    # HUF's and TWD's special cases are PAYOUT divisibility only — charges
    # remain two-decimal ("you can charge two-decimal amounts"), so the
    # default divisor is already correct for Price unit_amount.
    assert stripe.currency_divisor("huf") == 100
    assert stripe.currency_divisor("twd") == 100


def test_annual_price_normalises_to_monthly_in_native_currency(stripe):
    assert stripe.monthly_amount(price(currency="jpy", unit_amount=14400, interval="year"), 1) == 1200.0


def test_coupon_amount_off_scales_by_coupon_currency(stripe):
    # A JPY coupon's amount_off is already in major units.
    s = sub(
        "jp",
        [price(currency="jpy", unit_amount=1200)],
        discount={"coupon": {"percent_off": None, "amount_off": 200, "currency": "jpy"}},
    )
    assert stripe.apply_coupon(1200.0, s) == 1000.0
    u = sub(
        "us",
        [price(currency="usd", unit_amount=1999)],
        discount={"coupon": {"percent_off": None, "amount_off": 500, "currency": "usd"}},
    )
    assert stripe.apply_coupon(19.99, u) == pytest.approx(14.99)


def test_non_usd_mrr_is_excluded_counted_and_reported_native(stripe):
    jpy = price(currency="jpy", unit_amount=1200)
    usd = price(currency="usd", unit_amount=1999)
    book = stripe.summarize_book([sub("jp", [jpy]), sub("us", [usd])], plan_map(jpy, usd))
    row = {r["plan"]: r for r in book["by_plan"]}["unlimited"]
    # JPY 1,200 is NOT booked as USD 12: the payer counts, the dollars do not.
    assert row["mrr_usd"] == 19.99
    assert row["paying_subs"] == 2
    assert row["arpu_usd"] == 19.99  # USD MRR over USD payers
    assert book["paying_customers"] == 2
    assert book["non_usd_paying_subs"] == 1
    assert book["non_usd_mrr_native"] == {"jpy": 1200.0}


def test_customers_count_once_per_plan_not_per_item(stripe):
    two_items = [price(currency="usd", unit_amount=1999), price(currency="usd", unit_amount=999, interval="month")]
    book = stripe.summarize_book(
        [sub("a", two_items), sub("b", [price(currency="usd", unit_amount=1999)])],
        plan_map(*two_items, plan="multi") | plan_map(price(currency="usd", unit_amount=1999), plan="multi"),
    )
    row = {r["plan"]: r for r in book["by_plan"]}["multi"]
    # One customer with two subscription items, one with one: 2 payers, not 3.
    assert row["paying_subs"] == 2
    assert row["mrr_usd"] == round(19.99 + 9.99 + 19.99, 2)
    assert book["paying_customers"] == 2


def test_multi_plan_customer_counts_once_per_plan_and_once_overall(stripe):
    p1, p2 = price(currency="usd", unit_amount=1999), price(currency="usd", unit_amount=4999)
    book = stripe.summarize_book(
        [sub("a", [p1, p2]), sub("b", [p1])],
        {p1["id"]: "unlimited", p2["id"]: "architect"},
    )
    plans = {r["plan"]: r for r in book["by_plan"]}
    assert plans["unlimited"]["paying_subs"] == 2
    assert plans["architect"]["paying_subs"] == 1
    # The book-wide count is distinct customers, not the plan sum (2, not 3).
    assert plans["unlimited"]["paying_customers"] == 2
    assert plans["architect"]["paying_customers"] == 2
    assert book["paying_customers"] == 2


def test_trialing_counts_zero_mrr_and_app_subs_skipped(stripe):
    usd = price(currency="usd", unit_amount=1999)
    book = stripe.summarize_book(
        [
            sub("t", [usd], status="trialing"),
            {
                "id": "sub_app",
                "customer": "cus_app",
                "status": "active",
                "metadata": {"app_id": "x"},
                "items": {"data": [{"price": usd, "quantity": 1}]},
            },
            sub("p", [usd]),
        ],
        plan_map(usd),
    )
    row = {r["plan"]: r for r in book["by_plan"]}["unlimited"]
    assert row["paying_subs"] == 1
    assert row["trialing_subs"] == 1
    assert row["mrr_usd"] == 19.99
    assert book["paying_customers"] == 1


def test_loader_carries_customer_counts(stripe, tmp_path, monkeypatch):
    loader = load("load_bigquery")

    # build_rows reads three derived CSVs alongside the raw artifact.
    (tmp_path / "unit_cost_long.csv").write_text(
        "date,segment_type,segment,component,method,usd,users,usd_per_user_day\n"
        "2026-10-20,plan,unlimited,fully_loaded,measured,10,5,2\n"
    )
    (tmp_path / "unit_cost_reconciliation.csv").write_text(
        "date,pool,pool_usd,allocated_usd,delta_pct,invoice_source,note,inputs_settled\n"
    )
    comps_header = ",".join(loader.COMPS)
    (tmp_path / "user_day_allocated.csv").write_text(
        "date,uid_hash,cohort,plan,attempts,unpriced_attempts,tx_sec,%s,run_id,computed_at,inputs_settled\n"
        % comps_header
    )

    usd = price(currency="usd", unit_amount=1999)
    jpy = price(currency="jpy", unit_amount=1200)
    book = stripe.summarize_book(
        [sub("us", [usd]), sub("jp", [jpy])],
        plan_map(usd, plan="unlimited") | plan_map(jpy, plan="unlimited"),
    )
    (tmp_path / "stripe_plan_mrr.json").write_text(json.dumps(book))

    rows = loader.build_rows(tmp_path, tmp_path, "run-1", "t", None, "2026-10-22")[0]["plan_revenue_daily"]
    assert rows and rows[0]["paying_customers"] == 2
    assert rows[0]["non_usd_paying_subs"] == 1

    # An artifact written before the columns existed loads as NULL.
    legacy = json.loads(json.dumps(book))
    for row in legacy["by_plan"]:
        row.pop("paying_customers")
        row.pop("non_usd_paying_subs")
    (tmp_path / "stripe_plan_mrr.json").write_text(json.dumps(legacy))
    rows = loader.build_rows(tmp_path, tmp_path, "run-2", "t", None, "2026-10-22")[0]["plan_revenue_daily"]
    assert rows[0]["paying_customers"] is None
    assert rows[0]["non_usd_paying_subs"] is None
