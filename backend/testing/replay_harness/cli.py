"""Run local cases. Zero exit means expectations held, including expected failures."""

import argparse
import asyncio
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--case', type=Path, action='append', required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import table, write_report

    items = asyncio.run(run_cases(args.case))
    write_report(items, args.output)
    print(table(items))
    return 0 if all(item['expectation_met'] for item in items) else 1
