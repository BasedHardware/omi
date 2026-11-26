"""Synthetic paired replay quality-gate coverage."""

from pathlib import Path
from runpy import run_path

import pytest

EVALUATOR = run_path(str(Path(__file__).resolve().parents[2] / 'scripts/evaluate-conversation-flex.py'))
OUTLINE = EVALUATOR['OUTLINE']


@pytest.mark.parametrize('foreground,long_pairs', [(1, 30), (99, 30), (100, 29)])
def test_paired_replay_rejects_undersampled_strata(foreground, long_pairs):
    rows = make_pairs(foreground, long_pairs)
    with pytest.raises(ValueError, match='undersampled strata'):
        EVALUATOR['evaluate'](rows, OUTLINE)


def test_paired_replay_reports_strata_and_foreground_tails():
    report = EVALUATOR['evaluate'](make_pairs(100, 30), OUTLINE)
    assert report['pass']
    assert report['strata']['long'] == 30
    assert report['strata']['foreground'] == 100
    assert report['foreground_ms']['p99'] == {'baseline': 100, 'candidate': 100}


def make_pairs(foreground, long_pairs):
    result = {
        'model': 'synthetic',
        'schema_ok': True,
        'grounded': True,
        'title_ok': True,
        'boundaries': [],
        'critical_errors': 0,
        'missed_promotions': 0,
        'duplicate_publications': 0,
        'due_extractions_pending': 0,
        'deadline_met': True,
        'foreground_ms': 100,
        'usage': {'prompt_tokens': 10, 'prompt_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0}},
    }
    other = EVALUATOR['REQUIRED_TAGS'][OUTLINE] - {'foreground', 'long'}
    return [
        {
            'id': str(index),
            'lane': OUTLINE,
            'tags': [
                *other,
                *(['foreground'] if index < foreground else []),
                *(['long'] if index < long_pairs else []),
            ],
            'expected_boundaries': [],
            'baseline': result,
            'candidate': result,
        }
        for index in range(300)
    ]
