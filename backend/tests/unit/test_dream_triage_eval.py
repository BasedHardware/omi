"""Offline scoring contracts; these tests never call a model."""

import pytest

from scripts import dream_triage_eval as evaluation


def rows(hits=64, false_positives=15):
    return [
        {
            'problem': 'spelling',
            'canary': i < 5,
            'hit': i < hits,
            'candidates': int(i < hits),
            'error': None,
            'tokens': 10,
            'latency_ms': 20,
        }
        for i in range(75)
    ] + [
        {
            'problem': None,
            'canary': False,
            'hit': False,
            'candidates': int(i < false_positives),
            'error': None,
            'tokens': 10,
            'latency_ms': 20,
        }
        for i in range(50)
    ]


@pytest.mark.parametrize('hits,fp,passes', [(64, 15, True), (63, 15, False), (64, 16, False)])
def test_eval_gates_recall_and_false_positive_counts(hits, fp, passes):
    summary = evaluation.summarize(rows(hits, fp))
    assert summary['targets_met'] is passes
    assert summary['defect_hits'] == hits
    assert summary['clean_false_positives'] == fp


def test_eval_requires_five_canary_hits_and_no_errors():
    samples = rows(hits=75)
    samples[0]['hit'] = False
    assert not evaluation.summarize(samples)['targets_met']
    samples = rows()
    samples[-1]['error'] = 'ConnectError'
    assert not evaluation.summarize(samples)['targets_met']
    assert not evaluation.summarize(rows()[:-1])['targets_met']


def test_invented_fixture_covers_all_classes_and_both_projections():
    cases = evaluation.load_cases(evaluation.DEFAULT_FIXTURE)
    assert len(cases) == 29
    assert sum(case['expected_problem'] is not None for case in cases) == 18
