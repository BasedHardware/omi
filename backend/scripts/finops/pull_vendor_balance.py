"""Optional prepaid-balance snapshots for STT vendors (Soniox today).

Soniox exposes NO usage, invoice or billing endpoint for the organization key
(every such path returns 404). The one readable number is
``GET https://api.soniox.com/v1/organization/balance``:

  used_balance_usd       cumulative spend to date (a string)
  available_balance_usd  remaining prepaid balance (a string)
  invoice_billing_enabled

This pull only snapshots those numbers. Daily spend is DERIVED from
consecutive snapshots by ``daily_deltas`` below and published by
``load_bigquery.py``; a single snapshot never claims a day rate.

The artifact and the logs carry parsed numbers only: never the key, never the
raw response body. A missing key or an unavailable API is a skipped artifact
(reason recorded), never a failed daily job and never a guessed balance.
"""

from __future__ import annotations

import argparse
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal, localcontext
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

import auth_http

BALANCE_URL = "https://api.soniox.com/v1/organization/balance"
VENDOR = "soniox"
# The wall keeps its dated console constant until 2 snapshots exist (David
# 2026-10-22); the threshold itself is enforced on the wall side, where the
# snapshot count is read.
GAP_FLAG = "gap_spread"
RESET_FLAG = "baseline_reset"

# Bounded, sanitized skip vocabulary. The daily job copies this token into Cloud
# Logging, so it is a fixed set: never a vendor message, URL, header, response
# body or account value.
SKIP_REASONS = frozenset(
    {
        "key_unavailable",
        "permission_unavailable",
        "redirect_refused",
        "http_error",
        "transport_error",
        "invalid_response",
    }
)


class BalanceError(RuntimeError):
    """A sanitized transport/shape failure; never the HTTP body or the key."""

    def __init__(self, reason: str, detail: str = "", http_status: int | None = None):
        if reason not in SKIP_REASONS:
            raise ValueError("unbounded balance skip reason")
        super().__init__(detail or reason)
        self.reason = reason
        self.http_status = http_status


def usd(value) -> Decimal:
    """Parse one balance field. Soniox sends strings; accept numbers leniently."""
    if isinstance(value, bool):
        raise BalanceError("invalid_response", "invalid balance value")
    try:
        amount = Decimal(str(value))
    except Exception:
        raise BalanceError("invalid_response", "invalid balance value") from None
    if not amount.is_finite() or amount < 0:
        raise BalanceError("invalid_response", "invalid balance value")
    return amount


# BigQuery NUMERIC holds 29 integer and 9 fractional digits. The vendor sends
# more fractional digits than that (its first real snapshot was rejected with
# "Invalid NUMERIC value" on used_usd), so money is rounded half-up to nine
# decimals at the artifact boundary, the same policy the derived daily spend
# already uses (README: "NUMERIC outputs round to nine decimal places").
NUMERIC_SCALE = Decimal("0.000000001")
NUMERIC_LIMIT = Decimal(10) ** 29


def numeric_usd(amount: Decimal, *, pad: bool = False) -> str:
    """Render a parsed amount as a plain decimal string BigQuery NUMERIC accepts.

    Values with at most nine fractional digits keep their digits (``12.5`` stays
    ``12.5``, ``0`` stays ``0``). Longer ones round half-up to nine places. Never
    exponent notation (a quantized zero is ``0.000000000``), and a value outside
    the NUMERIC range after rounding is an invalid response, not a load error.
    ``pad=True`` always renders nine places (the derived daily spend's historical
    shape). Arithmetic runs at 60 digits so a 29-integer-digit value can be rounded.
    """
    with localcontext() as ctx:
        ctx.prec = 60
        if pad or amount.as_tuple().exponent < -9:
            amount = amount.quantize(NUMERIC_SCALE, rounding=ROUND_HALF_UP)
        if amount >= NUMERIC_LIMIT:
            raise BalanceError("invalid_response", "balance value out of range")
        return format(amount, "f")


def parse_balance(payload) -> dict:
    """Validate the balance document and return parsed numbers only."""
    if not isinstance(payload, dict):
        raise BalanceError("invalid_response", "balance response is not an object")
    used = usd(payload.get("used_balance_usd"))
    available = usd(payload.get("available_balance_usd"))
    invoice = payload.get("invoice_billing_enabled")
    if not isinstance(invoice, bool):
        raise BalanceError("invalid_response", "balance response missing invoice_billing_enabled")
    return {
        "used_usd": numeric_usd(used),
        "available_usd": numeric_usd(available),
        "invoice_billing_enabled": invoice,
    }


# Logical secret name -> local-cron env var (Cloud Run reads the file mount).
ORG_KEY_ENV = {
    "soniox_org": "FINOPS_SONIOX_ORG_KEY",
    "modulate_org": "FINOPS_MODULATE_ORG_KEY",
}


def optional_org_key(name: str) -> str | None:
    """The ORGANIZATION key by logical secret name; absent is None, never fatal."""
    if os.environ.get("FINOPS_AUTH") == "cloudrun":
        import cloudrun

        try:
            return cloudrun.secret(name)
        except (cloudrun.AuthError, OSError, UnicodeError):
            return None
    return os.environ.get(ORG_KEY_ENV.get(name, name.upper()), "").strip() or None


