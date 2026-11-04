"""Gate a candidate against a last-good ref with one fixed local replay adapter."""

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

# Direct execution with -I must still load this tree's adapter, never a snapshot's.
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from testing.replay_snapshot import backend_snapshot, resolve_refs
from testing.replay_harness.manifest import load_case
from testing.replay_harness.gate_resources import cleanup_scopes, prepare_output, private_write
from testing.replay_harness.report import StageResult, item_report


def digest_files(paths):
    """Length-frame relative names and bytes so paths/order/concatenation cannot alias."""
    digest = hashlib.sha256()
    for name, path in sorted(paths):
        for value in (name.encode(), path.read_bytes()):
            digest.update(len(value).to_bytes(8, 'big'))
            digest.update(value)
    return digest.hexdigest()


def case_digest(case):
    root = case.directory
    paths = [(name, root / name) for name in ('manifest.json', 'corpus.json')]
    for name in ('blobs', 'cassettes'):
        paths.extend((p.relative_to(root).as_posix(), p) for p in (root / name).rglob('*') if p.is_file())
    return digest_files(paths)


def adapter_digest():
    backend = Path(__file__).resolve().parents[2]
    # Include fixed test infrastructure as well as drivers and the snapshot helper.
    paths = [(p.relative_to(backend).as_posix(), p) for p in (backend / 'testing').rglob('*.py')]
    fixture = backend / 'tests/unit/fixtures/strict_firestore_transaction.py'
    paths.append((fixture.relative_to(backend).as_posix(), fixture))
    return digest_files(paths)


def case_id(case, key):
    if case.manifest.tier == 'C' and not key:
        raise ValueError('Tier C identity requires a random run key')
    value = case.manifest.id.encode()
    return (
        hmac.new(key, value, hashlib.sha256).hexdigest()
        if case.manifest.tier == 'C'
        else hashlib.sha256(value).hexdigest()
    )


def repeats_for(case, repeats):
    admission = case.corpus.get('admission', {})
    # Detect by stress shape, not manifest id (captured cases may rename it).
    return repeats if admission.get('drainers', 1) > 1 else 1


def stop(outcome):
    return next((s for s in outcome['stages'] if s['status'] != 'pass'), None)


def outcome_key(outcome):
    stopped = stop(outcome)
    if stopped:
        return stopped['status'], stopped['stage'], stopped.get('reason')
    return 'pass', tuple(s['stage'] for s in outcome['stages']), None


def majority(outcomes):
    key, count = Counter(outcome_key(o) for o in outcomes).most_common(1)[0]
    if count * 2 <= len(outcomes):
        return None
    return next(o for o in outcomes if outcome_key(o) == key)


def classify(baseline, candidate, manifest):
    """Use product outcomes, never whether an incident expectation still holds on REF."""
    before, after = stop(baseline), stop(candidate)
    if before:
        expected = manifest.stages.get(before['stage'], {})
        reproduced = (
            'expect_stop_stage' in expected
            and item_report(replace(manifest, stages={before['stage']: expected}), [StageResult(**before)])[
                'expectation_met'
            ]
        )
        passed_stage = any(s['stage'] == before['stage'] and s['status'] == 'pass' for s in candidate['stages'])
        if reproduced and passed_stage:
            return 'fixed'
    if before is None:
        return 'regressed' if after else 'unchanged_pass'
    if after is None or outcome_key(baseline) != outcome_key(candidate):
        return 'changed_reason'
    return 'still_failing'


def exception_sites(outcomes):
    return {
        (row['exception_type'], row.get('site'))
        for outcome in outcomes
        for stage in outcome['stages']
        for row in [stage, *stage.get('observations', [])]
        if row.get('exception_type')
    }


def compare(cases, reports, key=b'', repeats=3):
    rows = []
    baseline_exceptions, candidate_exceptions = set(), set()
    for case, before, after in zip(cases, reports['baseline'], reports['candidate'], strict=True):
        baseline_exceptions.update(exception_sites(before))
        candidate_exceptions.update(exception_sites(after))
        baseline, candidate = majority(before), majority(after)
        incomplete = any(
            not o['stages'] or any(s['status'] not in ('pass', 'stopped') for s in o['stages']) for o in before + after
        )
        rows.append(
            {
                'case_id': case_id(case, key),
                'identity_scheme': 'hmac-sha256' if case.manifest.tier == 'C' else 'sha256',
                **({'corpus_sha256': case_digest(case)} if case.manifest.tier == 'S' else {}),
                'fixed_by_ref': bool((case.manifest.gate or {}).get('fixed_by_ref')),
                'classification': (
                    classify(baseline, candidate, case.manifest) if baseline and candidate else 'changed_reason'
                ),
                'inconclusive': baseline is None or candidate is None or incomplete,
                'baseline': {'outcomes': before, 'majority': baseline},
                'candidate': {'outcomes': after, 'majority': candidate},
            }
        )
    new_sites = [
        {'exception_type': kind, 'site': site}
        for kind, site in sorted(
            candidate_exceptions - baseline_exceptions, key=lambda value: (value[0], value[1] or '')
        )
    ]
    passed = (
        bool(rows)
        and not new_sites
        and all(
            not row['inconclusive']
            and row['classification'] not in ('regressed', 'changed_reason')
            and (not row['fixed_by_ref'] or row['classification'] == 'fixed')
            for row in rows
        )
    )
    diagnostic = any(repeats_for(case, repeats) < 3 and repeats_for(case, 3) > 1 for case in cases)
    verdict = 'FAIL'
    if passed:
        verdict = (
            'DIAGNOSTIC' if diagnostic else 'PASS' if any(row['fixed_by_ref'] for row in rows) else 'REGRESSION_ONLY'
        )
    return {'cases': rows, 'new_exception_sites': new_sites, 'verdict': verdict}


