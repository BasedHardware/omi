"""The live quality receipt must require all cases/repeats and zero leaks."""

from copy import deepcopy
import json

import pytest

from models.dream_agent import Plan
from scripts import dream_reasoning_eval as evaluation
from utils import dream_prompt


def rows():
    return [
        dict(
            case=case,
            repeat=repeat,
            error=None,
            kept={'edits': int(case != 'clean_bilingual')},
            dropped_invalid={},
            validation_errors={},
            tokens=10,
            title_proposals=int(case.startswith('untitled')),
            expected_edit_hit=True,
            language_false_positives=0,
            feedback_evidence_overlap=0,
            clean_edits=0,
        )
        for repeat in range(1, 6)
        for case in ['untitled_en', 'untitled_vi', 'clean_bilingual', 'brand_vi']
    ]


def test_quality_eval_requires_all_twenty_successes():
    summary = evaluation.summarize(rows(), expected_runs=20)
    assert summary['targets_met']
    assert summary['title_proposals'] == 10
    assert not evaluation.summarize(rows()[:-1], expected_runs=20)['targets_met']


@pytest.mark.parametrize(
    'update',
    [
        {'error': 'TimeoutError'},
        {'expected_edit_hit': False},
        {'language_false_positives': 1},
        {'feedback_evidence_overlap': 1},
        {'clean_edits': 1},
    ],
)
def test_quality_eval_cannot_certify_transport_failures_missed_edits_or_leaks(update):
    samples = deepcopy(rows())
    samples[0].update(update)
    assert not evaluation.summarize(samples, expected_runs=20)['targets_met']


def test_quality_cases_fit_the_real_reasoning_projection():
    fixture = json.loads((evaluation.FIXTURE.parent / 'quality-fixtures.json').read_text())
    assert len(fixture['cases']) == 4
    mount = dream_prompt.mount(Plan, 24000)
    for case in fixture['cases']:
        assert evaluation.messages(dict(case, version=1), mount)
