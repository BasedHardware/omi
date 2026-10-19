# LIFECYCLE: permanent
"""Staging-only rehearsal wrapper around the fleet gate (contract (g) M2 rehearsal).

Usage: inject_gate.py --plan PLAN.json -- <real gate cmd...>   (the controller appends since/min/minutes/percent)

PLAN.json: [{"percent": 25, "line": "GATE_FAIL http_5xx_regression"},
            {"percent": 50, "line": "GATE_FAIL obligation_over_15m"}]
Each entry fires once, on the first gate call at that percent, and is marked used in the plan file.
Other calls run the real gate unchanged. ramp_controller refuses this wrapper on --env prod.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

EXIT = {'GATE_PASS': 0, 'GATE_FAIL': 1, 'GATE_NO_WORK': 2, 'GATE_PENDING': 3}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--' not in argv:
        print('GATE_FAIL invalid_arguments')
        return 1
    split = argv.index('--')
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    args = parser.parse_args(argv[:split])
    gate = argv[split + 1 :]
    if len(gate) < 5:
        print('GATE_FAIL invalid_arguments')
        return 1
    percent = float(gate[-1])
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    for entry in plan:
        if not entry.get('used') and float(entry['percent']) == percent:
            entry['used'] = True
            args.plan.write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
            line = str(entry['line'])
            print(json.dumps({'injected': True, 'percent': percent}))
            print(line)
            return EXIT.get(line.split(' ', 1)[0], 1)
    return subprocess.run(gate, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
