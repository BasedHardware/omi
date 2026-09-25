"""Unit tests for Firestore query-coverage ratchet and baseline freshness."""

import json
from pathlib import Path

import pytest

from scripts import firestore_query_coverage


def test_query_coverage_ratchet_rejects_a_new_raw_serving_shape():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 1,
        'registered_serving': 1,
        'raw_unregistered': [],
        'unsupported': [],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'new-raw', 'classification': 'raw_unregistered'},
        ],
    }

    assert firestore_query_coverage.check_ratchet(report, baseline) == [
        'new unregistered serving compound query shape(s): new-raw',
        'registered serving-query coverage percentage decreased',
    ]


@pytest.mark.slow
def test_query_coverage_baseline_tracks_current_raw_and_unsupported_debt():
    baseline_path = Path(__file__).resolve().parents[2] / 'scripts' / 'firestore_query_coverage_baseline.json'
    committed = json.loads(baseline_path.read_text(encoding='utf-8'))
    report = firestore_query_coverage.report_for(firestore_query_coverage.inventory(waiver_ids=set()))

    assert firestore_query_coverage.check_ratchet(report, committed) == []


def test_query_coverage_freshness_rejects_a_baselined_shape_that_is_gone():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 2,
        'registered_serving': 1,
        'raw_unregistered': ['retired-raw', 'still-raw'],
        'unsupported': ['retired-unsupported'],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'still-raw', 'classification': 'raw_unregistered'},
        ],
    }

    # The ratchet stays silent: today's debt is still a subset of the baselined debt.
    assert firestore_query_coverage.check_ratchet(report, baseline) == []
    assert firestore_query_coverage.check_baseline_freshness(report, baseline) == [
        'baselined raw_unregistered shape(s) no longer present: retired-raw',
        'baselined unsupported shape(s) no longer present: retired-unsupported',
        firestore_query_coverage.REGENERATE_HINT,
    ]


def test_query_coverage_freshness_allows_increased_summary_counts():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 1,
        'registered_serving': 0,
        'raw_unregistered': ['still-raw'],
        'unsupported': [],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'still-raw', 'classification': 'raw_unregistered'},
        ],
    }

    assert firestore_query_coverage.check_ratchet(report, baseline) == []
    assert firestore_query_coverage.check_baseline_freshness(report, baseline) == []
    assert firestore_query_coverage.baseline_count_increase_notices(report, baseline) == [
        'baseline registered_serving is 0, current inventory reports 1',
        'baseline eligible_serving is 1, current inventory reports 2',
        firestore_query_coverage.REGENERATE_HINT,
    ]


def test_query_coverage_freshness_rejects_decreased_summary_counts():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 4,
        'registered_serving': 2,
        'raw_unregistered': ['still-raw'],
        'unsupported': [],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'still-raw', 'classification': 'raw_unregistered'},
        ],
    }

    assert firestore_query_coverage.check_ratchet(report, baseline) == [
        'registered serving-query coverage count decreased',
    ]
    assert firestore_query_coverage.check_baseline_freshness(report, baseline) == [
        'baseline registered_serving is 2, current inventory reports 1',
        'baseline eligible_serving is 4, current inventory reports 2',
        firestore_query_coverage.REGENERATE_HINT,
    ]


def test_query_coverage_ratchet_passes_unchanged_inventory():
    baseline = {
        'schema_version': 1,
        'eligible_serving': 2,
        'registered_serving': 1,
        'raw_unregistered': ['still-raw'],
        'unsupported': [],
    }
    report = {
        'counts': {
            'serving': {
                'eligible': 2,
                'registered': 1,
                'raw_unregistered': 1,
                'waived': 0,
                'unsupported': 0,
            }
        },
        'queries': [
            {'id': 'registered', 'classification': 'registered'},
            {'id': 'still-raw', 'classification': 'raw_unregistered'},
        ],
    }

    assert firestore_query_coverage.check_ratchet(report, baseline) == []
    assert firestore_query_coverage.check_baseline_freshness(report, baseline) == []
    assert firestore_query_coverage.baseline_count_increase_notices(report, baseline) == []


@pytest.mark.slow
def test_committed_query_coverage_baseline_is_regenerated_from_the_current_inventory():
    baseline_path = Path(__file__).resolve().parents[2] / 'scripts' / 'firestore_query_coverage_baseline.json'
    committed = json.loads(baseline_path.read_text(encoding='utf-8'))
    report = firestore_query_coverage.report_for(firestore_query_coverage.inventory(waiver_ids=set()))

    assert firestore_query_coverage.check_baseline_freshness(report, committed) == []
    assert committed == firestore_query_coverage.baseline_for(report)
