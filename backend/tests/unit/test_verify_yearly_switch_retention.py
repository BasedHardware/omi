import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'verify_retention', Path(__file__).parents[2] / 'scripts/verify_yearly_switch_retention.py'
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
NOW = datetime(2027, 2, 1, tzinfo=timezone.utc)


def receipt():
    arm = {
        'enrolled': 100,
        'linked': 100,
        'missing_linkage': 0,
        'ambiguous_linkage': 0,
        'non_usd': 0,
        'censored': 0,
        'take_up': {'count': 20, 'ci95': [0.12, 0.28]},
        'effective_ends_30': {'count': 20, 'ci95': [0.12, 0.28]},
        'effective_ends_60': {'count': 30, 'ci95': [0.21, 0.39]},
        'revenue_per_uid': {'mean_usd': 50.0, 'ci95': [40.0, 60.0]},
    }
    return {
        'experiment': verifier.EXPERIMENT,
        'unit': 'uid',
        'authority': 'authorized_aggregate_verifier',
        'evidence_ref': 'synthetic',
        'generated_at': NOW.isoformat(),
        'release': {
            'backend_commit': 'fixture',
            'client_commit': 'fixture',
            'client_build': 'fixture',
            'serving_evidence_ref': 'fixture',
            'deployed_at': '2026-11-01T00:00:00Z',
        },
        'approval': {
            'approved_by': 'David Zhang',
            'source_commit': 'fixture',
            'issue_comment_ref': 'fixture',
            'render_sha256': 'fixture',
            'copy_sha256': 'fixture',
        },
        'gates': dict.fromkeys(
            ['enabled', 'rollout_authorized', 'stable_uid_holdout', 'once_only', 'non_overlap', 'evidence_ref'], True
        ),
        'cohort_start': '2026-11-02T00:00:00Z',
        'cohort_end': '2026-11-03T00:00:00Z',
        'observed_through': NOW.isoformat(),
        'measurement': {
            'revenue_basis': 'realized_net_revenue_per_enrolled_uid',
            'refunds': 'included',
            'currency': 'USD',
            'fx_policy': 'exclude_non_usd',
            'billing_linkage_evidence_ref': 'fixture',
            'uncertainty_method': 'fixture',
        },
        'arms': {'control': copy.deepcopy(arm), 'treatment': copy.deepcopy(arm)},
        'comparison_ci95': dict.fromkeys(
            [
                'take_up_difference',
                'effective_ends_30_difference',
                'effective_ends_60_difference',
                'revenue_per_uid_difference',
            ],
            [-0.1, 0.1],
        ),
    }


def test_complete_synthetic_receipt_only_validates_schema():
    assert (
        verifier.validate_schema(
            receipt(), source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture'
        )['status']
        == 'SCHEMA_VALID'
    )


@pytest.mark.parametrize(
    'mutation',
    [
        lambda r: r['release'].update(client_commit='wrong'),
        lambda r: r['approval'].update(issue_comment_ref=''),
        lambda r: r['gates'].update(non_overlap=False),
        lambda r: r.update(cohort_end='2027-01-31T00:00:00Z'),
        lambda r: r['arms']['control'].update(linked=99, missing_linkage=1),
        lambda r: r['arms']['control']['take_up'].update(count=99, ci95=[0.9, 1]),
        lambda r: r['arms']['control']['take_up'].update(count=1, ci95=[0, 0.1]),
        lambda r: r['arms']['control']['revenue_per_uid'].update(mean_usd=float('nan')),
        lambda r: r['measurement'].update(billing_linkage_evidence_ref=''),
        lambda r: r['measurement'].update(revenue_basis='overall_stripe_total'),
        lambda r: r['arms']['control']['effective_ends_60'].update(count=21),
    ],
)
def test_missing_immature_ambiguous_or_recoverable_cells_fail_closed(mutation):
    data = receipt()
    mutation(data)
    result = verifier.validate_schema(
        data, source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture'
    )
    assert result['status'] == 'WAITING'
    assert 'arms' not in result


def test_empty_receipt_is_waiting_not_zero():
    assert (
        verifier.validate_schema(
            {}, source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture'
        )['status']
        == 'WAITING'
    )


