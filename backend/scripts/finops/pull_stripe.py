#!/usr/bin/env python3
"""Live Stripe read-only: subscriptions -> paying subs, trialing subs, MRR and ARPU by plan.

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
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CATALOG = HERE.parent.parent / "config" / "plan_catalog.json"
ENV = pathlib.Path.home() / ".hermes/skills/omi/omi-stripe/references/.env"
COUNTED_STATUSES = ("active", "trialing", "past_due")


def auth_header() -> str:
    key = ""
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    hdr = auth_header()

    def get(path: str, **params):
        q = urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request("https://api.stripe.com/v1" + path + "?" + q, headers={"Authorization": hdr})
        return json.load(urllib.request.urlopen(req, timeout=60))

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


if __name__ == "__main__":
    main()
