"""Run lifecycle pytest scenarios in the stack's allowlisted child environment."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from testing.lifecycle_sim.preflight import preflight
from testing.lifecycle_sim.pytest_entry import extra_test_module_path
from testing.hermetic_network import block_outbound_network
from testing.listen_pusher_stack.run import Stack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true')
    parser.add_argument('--runxfail', action='store_true', help='local red-reason proof; never used by CI')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--extra-test-module', action='append', type=extra_test_module_path, default=[])
    args = parser.parse_args()
    root = (args.state_dir or Path(tempfile.mkdtemp(prefix='omi-lifecycle-sim-'))).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        return run_scenarios(root, args)
    finally:
        print(f'lifecycle_sim added_wall_seconds={time.monotonic() - started:.3f}', flush=True)
        # Only a fresh automatic root is ours to delete, including on refusal.
        if args.state_dir is None and not args.keep:
            shutil.rmtree(root)


def run_scenarios(root, args):
    # Firebase sets demo project variables, but some local CLI versions leave
    # GOOGLE_CLOUD_PROJECT unset. Set only the absent value; reject a real one.
    ambient = dict(os.environ)
    ambient.setdefault('GOOGLE_CLOUD_PROJECT', 'demo-omi-listen-stack')
    preflight(root, environ=ambient)
    with block_outbound_network():
        stack = Stack(root)
    env = stack.env | {
        'BUCKET_BATCH_PIPELINE': 'lifecycle-batch-artifacts',
        'BATCH_PIPELINE_RECORD_PROTOCOL_READY': 'true',
        'BATCH_PIPELINE_ENABLED': 'true',
        'BATCH_PIPELINE_PERCENT': '100',
        'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED': 'true',
        'BATCH_PIPELINE_LIVE_RECORD_ENABLED': 'true',
        'BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED': 'false',
        # Same external model boundaries as pipeline_sim: synthetic samples
        # do not exercise paid-spend admission or a real local-VAD model.
        'STT_CAP_DISPATCH_ENFORCEMENT': 'false',
        'STT_CAP_OFFLINE_ENFORCEMENT': 'false',
        'BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED': 'false',
        'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED': 'false',
        'OMP_NUM_THREADS': '1',
        'OPENBLAS_NUM_THREADS': '1',
        'OPENAI_API_KEY': 'fake-key-for-hermetic-simulation',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'LIFECYCLE_SIM_STATE_DIR': str(root),
    }
    command = [
        str(Path(__file__).resolve().parents[2] / '.venv/bin/python'),
        '-m',
        'testing.lifecycle_sim.pytest_entry',
    ]
    if args.runxfail:
        command.append('--runxfail')
    for module in args.extra_test_module:
        command.extend(['--extra-test-module', module])
    try:
        result = subprocess.run(command, env=env, cwd=Path(__file__).resolve().parents[2], check=False)
        return result.returncode
    finally:
        stack.close()


if __name__ == '__main__':
    raise SystemExit(main())
