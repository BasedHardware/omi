"""Gate a candidate against a last-good ref with one fixed local replay adapter."""

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

# Direct execution with -I must still load this tree's adapter, never a snapshot's.
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from testing.replay_snapshot import backend_snapshot, resolve_refs
from testing.replay_harness.manifest import load_case
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


def case_id(case):
    # Even a schema-valid Tier C id may be a customer identifier.
    return hashlib.sha256(case.manifest.id.encode()).hexdigest()


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


def compare(cases, reports):
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
                'case_id_sha256': case_id(case),
                'corpus_sha256': case_digest(case),
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
            and row['classification'] != 'regressed'
            and (not row['fixed_by_ref'] or row['classification'] == 'fixed')
            for row in rows
        )
    )
    return {'cases': rows, 'new_exception_sites': new_sites, 'verdict': 'PASS' if passed else 'FAIL'}


def markdown(result):
    rows = [
        f"Replay gate: **{result['verdict']}**",
        '',
        f"BASE `{result['refs']['baseline']}` → REF `{result['refs']['candidate']}`",
        '',
        '| case id sha256 (prefix) | target | classification | BASE / REF runs | inconclusive |',
        '|---|---|---|---:|---|',
    ]
    for row in result['cases']:
        rows.append(
            f"| {row['case_id_sha256'][:12]} | {row['fixed_by_ref']} | {row['classification']} | "
            f"{len(row['baseline']['outcomes'])} / {len(row['candidate']['outcomes'])} | {row['inconclusive']} |"
        )
    rows.extend(['', f"New exception class/sites: {len(result['new_exception_sites'])}"])
    return '\n'.join(rows) + '\n'


def run_side(backend, cases, repeats):
    worker = Path(__file__).with_name('gate_worker.py')
    # Allowlist process settings. No ADC, .env loading or inherited provider config.
    environment = {
        key: os.environ[key] for key in ('PATH', 'TMPDIR', 'SYSTEMROOT', 'FIRESTORE_EMULATOR_HOST') if key in os.environ
    }
    report = backend.parent / 'outcomes.json'
    subprocess.run(
        [sys.executable, '-I', str(worker), '--backend', str(backend), '--output', str(report)],
        input=json.dumps([{'path': str(c.directory), 'repeats': repeats_for(c, repeats)} for c in cases]).encode(),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=1800,
    )
    return json.loads(report.read_text())


def gate(repo, directories, ref, base, output, repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be positive')
    cases = [load_case(p) for p in directories]
    if not cases or len({case_id(c) for c in cases}) != len(cases):
        raise ValueError('cases must be nonempty and unique')
    # Keep case content outside OUTPUT, including accidental placement by a caller.
    output = output.resolve()
    if any(output == c.directory or output in c.directory.parents or c.directory in output.parents for c in cases):
        raise ValueError('output must be separate from case directories')
    refs = resolve_refs(repo, ref, base)
    identity = adapter_digest()
    digests = [case_digest(c) for c in cases]
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('gate.json', 'gate.md'):
        (output / name).unlink(missing_ok=True)
    reports = {}
    for label in ('baseline', 'candidate'):
        with backend_snapshot(repo, refs[label], output, label) as backend:
            reports[label] = run_side(backend, cases, repeats)
    if identity != adapter_digest() or digests != [case_digest(c) for c in cases]:
        raise ValueError('adapter or case changed during replay')
    result = {
        'schema_version': 1,
        'refs': refs,
        'adapter_sha256': identity,
        'repeats': repeats,
        **compare(cases, reports),
    }
    (output / 'gate.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    (output / 'gate.md').write_text(markdown(result))
    print(f"Replay gate: {result['verdict']} ({len(cases)} cases)")
    return 0 if result['verdict'] == 'PASS' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--case', type=Path, action='append', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3, help='runs per side for load-sensitive cases (default: 3)')
    args = parser.parse_args(argv)
    try:
        return gate(args.repo, args.case, args.ref, args.base, args.output, args.repeats)
    except Exception as error:
        # No paths, identifiers, manifest values, command lines or raw tracebacks.
        print(f'Replay gate: ERROR ({type(error).__name__})')
        return 2


if __name__ == '__main__':
    sys.exit(main())
