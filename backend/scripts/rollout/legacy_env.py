# LIFECYCLE: permanent
"""Generate safe legacy retirement env sets; writes a file, never deploys.

Apply the generated env set to every admission revision before the separate
runtime mode/percent CAS. Keep the exclusion disabled on a mode-only rollback:
owners outside retirement still have legacy; accepted batch work must drain.
"""

import argparse
import json
from pathlib import Path

EXCLUSION = 'BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED'


def retirement_env_sets(sets: dict, modes: dict[str, str]) -> dict:
    """Copy sets and couple every draining/dark service to language admission."""
    if any(mode not in {'on', 'draining', 'dark'} for mode in modes.values()) or any(
        name not in sets for name in modes
    ):
        raise ValueError('invalid retirement set')
    result = {name: {service: dict(env) for service, env in services.items()} for name, services in sets.items()}
    for name, mode in modes.items():
        if mode == 'on':
            continue
        services = result[name]
        if not any(service.startswith('cloud_run/') for service in services):
            raise ValueError('retirement set has no admission services')
        for service, env in services.items():
            if service.startswith('cloud_run/'):
                env[EXCLUSION] = 'false'
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--set', action='append', required=True, metavar='NAME=MODE')
    args = parser.parse_args()
    modes = {}
    for spec in args.set:
        name, sep, mode = spec.partition('=')
        if not sep or name in modes:
            parser.error('each retirement set needs one NAME=MODE')
        modes[name] = mode
    result = retirement_env_sets(json.loads(args.input.read_text()), modes)
    args.output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
