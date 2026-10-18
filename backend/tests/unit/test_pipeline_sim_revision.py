"""Revision replacement mid-run: un-awaited work is lost, awaited and durable work survives."""

from testing.pipeline_sim.scenarios import run


def test_background_first_summaries_are_lost_at_revision_replacement():
    sample = run('revision_replacement_mid_run', 1)
    sim = sample['sim']
    assert sim['lost_fire_and_forget_units'] > 0
    assert sim['summaries_never_completed'] > 0
    assert sample['verdict'] == 'GATE_FAIL first_summary_deadline'
    # Durable state-machine work survived: GPU pumps were SIGTERMed and restarted,
    # projections killed with the serving supervisor were replayed.
    assert sim['completion_rate'] == 1.0
    assert sim['job_states'] == {'committed': sample['admissions']}
    assert sim['drain'].get('request_scoped:killed', 0) == 0


def test_request_scoped_summaries_survive_the_same_replacement():
    sample = run('revision_replacement_mid_run', 1, summary_dispatch='task')
    sim = sample['sim']
    assert sim['summaries_never_completed'] == 0
    assert sim['drain'].get('request_scoped:killed', 0) == 0
    assert sim['drain']['request_scoped:completed'] > 0
    assert sample['verdict'] == 'GATE_PASS'
