"""Test-only adapter injection into the canonical MUX harness lifecycle.

Source pipeline/env.sh and hold that lane's actual MUX_OWNER lease first.
This changes only the backend import target, preserving canonical ports,
process supervision, emulators, offline providers and real emulator JWT auth.
"""

import os
from pathlib import Path
import runpy
import sys


def main():
    owner, lane = os.getenv('MUX_OWNER'), os.getenv('MUX_LANE')
    home = Path.home() / 'mobile-ux-agent'
    if not owner or lane not in ('sim', 'sim.2'):
        raise RuntimeError('MUX_OWNER and canonical sim|sim.2 lane required')
    lease = home / 'state' / 'locks' / lane / 'lease'
    actual = dict(line.split('=', 1) for line in lease.read_text().splitlines())['owner']
    if actual not in (owner, owner + '-backend'):
        raise RuntimeError('calling owner does not hold canonical lane')
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo / 'scripts' / 'dev-harness'))
    from dev_harness import cli

    original = cli._start_process

    def start(cfg, name, command, **kwargs):
        if name == 'backend':
            command = [*command]
            index = command.index('main:app')
            command[index] = 'testing.referral_campaign.server:create_app'
            command.insert(index + 1, '--factory')
        return original(cfg, name, command, **kwargs)

    cli._start_process = start
    runpy.run_path(str(home / 'pipeline' / 'lib' / 'harness_up.py'), run_name='__main__')


if __name__ == '__main__':
    main()
