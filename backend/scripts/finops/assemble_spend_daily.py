#!/usr/bin/env python3
"""Assemble settled company spend from the daily job's aggregate artifacts. No network."""

from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import json
import math
import pathlib
import re

from mercury_costs import days, infra_rows, load_map, spend_saas_rows
import load_mercury

HERE = pathlib.Path(__file__).resolve().parent
BASIS = HERE / 'spend_basis.json'


def read(raw: pathlib.Path, filename: str, default=None):
    path = raw / filename
    return json.loads(path.read_text()) if path.exists() else default


def amount(value) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('non-finite spend')
    return result


def assemble(
    raw: pathlib.Path,
    out: pathlib.Path,
    start: str,
    end: str,
    settled_through: str,
    basis: dict | None = None,
    mercury_rates: dict | None = None,
) -> dict:
    basis = basis or json.loads(BASIS.read_text())
    dates = [day for day in days(start, end) if day <= settled_through]
    rows, detail = [], []
    scopes = defaultdict(set)

    def add(day, line, source, status, usd, note='', **flags):
        if day > settled_through:
            return
        rule = basis['lines'][line if line in basis['lines'] else 'gcp:*']
        rows.append(
            dict(
                date=day,
                line=line,
                source=source,
                status=status,
                usd=amount(usd),
                **{k: rule[k] for k in ('in_all_in', 'in_margin_basis', 'basis_class')},
                basis_version=basis['version'],
                note=note,
                inputs_settled=True,
            )
        )
        rows[-1].update(flags)
        scopes[source].add(day)

    # Full service/SKU export, never the truncated top-resource extract.
    gcp = read(raw, 'gcp_day_service_sku.json')
    if gcp is not None:
        scopes['billing_export'].update(dates)
        totals = defaultdict(float)
        sku_totals = defaultdict(float)
        for r in gcp:
            day = r['usage_day']
            if day not in dates:
                continue
            dev = r['project_id'] != 'based-hardware'
            service, sku = r['service'], r['sku']
            if dev:
                line = 'gcp_dev'
            elif service == 'Vertex AI':
                line = (
                    'gcp_vertex_provisioned_throughput'
                    if sku.startswith('Vertex AI: Provisioned Throughput')
                    else 'gcp_vertex_ai'
                )
            elif service == 'Gemini API':
                line = 'gcp_gemini_api'
            else:
                line = 'gcp:' + re.sub(r'[^a-z0-9]+', '_', service.lower()).strip('_')
            totals[day, line] += amount(r['net'])
            sku_totals[day, 'dev' if dev else 'prod', service, sku] += amount(r['net'])
        for (day, line), usd in sorted(totals.items()):
            note = (
                'unsplit service total; fixed fallback from basis; see SKU detail'
                if line.startswith('gcp:')
                else 'prepaid PT fee excluded from margin basis' if line.endswith('throughput') else ''
            )
            add(day, line, 'billing_export', 'billed', usd, note)
        detail = [
            dict(date=d, project_class=p, service=s, sku=k, usd_net=v) for (d, p, s, k), v in sorted(sku_totals.items())
        ]

    for filename, line, source, label in (
        ('openai_cost_daily.json', 'llm_openai', 'openai_admin_api', 'end_time_iso'),
        ('anthropic_cost_daily.json', 'llm_anthropic_api', 'anthropic_admin_api', 'starting_at'),
    ):
        invoice = read(raw, filename)
        if invoice is None or invoice.get('status') == 'skipped':
            continue
        totals = defaultdict(float)
        if label == 'starting_at':
            totals.update({day: 0.0 for day in dates})  # successful zero cost_report
        for bucket in invoice['data']:
            day = bucket[label][:10]
            if label == 'end_time_iso':
                day = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
            if day in dates:
                totals[day] += sum(
                    amount(x['amount']['value'] if label == 'end_time_iso' else x['amount_usd'])
                    for x in bucket['results']
                )
        for day, usd in sorted(totals.items()):
            add(day, line, source, 'measured', usd)

    stt = read(raw, 'stt_vendor_cost_daily.json', {})
    for vendor, source in (('soniox', 'soniox_usage_api'), ('deepgram', 'deepgram_billing_api')):
        for day, usd in stt.get('providers', {}).get(vendor, {}).items():
            if day in dates:
                add(day, 'stt_' + vendor, source, 'measured', usd)

    modelled = read(raw, 'stt_modulate_modelled_daily.json', {})
    modelled_days = set()
    # A successful modelled artifact may have holes. Replace the run window,
    # including holes, so a vanished series never leaves a stale estimate behind.
    scopes['prometheus'].update(dates)
    if modelled.get('status') == 'ready':
        for r in modelled['rows']:
            if r['date'] in dates:
                add(r['date'], 'stt_modulate_modelled', 'prometheus', 'estimate', r['usd'])
                modelled_days.add(r['date'])

    config = load_map()
    cash = load_mercury.ready_snapshot(raw, config)
    if cash is not None:
        window = [d for d in days(cash['start'], cash['end']) if d <= settled_through]
        scopes['mercury'].update(window)
        by_vendor = defaultdict(float)
        for r in cash['rows']:
            by_vendor[r['date'], r['vendor']] += amount(r['amount_usd'])
        # The loader supplies the exact rates it just computed with retained annual
        # history. Offline assembly derives the same rates from the raw window alone.
        rates = mercury_rates or {
            'saas': spend_saas_rows(cash['rows'], window, config),
            'infra': infra_rows(cash['rows'], window, config),
        }
        for kind, line in (('saas', 'saas_tooling'), ('infra', 'infra_non_gcp')):
            for r in rates[kind]:
                if r['date'] not in window or r['coverage_days'] < 30 or not r['inputs_complete']:
                    continue  # no partial-window zero or undercount dressed as measured
                note = 'Mercury run rate; annual_history_complete=%s; inputs_complete=%s' % (
                    r['annual_history_complete'],
                    r['inputs_complete'],
                )
                add(r['date'], line, 'mercury', 'measured', r['amount_usd'], note)
        for day in window:
            for vendor, line in (
                ('modulate', 'stt_modulate_cash'),
                ('anthropic', 'saas_anthropic_seats'),
                ('openrouter', 'openrouter'),
                ('xai', 'xai'),
                ('replicate', 'replicate'),
            ):
                usd = by_vendor[day, vendor]  # ready aggregate window proves a real cash zero
                add(
                    day,
                    line,
                    'mercury',
                    'measured',
                    usd,
                    'cash',
                    **({'in_all_in': day not in modelled_days} if vendor == 'modulate' else {}),
                )
            seven = days((dt.date.fromisoformat(day) - dt.timedelta(days=6)).isoformat(), day)
            if seven[0] >= cash['start']:
                avg = sum(by_vendor[d, 'anthropic'] for d in seven) / 7
                add(
                    day,
                    'agent_tooling_claude_code',
                    'mercury',
                    'estimate',
                    min(basis['adjustments']['agent_tooling_excluded']['cap_usd_day'], avg),
                    'Mercury Anthropic 7d average, capped',
                )
        # Mercury refresh is wider than the modelled artifact. For older cash days
        # the loader resolves all-in preference against existing settled model rows.

    fees = read(raw, 'stripe_fee_daily.json', {})
    book = read(raw, 'stripe_plan_mrr.json')
    if fees.get('status') == 'ready':
        by_day = {r['date']: r for r in fees['rows']}
        for day in dates:
            if day not in by_day:
                continue
            add(day, 'stripe_fees', 'stripe_api', 'measured', by_day[day]['fee_usd'])
            seven = days((dt.date.fromisoformat(day) - dt.timedelta(days=6)).isoformat(), day)
            if book is None or not set(seven) <= by_day.keys():
                continue
            volume = sum(amount(by_day[d]['volume_usd']) for d in seven)
            if volume > 0:
                rate = sum(amount(by_day[d]['fee_usd']) for d in seven) / volume
                mrr = sum(amount(p['mrr_usd']) for p in book['by_plan'] if not p['plan'].startswith('unmapped:'))
                add(
                    day,
                    'stripe_fees_subscription',
                    'stripe_api',
                    'estimate',
                    rate * mrr / 30.44,
                    '7d fee/volume x snapshot MRR/30.44; snapshot is not historical MRR',
                )
    for day in dates:
        add(
            day,
            'pinecone',
            'rate_card',
            'estimate',
            basis['adjustments']['pinecone_included']['usd_day'],
            'measured serving run-rate from margin basis',
        )

    keys = [(r['date'], r['line'], r['source'], r['status']) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate spend key')
    artifact = dict(
        rows=sorted(rows, key=lambda r: (r['date'], r['source'], r['line'], r['status'])),
        scopes={s: sorted(ds) for s, ds in sorted(scopes.items()) if ds},
        frontier=settled_through,
        modelled_window=dates,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / 'spend_daily.json').write_text(json.dumps(artifact, indent=1) + '\n')
    (out / 'spend_daily_gcp_sku.json').write_text(json.dumps(detail, indent=1) + '\n')
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=pathlib.Path)
    parser.add_argument('out', type=pathlib.Path)
    parser.add_argument('start')
    parser.add_argument('end')
    parser.add_argument('--settled-through', required=True)
    args = parser.parse_args()
    assemble(args.raw, args.out, args.start, args.end, args.settled_through)


if __name__ == '__main__':
    main()
