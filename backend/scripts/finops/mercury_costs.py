"""Aggregate-only Mercury classification and SaaS amortization. No network or import IO."""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal
import json
import pathlib
import re

DAYS_PER_MONTH = Decimal('30.4375')
ANNUAL_REPEAT_MIN_DAYS = 304  # ~10 months: yearly spacing, not monthly or quarterly
ANNUAL_REPEAT_MAX_DAYS = 426  # ~14 months
ANNUAL_OUTLIER_MULTIPLE = Decimal('5')
ANNUAL_OUTLIER_MIN_OTHERS = 3  # a stable monthly median needs at least three other charges
# Cadence detection covers software spend; the SaaS run-rate line amortizes the
# `saas` subset only (stt/llm cash stays a cross-check line and never enters SaaS).
CADENCE_CATEGORIES = ('saas', 'stt_vendor', 'llm_vendor')
SAAS_RUN_RATE_CATEGORIES = ('saas',)
INFRA_RUN_RATE_CATEGORY = 'infra_non_gcp'
# Infra vendors whose Mercury cash is already counted on another wall line are
# kept out of the infra run-rate `amount_usd`: `stripe_fees` cash is the same
# money as the measured `stripe_fee_daily` line (Stripe balance transactions),
# so counting it there would double the fees line. Their own run rate rides
# along in `stripe_fees_usd` so the wall can count that cash on the infra line
# on a day the measured fee line is unavailable — never on both lines, never
# on neither. STT compute vendors never overlap this category (they map to
# `stt_vendor`; pinned by test).
INFRA_EXCLUDED_VENDORS = frozenset({'stripe_fees'})
CATEGORIES = {
    'saas',
    'stt_vendor',
    'llm_vendor',
    'infra_non_gcp',
    'gcp',
    'marketing',
    'fulfillment',
    'hardware_cogs',
    'travel_meals',
    'professional_services',
    'facilities',
    'other_opex',
    'excluded',
}
DEFAULT_MAX_UNCATEGORIZED_USD = Decimal('2500')
# Vendor labels for rule-classified aggregates; never a raw counterparty name.
SYNTHETIC_VENDORS = ('mercury_category', 'category_data', 'uncategorized_payment')
MAP_PATH = pathlib.Path(__file__).with_name('mercury_vendor_map.json')


class MercuryError(RuntimeError):
    """Bounded messages only: never include response data, identifiers or token."""


def normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def load_map(path: pathlib.Path = MAP_PATH) -> dict:
    config = json.loads(path.read_text())
    schema_version = config.get('schema_version')
    if schema_version not in (1, 2):
        raise MercuryError('unsupported Mercury vendor map')
    for key in ('mercury_category_rules', 'category_data_rules', 'uncategorized_kind_rules'):
        if key not in config and (schema_version == 1 or key == 'uncategorized_kind_rules'):
            config[key] = {}
        if not isinstance(config.get(key), dict):
            raise MercuryError('invalid Mercury vendor map')
    for key in ('mercury_category_rules', 'category_data_rules', 'uncategorized_kind_rules'):
        for name, category in config[key].items():
            if (
                not isinstance(name, str)
                or not name
                # Mercury kinds are camelCase identifiers; category names are normalized text.
                or (normalize(name) != name if key != 'uncategorized_kind_rules' else not name.isalnum())
                or not isinstance(category, str)
                or category not in CATEGORIES
            ):
                raise MercuryError('invalid Mercury category rule')
    try:
        max_uncategorized = Decimal(str(config.get('max_uncategorized_usd', DEFAULT_MAX_UNCATEGORIZED_USD)))
    except Exception:
        raise MercuryError('invalid Mercury vendor map') from None
    if not max_uncategorized.is_finite() or max_uncategorized < 0:
        raise MercuryError('invalid Mercury vendor map')
    aliases = {}
    for vendor, entry in config['vendors'].items():
        if (
            not re.fullmatch(r'[a-z][a-z0-9_]*', vendor)
            or not isinstance(entry, dict)
            or not isinstance(entry.get('category'), str)
            or entry['category'] not in CATEGORIES
            or not isinstance(entry.get('aliases'), list)
        ):
            raise MercuryError('invalid Mercury vendor map')
        if type(entry['annual']) is not bool or (entry['annual'] and entry['category'] != 'saas'):
            raise MercuryError('annual billing must be an explicit SaaS boolean')
        for alias in entry['aliases']:
            name = normalize(alias)
            if not name or (name in aliases and aliases[name] != vendor):
                raise MercuryError('empty or ambiguous Mercury vendor alias')
            aliases[name] = vendor
    return config


