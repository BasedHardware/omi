#!/usr/bin/env python3
"""Collect CV1 .24 software baseline evidence and optionally verify a simulator receipt."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

from cv1_release import SIM_SCENARIOS, sim_catalog, validate_sim_report

REPO = Path(__file__).resolve().parents[4]
BASELINE_SHA = '2fd0a9d94f238b6c338d6c67aec1e77f783159d9'  # Omi_CV1_v3.0.24
WORKFLOW = '.github/workflows/firmware_release.yml'
BODY_SCRIPT = 'omi/firmware/scripts/ci/make-release-body.sh'
HOST_RUNNER = 'omi/firmware/omi/tests/run_host_regressions.py'


def git(*args):
    return subprocess.check_output(['git', '-C', REPO, *args], text=True, timeout=20)


def replay_offer(workflow, root, temp, minimum):
    """Execute only the checked-in release-body step with local inputs."""
    step = workflow.split('      - name: Generate release body\n', 1)[1].split('\n      - name:', 1)[0]
    command = textwrap.dedent(step.split('        run: |\n', 1)[1])
    temp.mkdir()
    env = dict(
        PATH=os.environ['PATH'],
        RUNNER_TEMP=str(temp),
        GITHUB_OUTPUT=str(temp / 'github-output'),
        TITLE='Omi CV1 Firmware v3.0.24',
        VER='3.0.24',
        MIN_FW=minimum,
    )
    result = subprocess.run(['bash', '-e', '-c', command], cwd=root, env=env, capture_output=True, text=True, timeout=10)
    body = temp / 'cv1-body.md'
    metadata = body.read_text().splitlines() if body.exists() else []
    return {
        'exit_code': result.returncode,
        'body_written': body.exists(),
        'version_emitted': 'release_firmware_version:3.0.24' in metadata,
        'minimums': [line.partition(':')[2] for line in metadata if line.startswith('minimum_firmware_required:')],
        'output_written': (temp / 'github-output').exists(),
        'required_minimum_error': 'minimum_firmware_required is required' in result.stdout + result.stderr,
    }


def offer_check(temp):
    root = temp / 'public-source'
    script = root / BODY_SCRIPT
    script.parent.mkdir(parents=True)
    script.write_text(git('show', f'{BASELINE_SHA}:{BODY_SCRIPT}'))
    baseline = replay_offer(git('show', f'{BASELINE_SHA}:{WORKFLOW}'), root, temp / 'public', '')
    workflow = (REPO / WORKFLOW).read_text()
    blank = replay_offer(workflow, REPO, temp / 'candidate-blank', '')
    supplied = replay_offer(workflow, REPO, temp / 'candidate-supplied', '3.0.6')
    return {
        'evidence': 'offline release workflow replay',
        'baseline_reproduced': baseline['exit_code'] == 0 and baseline['version_emitted']
        and baseline['output_written'] and not baseline['minimums'],
        'candidate_passed': blank['exit_code'] == 1 and blank['required_minimum_error']
        and not blank['body_written'] and not blank['output_written']
        and supplied['exit_code'] == 0 and supplied['version_emitted']
        and supplied['output_written'] and supplied['minimums'] == ['3.0.6'],
        'baseline': baseline,
        'candidate': {'blank_minimum': blank, 'explicit_minimum': supplied},
    }


def host_checks(temp):
    build = temp / 'host'
    proc = subprocess.run(
        [sys.executable, str(REPO / HOST_RUNNER), '--cv1-baseline', '--output', str(build)],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )
    report = json.loads((build / 'results.json').read_text())
    if proc.returncode:
        last = report['commands'][-1] if report['commands'] else {}
        detail = last.get('stderr') or report.get('error') or proc.stderr
        raise RuntimeError(f'Host regression suite exited {proc.returncode}: {detail.strip()}')
    if report['state'] != 'passed' or report['cv1_baseline_sha'] != BASELINE_SHA or not report['source_unchanged']:
        raise RuntimeError('Host report failed or did not prove the pinned public baseline')
    commands = {row['name']: row for row in report['commands']}

    def observed(name):
        row = commands[name]
        return row['exit_code'] == row['expected_exit_code'] == 0, row['stdout'].strip().splitlines()

    checks = {}
    for check_id, name in (('ble-retry-churn', 'conn-params'), ('recording-polls-stalled-drain', 'storage')):
        baseline_ok, baseline = observed(name + '-baseline')
        candidate_ok, candidate = observed(name)
        checks[check_id] = {
            'evidence': 'host production C with API shims',
            'baseline_reproduced': baseline_ok,
            'candidate_passed': candidate_ok,
            'baseline': baseline,
            'candidate': candidate,
        }
    return checks


def simulator_receipt(path, sha, dirty, version):
    if path is None:
        return {'verdict': 'pending'}
    if dirty:
        raise ValueError('Simulator receipt requires a clean firmware and release workflow checkout')
    raw = path.read_bytes()
    report = json.loads(raw)
    validate_sim_report(report, sha, version, sim_catalog(REPO / SIM_SCENARIOS))
    if report['fuzz']['seeds'] < 40:
        raise ValueError('G0 requires at least 40 simulator fuzz seeds')
    return {
        'verdict': 'pass',
        'sha256': hashlib.sha256(raw).hexdigest(),
        'scenarios': report['counts']['passed'],
        'fuzz_seeds': report['fuzz']['seeds'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new JSON receipt path')
    parser.add_argument('--sim-report', type=Path, help='optional full simulator receipt for this exact clean SHA')
    args = parser.parse_args()
    sha = git('rev-parse', 'HEAD').strip()
    dirty = bool(git('status', '--porcelain', '--', 'omi/firmware', WORKFLOW).strip())
    version = next(
        line.split('=', 1)[1].strip('"')
        for line in (REPO / 'omi/firmware/omi/omi.conf').read_text().splitlines()
        if line.startswith('CONFIG_BT_DIS_FW_REV_STR=')
    )
    report = {
        'kind': 'omi-cv1-g0-report',
        'schema_version': 1,
        'baseline_sha': BASELINE_SHA,
        'source_sha': sha + ('-dirty' if dirty else ''),
        'firmware_version': version,
        'software_verdict': 'fail',
        'g0_verdict': 'blocked',
        'checks': {},
        'stock_loader_ota_rejection': {'verdict': 'pending', 'evidence': 'requires stock rejection and qualified control'},
        'simulator': {'verdict': 'pending'},
        'errors': [],
    }
    with args.output.open('x', encoding='utf-8') as output, tempfile.TemporaryDirectory(prefix='cv1-g0-') as tmp:
        for name, check in (
            ('host probes', lambda: host_checks(Path(tmp))),
            ('workflow replay', lambda: {'missing-update-offer': offer_check(Path(tmp))}),
        ):
            try:
                report['checks'].update(check())
            except (OSError, RuntimeError, KeyError, ValueError, IndexError, subprocess.SubprocessError) as error:
                report['errors'].append(f'{name}: {error}')
        checks = report['checks'].values()
        software_ok = len(checks) == 3 and all(row['baseline_reproduced'] and row['candidate_passed'] for row in checks)
        report['software_verdict'] = 'pass' if software_ok else 'fail'
        try:
            report['simulator'] = simulator_receipt(args.sim_report, sha, dirty, version)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report['simulator'] = {'verdict': 'fail'}
            report['errors'].append(f'simulator receipt: {error}')
        json.dump(report, output, indent=2)
        output.write('\n')
    return 2 if software_ok and not report['errors'] else 1


if __name__ == '__main__':
    sys.exit(main())
