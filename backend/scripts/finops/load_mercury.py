"""Load only Mercury aggregates through the existing FinOps BigQuery helpers."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

from mercury_costs import (
    CATEGORIES,
    SYNTHETIC_VENDORS,
    MercuryError,
    anniversary,
    days,
    infra_rows,
    load_map,
    money,
    saas_rows,
)

META = [('run_id', 'STRING'), ('computed_at', 'TIMESTAMP')]
RUN_RATE_COLUMNS = [
    ('date', 'DATE'),
    ('vendor', 'STRING'),
    ('category', 'STRING'),
    ('amount_usd', 'NUMERIC'),
    ('annual_monthly_usd', 'NUMERIC'),
    ('annual_estimated_usd', 'NUMERIC'),
    ('unmapped_usd', 'NUMERIC'),
    ('unmapped_count', 'INT64'),
    ('coverage_days', 'INT64'),
    ('annual_history_complete', 'BOOL'),
    ('annual_history_reason', 'STRING'),
    ('inputs_complete', 'BOOL'),
]
# The infra run rate also carries the excluded fee-vendor cash
# (mercury_costs.INFRA_EXCLUDED_VENDORS) as its own run rate: the wall counts
# it on the infra line only on days the measured Stripe fee line is unavailable.
INFRA_RUN_RATE_COLUMNS = RUN_RATE_COLUMNS + [('stripe_fees_usd', 'NUMERIC')]
SCHEMAS = {
    'mercury_vendor_spend_daily': [
        ('date', 'DATE'),
        ('vendor', 'STRING'),
        ('category', 'STRING'),
        ('amount_usd', 'NUMERIC'),
        ('transaction_count', 'INT64'),
    ]
    + META,
    'mercury_saas_daily': RUN_RATE_COLUMNS + META,
    # Non-GCP infra run rate (Modal, AWS, Runpod, …): same cadence treatment as
    # SaaS, over the infra_non_gcp category; dark until the first load after
    # this table ships, so the wall treats it as an unavailable line, never a guess.
    # Every field `infra_rows` emits has a column here (pinned by test), so
    # `ensure_table` creates the table whole and `load_replace` drops nothing.
    'mercury_infra_non_gcp_daily': INFRA_RUN_RATE_COLUMNS + META,
}
CLUSTER = {name: ['category', 'vendor'] for name in SCHEMAS}


def ready_snapshot(raw: pathlib.Path, config: dict) -> dict | None:
    path = raw / 'mercury_vendor_spend_daily.json'
    if not path.exists():
        return None
    snapshot = json.loads(path.read_text())
    if snapshot.get('status') == 'skipped':
        return None
    if set(snapshot) != {'status', 'start', 'end', 'rows'} or snapshot['status'] != 'ready':
        raise MercuryError('invalid Mercury aggregate artifact')
    window = set(days(snapshot['start'], snapshot['end']))
    if len(window) > 400:
        raise MercuryError('invalid Mercury aggregate window')
    keys, coverage = set(), set()
    for row in snapshot['rows']:
        if set(row) != {'date', 'vendor', 'category', 'amount_usd', 'transaction_count'}:
            raise MercuryError('Mercury artifact must contain aggregates only')
        vendor, category = row['vendor'], row['category']
        entry = config['vendors'].get(vendor)
        valid = (
            (entry and category == entry['category'] and category != 'excluded')
            or (vendor == category and category in ('unmapped', 'excluded'))
            or (vendor in SYNTHETIC_VENDORS and category in CATEGORIES and category != 'excluded')
        )
        if not valid or row['date'] not in window:
            raise MercuryError('unknown Mercury aggregate key')
        key = row['date'], vendor, category
        if key in keys or money(row['amount_usd']) < 0:
            raise MercuryError('duplicate or negative Mercury aggregate')
        if type(row['transaction_count']) is not int or row['transaction_count'] < 0:
            raise MercuryError('invalid Mercury aggregate count')
        keys.add(key)
        if vendor == 'unmapped':
            coverage.add(row['date'])
    if coverage != window:
        raise MercuryError('incomplete Mercury aggregate window')
    return snapshot


def load(raw: pathlib.Path, run_id: str, computed_at: str, ensure_table, load_replace, bq) -> dict:
    config = load_map()
    snapshot = ready_snapshot(raw, config)
    if snapshot is None:
        return {}  # dark: no table creation, reads or writes when skipped/unavailable
    start, end = snapshot['start'], snapshot['end']
    ensure_table('mercury_vendor_spend_daily')
    # Keep prior aggregate history so known annual bills survive the 90-day refresh.
    # Exclude every refreshed date from history: a correction/reversal must replace it.
    prior_start = anniversary(dt.date.fromisoformat(start), -1).isoformat()
    history = json.loads(
        bq(
            [
                'query',
                '--use_legacy_sql=false',
                '--format=json',
                '--maximum_bytes_billed=104857600',
            ],
            stdin=(
                "SELECT FORMAT_DATE('%%F', date) AS date, vendor, category, "
                "CAST(amount_usd AS STRING) AS amount_usd, transaction_count "
                "FROM `based-hardware.omi_finops.mercury_vendor_spend_daily` "
                "WHERE date >= DATE('%s') AND date < DATE('%s')" % (prior_start, start)
            ),
        )
    )
    # Do not log history; it contains only the same aggregate projection.
    for row in history:
        if row['category'] not in CATEGORIES | {'unmapped'}:
            raise MercuryError('invalid stored Mercury aggregate category')
    window = days(start, end)
    cost_rows = saas_rows(history + snapshot['rows'], window, config)
    infra_cost_rows = infra_rows(history + snapshot['rows'], window, config)
    metadata = {'run_id': run_id, 'computed_at': computed_at}
    vendors = [dict(row, **metadata) for row in snapshot['rows']]
    costs = [dict(row, **metadata) for row in cost_rows]
    infra_costs = [dict(row, **metadata) for row in infra_cost_rows]
    ensure_table('mercury_saas_daily')
    ensure_table('mercury_infra_non_gcp_daily')
    return {
        'mercury_vendor_spend_daily': load_replace('mercury_vendor_spend_daily', vendors, window),
        'mercury_saas_daily': load_replace('mercury_saas_daily', costs, window),
        'mercury_infra_non_gcp_daily': load_replace('mercury_infra_non_gcp_daily', infra_costs, window),
    }
