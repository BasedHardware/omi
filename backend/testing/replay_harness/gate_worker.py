"""Private subprocess: fixed testing packages with product-only snapshot imports."""

import argparse
import asyncio
import importlib.util
import json
import signal
from pathlib import Path
import sys
from types import ModuleType


def configure_imports(backend):
    fixed = Path(__file__).resolve().parents[2]
    # `testing` is a namespace package. Pin its path explicitly so even snapshots
    # with their own __init__.py cannot replace the fixed adapter or test support.
    package = ModuleType('testing')
    package.__path__ = [str(fixed / 'testing')]
    sys.modules['testing'] = package
    spec = importlib.util.spec_from_file_location('tests', fixed / 'tests/__init__.py')
    package = importlib.util.module_from_spec(spec)
    sys.modules['tests'] = package
    spec.loader.exec_module(package)
    sys.path.insert(0, str(backend))


async def replay(request):
    from testing.replay_harness.runner import run_cases
    from testing.replay_harness.gate_resources import CURRENT_SCOPE

    results = []
    for case in request:
        outcomes = []
        for scope in case['scopes']:
            token = CURRENT_SCOPE.set(scope)
            try:
                item = (await run_cases([Path(case['path'])]))[0]
            finally:
                CURRENT_SCOPE.reset(token)
            # The runner's stage reports are sanitized. Its metadata fields are
            # free text and its item id is private, so neither is persisted here.
            outcomes.append(
                {
                    key: item[key]
                    for key in ('stages', 'furthest_stage', 'stop_reason', 'duration_ms', 'verdict', 'expectation_met')
                }
            )
        results.append(outcomes)
    return results


async def cooperative_replay(request):
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        return await replay(request)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    configure_imports(args.backend)
    results = asyncio.run(cooperative_replay(json.load(sys.stdin)))
    from testing.replay_harness.gate_resources import private_write

    private_write(args.output, json.dumps(results).encode())


if __name__ == '__main__':
    main()
