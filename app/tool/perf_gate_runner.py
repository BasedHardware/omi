#!/usr/bin/env python3
"""Bound the entire repeated gate to 9m30s, kill its process group on timeout."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

APP = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flutter_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        repeats = int(os.environ.get('PERF_GATE_REPEATS', '3'))
    except ValueError:
        parser.error('PERF_GATE_REPEATS must be 1..10')
    if not 1 <= repeats <= 10:
        parser.error('PERF_GATE_REPEATS must be 1..10')
    for key in os.environ:
        if key in {'HOME_ITEMS', 'DETAIL_MESSAGES', 'MEMORY_ITEMS', 'CHAT_HISTORY', 'LIVE_SEGMENTS'} or key in {'PERF_HOME_ITEMS', 'PERF_DETAIL_MESSAGES', 'PERF_MEMORY_ITEMS', 'PERF_CHAT_HISTORY', 'PERF_LIVE_SEGMENTS', 'PERF_SEMANTICS', 'PERF_BUDGET_FILE'}:
            parser.error(f'{key} cannot override an admission dataset/budget; use perf_harness.sh for exploration')
    if os.environ.get('PERF_GATE_MUTATION', '') not in {'', 'held_semantics'}:
        parser.error('unknown PERF_GATE_MUTATION; supported: held_semantics')
    artifact_root = APP.parent / '.agent-artifacts/perf-gate/runs'
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifacts = Path(os.environ.get('PERF_SCORECARD_DIR') or tempfile.mkdtemp(prefix='run-', dir=artifact_root))
    artifacts.mkdir(parents=True, exist_ok=True)
    if list(artifacts.glob('scorecard-*.json')):
        parser.error('PERF_SCORECARD_DIR must contain no previous scorecards; use a fresh directory')
    env = dict(os.environ, PERF_SCORECARD_DIR=str(artifacts.resolve()), PERF_BUDGET_FILE=str(APP / 'integration_test/perf/budgets.json'))
    deadline = time.monotonic() + 570
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=APP, text=True).strip()
    env['PERF_SOURCE_SHA'] = source_sha
    status = 0
    outcomes = []
    for run in range(1, repeats + 1):
        print(f'PERF GATE run {run}/{repeats}', flush=True)
        command = ['nice', '-n', '10', 'flutter', 'test', '--no-pub', '--concurrency=1', '--dart-define=OMI_APP_PROFILE=local_dev', '--dart-define=PERF_GATE_INNER_REPEATS=1', 'test/perf/production_shell_gate_test.dart', *args.flutter_args]
        started = time.monotonic()
        log_path = artifacts / f'run-{run}.log'
        log = log_path.open('w')
        print(f'Flutter output: {log_path}', flush=True)
        process = subprocess.Popen(command, cwd=APP, env=env, start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            print('PERF RED: gate exceeded 9m30s; partial evidence is not admission', flush=True)
            log.close()
            status = 1
            outcomes.append({'run': run, 'exit_code': 124, 'elapsed_seconds': time.monotonic() - started})
            break
        finally:
            log.close()
        if code:
            print(''.join(log_path.read_text(errors='replace').splitlines(keepends=True)[-70:]), flush=True)
        outcomes.append({'run': run, 'exit_code': code, 'elapsed_seconds': time.monotonic() - started})
        status = status or code
    (artifacts / 'run-status.json').write_text(json.dumps({'source_sha': source_sha, 'runs': outcomes}, indent=2) + '\n')
    report = subprocess.run([sys.executable, str(APP / 'tool/perf_gate_report.py'), str(artifacts), '--expected-runs', str(repeats)])
    print(f'PERF {"RED" if status or report.returncode else "GREEN"}: {artifacts}', flush=True)
    return bool(status or report.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
