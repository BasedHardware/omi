"""Compare a fixed replay adapter/corpus against two immutable Git refs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def adapter_digest(gate_path, runner_path, incident_path, transaction_fixture_path):
    """Every fixed transaction capability is part of the comparison identity."""
    return hashlib.sha256(
        gate_path.read_bytes()
        + runner_path.read_bytes()
        + incident_path.read_bytes()
        + transaction_fixture_path.read_bytes()
    ).hexdigest()


def compare(candidate, baseline):
    new_exceptions = sorted(set(candidate['exceptions']) - set(baseline['exceptions']))
    old_blocked = {sid for row in baseline['chain_blocks'] for sid in row.get('units', [])}
    old_blocks = {(row['owner'], row['head']): row['blocked_units'] for row in baseline['chain_blocks']}
    new_blocks = [
        row
        for row in candidate['chain_blocks']
        if (
            bool(set(row['units']) - old_blocked)
            if 'units' in row
            else row['blocked_units'] > old_blocks.get((row['owner'], row['head']), 0)
        )
    ]
    # Per-unit checks also catch a known exception/site spreading to new shapes.
    changed_units = {
        unit: sorted(set(issues) - set(baseline['unit_issues'].get(unit, [])))
        for unit, issues in candidate['unit_issues'].items()
        if set(issues) - set(baseline['unit_issues'].get(unit, []))
    }
    # Fixing a chain head exposes work the baseline never reached. A known
    # site on an already-blocked unit is new evidence, not a regression.
    # New classes/sites still fail even when previously unreachable.
    newly_reached = {
        unit: sites
        for unit, sites in changed_units.items()
        if unit in old_blocked and not set(sites).intersection(new_exceptions)
    }
    new_units = {unit: sites for unit, sites in changed_units.items() if unit not in newly_reached}

    def unit_counts(report, unit):
        return report.get('unit_exception_counts', {}).get(
            unit, {site: 1 for site in report['unit_issues'].get(unit, [])}
        )

    increased_units = {
        unit: {
            site: {'baseline': unit_counts(baseline, unit).get(site, 0), 'candidate': count}
            for site, count in unit_counts(candidate, unit).items()
            if count > unit_counts(baseline, unit).get(site, 0)
        }
        for unit in candidate['unit_issues']
        if unit not in newly_reached
    }
    increased_units = {unit: sites for unit, sites in increased_units.items() if sites}
    increased_counts = {
        site: {'baseline': baseline['exceptions'].get(site, 0), 'candidate': count}
        for site, count in candidate['exceptions'].items()
        if count
        > baseline['exceptions'].get(site, 0) + sum(unit_counts(candidate, unit).get(site, 0) for unit in newly_reached)
    }
    return {
        'new_exception_sites': new_exceptions,
        'new_chain_blocks': new_blocks,
        'new_unit_failures': new_units,
        'newly_reached_known_failures': newly_reached,
        'increased_unit_exception_counts': increased_units,
        'increased_exception_counts': increased_counts,
        'regression': bool(new_exceptions or new_blocks or new_units or increased_units or increased_counts),
    }


def count_synthetic_failures(report, incidents):
    # Check both boundary lists explicitly, independent of the runner also
    # recording boundary failures in its exception map.
    return (
        len(incidents['exceptions'])
        + len(incidents['chain_blocks'])
        + len(report['boundaries']['failures'])
        + len(incidents['boundaries']['failures'])
    )


GEOMETRY_LIMITS = frozenset(
    {'missing_decoded_duration', 'missing_source_geometry', 'missing_vad_spans', 'missing_speech_accounting'}
)


def gate(repo, corpus, ref, base, output, allow_incomplete=False, require_captured_geometry=False):
    runner = Path(__file__).with_name('runner.py')
    transaction_fixture = Path(__file__).resolve().parents[2] / 'tests/unit/fixtures/strict_firestore_transaction.py'
    resolved = {
        label: subprocess.check_output(
            ['git', '-C', str(repo), 'rev-parse', '--verify', f'{value}^{{commit}}'], text=True
        ).strip()
        for label, value in (('candidate', ref), ('baseline', base))
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    reports = {}
    incidents = {}
    fixture = runner.with_name('regressions.json')
    for label, sha in resolved.items():
        with tempfile.TemporaryDirectory(prefix=f'batch-replay-{label}-', dir=output) as directory:
            snapshot = Path(directory)
            archive = snapshot / 'source.tar'
            with archive.open('wb') as stream:
                subprocess.run(['git', '-C', str(repo), 'archive', sha, 'backend'], stdout=stream, check=True)
            with tarfile.open(archive) as bundle:
                bundle.extractall(snapshot, filter='data')
            report = output / f'{label}.json'
            environment = {
                key: value
                for key, value in os.environ.items()
                if not (
                    key.startswith(('GOOGLE_', 'GCLOUD_', 'GCP_', 'CLOUDSDK_', 'OMI_', 'BATCH_', 'REDIS_'))
                    or key in {'SERVICE_ACCOUNT_JSON', 'ENCRYPTION_SECRET', 'OPENAI_API_KEY', 'PYTHONPATH'}
                )
            }
            # stdout/stderr are private diagnostic files. Never surface raw
            # product logs or unexpected import errors to shared operator output.
            with (output / f'{label}.log').open('wb') as stream:
                subprocess.run(
                    [
                        sys.executable,
                        '-I',
                        str(runner),
                        '--backend',
                        str(snapshot / 'backend'),
                        '--corpus',
                        str(corpus.resolve()),
                        '--output',
                        str(report.resolve()),
                    ],
                    env=environment,
                    stdout=stream,
                    stderr=stream,
                    check=True,
                    timeout=1800,
                )
            reports[label] = json.loads(report.read_text())
            if corpus.resolve() == fixture.resolve():
                incidents[label] = reports[label]
            else:
                incident_report = output / f'{label}.incidents.json'
                with (output / f'{label}.incidents.log').open('wb') as stream:
                    subprocess.run(
                        [
                            sys.executable,
                            '-I',
                            str(runner),
                            '--backend',
                            str(snapshot / 'backend'),
                            '--corpus',
                            str(fixture),
                            '--output',
                            str(incident_report.resolve()),
                        ],
                        env=environment,
                        stdout=stream,
                        stderr=stream,
                        check=True,
                        timeout=1800,
                    )
                incidents[label] = json.loads(incident_report.read_text())
    diff = compare(reports['candidate'], reports['baseline'])
    incident_diff = compare(incidents['candidate'], incidents['baseline'])
    coverage = reports['candidate']['coverage']
    limits = {key: count for key, count in coverage.items() if key in GEOMETRY_LIMITS and count}
    incomplete = {
        key: count
        for key, count in coverage.items()
        if key.startswith(('missing_', 'invalid_')) and count and key not in GEOMETRY_LIMITS
    }
    if require_captured_geometry:
        incomplete.update(limits)
    synthetic_failures = count_synthetic_failures(reports['candidate'], incidents['candidate'])
    result = {
        'schema': 1,
        'refs': resolved,
        'corpus_sha256': hashlib.sha256(corpus.read_bytes()).hexdigest(),
        'adapter_sha256': adapter_digest(Path(__file__), runner, fixture, transaction_fixture),
        'transaction_fixture_sha256': hashlib.sha256(transaction_fixture.read_bytes()).hexdigest(),
        **diff,
        'synthetic_comparison': incident_diff,
        'synthetic_failures': synthetic_failures,
        'coverage_scope': 'firestore-structure+synthetic-boundaries',
        'coverage_ruling': 'lead:a76a1a',
        'coverage_limits': limits,
        'incomplete': incomplete,
        'diagnostic_only': allow_incomplete,
        'verdict': (
            'FAIL'
            if diff['regression']
            or incident_diff['regression']
            or synthetic_failures
            or (incomplete and not allow_incomplete)
            else 'PASS'
        ),
    }
    (output / 'gate.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(
        json.dumps(
            {
                'verdict': result['verdict'],
                'refs': resolved,
                'new_exception_sites': diff['new_exception_sites'],
                'new_chain_blocks': len(diff['new_chain_blocks']),
                'incomplete': incomplete,
                'diagnostic_only': allow_incomplete,
                'synthetic_failures': synthetic_failures,
                'coverage_scope': result['coverage_scope'],
                'coverage_limits': limits,
            },
            sort_keys=True,
        )
    )
    return 1 if result['verdict'] == 'FAIL' else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true', help='diagnostic comparison; not a deploy receipt')
    parser.add_argument(
        '--require-captured-geometry', action='store_true', help='also require observed artifact geometry'
    )
    args = parser.parse_args()
    sys.exit(
        gate(
            args.repo,
            args.corpus,
            args.ref,
            args.base,
            args.output,
            args.allow_incomplete,
            args.require_captured_geometry,
        )
    )