def markdown(result):
    rows = [
        f"Replay gate: **{result['verdict']}**",
        '',
        f"BASE `{result['refs']['baseline']}` → REF `{result['refs']['candidate']}`",
        '',
        '| case identity (prefix) | target | classification | BASE / REF runs | inconclusive |',
        '|---|---|---|---:|---|',
    ]
    for row in result['cases']:
        rows.append(
            f"| {row['case_id'][:12]} | {row['fixed_by_ref']} | {row['classification']} | "
            f"{len(row['baseline']['outcomes'])} / {len(row['candidate']['outcomes'])} | {row['inconclusive']} |"
        )
    rows.extend(['', f"New exception class/sites: {len(result['new_exception_sites'])}"])
    return '\n'.join(rows) + '\n'


def run_side(backend, cases, repeats, timeout=1800, grace=10, worker=None):
    worker = worker or Path(__file__).with_name('gate_worker.py')
    environment = {
        key: os.environ[key] for key in ('PATH', 'TMPDIR', 'SYSTEMROOT', 'FIRESTORE_EMULATOR_HOST') if key in os.environ
    }
    report = backend.parent / 'outcomes.json'
    scratch = Path('/Volumes/Ephemeral/scratch')
    with tempfile.TemporaryDirectory(
        prefix='replay-gate-resources-', dir=scratch if scratch.is_dir() else None
    ) as directory:
        root = Path(directory)
        request = []
        for index, case in enumerate(cases):
            scopes = []
            for repeat in range(repeats_for(case, repeats)):
                scope_root = root / f'{index}-{repeat}'
                scope_root.mkdir(mode=0o700)
                scopes.append({'root': str(scope_root), 'token': uuid.uuid4().hex[:24]})
            request.append({'path': str(case.directory), 'scopes': scopes})
        process = subprocess.Popen(
            [sys.executable, '-I', str(worker), '--backend', str(backend), '--output', str(report)],
            stdin=subprocess.PIPE,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.communicate(json.dumps(request).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            cleanup_scopes(root, environment.get('FIRESTORE_EMULATOR_HOST', ''))
            raise
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            cleanup_scopes(root, environment.get('FIRESTORE_EMULATOR_HOST', ''))
            raise
        if process.returncode:
            cleanup_scopes(root, environment.get('FIRESTORE_EMULATOR_HOST', ''))
            raise RuntimeError('replay worker failed')
    return json.loads(report.read_text())


def gate(repo, directories, ref, base, output, repeats=3, regression_only=False, worker_timeout=1800):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be positive')
    if worker_timeout <= 0:
        raise ValueError('worker timeout must be positive')
    cases = [load_case(p) for p in directories]
    if not cases or len({c.manifest.id for c in cases}) != len(cases):
        raise ValueError('cases must be nonempty and unique')
    # Keep case content outside OUTPUT, including accidental placement by a caller.
    prepare_output(output)
    output = output.resolve()
    if any(output == c.directory or output in c.directory.parents or c.directory in output.parents for c in cases):
        raise ValueError('output must be separate from case directories')
    refs = resolve_refs(repo, ref, base)
    identity = adapter_digest()
    digests = [case_digest(c) for c in cases]
    key = os.urandom(32)
    private_write(output / 'identity.key', key)
    for name in ('gate.json', 'gate.md'):
        (output / name).unlink(missing_ok=True)
    reports = {}
    for label in ('baseline', 'candidate'):
        with backend_snapshot(repo, refs[label], output, label) as backend:
            reports[label] = run_side(backend, cases, repeats, worker_timeout)
    if identity != adapter_digest() or digests != [case_digest(c) for c in cases]:
        raise ValueError('adapter or case changed during replay')
    result = {
        'schema_version': 1,
        'refs': refs,
        'adapter_sha256': identity,
        'repeats': repeats,
        **compare(cases, reports, key, repeats),
    }
    private_write(output / 'gate.json', (json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
    private_write(output / 'gate.md', markdown(result).encode())
    print(f"Replay gate: {result['verdict']} ({len(cases)} cases)")
    return exit_code(result['verdict'], regression_only)


def exit_code(verdict, regression_only=False):
    return 0 if verdict == 'PASS' or (regression_only and verdict == 'REGRESSION_ONLY') else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--case', type=Path, action='append', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3, help='runs per side for load-sensitive cases (default: 3)')
    parser.add_argument(
        '--regression-only', action='store_true', help='allow REGRESSION_ONLY to exit zero; never a ship PASS'
    )
    parser.add_argument(
        '--worker-timeout', type=float, default=1800, help='seconds per worker side before cooperative cleanup'
    )
    args = parser.parse_args(argv)
    try:
        return gate(
            args.repo,
            args.case,
            args.ref,
            args.base,
            args.output,
            args.repeats,
            args.regression_only,
            args.worker_timeout,
        )
    except Exception as error:
        # No paths, identifiers, manifest values, command lines or raw tracebacks.
        print(f'Replay gate: ERROR ({type(error).__name__})')
        return 2


if __name__ == '__main__':
    sys.exit(main())
