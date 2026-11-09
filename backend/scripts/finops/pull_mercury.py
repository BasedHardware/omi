#!/usr/bin/env python3
"""Read-only Mercury posted spend; project responses to safe aggregates in memory.

Never persist a raw response or print an HTTP body, token, counterparty or cursor.
API: https://docs.mercury.com/reference/listtransactions

FINOPS_MERCURY_BACKFILL_DAYS=N (91..400) widens one run to N posted days for the
one-time annual-history backfill; see backfill_start and the finops README.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import auth_http
from mercury_costs import MercuryError, aggregate_page, aggregate_rows, days, load_map

FILENAME = 'mercury_vendor_spend_daily.json'
BACKFILL_LIMIT_DAYS = 400  # matches the loader's aggregate-window cap; 13 months fits


class NoRedirect(auth_http.NoRedirect):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MercuryError('Mercury redirect refused')


def get_page(params: dict, token: str) -> dict:
    request = urllib.request.Request(
        'https://api.mercury.com/api/v1/transactions?' + urllib.parse.urlencode(params),
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'},
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
            return json.load(response, parse_float=str)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError('Mercury read permission unavailable') from None
        raise MercuryError('Mercury HTTP %d' % error.code) from None
    except (OSError, ValueError):
        raise MercuryError('Mercury transport/JSON failure') from None


def optional_token() -> str | None:
    if os.environ.get('FINOPS_AUTH') == 'cloudrun':
        import cloudrun

        try:
            return cloudrun.secret('mercury')
        except (cloudrun.AuthError, OSError, UnicodeError):
            return None
    return os.environ.get('FINOPS_MERCURY_READONLY_TOKEN', '').strip() or None


def fetch_aggregates(start: str, end: str, token: str, config: dict) -> list[dict]:
    end_excl = (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat()
    params = {
        'status': 'sent',
        'postedStart': start + 'T00:00:00Z',
        'postedEnd': end_excl + 'T00:00:00Z',
        'order': 'asc',
        'limit': 1000,
    }
    totals, seen, cursors = {}, set(), set()
    while True:
        payload = get_page(params, token)
        try:
            transactions = payload['transactions']
            aggregate_page(transactions, config, start, end, totals, seen)
            more = payload['page'].get('nextPage')
            if not more:
                break
            if not transactions:
                raise MercuryError('Mercury pagination did not advance')
            # Follow Mercury's official Go SDK CursorIDTransactions.GetNextPage:
            # it passes the last item's ID as the exclusive start_after cursor.
            # Use the last actual transaction id rather than guessing whether
            # page.nextPage points at a last-seen or first-unseen transaction.
            cursor = transactions[-1]['id']
            if cursor in cursors:
                raise MercuryError('Mercury pagination did not advance')
            cursors.add(cursor)
            params['start_after'] = cursor
        except MercuryError:
            raise
        except Exception:
            raise MercuryError('invalid Mercury transaction response') from None
    return aggregate_rows(totals, start, end)


def backfill_start(end: str) -> str | None:
    """One-time annual-history backfill: FINOPS_MERCURY_BACKFILL_DAYS=N widens a
    single job run to N posted days ending at `--end` (13 months needs ~400).
    The env route exists because the Cloud Run job invokes this pull with fixed
    arguments; `--backfill-from` serves explicit local/one-off runs. Re-running
    over the same window re-derives the same (date, vendor) aggregates — the
    loader replaces, never appends — so the backfill is idempotent."""
    raw = os.environ.get('FINOPS_MERCURY_BACKFILL_DAYS', '').strip()
    if not raw:
        return None
    if not raw.isdigit():
        raise MercuryError('FINOPS_MERCURY_BACKFILL_DAYS must be a whole number of days')
    span = int(raw)
    if not 90 < span <= BACKFILL_LIMIT_DAYS:
        raise MercuryError('FINOPS_MERCURY_BACKFILL_DAYS must be 91..%d' % BACKFILL_LIMIT_DAYS)
    return (dt.date.fromisoformat(end) - dt.timedelta(days=span - 1)).isoformat()


def pull(raw: pathlib.Path, end: str, backfill_from: str | None = None) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    path = raw / FILENAME
    path.unlink(missing_ok=True)  # a skipped/failed refresh cannot reuse a prior ready artifact
    start = backfill_from or backfill_start(end) or (dt.date.fromisoformat(end) - dt.timedelta(days=89)).isoformat()
    if len(days(start, end)) > 400:
        raise MercuryError('Mercury explicit backfill is limited to 400 UTC days')
    reason = None
    if os.environ.get('FINOPS_MERCURY_ENABLED', '').lower() != 'true':
        reason = 'disabled'
    else:
        token = optional_token()
        if not token:
            reason = 'secret_unavailable'
        else:
            config = load_map()
            try:
                rows = fetch_aggregates(start, end, token, config)
            except PermissionError:
                reason = 'permission_unavailable'
    if reason:
        sys.stderr.write('WARNING: Mercury vendor spend skipped: %s\n' % reason)
        path.write_text(json.dumps({'status': 'skipped', 'reason': reason}))
        return
    path.write_text(json.dumps({'status': 'ready', 'start': start, 'end': end, 'rows': rows}, indent=1))
    sys.stderr.write('Mercury aggregate window %s..%s complete\n' % (start, end))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', required=True)
    parser.add_argument('--end', required=True, help='last posted UTC day, inclusive; normal pull refreshes 90 days')
    parser.add_argument('--backfill-from', help='explicit initial history for annual bills, at most 400 days')
    args = parser.parse_args()
    try:
        pull(pathlib.Path(args.raw), args.end, args.backfill_from)
    except MercuryError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
