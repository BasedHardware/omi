import copy
from datetime import datetime, timezone
import importlib.util
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


def test_complete_synthetic_receipt_only_exercises_acceptance_parser():
    assert (
        verifier.verify(receipt(), source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture')[
            'status'
        ]
        == 'LIVE_MATURE_EVIDENCE'
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
    ],
)
def test_missing_immature_ambiguous_or_recoverable_cells_fail_closed(mutation):
    data = receipt()
    mutation(data)
    result = verifier.verify(data, source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture')
    assert result['status'] == 'WAITING'
    assert 'arms' not in result


def test_empty_receipt_is_waiting_not_zero():
    assert (
        verifier.verify({}, source_revision='fixture', now=NOW, render_digest='fixture', copy_digest='fixture')[
            'status'
        ]
        == 'WAITING'
    )
