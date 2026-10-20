"""Aggregate-only Mercury classification and SaaS amortization. No network or import IO."""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal
import json
import pathlib
import re

DAYS_PER_MONTH = Decimal('30.4375')
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


def saas_rows(rows: list[dict], dates: list[str], config: dict) -> list[dict]:
    """Normal SaaS: last 30 posted days / 30.4375. Annual: bill / 12 / 30.4375
    for the following 12 calendar months. Older annual aggregates survive refresh.
    A complete line requires all 30 days, uncategorized spend at or below the map's
    threshold, and (when annual vendors exist) a full preceding year's coverage
    with uncategorized spend at or below that threshold. The legacy unmapped_usd
    and unmapped_count output fields now report uncategorized spend and transactions.
    """
    annual = {v for v, entry in config['vendors'].items() if entry['annual']}
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
        annual_complete = not annual or (required_annual <= coverage and not annual_unknown)
        monthly, annual_monthly, uncategorized = Decimal(0), Decimal(0), Decimal(0)
        unmapped_count = 0
        for row in rows:
            if row['date'] > date:
                continue
            value = money(row['amount_usd'])
            if value < 0:
                raise MercuryError('negative aggregate Mercury spend')
            if row['category'] == 'saas':
                if row['vendor'] in annual:
                    if day < anniversary(dt.date.fromisoformat(row['date']), 1):
                        annual_monthly += value / 12
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
                'category': 'saas',
                'amount_usd': str(((monthly + annual_monthly) / DAYS_PER_MONTH).quantize(Decimal('0.000000001'))),
                'annual_monthly_usd': str(annual_monthly.quantize(Decimal('0.000000001'))),
                'unmapped_usd': str(uncategorized),
                'unmapped_count': unmapped_count,
                'coverage_days': covered,
                'annual_history_complete': annual_complete,
                'inputs_complete': covered == 30 and annual_complete and uncategorized <= max_uncategorized,
            }
        )
    return output
