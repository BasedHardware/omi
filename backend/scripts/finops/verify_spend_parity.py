#!/usr/bin/env python3
"""Read-only aggregate parity gate for the 2026-11-04 spend ledger.

Run with the ro-prod bot after the deploy owner backfills; --fixture replays an
assembled spend_daily.json offline. Does not create tables, load rows or read users.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess

EXPECTED = {
    'gcp_ex_vertex': 1680.85,
    'vertex': 328.68,
    'llm_openai': 295.68,
    'stt_soniox': 8.25,
    'stt_modulate_cash': 200.0,
    'saas_tooling': 750.50,
    'stripe_fees': 281.84,
    'infra_non_gcp': 3.41,
}
# The report's component figures sum to 3549.21, not its rounded 3543 headline.
EXPECTED_ALL_IN = sum(EXPECTED.values())
QUERY = """
SELECT line, source, status, in_all_in, in_margin_basis, inputs_settled,
       basis_class, basis_version, SUM(usd) AS usd, COUNT(*) AS row_count
FROM `based-hardware.omi_finops.spend_daily`
WHERE date = DATE('2026-11-04')
GROUP BY line, source, status, in_all_in, in_margin_basis, inputs_settled, basis_class, basis_version
ORDER BY line, source, status
"""


def verify(rows: list[dict]) -> dict:
    totals = {key: 0.0 for key in EXPECTED}
    seen = set()
    all_in = 0.0
    keys = set()
    for row in rows:
        if row.get('date', '2026-11-04') != '2026-11-04':
            continue
        line = row['line']
        key = (line, row['source'], row['status'])
        if key in keys or int(row.get('row_count', 1)) != 1:
            raise ValueError('duplicate ledger key: %s' % (key,))
        keys.add(key)
        if line == 'stt_modulate_modelled':
            raise ValueError('11-04 Modulate modelled must be absent, never zero')
        if row['status'] == 'provisional' or row['inputs_settled'] is not True:
            raise ValueError('unsettled row in settled parity day')
        if not row['basis_version']:
            raise ValueError('missing basis version')
        usd = float(row['usd'])
        if not math.isfinite(usd):
            raise ValueError('non-finite parity spend')
        group = (
            'gcp_ex_vertex'
            if line.startswith('gcp:')
            else 'vertex' if line in {'gcp_vertex_ai', 'gcp_vertex_provisioned_throughput', 'gcp_gemini_api'} else line
        )
        if group in totals:
            totals[group] += usd
            seen.add(group)
        if row['in_all_in']:
            all_in += usd
    for key, expected in EXPECTED.items():
        if key not in seen or abs(totals[key] - expected) > 1:
            raise ValueError(
                '%s: got %s, expected %.2f +/- 1' % (key, totals[key] if key in seen else 'absent', expected)
            )
    if abs(all_in - EXPECTED_ALL_IN) > 2:
        raise ValueError('all-in %.2f != %.2f +/- 2 (component sum)' % (all_in, EXPECTED_ALL_IN))
    return dict(totals, all_in=round(all_in, 6), stt_modulate_modelled_rows=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=pathlib.Path, help='assembled spend_daily.json; no credentials needed')
    parser.add_argument('--print-query', action='store_true')
    args = parser.parse_args()
    if args.print_query:
        print(QUERY)
        return
    if args.fixture:
        rows = json.loads(args.fixture.read_text())['rows']
    else:
        # Inspect the active CLI identity without activating credentials or using
        # gcpauth's legacy laptop environment loader.
        active = subprocess.run(
            ['gcloud', 'config', 'get-value', 'account'], capture_output=True, text=True, check=True
        )
        if active.stdout.strip() != 'read-only-bot-account@based-hardware.iam.gserviceaccount.com':
            raise SystemExit('source gcp-agent-env.sh ro-prod and select the read-only bot first')
        result = subprocess.run(
            [
                'bq',
                '--project_id=based-hardware',
                'query',
                '--use_legacy_sql=false',
                '--maximum_bytes_billed=104857600',
                '--max_rows=10000',
                '--format=json',
            ],
            input=QUERY,
            capture_output=True,
            text=True,
            check=True,
        )
        rows = json.loads(result.stdout)
    print(json.dumps(verify(rows), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
