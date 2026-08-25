#!/usr/bin/env python3
"""Find users whose Firestore entitlement does not match active Stripe subs.

This is a support/audit script for Stripe webhook eventual-consistency races.
It treats Stripe active/trialing subscriptions with `metadata.uid` and a known paid
price id as source-of-truth, then compares against `users/{uid}` in Firestore.

Usage:
  STRIPE_API_KEY=sk_live_... python scripts/support/find_stripe_entitlement_mismatches.py \
    --project based-hardware --output /tmp/stripe-entitlement-mismatches.json

The script is read-only. It does not repair users.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, cast

from google.cloud import firestore

# Keep in sync with backend/utils/subscription.py and production Cloud Run env.
# Env vars override these defaults when present.
DEFAULT_PRICE_TO_PLAN = {
    # Current Operator
    "price_1TMxVM1F8wnoWYvw9uaoYX7V": "operator",
    "price_1TMxVM1F8wnoWYvwNfXdF6LW": "operator",
    # Current Architect / legacy Pro
    "price_1TAfBB1F8wnoWYvw8XBFM1dX": "architect",
    "price_1TLFac1F8wnoWYvwtPxZhtzE": "architect",
    # Current/legacy Neo / Unlimited
    "price_1RtJPm1F8wnoWYvwhVJ38kLb": "unlimited",
    "price_1RtJQ71F8wnoWYvwKMPaGlGY": "unlimited",
    "price_1TNIHd1F8wnoWYvwkIrekcQZ": "unlimited",
    "price_1TNIHd1F8wnoWYvwlKywJ8TO": "unlimited",
}

ENV_PRICE_PLAN_KEYS = {
    "STRIPE_OPERATOR_MONTHLY_PRICE_ID": "operator",
    "STRIPE_OPERATOR_ANNUAL_PRICE_ID": "operator",
    "STRIPE_ARCHITECT_MONTHLY_PRICE_ID": "architect",
    "STRIPE_ARCHITECT_ANNUAL_PRICE_ID": "architect",
    "STRIPE_PRO_MONTHLY_PRICE_ID": "architect",
    "STRIPE_PRO_ANNUAL_PRICE_ID": "architect",
    "STRIPE_UNLIMITED_MONTHLY_PRICE_ID": "unlimited",
    "STRIPE_UNLIMITED_ANNUAL_PRICE_ID": "unlimited",
    "STRIPE_NEO_MONTHLY_PRICE_ID": "unlimited",
    "STRIPE_NEO_ANNUAL_PRICE_ID": "unlimited",
}

PAID_PLANS = {"unlimited", "operator", "architect"}


@dataclass
class StripeSub:
    uid: str
    stripe_subscription_id: str
    stripe_customer_id: str
    stripe_status: str
    expected_plan: str
    price_id: str
    current_period_start: int | None
    current_period_end: int | None
    cancel_at_period_end: bool
    customer_email: str | None = None


@dataclass
class Mismatch:
    uid: str
    reason: str
    expected_plan: str
    stripe_subscription_id: str
    stripe_customer_id: str
    price_id: str
    customer_email: str | None
    firestore_plan: str | None
    firestore_status: str | None
    firestore_subscription_id: str | None
    firestore_customer_id: str | None
    firestore_exists: bool


def stripe_get(api_key: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.stripe.com/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 support script, fixed host
        return json.load(resp)


def price_to_plan_map() -> dict[str, str]:
    mapping = dict(DEFAULT_PRICE_TO_PLAN)
    for env_key, plan in ENV_PRICE_PLAN_KEYS.items():
        price_id = os.getenv(env_key)
        if price_id:
            mapping[price_id] = plan
    return mapping


def iter_stripe_subscriptions(api_key: str, statuses: list[str]) -> list[dict[str, Any]]:
    subscriptions: list[dict[str, Any]] = []
    for status in statuses:
        params: dict[str, Any] = {"status": status, "limit": 100, "expand[]": "data.customer"}
        while True:
            page = stripe_get(api_key, "subscriptions", params)
            data = page.get("data", [])
            subscriptions.extend(data)
            if not page.get("has_more"):
                break
            params["starting_after"] = data[-1]["id"]
            # Be gentle with Stripe when paging large accounts.
            time.sleep(0.05)
    return subscriptions


def build_stripe_source_of_truth(
    api_key: str, statuses: list[str]
) -> tuple[dict[str, StripeSub], list[dict[str, Any]]]:
    plan_by_price = price_to_plan_map()
    by_uid: dict[str, StripeSub] = {}
    skipped: list[dict[str, Any]] = []

    for sub in iter_stripe_subscriptions(api_key, statuses):
        metadata: dict[str, Any] = cast(dict[str, Any], sub.get("metadata") or {})
        uid: Any = metadata.get("uid")
        items: list[dict[str, Any]] = cast(
            list[dict[str, Any]], cast(dict[str, Any], sub.get("items") or {}).get("data") or []
        )
        price_id: Any = items[0].get("price", {}).get("id") if items else None
        expected_plan: Any = plan_by_price.get(price_id or "")
        if not uid or not expected_plan:
            skipped.append(
                {
                    "subscription_id": sub.get("id"),
                    "status": sub.get("status"),
                    "uid": uid,
                    "price_id": price_id,
                    "reason": "missing_uid_or_unknown_price",
                }
            )
            continue

        customer: Any = sub.get("customer")
        customer_id: Any
        customer_email: Any
        if isinstance(customer, dict):
            customer_dict: dict[str, Any] = cast(dict[str, Any], customer)
            customer_id = customer_dict.get("id")
            customer_email = customer_dict.get("email")
        else:
            customer_id = customer
            customer_email = None

        candidate = StripeSub(
            uid=uid,
            stripe_subscription_id=sub["id"],
            stripe_customer_id=customer_id or "",
            stripe_status=sub.get("status", ""),
            expected_plan=expected_plan,
            price_id=price_id or "",
            current_period_start=sub.get("current_period_start"),
            current_period_end=sub.get("current_period_end"),
            cancel_at_period_end=bool(sub.get("cancel_at_period_end", False)),
            customer_email=customer_email,
        )

        # If Stripe somehow has multiple active paid subs for a uid, keep the one
        # with the furthest period end and let the mismatch report surface the ids.
        existing = by_uid.get(uid)
        if not existing or (candidate.current_period_end or 0) > (existing.current_period_end or 0):
            by_uid[uid] = candidate

    return by_uid, skipped


def compare_firestore(project: str, stripe_by_uid: dict[str, StripeSub]) -> list[Mismatch]:
    db = firestore.Client(project=project)
    mismatches: list[Mismatch] = []

    for uid, stripe_sub in sorted(stripe_by_uid.items()):
        snap: Any = cast(Any, db.collection("users").document(uid).get())  # type: ignore[reportUnknownMemberType]
        if not snap.exists:
            mismatches.append(
                Mismatch(
                    uid=uid,
                    reason="firestore_user_missing",
                    expected_plan=stripe_sub.expected_plan,
                    stripe_subscription_id=stripe_sub.stripe_subscription_id,
                    stripe_customer_id=stripe_sub.stripe_customer_id,
                    price_id=stripe_sub.price_id,
                    customer_email=stripe_sub.customer_email,
                    firestore_plan=None,
                    firestore_status=None,
                    firestore_subscription_id=None,
                    firestore_customer_id=None,
                    firestore_exists=False,
                )
            )
            continue

        data: dict[str, Any] = cast(dict[str, Any], snap.to_dict() or {})
        fs_sub: dict[str, Any] = cast(dict[str, Any], data.get("subscription") or {})
        fs_plan: Any = fs_sub.get("plan")
        fs_status: Any = fs_sub.get("status")
        fs_sub_id: Any = fs_sub.get("stripe_subscription_id")
        fs_customer_id: Any = data.get("stripe_customer_id")

        reasons: list[str] = []

        if fs_plan != stripe_sub.expected_plan:
            reasons.append(f"plan:{fs_plan}->{stripe_sub.expected_plan}")
        if fs_status != "active":
            reasons.append(f"status:{fs_status}->active")
        if fs_sub_id != stripe_sub.stripe_subscription_id:
            reasons.append(f"subscription_id:{fs_sub_id}->{stripe_sub.stripe_subscription_id}")
        if fs_customer_id != stripe_sub.stripe_customer_id:
            reasons.append(f"customer_id:{fs_customer_id}->{stripe_sub.stripe_customer_id}")
        if fs_plan not in PAID_PLANS:
            reasons.append("firestore_not_paid")

        if reasons:
            mismatches.append(
                Mismatch(
                    uid=uid,
                    reason=", ".join(reasons),
                    expected_plan=stripe_sub.expected_plan,
                    stripe_subscription_id=stripe_sub.stripe_subscription_id,
                    stripe_customer_id=stripe_sub.stripe_customer_id,
                    price_id=stripe_sub.price_id,
                    customer_email=stripe_sub.customer_email,
                    firestore_plan=fs_plan,
                    firestore_status=fs_status,
                    firestore_subscription_id=fs_sub_id,
                    firestore_customer_id=fs_customer_id,
                    firestore_exists=True,
                )
            )

    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("GOOGLE_CLOUD_PROJECT", "based-hardware"))
    parser.add_argument(
        "--statuses", nargs="+", default=["active", "trialing"], help="Stripe subscription statuses to scan"
    )
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument(
        "--include-skipped", action="store_true", help="Include skipped Stripe subs with no uid/unknown price in output"
    )
    args = parser.parse_args()

    api_key = os.getenv("STRIPE_API_KEY")
    if not api_key:
        print("STRIPE_API_KEY is required", file=sys.stderr)
        return 2

    stripe_by_uid, skipped = build_stripe_source_of_truth(api_key, args.statuses)
    mismatches = compare_firestore(args.project, stripe_by_uid)

    result = {
        "project": args.project,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "stripe_statuses": args.statuses,
        "stripe_paid_uid_count": len(stripe_by_uid),
        "mismatch_count": len(mismatches),
        "mismatches": [asdict(m) for m in mismatches],
    }
    if args.include_skipped:
        result["skipped"] = skipped

    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
