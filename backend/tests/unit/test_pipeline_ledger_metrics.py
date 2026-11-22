"""The C2 census gauges: bounded labels, exact values, no owner identity."""

from __future__ import annotations

from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from utils.conversations import pipeline_ledger_metrics as metrics


def _result():
    return {
        'generated_at': 1_800_000_000.0,
        'stuck': {
            'by_stage': {'capturing': 0, 'sealed': 2, 'transcribed': 1, 'noted': 0},
            'affected_users': {'capturing': 0, 'sealed': 1, 'transcribed': 1, 'noted': 0},
            'oldest_age_seconds': {'capturing': 0, 'sealed': 120.0, 'transcribed': 30.0, 'noted': 0},
            'total': 3,
        },
        'new_stuck_per_hour': {
            'by_stage': {'capturing': 0, 'sealed': 1, 'transcribed': 0, 'noted': 0},
            'total': 1,
        },
        'end_types': {'unknown_share': 0.25},
    }


def _samples():
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample
        for family in text_string_to_metric_families(generate_latest().decode())
        for sample in family.samples
    }


def test_refresh_sets_bounded_stage_gauges():
    metrics.refresh_gauges(_result())
    samples = _samples()
    assert samples[('omi_pipeline_ledger_stuck_rows', (('stage', 'sealed'),))].value == 2
    assert samples[('omi_pipeline_ledger_stuck_users', (('stage', 'sealed'),))].value == 1
    assert samples[('omi_pipeline_ledger_oldest_stuck_age_seconds', (('stage', 'sealed'),))].value == 120.0
    assert samples[('omi_pipeline_ledger_new_stuck_per_hour', (('stage', 'sealed'),))].value == 1
    assert samples[('omi_pipeline_ledger_unknown_end_type_share', ())].value == 0.25
    assert samples[('omi_pipeline_ledger_refreshed_at_seconds', ())].value == 1_800_000_000.0


def test_gauges_never_carry_an_owner_label():
    metrics.refresh_gauges(_result())
    for family in text_string_to_metric_families(generate_latest().decode()):
        if not family.name.startswith('omi_pipeline_ledger_'):
            continue
        for sample in family.samples:
            assert 'uid' not in sample.labels
            assert 'owner' not in sample.labels
            assert 'conversation' not in sample.labels
