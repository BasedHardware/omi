"""``python -m testing.pipeline_sim run <scenario> [--seed N] [--json] [--param key=value ...]``.

``python -m testing.pipeline_sim projection-drain [--mode M ...] [--rows N] [--owners N]``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from testing.hermetic_network import block_outbound_network
from testing.pipeline_sim import projection_drain
from testing.pipeline_sim.scenarios import SCENARIOS, run


def _value(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_sim')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='list scenarios')
    runner = commands.add_parser('run', help='run one scenario and print its gate sample')
    runner.add_argument('scenario', choices=sorted(SCENARIOS))
    runner.add_argument('--seed', type=int, default=1)
    runner.add_argument('--json', action='store_true', help='print the full sample as JSON')
    runner.add_argument('--param', action='append', default=[], help='scenario parameter key=value (JSON value)')
    drain = commands.add_parser('projection-drain', help='owner-chain projection rows/min per mode')
    drain.add_argument('--mode', action='append', choices=sorted(projection_drain.MODES))
    drain.add_argument('--rows', type=int, default=1200)
    drain.add_argument('--owners', type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == 'list':
        for name, factory in sorted(SCENARIOS.items()):
            print(f'{name}: {(factory.__doc__ or "").strip().splitlines()[0]}')
        return 0
    if args.command == 'projection-drain':
        with block_outbound_network():
            for mode in args.mode or list(projection_drain.MODES):
                result = projection_drain.run(mode, rows=args.rows, owners=args.owners)
                print(
                    f"{mode}: rows/owner={result['rows_per_owner']} owners={result['owners']} "
                    f"rows_per_min min={result['rows_per_min_min']} max={result['rows_per_min_max']} "
                    f"all_persisted={result['all_persisted']} chain_order={result['chain_order']} "
                    f"check_transactions={result['check_transactions']} result_loads={result['result_loads']}"
                )
        return 0
    params = dict(item.split('=', 1) for item in args.param)
    logging.disable(logging.CRITICAL)  # product code logs every transition; the sample is the output
    with block_outbound_network():
        sample = run(args.scenario, args.seed, **{key: _value(value) for key, value in params.items()})
    if args.json:
        json.dump(sample, sys.stdout, indent=2, sort_keys=True, default=str)
        print()
    else:
        sim = sample['sim']
        print(f"{args.scenario} seed={args.seed}: {sample['verdict']}")
        for key in (
            'completion_rate',
            'accept_to_projection_p50_seconds',
            'accept_to_projection_p95_seconds',
            'paid_fallback_calls',
            'lost_fire_and_forget_units',
        ):
            print(f'  {key}={sim[key]}')
        for key in (
            'terminal_unrecovered_speech_fraction',
            'quarantine_projection_cohort_count',
            'quarantine_projection_p95_seconds',
            'first_summary_max_overdue_seconds',
            'first_summary_breach_rate',
            'recovery_obligations_over_15m',
            'projection_obligations_over_15m',
        ):
            print(f'  {key}={sample[key]}')
    return sample['verdict_code']
