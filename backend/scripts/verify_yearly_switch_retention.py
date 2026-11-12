#!/usr/bin/env python3
"""Read an authorized aggregate receipt; never contact a service or write data.

Receipts are evidence supplied by an authorized verifier, not authenticated by
this parser. Local fixtures prove the gate, never deployment or causal lift.
No raw receipt content, IDs, small cells or recoverable complements are printed.
"""

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import subprocess

EXPERIMENT = 'EXP-006-yearly-switch-retention'


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def interval(value):
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(type(x) in (int, float) and math.isfinite(x) for x in value)
        and value[0] <= value[1]
    )


def verify(receipt, *, source_revision, now=None, render_digest=None, copy_digest=None):
    """Return only allowlisted protected fields. All gates are required."""
    now = now or datetime.now(timezone.utc)
    waiting = []
    report = {}

    def require(condition, name):
        if not condition:
            waiting.append(name)

    try:
        packet = Path(__file__).resolve().parents[2] / '.agent-artifacts/ui-evidence/yearly-retention'
        if render_digest is None:
            manifest_bytes = (packet / 'render-manifest.json').read_bytes()
            manifest = json.loads(manifest_bytes)
            require(bool(manifest['renders']), 'render packet')
            for render in manifest['renders']:
                name = render['file']
                if Path(name).name != name or not name.endswith('.png'):
                    raise ValueError('invalid render path')
                require(
                    hashlib.sha256((packet / name).read_bytes()).hexdigest() == render['sha256'], 'render integrity'
                )
            render_digest = hashlib.sha256(manifest_bytes).hexdigest()
        if copy_digest is None:
            copy_digest = hashlib.sha256((packet / 'copy.json').read_bytes()).hexdigest()
        require(receipt['experiment'] == EXPERIMENT and receipt['unit'] == 'uid', 'UID experiment')
        require(
            receipt['authority'] == 'authorized_aggregate_verifier' and bool(receipt['evidence_ref']),
            'receipt authority',
        )
        generated = timestamp(receipt['generated_at'])
        require(now - timedelta(hours=24) <= generated <= now, 'fresh receipt')
        release = receipt['release']
        require(
            release['backend_commit'] == source_revision == release['client_commit']
            and bool(release['client_build'])
            and bool(release['serving_evidence_ref']),
            'exact backend/client serving release',
        )
        approval = receipt['approval']
        require(
            approval['approved_by'] == 'David Zhang'
            and approval['source_commit'] == source_revision
            and approval['issue_comment_ref']
            and approval['render_sha256'] == render_digest
            and approval['copy_sha256'] == copy_digest,
            'exact render/copy approval',
        )
        gates = receipt['gates']
        require(
            all(
                gates[k] is True
                for k in ('enabled', 'rollout_authorized', 'stable_uid_holdout', 'once_only', 'non_overlap')
            )
            and bool(gates['evidence_ref']),
            'flags/admission/holdout evidence',
        )
        start = timestamp(receipt['cohort_start'])
        end = timestamp(receipt['cohort_end'])
        observed = timestamp(receipt['observed_through'])
        require(timestamp(release['deployed_at']) <= start <= end <= observed <= generated, 'cohort/release chronology')
        require(end + timedelta(days=60) <= observed, 'day-60 maturity')
        measurement = receipt['measurement']
        require(
            measurement['revenue_basis'] == 'realized_net_revenue_per_enrolled_uid'
            and measurement['refunds'] == 'included'
            and measurement['currency'] == 'USD'
            and measurement['fx_policy'] == 'exclude_non_usd'
            and bool(measurement['billing_linkage_evidence_ref'])
            and bool(measurement['uncertainty_method']),
            'arm-linked revenue definition/authority',
        )
        arms = receipt['arms']
        require(set(arms) == {'control', 'treatment'}, 'both arms')
        for arm in ('control', 'treatment'):
            values = arms[arm]
            n = values['enrolled']
            require(type(n) is int and n >= 10, 'protected enrollment')
            counts = [values[k] for k in ('linked', 'missing_linkage', 'ambiguous_linkage', 'non_usd', 'censored')]
            require(all(type(x) is int and x >= 0 for x in counts) and sum(counts) == n, 'coverage accounting')
            # Complete by-arm outcomes are needed for final acceptance. Missing
            # linkage remains unknown: never put excluded UIDs in a zero bucket.
            require(counts == [n, 0, 0, 0, 0], 'complete authorized outcome linkage')
            protected = type(n) is int and n >= 10
            for metric in ('take_up', 'effective_ends_30', 'effective_ends_60'):
                value = values[metric]
                count = value['count']
                cell_safe = type(count) is int and type(n) is int and 10 <= count <= n - 10
                require(cell_safe, f'protected {metric}')
                ci = value['ci95']
                require(interval(ci) and 0 <= ci[0] <= count / n <= ci[1] <= 1, f'{metric} uncertainty')
                protected = protected and cell_safe
            require(
                values['effective_ends_30']['count'] <= values['effective_ends_60']['count'], 'cumulative paid ends'
            )
            require(
                values['effective_ends_60']['count'] - values['effective_ends_30']['count'] >= 10,
                'protected day-31-to-60 recoverable complement',
            )
            revenue = values['revenue_per_uid']
            mean = revenue['mean_usd']
            require(
                type(mean) in (int, float)
                and math.isfinite(mean)
                and interval(revenue['ci95'])
                and revenue['ci95'][0] <= mean <= revenue['ci95'][1],
                'revenue uncertainty',
            )
            # Suppress the entire table if any cell/complement is unsafe or any
            # coverage/maturity gate fails. No partial totals permit recovery.
            if protected:
                report[arm] = {'enrolled': n}
                for key in ('take_up', 'effective_ends_30', 'effective_ends_60'):
                    report[arm][key] = {'count': values[key]['count'], 'ci95': values[key]['ci95']}
                report[arm]['revenue_per_uid'] = {'mean_usd': mean, 'ci95': revenue['ci95']}
        # Inter-arm uncertainty is supplied by the authorized aggregate analysis,
        # including UID linkage sensitivity; the parser does not invent intervals.
        require(
            all(
                interval(receipt['comparison_ci95'][key])
                for key in (
                    'take_up_difference',
                    'effective_ends_30_difference',
                    'effective_ends_60_difference',
                    'revenue_per_uid_difference',
                )
            ),
            'between-arm uncertainty',
        )
    except (OSError, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        waiting.append('missing or malformed authorized receipt fields')
    if waiting:
        return {'status': 'WAITING', 'waiting': sorted(set(waiting)), 'metrics': 'SUPPRESSED_OR_UNAVAILABLE'}
    return {
        'status': 'LIVE_MATURE_EVIDENCE',
        'unit': 'uid',
        'arms': report,
        'comparison_ci95': {
            key: receipt['comparison_ci95'][key]
            for key in (
                'take_up_difference',
                'effective_ends_30_difference',
                'effective_ends_60_difference',
                'revenue_per_uid_difference',
            )
        },
        'limitations': 'UID randomization; linked accounts/duplicate customers may contaminate arms. '
        'Annual upfront collections are not recurring-revenue lift or observed annual renewal retention.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read-only', action='store_true', required=True)
    parser.add_argument('--require-live', action='store_true', required=True)
    parser.add_argument('--require-mature-holdout', action='store_true', required=True)
    parser.add_argument('--receipt', type=Path, default=os.getenv('YEARLY_SWITCH_RETENTION_RECEIPT'))
    args = parser.parse_args()
    if args.receipt is None:
        print(
            json.dumps(
                {
                    'status': 'WAITING',
                    'waiting': ['authorized serving, approval and mature arm-linked aggregate receipt'],
                }
            )
        )
        return 2
    try:
        revision = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2], text=True
        ).strip()
        dirty = subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=Path(__file__).resolve().parents[2], text=True
        ).strip()
        receipt = json.loads(args.receipt.read_text())
        result = (
            {'status': 'WAITING', 'waiting': ['clean exact source checkout']}
            if dirty
            else verify(receipt, source_revision=revision)
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        result = {'status': 'WAITING', 'waiting': ['readable authorized aggregate receipt']}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result['status'] == 'LIVE_MATURE_EVIDENCE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
