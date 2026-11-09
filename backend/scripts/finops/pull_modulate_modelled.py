#!/usr/bin/env python3
"""Modelled daily Modulate STT cost: measured volume x a committed, dated price.

Modulate exposes no usage or balance API (every GET path probed returns 404),
so the vendor line can never be measured. What IS measured is the volume:
`omi_live_stt_audio_seconds_total{provider=...}` (VAD speech seconds flushed
to backend-provider live sessions) is pulled by `pull_prometheus.py` into
`raw/prom_stt_7d.json`. This script multiplies the `modulate` series by the
committed unit price from `backend/config/rate_card_v2.json` and marks every
row `modelled` — never measured.

Coverage caveat, disclosed on the wall through the Mercury reconciliation:
the Prometheus series covers live/PTT streaming sessions metered by the
backend; any Modulate batch-REST volume outside that counter shows up as
reconciliation variance against Mercury cash, not as a hidden zero.

The committed price (rate card v2, committed 2026-10-18 @ f6a358902db):
$0.06 per audio hour — Modulate "Multilingual Transcription" streaming
WebSocket list price, platform.modulate.ai pricing (100 credits = $1, so
$0.06/h is 6 credits/h); live SKU velma-2-stt-streaming, not Velma Triage.
The card is SHA-pinned by backend tests; changing the price is a reviewed
commit that updates this line's date with it.

The Modulate ORG key binding exists for a future API; this script never
reads it and never calls a Modulate endpoint.
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


def modelled_rows(seconds: dict[str, Decimal], price: dict) -> list[dict]:
    per_hour = Decimal(price["price_usd_per_hour"])
    return [
        {
            "date": day,
            "audio_seconds": str(amount.quantize(Decimal("0.000000001"))),
            "usd": str((amount / Decimal(3600) * per_hour).quantize(Decimal("0.000000001"))),
        }
        for day, amount in sorted(seconds.items())
    ]


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
    else:
        try:
            price = price_from_card(card)
            seconds = modulate_seconds(prom, a.start, a.end)
            if not seconds:
                reason = "prometheus_series_missing"
        except ModelledError as error:
            reason = "rate_card_invalid"
            sys.stderr.write("WARNING: Modulate modelled line skipped: %s\n" % error)
    if reason:
        sys.stderr.write("WARNING: Modulate modelled STT line skipped: %s\n" % reason)
        path.write_text(json.dumps({"status": "skipped", "reason": reason}))
        return
    rows = modelled_rows(seconds, price)
    path.write_text(json.dumps({"status": "ready", "method": "modelled", **price, "rows": rows}, indent=1))
    total = sum((Decimal(r["usd"]) for r in rows), Decimal(0))
    sys.stderr.write(
        "modulate modelled %s..%s: %d days, $%s total at $%s/hour (price as-of %s)\n"
        % (a.start, a.end, len(rows), total, price["price_usd_per_hour"], price["price_as_of"])
    )


if __name__ == "__main__":
    main()
