#!/usr/bin/env python3
"""Modelled daily Modulate cost: measured live, REST STT and LID audio volume.

Live seconds use the SHA-pinned streaming rate card. REST accepted seconds
from GKE and Cloud Run use finops-owned, dated public batch and LID prices.
Errors are logged as an unpriced upper bound. Failed queries skip the whole
window so missing batch data cannot silently publish a live-only undercount.
Every row is modelled; Mercury cash remains the reconciliation authority.
This script never reads the Modulate ORG key or calls a Modulate endpoint.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import datetime as dt
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RATE_CARD = HERE.parent.parent / "config" / "rate_card_v2.json"
# Date of the commit that introduced the v2 modulate entry (f6a358902db).
RATE_CARD_AS_OF = "2026-10-18"
REST_PRICES = HERE / "modulate_prices.json"
REST_QUERIES = {
    "d_modulate_rest_audio_seconds": "prometheus",
    "d_gmp_modulate_rest_audio_seconds": "gmp-cloud-run",
}
PROVIDER = "modulate"
ARTIFACT = "stt_modulate_modelled_daily.json"


class ModelledError(RuntimeError):
    """A sanitized failure; never a credential or raw response."""


def price_from_card(card: dict) -> dict:
    entry = (card.get("transcription") or {}).get(PROVIDER)
    if not isinstance(entry, dict):
        raise ModelledError("rate card has no modulate transcription price")
    micros = entry.get("micro_usd_per_hour")
    if type(micros) is not int or micros <= 0:
        raise ModelledError("rate card modulate price is not a positive integer")
    if entry.get("status") != "card":
        raise ModelledError("rate card modulate price is not committed card status")
    source = entry.get("source")
    if not isinstance(source, str) or not source:
        raise ModelledError("rate card modulate price carries no source citation")
    return {
        "price_usd_per_hour": str((Decimal(micros) / Decimal(1_000_000)).quantize(Decimal("0.000000001"))),
        "price_source": source,
        "price_as_of": RATE_CARD_AS_OF,
    }


def rest_prices() -> dict:
    """Load committed batch prices with the same positive-micros contract as the card."""
    try:
        prices = json.loads(REST_PRICES.read_text())
    except (OSError, ValueError):
        raise ModelledError("rest_prices_unavailable") from None
    if not isinstance(prices, dict):
        raise ModelledError("rest_prices_invalid")
    result = {}
    for sku, prefix in (("batch_stt", "rest"), ("lid", "lid")):
        entry = prices.get(sku)
        try:
            price = price_from_card({"transcription": {PROVIDER: entry}})
            as_of = entry.get("as_of")
            if not isinstance(as_of, str) or dt.date.fromisoformat(as_of).isoformat() != as_of:
                raise ValueError("invalid date")
        except (ModelledError, ValueError, TypeError):
            raise ModelledError("rest_prices_invalid") from None
        result.update(
            {
                prefix + "_price_usd_per_hour": price["price_usd_per_hour"],
                prefix + "_price_source": price["price_source"],
                prefix + "_price_as_of": as_of,
            }
        )
    return result


def queries_succeeded(prom: dict) -> bool:
    daily = prom.get("daily") or {}
    # Older artifacts without the new queries cannot establish complete coverage.
    required = {"d_live_stt_audio_seconds", *REST_QUERIES}
    return required <= daily.keys() and all(
        (entry.get("result") or {}).get("status") == "success" for entry in daily.values()
    )


def modulate_rest_seconds(prom: dict, start: str, end: str) -> dict[str, dict[str, Decimal]]:
    """Accepted REST audio from disjoint GKE/GMP sources; bucket T = day T-1."""
    seconds = {}
    errors = {}
    for name, datasource in REST_QUERIES.items():
        entry = (prom.get("daily") or {}).get(name) or {}
        if entry.get("datasource") != datasource:
            raise ModelledError("modulate REST query has an invalid datasource")
        result = entry.get("result") or {}
        for series in result.get("data", {}).get("result", []):
            metric = series.get("metric") or {}
            # Defensive check for Cloud Run results accidentally present in GKE.
            if datasource == "prometheus" and metric.get("cluster") == "__run__":
                continue
            if metric.get("provider", PROVIDER) != PROVIDER:
                continue
            endpoint, outcome = metric.get("endpoint"), metric.get("outcome")
            if endpoint not in {"stt", "lid"} or outcome not in {"ok", "error"}:
                continue
            for ts, value in series.get("values", []):
                day = (dt.datetime.fromtimestamp(int(ts), dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
                if not start <= day <= end:
                    continue
                amount = Decimal(str(value))
                if not amount.is_finite() or amount < 0:
                    raise ModelledError("modulate REST audio-seconds series carries an invalid value")
                daily = seconds.setdefault(day, {"stt": Decimal(0), "lid": Decimal(0)})
                if outcome == "ok":
                    daily[endpoint] += amount
                else:
                    key = (day, endpoint)
                    errors[key] = errors.get(key, Decimal(0)) + amount
    for (day, endpoint), amount in sorted(errors.items()):
        sys.stderr.write("modulate REST %s %s error seconds=%s (unpriced upper bound)\n" % (day, endpoint, amount))
    return seconds


def modulate_seconds(prom: dict, start: str, end: str) -> dict[str, Decimal]:
    """provider=modulate daily seconds from the prom artifact; bucket T = day T-1."""
    series = ((prom.get("daily") or {}).get("d_live_stt_audio_seconds") or {}).get("result") or {}
    rows = series.get("data", {}).get("result", []) if series.get("status") == "success" else []
    seconds: dict[str, Decimal] = {}
    for s in rows:
        if (s.get("metric") or {}).get("provider") != PROVIDER:
            continue
        for ts, value in s.get("values", []):
            day = (dt.datetime.fromtimestamp(int(ts), dt.timezone.utc) - dt.timedelta(days=1)).date().isoformat()
            if start <= day <= end:
                amount = Decimal(str(value))
                if not amount.is_finite() or amount < 0:
                    raise ModelledError("modulate audio-seconds series carries an invalid value")
                seconds[day] = seconds.get(day, Decimal(0)) + amount
    return seconds


def modelled_rows(
    seconds: dict[str, Decimal], price: dict, rest_seconds: dict[str, dict[str, Decimal]], rest_price: dict
) -> list[dict]:
    rows = []
    for day in sorted(seconds.keys() | rest_seconds.keys()):
        live = seconds.get(day, Decimal(0))
        rest = rest_seconds.get(day, {})
        stt, lid = rest.get("stt", Decimal(0)), rest.get("lid", Decimal(0))
        usd = (
            live * Decimal(price["price_usd_per_hour"])
            + stt * Decimal(rest_price["rest_price_usd_per_hour"])
            + lid * Decimal(rest_price["lid_price_usd_per_hour"])
        ) / Decimal(3600)
        rows.append(
            {
                "date": day,
                **{
                    key: format(value.quantize(Decimal("0.000000001")), "f")
                    for key, value in {
                        "audio_seconds": live + stt + lid,
                        "live_seconds": live,
                        "rest_stt_seconds": stt,
                        "lid_seconds": lid,
                        "usd": usd,
                    }.items()
                },
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True, help="first usage day, inclusive")
    ap.add_argument("--end", required=True, help="last usage day, inclusive")
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    raw = pathlib.Path(a.raw)
    path = raw / ARTIFACT
    path.unlink(missing_ok=True)  # a skipped refresh must not reuse a prior artifact
    try:
        card = json.loads(RATE_CARD.read_text())
    except (OSError, ValueError):
        card = None
    prom_path = raw / "prom_stt_7d.json"
    prom = json.loads(prom_path.read_text()) if prom_path.exists() else None
    reason = None
    price = None
    if card is None:
        reason = "rate_card_unavailable"
    elif prom is None:
        reason = "prometheus_artifact_unavailable"
    elif not queries_succeeded(prom):
        reason = "gmp_query_failed"
    else:
        try:
            price = price_from_card(card)
        except ModelledError:
            reason = "rate_card_invalid"
        if not reason:
            try:
                rest_price = rest_prices()
            except ModelledError as error:
                reason = str(error)
        if not reason:
            try:
                seconds = modulate_seconds(prom, a.start, a.end)
                rest_seconds = modulate_rest_seconds(prom, a.start, a.end)
                if not seconds and not rest_seconds:
                    reason = "prometheus_series_missing"
            except ModelledError:
                reason = "prometheus_series_invalid"
    if reason:
        sys.stderr.write("WARNING: Modulate modelled STT line skipped: %s\n" % reason)
        path.write_text(json.dumps({"status": "skipped", "reason": reason}))
        return
    rows = modelled_rows(seconds, price, rest_seconds, rest_price)
    path.write_text(
        json.dumps({"status": "ready", "method": "modelled", **price, **rest_price, "rows": rows}, indent=1)
    )
    total = sum((Decimal(r["usd"]) for r in rows), Decimal(0))
    sys.stderr.write(
        "modulate modelled %s..%s: %d days, $%s total; live $%s/hour (price as-of %s), REST STT $%s/hour, LID $%s/hour\n"
        % (
            a.start,
            a.end,
            len(rows),
            total,
            price["price_usd_per_hour"],
            price["price_as_of"],
            rest_price["rest_price_usd_per_hour"],
            rest_price["lid_price_usd_per_hour"],
        )
    )


if __name__ == "__main__":
    main()
