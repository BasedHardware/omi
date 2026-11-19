"""Run local cases. Zero exit means expectations held, including expected failures."""

import argparse
import asyncio
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('--case', type=Path, action='append', required=True)
    run.add_argument('--runtime-env', help='offline service[:prod|dev] runtime config (default env: prod)')
    run.add_argument('--output', type=Path, required=True)
    run.add_argument(
        '--privacy-ttl-override-s', type=int, help='test-only cache TTL monkeypatch; never changes the manifest bound'
    )
    from testing.replay_harness.decryption import add_arguments, file_options

    add_arguments(run)
    args = parser.parse_args(argv)
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.report import table, write_report

    try:
        items = asyncio.run(
            run_cases(
                args.case,
                privacy_ttl_override_s=args.privacy_ttl_override_s,
                runtime_env=args.runtime_env,
                **file_options(args),
            )
        )
    except Exception as error:
        print(f'Replay: ERROR ({type(error).__name__})')
        return 2
    write_report(items, args.output)
    print(table(items))
    return 0 if all(item['expectation_met'] for item in items) else 1