def classify(transaction: dict, config: dict) -> tuple[str, str]:
    # Read only classification fields. Never inspect notes, memos, bank/card/account details.
    category_data_name = normalize((transaction.get('categoryData') or {}).get('name') or '')
    merchant_category = normalize(transaction.get('mercuryCategory') or '')
    if transaction['kind'] in config['excluded_kinds'] or any(
        c in config['excluded_categories'] for c in (category_data_name, merchant_category)
    ):
        return 'excluded', 'excluded'
    name = normalize(transaction.get('counterpartyName') or '')
    matches = []
    for vendor, entry in config['vendors'].items():
        for alias in entry['aliases']:
            alias = normalize(alias)
            if name == alias or name.startswith(alias + ' '):
                matches.append((len(alias), vendor, entry['category']))
    if matches:
        _, vendor, category = max(matches)
        return ('excluded', 'excluded') if category == 'excluded' else (vendor, category)
    category = config.get('mercury_category_rules', {}).get(merchant_category)
    if category:
        return ('excluded', 'excluded') if category == 'excluded' else ('mercury_category', category)
    category = config.get('category_data_rules', {}).get(category_data_name)
    if category:
        return ('excluded', 'excluded') if category == 'excluded' else ('category_data', category)
    # Last resort by transfer kind: unlabelled wires/ACH are suppliers and contractors;
    # SaaS paid that way must be named in the vendor map.
    category = config.get('uncategorized_kind_rules', {}).get(transaction['kind'])
    if category:
        return ('excluded', 'excluded') if category == 'excluded' else ('uncategorized_payment', category)
    return 'unmapped', 'unmapped'