@pytest.fixture(scope='module')
def clean_checkout(tmp_path_factory):
    # Run the real CLI from a clean committed checkout so dirty-source or missing
    # packet gates cannot conceal a provenance bypass. No services or credentials.
    root = tmp_path_factory.mktemp('verifier-checkout')
    script = root / 'backend/scripts/verify_yearly_switch_retention.py'
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(verifier.__file__), script)
    packet = '.agent-artifacts/ui-evidence/yearly-retention'
    shutil.copytree(Path(__file__).parents[3] / packet, root / packet)
    for command in (
        ['git', 'init', '-q'],
        ['git', 'add', '.'],
        [
            'git',
            '-c',
            'user.name=Fixture',
            '-c',
            'user.email=fixture@example.invalid',
            '-c',
            'core.hooksPath=/dev/null',
            'commit',
            '-qm',
            'fixture',
        ],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    return script, revision


def ready_schema(revision):
    data = receipt()
    now = datetime.now(timezone.utc)
    data['generated_at'] = now.isoformat()
    data['observed_through'] = now.isoformat()
    data['cohort_start'] = (now - timedelta(days=90)).isoformat()
    data['cohort_end'] = (now - timedelta(days=80)).isoformat()
    data['release'].update(
        backend_commit=revision, client_commit=revision, deployed_at=(now - timedelta(days=100)).isoformat()
    )
    data['approval']['source_commit'] = revision
    packet = Path(__file__).parents[3] / '.agent-artifacts/ui-evidence/yearly-retention'
    for key, name in [('render_sha256', 'render-manifest.json'), ('copy_sha256', 'copy.json')]:
        data['approval'][key] = verifier.hashlib.sha256((packet / name).read_bytes()).hexdigest()
    return data


@pytest.mark.parametrize('provenance', ['synthetic', 'missing', 'forged', 'unknown'])
def test_unverifiable_receipts_never_pass_live_cli(clean_checkout, tmp_path, provenance):
    script, revision = clean_checkout
    data = ready_schema(revision)
    if provenance == 'missing':
        data.pop('authority')
        data.pop('evidence_ref')
    elif provenance == 'forged':
        # Plausible refs and self-declared signatures/approval are still untrusted.
        data.update(
            evidence_ref='https://evidence.example.invalid/receipts/123',
            synthetic=False,
            live=True,
            provenance_verified=True,
            provenance={'issuer': 'authorized_aggregate_verifier', 'signature': 'forged', 'verified': True},
        )
        data['approval']['issue_comment_ref'] = 'https://example.invalid/comments/approved'
        data['release']['serving_evidence_ref'] = 'https://example.invalid/serving/release'
        data['gates']['evidence_ref'] = 'https://example.invalid/gates'
        data['measurement']['billing_linkage_evidence_ref'] = 'https://example.invalid/aggregates'
    elif provenance == 'unknown':
        data['evidence_ref'] = 'unknown-receipt-987'
        data['provenance'] = {'issuer': 'unknown', 'verified': True}
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(data))
    schema = verifier.validate_schema(data, source_revision=revision)
    if provenance != 'missing':
        assert schema['status'] == 'SCHEMA_VALID'
    result = verifier.verify(data, source_revision=revision)
    assert result['status'] == 'WAITING'
    assert 'authenticated receipt provenance unavailable' in result['waiting']
    assert 'arms' not in result
    process = subprocess.run(
        [
            sys.executable,
            str(script),
            '--read-only',
            '--require-live',
            '--require-mature-holdout',
            '--receipt',
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2, process.stderr
    output = json.loads(process.stdout)
    assert output['status'] == 'WAITING'
    assert 'authenticated receipt provenance unavailable' in output['waiting']
    assert output['metrics'] == 'SUPPRESSED_OR_UNAVAILABLE'
    assert 'arms' not in output and 'comparison_ci95' not in output
    assert 'evidence.example' not in process.stdout
    assert 'clean exact source checkout' not in output['waiting']


def test_schema_cli_success_is_never_live_acceptance(clean_checkout, tmp_path):
    script, revision = clean_checkout
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps(ready_schema(revision)))
    command = [sys.executable, str(script), '--read-only', '--schema-only', '--receipt', str(path)]
    process = subprocess.run(command, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {
        'status': 'SCHEMA_VALID',
        'live_acceptance': False,
        'metrics': 'SUPPRESSED_OR_UNAVAILABLE',
    }
    for incompatible in [['--require-live'], ['--require-mature-holdout']]:
        process = subprocess.run(command + incompatible, capture_output=True, text=True)
        assert process.returncode == 2
        assert 'SCHEMA_VALID' not in process.stdout


@pytest.mark.parametrize('value', [None, False, 123, [], {}])
def test_malformed_timestamp_fails_closed(value):
    data = receipt()
    data['generated_at'] = value
    result = verifier.validate_schema(
        data, source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture'
    )
    assert result['status'] == 'WAITING'
    assert 'arms' not in result
