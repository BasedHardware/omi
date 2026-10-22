#!/usr/bin/env python3
"""Live Stripe read-only: subscriptions -> paying subs, trialing subs, MRR and ARPU by plan,
plus daily processing fees from balance transactions.

This is a SNAPSHOT of the subscription book at the moment it runs. Stripe is not replayable
per historical day from this endpoint, so `plan_revenue_daily` carries `snapshot_date`
alongside `date`: the same snapshot is written against each loaded usage day and the two
columns say plainly that revenue is as-of the snapshot, not as-of the usage day.

Rules baked in:
  * price_id -> plan_id comes from backend/config/plan_catalog.json (prod prices only).
  * trialing subscriptions count in `trialing_subs` and contribute $0 MRR.
  * coupons are applied (percent_off then amount_off).
  * subscriptions carrying metadata.app_id are marketplace app subscriptions, not Omi plans.
  * yearly/weekly/daily intervals are normalised to a monthly figure.
The API key is read from the omi-stripe skill env and never printed or written.

The fee leg refreshes the trailing 90 posted UTC days ending at --end into
`stripe_fee_daily.json`: per day the net `fee` sum across ALL balance-transaction
types (a refund carries a negative fee, so fees are net of refunds on their own
day), the gross charge volume, the row count, and how many rows were non-USD
(counted, never summed: no implicit FX). Only aggregates are persisted.

A restricted key without balance-transaction read scope gets 401/403 here. That is
an UNAVAILABLE state, never a guess: the artifact is written with
status=skipped/permission_unavailable, the subscription book is unaffected, and
the pull exits 0 so the daily job keeps running. The exact scope needed: Read on
the "Balance" category (endpoint GET /v1/balance_transactions). Other HTTP or
shape failures also skip (reason=error) rather than fail the whole pull.
"""

from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import auth_http  # noqa: E402

CATALOG = HERE.parent.parent / "config" / "plan_catalog.json"
ENV = pathlib.Path.home() / ".hermes/skills/omi/omi-stripe/references/.env"
COUNTED_STATUSES = ("active", "trialing", "past_due")
FEE_FILE = "stripe_fee_daily.json"
FEE_WINDOW_DAYS = 90
FEE_MAX_PAGES = 2000
SCOPE_HINT = (
    "Stripe fee line unavailable: the restricted key lacks read access to balance "
    "transactions. Grant Read on the 'Balance' category (GET /v1/balance_transactions) "
    "to the finops Stripe key."
)


class FeeUnavailable(RuntimeError):
    """Bounded message only; never contains an HTTP body or the key."""


