"""Gate a candidate against a last-good ref with one fixed local replay adapter."""

import argparse
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
from testing.replay_harness.decryption import add_arguments, file_options, load_decryption


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


def unanimous(outcomes, key=outcome_key):
    if not outcomes or any(key(o) != key(outcomes[0]) for o in outcomes[1:]):
        return None
    return outcomes[0]


def reproduces_expected_stop(outcome, manifest):
    stopped = stop(outcome)
    if stopped is None:
        return False
    expected = manifest.stages.get(stopped['stage'], {})
    return (
        'expect_stop_stage' in expected
        and item_report(replace(manifest, stages={stopped['stage']: expected}), [StageResult(**stopped)])[
            'expectation_met'
        ]
    )


def classify(baseline, candidate, manifest):
    """Use product outcomes, never whether an incident expectation still holds on REF."""
    before, after = stop(baseline), stop(candidate)
    if before:
        passed_stage = any(s['stage'] == before['stage'] and s['status'] == 'pass' for s in candidate['stages'])
        if reproduces_expected_stop(baseline, manifest) and passed_stage:
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


def baseline_unanimous(case, outcomes):
    # The reason matcher also examines sanitized observations. Every BASE run
    # must agree on reproduction, not only on its primary reason.
    return unanimous(
        outcomes, key=lambda outcome: (outcome_key(outcome), reproduces_expected_stop(outcome, case.manifest))
    )


def needs_retry(case, before, after):
    return repeats_for(case, 3) > 1 and baseline_unanimous(case, before) is not None and unanimous(after) is None


def compare(cases, reports, key=b'', repeats=3):
    rows = []
    baseline_exceptions, candidate_exceptions = set(), set()
    for index, (case, before, after) in enumerate(zip(cases, reports['baseline'], reports['candidate'], strict=True)):
        retry = reports.get('candidate_retry', {}).get(index, [])
        baseline_exceptions.update(exception_sites(before))
        candidate_exceptions.update(exception_sites(after + retry))
        baseline = baseline_unanimous(case, before)
        candidate = unanimous(after)
        asymmetric = needs_retry(case, before, after)
        if asymmetric and retry:
            confirmed = baseline_unanimous(case, retry)
            # Only an equal confirmation can clear initial REF instability.
            # Neither mixed batch can establish a fix or regression.
            if (
                confirmed is not None
                and outcome_key(confirmed) == outcome_key(baseline)
                and (
                    reproduces_expected_stop(confirmed, case.manifest)
                    == reproduces_expected_stop(baseline, case.manifest)
                )
            ):
                candidate = confirmed
        load_sensitive = repeats_for(case, 3) > 1
        target = bool((case.manifest.gate or {}).get('fixed_by_ref'))
        expected_runs = repeats_for(case, repeats)
        incomplete = (
            len(before) != expected_runs
            or len(after) != expected_runs
            or (bool(retry) and (not asymmetric or len(retry) != expected_runs))
            or any(
                not o['stages'] or any(s['status'] not in ('pass', 'stopped') for s in o['stages'])
                for o in before + after + retry
            )
        )
        unstable = load_sensitive and (baseline is None or candidate is None)
        classification = (
            'unstable'
            if unstable
            else (classify(baseline, candidate, case.manifest) if baseline and candidate else 'changed_reason')
        )
        minimum_runs = (5 if target else 3) if load_sensitive else 1
        insufficient = min(len(before), len(after)) < minimum_runs
        if load_sensitive and classification == 'fixed':
            # A later stop is not an end-to-end stress pass. A small unanimous
            # sample cannot establish a target fix either.
            if stop(candidate) is not None:
                classification = 'changed_reason'
            elif insufficient:
                classification = 'insufficient_repeats'
        rows.append(
            {
                'case_id': case_id(case, key),
                'identity_scheme': 'hmac-sha256' if case.manifest.tier == 'C' else 'sha256',
                **({'corpus_sha256': case_digest(case)} if case.manifest.tier == 'S' else {}),
                'fixed_by_ref': target,
                'classification': classification,
                'incomplete': incomplete,
                'insufficient_repeats': insufficient,
                'inconclusive': incomplete or (unstable and (target or asymmetric)),
                'baseline': {'outcomes': before, 'unanimous': baseline},
                'candidate': {
                    'outcomes': after + retry,
                    'retry_start': len(after) if retry else None,
                    'unanimous': candidate,
                },
            }
        )
    new_sites = [
        {'exception_type': kind, 'site': site}
        for kind, site in sorted(
            candidate_exceptions - baseline_exceptions, key=lambda value: (value[0], value[1] or '')
        )
    ]
    hard_failure = (
        not rows
        or bool(new_sites)
        or any(row['incomplete'] or row['classification'] in ('regressed', 'changed_reason') for row in rows)
    )
    verdict = 'FAIL'
    if not hard_failure:
        if any(row['inconclusive'] for row in rows):
            verdict = 'INCONCLUSIVE'
        elif any(row['insufficient_repeats'] for row in rows):
            verdict = 'DIAGNOSTIC'
        elif any(row['fixed_by_ref'] and row['classification'] != 'fixed' for row in rows):
            verdict = 'FAIL'
        else:
            verdict = 'PASS' if any(row['fixed_by_ref'] for row in rows) else 'REGRESSION_ONLY'
    return {'cases': rows, 'new_exception_sites': new_sites, 'verdict': verdict}


