"""Optional, company-level STT invoices. Never persist keys or request identifiers.

Soniox: https://soniox.com/docs/api-reference/other/get_usage_summary
Deepgram: https://developers.deepgram.com/reference/manage/billing/breakdown/get
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import auth_http


class InvoiceError(RuntimeError):
    """A sanitized provider/shape failure; never contains an HTTP body or credential."""


def usd(value) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise InvoiceError("invalid STT cost")
    return amount


def get_json(url: str, key: str, params: dict, scheme: str = "Bearer") -> dict:
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params), headers={"Authorization": scheme + " " + key}
    )
    try:
        with auth_http.open_authenticated(request, timeout=60) as response:
            return json.load(response, parse_float=Decimal)
    except auth_http.RedirectRefused:
        raise InvoiceError("STT usage redirect refused") from None
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError("STT usage permission unavailable") from None
        raise InvoiceError("STT usage HTTP %d" % error.code) from None
    except (OSError, ValueError):
        raise InvoiceError("STT usage transport/JSON failure") from None


def optional_key(provider: str) -> str | None:
    """Cloud Run uses existing file mounts; local execution uses explicit env only."""
    if os.environ.get("FINOPS_AUTH") == "cloudrun":
        import cloudrun

        try:
            return cloudrun.secret(provider)
        except (cloudrun.AuthError, OSError, UnicodeError):
            return None
    return os.environ.get(provider.upper() + "_API_KEY", "").strip() or None


def dates(start: str, end_excl: str) -> list[str]:
    lo, hi = dt.date.fromisoformat(start), dt.date.fromisoformat(end_excl)
    if hi <= lo:
        raise InvoiceError("STT window must contain at least one UTC day")
    return [(lo + dt.timedelta(days=i)).isoformat() for i in range((hi - lo).days)]


def soniox_costs(start: str, end_excl: str, key: str) -> dict[str, str]:
    """Summary is non-paginated; chunk windows at its 366 UTC-day limit.

    Sum STT model cost_usd (already includes input/output, API and playground).
    Never add total + model costs, or split cost fields, which would double-count.
    """
    days = dates(start, end_excl)
    costs = {day: Decimal(0) for day in days}
    for offset in range(0, len(days), 366):
        chunk = days[offset : offset + 366]
        stop = (dt.date.fromisoformat(chunk[-1]) + dt.timedelta(days=1)).isoformat()
        payload = get_json(
            "https://api.soniox.com/v1/usage/summary",
            key,
            {"start_time": chunk[0] + "T00:00:00Z", "end_time": stop + "T00:00:00Z"},
        )
        # Validate total's day coverage too: missing coverage is not measured zero.
        total = payload["total"]
        if set(total["days"]) != set(chunk) or len(total["days"]) != len(chunk):
            raise InvoiceError("Soniox summary has incomplete UTC-day coverage")
        for model in payload["models"]:
            if not model["model"].startswith("stt-"):
                continue
            model_days, amounts = model["days"], model["cost_usd"]
            if len(model_days) != len(amounts) or len(set(model_days)) != len(model_days):
                raise InvoiceError("Soniox summary day/cost arrays do not align")
            for day, amount in zip(model_days, amounts):
                if day not in chunk:
                    raise InvoiceError("Soniox summary day outside requested UTC window")
                costs[day] += usd(amount)
    return {day: str(amount) for day, amount in costs.items()}


def deepgram_costs(start: str, end_excl: str, key: str, project: str) -> dict[str, dict[str, str]]:
    """Daily billing dollars, with an explicit company project; never discover BYOK projects.

    Query through the following date and select the exact daily grouping. This
    handles an inclusive end without counting its next-day bucket twice.

    Known STT is streaming/sync nova, base, enhanced, or whisper. Any other
    positive dollars are unclassified. Counting them as STT would mix TTS and
    other products into the speech bill; dropping them and still calling the
    day measured would hide a new STT model. A day with unclassified dollars
    is incomplete and must not be published as measured.
    """
    costs = {}
    project = urllib.parse.quote(project, safe="")
    for day in dates(start, end_excl):
        next_day = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
        payload = get_json(
            "https://api.deepgram.com/v1/projects/%s/billing/breakdown" % project,
            key,
            {"start": day, "end": next_day, "deployment": "hosted", "grouping": "line_item"},
            scheme="Token",
        )
        if payload["resolution"] != {"units": "day", "amount": 1}:
            raise InvoiceError("Deepgram billing resolution is not daily")
        known = Decimal(0)
        unclassified = Decimal(0)
        for row in payload["results"]:
            group = row["grouping"]
            if group["start"] not in (day, next_day) or group["end"] != group["start"]:
                raise InvoiceError("Deepgram billing day outside requested UTC window")
            if group["start"] != day:
                continue
            amount = usd(row["dollars"])
            if amount == 0:
                continue
            mode, separator, model = group["line_item"].partition("::")
            recognized = (
                separator == "::"
                and mode in ("streaming", "sync")
                and model.startswith(("nova", "base", "enhanced", "whisper"))
            )
            if recognized:
                known += amount
            else:
                unclassified += amount
        costs[day] = {
            "usd": str(known),
            "unclassified_usd": str(unclassified),
            "status": "incomplete" if unclassified > 0 else "measured",
        }
    return costs


def pull(raw: pathlib.Path, start: str, end_excl: str) -> None:
    """Overwrite on every pull, including skip, so reused run dirs cannot leak old costs."""
    providers, skipped, incomplete = {}, [], {}
    for provider in ("soniox", "deepgram"):
        key = optional_key(provider)
        project = os.environ.get("FINOPS_DEEPGRAM_PROJECT_ID", "").strip()
        if not key or (provider == "deepgram" and not project):
            sys.stderr.write("WARNING: %s measured STT skipped: secret/config unavailable\n" % provider)
            skipped.append(provider)
            continue
        try:
            costs = (
                soniox_costs(start, end_excl, key)
                if provider == "soniox"
                else deepgram_costs(start, end_excl, key, project)
            )
        except PermissionError:
            sys.stderr.write("WARNING: %s measured STT skipped: usage API permission unavailable\n" % provider)
            skipped.append(provider)
            continue
        if provider == "deepgram" and any(row["status"] != "measured" for row in costs.values()):
            sys.stderr.write("WARNING: %s measured STT skipped: unclassified positive line items\n" % provider)
            incomplete[provider] = costs
            continue
        if provider == "deepgram":
            costs = {day: row["usd"] for day, row in costs.items()}
        providers[provider] = costs
    document = {"providers": providers, "skipped": skipped}
    if incomplete:
        document["incomplete"] = incomplete
    (raw / "stt_vendor_cost_daily.json").write_text(json.dumps(document, indent=1))