def auth_header() -> str:
    key = ""
    if os.environ.get("FINOPS_AUTH") == "cloudrun":
        sys.path.insert(0, str(HERE))
        from cloudrun import secret

        key = secret("stripe")
    else:
        for line in ENV.read_text().splitlines():
            if line.startswith("STRIPE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("no STRIPE_API_KEY in %s" % ENV)
    return "Basic " + base64.b64encode((key + ":").encode()).decode()


def monthly_amount(price: dict, qty: int) -> float:
    amt = (price.get("unit_amount") or 0) / 100.0 * qty
    rec = price.get("recurring") or {}
    iv, ic = rec.get("interval"), rec.get("interval_count") or 1
    if iv == "month":
        return amt / ic
    if iv == "year":
        return amt / (12 * ic)
    if iv == "week":
        return amt * (4.33 / ic)
    if iv == "day":
        return amt * 30 / ic
    return 0.0


def apply_coupon(monthly: float, sub: dict) -> float:
    disc = sub.get("discount") or {}
    c = disc.get("coupon") or {}
    if c.get("percent_off"):
        return monthly * (1 - c["percent_off"] / 100)
    if c.get("amount_off"):
        return max(0.0, monthly - c["amount_off"] / 100)
    return monthly


def fee_page(get, params: dict) -> dict:
    """One balance-transaction page, with the scope/transport errors classified."""
    try:
        return get("/balance_transactions", **params)
    except SystemExit:
        raise FeeUnavailable("stripe redirect refused") from None
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError("stripe balance-transaction permission unavailable") from None
        raise FeeUnavailable("stripe fees HTTP %d" % error.code) from None
    except (OSError, ValueError):
        raise FeeUnavailable("stripe fees transport/JSON failure") from None


def pull_fees(get, raw: pathlib.Path, end: str) -> None:
    """Refresh the trailing FEE_WINDOW_DAYS ending at --end (inclusive) into aggregates.

    Skips (permission, transport, shape) never fail the pull and never publish a
    guessed number: the artifact carries status=skipped with the reason.
    """
    path = raw / FEE_FILE
    path.unlink(missing_ok=True)  # a skipped refresh must not reuse a prior artifact
    end_day = dt.date.fromisoformat(end)
    start_day = end_day - dt.timedelta(days=FEE_WINDOW_DAYS - 1)
    window = [(start_day + dt.timedelta(days=i)).isoformat() for i in range((end_day - start_day).days + 1)]
    try:
        rows = aggregate_fees(get, window)
    except PermissionError:
        sys.stderr.write("WARNING: %s\n" % SCOPE_HINT)
        path.write_text(json.dumps({"status": "skipped", "reason": "permission_unavailable"}))
        return
    except FeeUnavailable as error:
        sys.stderr.write("WARNING: Stripe fee line skipped: %s\n" % error)
        path.write_text(json.dumps({"status": "skipped", "reason": "error"}))
        return
    path.write_text(json.dumps({"status": "ready", "start": window[0], "end": window[-1], "rows": rows}, indent=1))
    month = sum(r["fee_usd"] for r in rows[-30:])
    sys.stderr.write("Stripe fees %s..%s: last-30-posted-days net $%.2f\n" % (window[0], window[-1], month))


def aggregate_fees(get, window: list[str]) -> list[dict]:
    """Sum fee/amount/count per UTC created day over every balance-transaction type.

    `fee` is signed: refunds return the original fee as a negative amount on the
    refund's own day, so the per-day sum is fees net of refunds without pairing.
    Non-USD rows are counted, never summed (no implicit FX).
    """
    start = dt.datetime.fromisoformat(window[0] + "T00:00:00+00:00")
    end_excl = dt.datetime.fromisoformat(window[-1] + "T00:00:00+00:00") + dt.timedelta(days=1)
    days = {day: {"fee": 0, "volume": 0, "count": 0, "foreign": 0} for day in window}
    starting = None
    for _ in range(FEE_MAX_PAGES):
        params = {
            "limit": 100,
            "created[gte]": int(start.timestamp()),
            "created[lt]": int(end_excl.timestamp()),
        }
        if starting:
            params["starting_after"] = starting
        page = fee_page(get, params)
        try:
            data = page["data"]
            for txn in data:
                day = dt.datetime.fromtimestamp(int(txn["created"]), dt.timezone.utc).date().isoformat()
                bucket = days.get(day)
                if bucket is None:
                    raise FeeUnavailable("stripe fee day outside requested window")
                if (txn.get("currency") or "usd") != "usd":
                    bucket["foreign"] += 1
                else:
                    bucket["fee"] += int(txn.get("fee") or 0)
                    if txn.get("type") in ("charge", "payment"):
                        bucket["volume"] += int(txn.get("amount") or 0)
                bucket["count"] += 1
            if not page.get("has_more") or not data:
                break
            starting = data[-1]["id"]
        except FeeUnavailable:
            raise
        except (KeyError, TypeError, ValueError):
            raise FeeUnavailable("invalid stripe balance-transaction response") from None
    else:
        raise FeeUnavailable("stripe fee pagination did not terminate")
    return [
        {
            "date": day,
            "fee_usd": round(bucket["fee"] / 100, 6),
            "volume_usd": round(bucket["volume"] / 100, 6),
            "transaction_count": bucket["count"],
            "foreign_transaction_count": bucket["foreign"],
        }
        for day, bucket in days.items()
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument(
        "--end",
        default=dt.datetime.now(dt.timezone.utc).date().isoformat(),
        help="last fee UTC day, inclusive; the fee window refreshes 90 days ending here",
    )
    a = ap.parse_args()
    hdr = auth_header()

    def get(path: str, **params):
        q = urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request("https://api.stripe.com/v1" + path + "?" + q, headers={"Authorization": hdr})
        try:
            with auth_http.open_authenticated(req, timeout=60) as response:
                return json.load(response)
        except auth_http.RedirectRefused:
            raise SystemExit("stripe redirect refused") from None

    price_plan = {}
    if CATALOG.exists():
        cat = json.load(open(CATALOG))
        price_plan = {
            x["price_id"]: x["plan_id"]
            for x in cat.get("recognized_stripe_prices", [])
            if x.get("environment") == "prod"
        }

    by_plan = collections.defaultdict(
        lambda: {"paying_subs": 0, "trialing_subs": 0, "mrr_usd": 0.0, "cancel_at_period_end": 0}
    )
    by_price = collections.defaultdict(lambda: {"subs": 0, "trialing": 0, "mrr": 0.0})
    starting, scanned = None, 0
    while True:
        params = dict(limit=100, status="all")
        if starting:
            params["starting_after"] = starting
        r = get("/subscriptions", **params)
        for s in r["data"]:
            if s["status"] not in COUNTED_STATUSES:
                continue
            if (s.get("metadata") or {}).get("app_id"):
                continue
            scanned += 1
            for it in s["items"]["data"]:
                p = it["price"]
                plan = price_plan.get(p["id"], "unmapped:" + p["id"])
                m = apply_coupon(monthly_amount(p, it.get("quantity") or 1), s)
                g = by_plan[plan]
                if s["status"] == "trialing":
                    g["trialing_subs"] += 1
                else:
                    g["paying_subs"] += 1
                    g["mrr_usd"] += m
                g["cancel_at_period_end"] += bool(s.get("cancel_at_period_end"))
                q = by_price[(plan, p["id"], (p.get("recurring") or {}).get("interval"), p.get("unit_amount"))]
                q["subs"] += 1
                q["trialing"] += s["status"] == "trialing"
                q["mrr"] += 0.0 if s["status"] == "trialing" else m
        if not r.get("has_more"):
            break
        starting = r["data"][-1]["id"]

    rows = []
    for plan, g in by_plan.items():
        rows.append(
            {
                "plan": plan,
                "paying_subs": g["paying_subs"],
                "trialing_subs": g["trialing_subs"],
                "mrr_usd": round(g["mrr_usd"], 2),
                "arpu_usd": round(g["mrr_usd"] / g["paying_subs"], 4) if g["paying_subs"] else 0.0,
                "cancel_at_period_end": g["cancel_at_period_end"],
            }
        )
    rows.sort(key=lambda x: -x["mrr_usd"])
    raw = pathlib.Path(a.raw)
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "stripe_plan_mrr.json").write_text(
        json.dumps(
            {
                "subscriptions_scanned": scanned,
                "by_plan": rows,
                "by_price": [
                    {"plan": k[0], "price_id": k[1], "interval": k[2], "unit_amount": k[3], **v}
                    for k, v in sorted(by_price.items(), key=lambda kv: -kv[1]["mrr"])
                ],
            },
            indent=1,
        )
    )
    for x in rows:
        sys.stderr.write(
            "  %-24s paying=%-5d trial=%-4d mrr=$%-10.2f arpu=$%.2f\n"
            % (x["plan"], x["paying_subs"], x["trialing_subs"], x["mrr_usd"], x["arpu_usd"])
        )
    sys.stderr.write("subscriptions scanned: %d\n" % scanned)
    # After the book: a fee-leg skip must never lose the subscription snapshot.
    pull_fees(get, raw, a.end)


if __name__ == "__main__":
    main()