def money(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception:
        raise MercuryError('invalid Mercury amount') from None
    if not amount.is_finite():
        raise MercuryError('invalid Mercury amount')
    return amount


def days(start: str, end: str) -> list[str]:
    lo, hi = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if hi < lo:
        raise MercuryError('invalid Mercury date window')
    return [(lo + dt.timedelta(days=i)).isoformat() for i in range((hi - lo).days + 1)]


def aggregate_page(transactions: list[dict], config: dict, start: str, end: str, totals: dict, seen: set) -> None:
    for transaction in transactions:
        ident = transaction['id']
        if ident in seen:
            continue
        seen.add(ident)  # transient pagination dedupe only; never persisted
        if transaction['status'] != 'sent' or not transaction.get('postedAt'):
            continue
        timestamp = dt.datetime.fromisoformat(transaction['postedAt'].replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            raise MercuryError('Mercury posted date must include a timezone')
        day = timestamp.astimezone(dt.timezone.utc).date().isoformat()
        if not start <= day <= end:
            continue
        amount = money(transaction['amount'])  # account USD, NOT merchant's foreign minor units
        if amount >= 0:
            continue  # incoming payments, credits and incoming refunds are outside outgoing spend
        vendor, category = classify(transaction, config)
        # No raw counterparty, id, account or personal fields leave this projection.
        key = day, vendor, category
        total = totals.setdefault(key, [Decimal(0), 0])
        total[0] -= amount
        total[1] += 1


def aggregate_rows(totals: dict, start: str, end: str) -> list[dict]:
    # One zero-or-positive unmapped total per day is also the complete-fetch coverage marker.
    for day in days(start, end):
        totals.setdefault((day, 'unmapped', 'unmapped'), [Decimal(0), 0])
    return [
        {'date': day, 'vendor': vendor, 'category': category, 'amount_usd': str(amount), 'transaction_count': count}
        for (day, vendor, category), (amount, count) in sorted(totals.items())
    ]


def anniversary(day: dt.date, years: int) -> dt.date:
    year = day.year + years
    return day.replace(year=year, day=min(day.day, calendar.monthrange(year, day.month)[1]))


def detect_annual_charges(
    rows: list[dict], config: dict, categories: tuple[str, ...] = SAAS_RUN_RATE_CATEGORIES
) -> dict[tuple[str, str], str]:
    """Automatic yearly-cadence detection from charge history; no name inference.

    Returns (vendor, posted day) -> basis for every charge treated as an annual
    bill:
      override  manual `annual: true` correction in the vendor map
      repeat    about one charge per 12 months (gap to the previous or next
                charge within the ~10..14-month band)
      outlier   a charge at least ANNUAL_OUTLIER_MULTIPLE times that vendor's
                other-charge median (a yearly bill next to monthly ones)
      one_off   the vendor's only charge in the available history: ambiguous,
                amortized /12 for run-rate purposes and reported as estimated

    `annual: false` in the map means auto-detect (the default); only `true`
    forces. Synthetic rule-classified vendors (mercury_category, category_data)
    share one blended series behind the rule. Callers cadence-checking other
    software categories pass them via `categories` (CADENCE_CATEGORIES).
    """
    overrides = {v for v, entry in config['vendors'].items() if entry['annual']}
    series: dict[str, list[tuple[str, Decimal]]] = {}
    for row in rows:
        if row['category'] in categories:
            series.setdefault(row['vendor'], []).append((row['date'], money(row['amount_usd'])))
    annual: dict[tuple[str, str], str] = {}
    for vendor, charges in series.items():
        charges.sort()
        if vendor in overrides:
            annual.update(((vendor, day), 'override') for day, _ in charges)
            continue
        if len(charges) == 1:
            annual[(vendor, charges[0][0])] = 'one_off'
            continue
        posted = [dt.date.fromisoformat(day) for day, _ in charges]
        for i, (day, amount) in enumerate(charges):
            gaps = []
            if i:
                gaps.append((posted[i] - posted[i - 1]).days)
            if i + 1 < len(posted):
                gaps.append((posted[i + 1] - posted[i]).days)
            if any(ANNUAL_REPEAT_MIN_DAYS <= gap <= ANNUAL_REPEAT_MAX_DAYS for gap in gaps):
                annual[(vendor, day)] = 'repeat'
                continue
            others = sorted(value for j, (_, value) in enumerate(charges) if j != i)
            if len(others) >= ANNUAL_OUTLIER_MIN_OTHERS:
                median = others[len(others) // 2]
                if median > 0 and amount >= ANNUAL_OUTLIER_MULTIPLE * median:
                    annual[(vendor, day)] = 'outlier'
    return annual


def run_rate_rows(rows: list[dict], dates: list[str], config: dict, category: str) -> list[dict]:
    """Shared run rate for one category (SaaS today, non-GCP infra alongside):
    last 30 posted days / 30.4375 plus detected annual bills / 12 / 30.4375 for
    the following 12 calendar months (manual override, ~yearly repeat,
    monthly-median outlier, or an ambiguous one-off reported as estimated in
    `annual_estimated_usd`). Older annual aggregates survive refresh.
    `inputs_complete` covers the 30-posted-day cash window: all 30 days fetched
    and uncategorized spend at or below the map's threshold.
    `annual_history_complete` requires a full preceding 365 covered days and
    tolerates no above-threshold uncategorized year-window spend, regardless of
    configured annual vendors: an empty override map no longer implies
    complete (2026-10-23). While false, `annual_history_reason` names the
    blocking gate: `history_under_12_months` or `uncategorized_above_threshold`.
    The legacy unmapped_usd and unmapped_count output fields report
    uncategorized spend and transactions.
    """
    annual = detect_annual_charges(rows, config, categories=(category,))
    max_uncategorized = money(config.get('max_uncategorized_usd', DEFAULT_MAX_UNCATEGORIZED_USD))
    coverage = {r['date'] for r in rows if r['vendor'] == 'unmapped' and r['category'] == 'unmapped'}
    output = []
    for date in dates:
        day = dt.date.fromisoformat(date)
        lower = (day - dt.timedelta(days=29)).isoformat()
        year_lower = anniversary(day, -1)
        required_annual = {d for d in days(year_lower.isoformat(), date) if d > year_lower.isoformat()}
        annual_uncategorized = sum(
            (money(r['amount_usd']) for r in rows if r['category'] == 'unmapped' and r['date'] in required_annual),
            Decimal(0),
        )
        annual_unknown = annual_uncategorized > max_uncategorized
        history_covered = required_annual <= coverage
        annual_complete = history_covered and not annual_unknown
        if annual_complete:
            annual_reason = None
        elif not history_covered:
            annual_reason = 'history_under_12_months'
        else:
            annual_reason = 'uncategorized_above_threshold'
        monthly, annual_monthly, annual_estimated, uncategorized = Decimal(0), Decimal(0), Decimal(0), Decimal(0)
        unmapped_count = 0
        for row in rows:
            if row['date'] > date:
                continue
            value = money(row['amount_usd'])
            if value < 0:
                raise MercuryError('negative aggregate Mercury spend')
            if row['category'] == category:
                basis = annual.get((row['vendor'], row['date']))
                if basis:
                    if day < anniversary(dt.date.fromisoformat(row['date']), 1):
                        annual_monthly += value / 12
                        if basis == 'one_off':
                            annual_estimated += value / 12
                elif row['date'] >= lower:
                    monthly += value
            elif row['category'] == 'unmapped' and row['date'] >= lower:
                uncategorized += value
                unmapped_count += int(row['transaction_count'])
        covered = len(set(days(lower, date)) & coverage)
        output.append(
            {
                'date': date,
                'vendor': 'all',
                'category': category,
                'amount_usd': str(((monthly + annual_monthly) / DAYS_PER_MONTH).quantize(Decimal('0.000000001'))),
                'annual_monthly_usd': str(annual_monthly.quantize(Decimal('0.000000001'))),
                'annual_estimated_usd': str(annual_estimated.quantize(Decimal('0.000000001'))),
                'unmapped_usd': str(uncategorized),
                'unmapped_count': unmapped_count,
                'coverage_days': covered,
                'annual_history_complete': annual_complete,
                'annual_history_reason': annual_reason,
                'inputs_complete': covered == 30 and uncategorized <= max_uncategorized,
            }
        )
    return output


def saas_rows(rows: list[dict], dates: list[str], config: dict) -> list[dict]:
    """The SaaS run rate (`mercury_saas_daily`): the shared cadence treatment
    over the `saas` category only — stt/llm/infra cash never enters SaaS."""
    return run_rate_rows(rows, dates, config, SAAS_RUN_RATE_CATEGORIES[0])


def infra_rows(rows: list[dict], dates: list[str], config: dict) -> list[dict]:
    """The non-GCP infra run rate (`mercury_infra_non_gcp_daily`): Modal, AWS,
    Runpod and similar — cash that is not in GCP billing, so the wall's all-in
    software cost stack counts it here exactly once. Same cadence treatment as
    SaaS (yearly repeats and one-off charges amortize ÷12; a one-off stays an
    ambiguity reported as estimated). Vendors measured on their own wall line
    (the Stripe fee table) are kept out of `amount_usd` so no dollar is counted
    twice; their cash gets the same run-rate treatment on its own and is
    reported in `stripe_fees_usd`, so the wall can still count it on a day the
    measured fee line is dark. STT compute vendors live in `stt_vendor` and
    never enter this line."""
    kept = [row for row in rows if row['vendor'] not in INFRA_EXCLUDED_VENDORS]
    excluded = [row for row in rows if row['vendor'] in INFRA_EXCLUDED_VENDORS]
    output = run_rate_rows(kept, dates, config, INFRA_RUN_RATE_CATEGORY)
    # Cadence detection is per vendor, so splitting the series by vendor keeps
    # every charge's annual/monthly basis identical to the combined run.
    for row, fees in zip(output, run_rate_rows(excluded, dates, config, INFRA_RUN_RATE_CATEGORY)):
        row['stripe_fees_usd'] = fees['amount_usd']
    return output
