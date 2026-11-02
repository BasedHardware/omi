"""Revision replacement mid-run: un-awaited work is lost, awaited and durable work survives."""

import pytest

from testing.pipeline_sim.scenarios import run


@pytest.fixture(scope='module')
def samples() -> dict[str, dict]:
    # Simulate once in setup; the fast-unit CPU guard measures only the assertions below.
    return {
        # Isolate revision/summary ownership from intentionally retained ASR debt.
        # The default-on safety behavior is covered by scenario/golden suites.
        'background': run(
            'revision_replacement_mid_run',
            1,
            overrides={'flags': {'BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED': 'false'}},
        ),
        'task': run(
            'revision_replacement_mid_run',
            1,
            summary_dispatch='task',
            overrides={'flags': {'BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED': 'false'}},
        ),
    }


def test_background_first_summaries_are_lost_at_revision_replacement(samples):
    sample = samples['background']
    sim = sample['sim']
    assert sim['lost_fire_and_forget_units'] > 0
    assert sim['summaries_never_completed'] > 0
    assert sample['verdict'] == 'GATE_FAIL first_summary_deadline'
    # Durable state-machine work survived: GPU pumps were SIGTERMed and restarted,
    # projections killed with the serving supervisor were replayed.
    assert sim['completion_rate'] == 1.0
    assert sim['job_states'] == {'committed': sample['admissions']}
    assert sim['drain'].get('request_scoped:killed', 0) == 0


def test_request_scoped_summaries_survive_the_same_replacement(samples):
    sample = samples['task']
    sim = sample['sim']
    assert sim['summaries_never_completed'] == 0
    assert sim['drain'].get('request_scoped:killed', 0) == 0
    assert sim['drain']['request_scoped:completed'] > 0
    assert sample['verdict'] == 'GATE_PASS'