def markdown(result):
    rows = [
        f"Replay gate: **{result['verdict']}**",
        '',
        f"BASE `{result['refs']['baseline']}` → REF `{result['refs']['candidate']}`",
        f"decryption: {result.get('decryption', 'off')}",
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


def run_side(backend, cases, repeats, timeout=1800, grace=10, worker=None, *, decryption_files=None, runtime_env=None):
    worker = worker or Path(__file__).with_name('gate_worker.py')
    environment = {
        key: os.environ[key] for key in ('PATH', 'TMPDIR', 'SYSTEMROOT', 'FIRESTORE_EMULATOR_HOST') if key in os.environ
    }
    options = [
        argument
        for name, path in (decryption_files or {}).items()
        if path is not None
        for argument in ('--' + name.replace('_', '-'), str(Path(path).resolve()))
    ]
    if runtime_env is not None:
        options.extend(['--runtime-env', runtime_env])
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
            [sys.executable, '-I', str(worker), '--backend', str(backend), '--output', str(report), *options],
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


def gate(
    repo,
    directories,
    ref,
    base,
    output,
    repeats=3,
    regression_only=False,
    worker_timeout=1800,
    *,
    secret_file=None,
    uid_file=None,
    consent_file=None,
    runtime_env=None,
):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be positive')
    if worker_timeout <= 0:
        raise ValueError('worker timeout must be positive')
    cases = [load_case(p) for p in directories]
    if not cases or len({c.manifest.id for c in cases}) != len(cases):
        raise ValueError('cases must be nonempty and unique')
    decryption_files = dict(secret_file=secret_file, uid_file=uid_file, consent_file=consent_file)
    credentials = load_decryption(**decryption_files)
    if credentials:
        for case in cases:
            credentials.validate(case)
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
    worker_options = {'decryption_files': decryption_files} if credentials else {}
    if runtime_env is not None:
        worker_options['runtime_env'] = runtime_env
    reports = {}
    for label in ('baseline', 'candidate'):
        with backend_snapshot(repo, refs[label], output, label) as backend:
            reports[label] = run_side(backend, cases, repeats, worker_timeout, **worker_options)
            if label == 'candidate':
                retry_indices = [
                    index
                    for index, case in enumerate(cases)
                    if needs_retry(case, reports['baseline'][index], reports['candidate'][index])
                ]
                if retry_indices:
                    retried = run_side(
                        backend,
                        [cases[index] for index in retry_indices],
                        repeats,
                        worker_timeout,
                        **worker_options,
                    )
                    reports['candidate_retry'] = dict(zip(retry_indices, retried, strict=True))
    if identity != adapter_digest() or digests != [case_digest(c) for c in cases]:
        raise ValueError('adapter or case changed during replay')
    result = {
        'schema_version': 1,
        'refs': refs,
        'adapter_sha256': identity,
        'repeats': repeats,
        'decryption': 'on' if credentials else 'off',
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
    parser.add_argument('--runtime-env', help='render service[:prod|dev] separately from each archived tree')
    add_arguments(parser)
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
            runtime_env=args.runtime_env,
            **file_options(args),
        )
    except Exception as error:
        # No paths, identifiers, manifest values, command lines or raw tracebacks.
        print(f'Replay gate: ERROR ({type(error).__name__})')
        return 2


if __name__ == '__main__':
    sys.exit(main())