def fetch_balance(key: str) -> dict:
    request = urllib.request.Request(BALANCE_URL, headers={"Authorization": "Bearer " + key})
    try:
        with auth_http.open_authenticated(request, timeout=60) as response:
            return parse_balance(json.load(response))
    except auth_http.RedirectRefused:
        raise BalanceError("redirect_refused", "balance redirect refused") from None
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError("balance permission unavailable") from None
        raise BalanceError("http_error", "balance HTTP %d" % error.code, http_status=error.code) from None
    except (OSError, ValueError):
        raise BalanceError("transport_error", "balance transport/JSON failure") from None


def write_skip(path: pathlib.Path, reason: str, http_status: int | None = None) -> None:
    """Record a bounded skip reason in the artifact and on stderr.

    The reason is a fixed token from ``SKIP_REASONS``; the optional HTTP status is
    an integer. Neither the key, the request, nor any response body is written.
    """
    if reason not in SKIP_REASONS:
        raise ValueError("unbounded balance skip reason")
    document = {"status": "skipped", "reason": reason}
    if http_status is not None:
        document["http_status"] = http_status
    path.write_text(json.dumps(document))
    suffix = " http_status=%d" % http_status if http_status is not None else ""
    sys.stderr.write("WARNING: Soniox balance snapshot skipped: %s%s\n" % (reason, suffix))


def pull(raw: pathlib.Path, now: dt.datetime | None = None) -> None:
    """Snapshot the Soniox balance into the run's raw dir; skip, never fail."""
    path = raw / "vendor_balance_snapshot.json"
    path.unlink(missing_ok=True)  # a skipped refresh must not reuse a prior artifact
    key = optional_org_key("soniox_org")
    if not key:
        write_skip(path, "key_unavailable")
        return
    try:
        parsed = fetch_balance(key)
    except PermissionError:
        write_skip(path, "permission_unavailable")
        return
    except BalanceError as error:
        write_skip(path, error.reason, error.http_status)
        return
    ts = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    document = {"status": "ready", "vendor": VENDOR, "ts": ts, **parsed}
    path.write_text(json.dumps(document, indent=1))
    # Parsed numbers only; the key and the raw response are never logged.
    sys.stderr.write(
        "soniox balance @%s: used $%s available $%s (invoice billing %s)\n"
        % (ts, parsed["used_usd"], parsed["available_usd"], "on" if parsed["invoice_billing_enabled"] else "off")
    )


def main() -> None:
    """CLI entry the daily job runs (`pull_vendor_balance.py --raw DIR`).

    Without this the file defined `pull()` but nothing called it: the step ran,
    exited 0 and wrote no artifact, and the loader treats a missing artifact as
    "dark", so `vendor_balance_snapshot` was never created.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, help="the run's raw directory")
    args = ap.parse_args()
    pull(pathlib.Path(args.raw))


def _day(ts: str) -> str:
    return ts[:10]


def _difference(current: Decimal, previous: Decimal) -> Decimal:
    """Exact difference at 60 digits (the default 28 would round a 29-digit value)."""
    with localcontext() as ctx:
        ctx.prec = 60
        return current - previous


def _share(delta: Decimal, days: int) -> Decimal:
    """One day's share of a gap-spread delta, divided at 60 digits."""
    with localcontext() as ctx:
        ctx.prec = 60
        return delta / days


def daily_deltas(snapshots: list[dict]) -> list[dict]:
    """Per-UTC-day spend from consecutive snapshots, oldest first.

    Each interval (prev, cur] belongs to the UTC days strictly after
    ``day(prev)`` through ``day(cur)``: with daily runs that is exactly the
    current snapshot's day. A run gap spreads the delta evenly over the missed
    days and flags them ``gap_spread`` (an assumption, not a measurement). A
    lower ``used`` value is a recharge/reset: the day is unmeasured, ``usd`` is
    NULL with flag ``baseline_reset``, and the new value becomes the baseline
    for the next interval. Two snapshots inside one UTC day both attribute to
    that day. The first snapshot only establishes a baseline (no row).
    """
    ordered = sorted(snapshots, key=lambda s: s["ts"])
    rows: list[dict] = []
    for prev, cur in zip(ordered, ordered[1:]):
        used_prev, used_cur = usd(prev["used_usd"]), usd(cur["used_usd"])
        end_day = dt.date.fromisoformat(_day(cur["ts"]))
        if used_cur < used_prev:
            rows.append(
                {
                    "date": end_day.isoformat(),
                    "vendor": VENDOR,
                    "usd": None,
                    "flag": RESET_FLAG,
                    "interval_start": prev["ts"],
                    "interval_end": cur["ts"],
                }
            )
            continue
        delta = _difference(used_cur, used_prev)
        start = dt.date.fromisoformat(_day(prev["ts"])) + dt.timedelta(days=1)
        covered = [(start + dt.timedelta(days=i)).isoformat() for i in range((end_day - start).days + 1)]
        if not covered:  # two snapshots inside one UTC day: both spend to that day
            covered = [end_day.isoformat()]
        flag = GAP_FLAG if len(covered) > 1 else ""
        for day in covered:
            rows.append(
                {
                    "date": day,
                    "vendor": VENDOR,
                    "usd": numeric_usd(_share(delta, len(covered)), pad=True),
                    "flag": flag,
                    "interval_start": prev["ts"],
                    "interval_end": cur["ts"],
                }
            )
    return rows


if __name__ == "__main__":
    main()
