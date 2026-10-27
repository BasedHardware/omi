"""Characterization goldens for the batch pipeline driven by testing/pipeline_sim.

Each golden is the normalized, externally visible trace (``testing.pipeline_sim.trace``) of a small seeded
run on the real batch state machine. A diff means observable behavior changed: review it, and when the
change is intended regenerate the goldens and commit them with the change:

    cd backend && PIPELINE_GOLDEN_UPDATE=1 python -m pytest tests/unit/test_pipeline_characterization.py

Every simulation runs in a module fixture (setup phase), so the fast-unit CPU guard measures only the
comparisons.
"""

import json
import os
from pathlib import Path

import pytest

from diarizer import batch_pipeline as worker_module
from config import batch_pipeline_empty_asr as empty_safety
from testing.pipeline_sim.trace import GOLDEN_CONFIGS, describe_diff, dumps, golden_trace

GOLDEN_DIR = Path(__file__).parent / 'fixtures' / 'pipeline_sim_goldens'
UPDATE = os.environ.get('PIPELINE_GOLDEN_UPDATE') == '1'


def _never_fits(samples, max_padded_seconds):
    return False


# Deliberate behavior changes in REAL product modules; each must change its golden.
PERTURBATIONS = {
    # The worker never attempts the padded retry, so a padded-retry rescue becomes a paid quarantine.
    'skip_padded_retry': ('empty_asr_padded_retry', worker_module, 'padded_retry_fits', _never_fits),
    # The explicit safety rollback may dispose speech; shipping retains it held.
    'allow_terminal_empty': (
        'empty_asr_terminal',
        empty_safety,
        'safety_net_enabled',
        lambda: False,
    ),
}


@pytest.fixture(scope='module')
def traces() -> dict[str, str]:
    return {name: dumps(golden_trace(name)) for name in sorted(GOLDEN_CONFIGS)}


@pytest.fixture(scope='module')
def reruns() -> dict[str, str]:
    return {name: dumps(golden_trace(name)) for name in ('healthy', 'privacy_fence_midflight')}


@pytest.fixture(scope='module')
def perturbed() -> dict[str, str]:
    out = {}
    for key, (name, module, attribute, replacement) in PERTURBATIONS.items():
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(module, attribute, replacement)
            out[key] = dumps(golden_trace(name))
    return out


@pytest.mark.parametrize('name', sorted(GOLDEN_CONFIGS))
def test_trace_matches_golden(name, traces):
    path = GOLDEN_DIR / f'{name}.json'
    actual = traces[name]
    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != actual:
            path.write_text(actual)
        return
    assert path.exists(), f'missing golden {path.name}; regenerate with PIPELINE_GOLDEN_UPDATE=1'
    expected = path.read_text()
    if actual != expected:
        pytest.fail(
            'pipeline behavior changed (regenerate with PIPELINE_GOLDEN_UPDATE=1 only if intended):\n'
            + describe_diff(expected, actual, label=path.name),
            pytrace=False,
        )


def test_every_golden_file_has_a_configuration():
    assert sorted(path.stem for path in GOLDEN_DIR.glob('*.json')) == sorted(GOLDEN_CONFIGS)


def test_trace_is_deterministic_for_a_seed(traces, reruns):
    for name, rerun in reruns.items():
        assert rerun == traces[name], name


def test_trace_has_no_raw_synthetic_identifiers_or_tokens(traces):
    for name, text in traces.items():
        assert 'sim-owner-' not in text and 'sim-conv-' not in text and 'sim://' not in text, name
        assert '"token"' not in text and '<hex64>' not in text, name


@pytest.mark.parametrize('key', sorted(PERTURBATIONS))
def test_a_deliberate_behavior_change_breaks_the_golden(key, traces, perturbed):
    name = PERTURBATIONS[key][0]
    assert perturbed[key] != traces[name]
    baseline, changed = json.loads(traces[name]), json.loads(perturbed[key])
    if key == 'skip_padded_retry':
        # A segment the padded retry rescued now spends a paid recovery call.
        assert changed['totals']['paid_calls'] > baseline['totals']['paid_calls']
    else:
        assert 'failed_held' in baseline['totals']['recovery_states']
        assert 'failed_held' not in changed['totals']['recovery_states']
    summary = describe_diff(traces[name], perturbed[key], label=name).splitlines()[0]
    assert not summary.startswith('0 changed'), summary


@pytest.fixture(scope='module')
def wrong_role_traces():
    from testing.pipeline_sim.trace import trace

    out = {}
    for stage in ('projection', 'recovery'):
        config = GOLDEN_CONFIGS['role_policy']()
        config.stage_roles[stage] = 'sync'
        out[stage] = dumps(trace(config))
    return out


@pytest.mark.parametrize('stage', ['projection', 'recovery'])
def test_wrong_role_breaks_the_policy_golden(stage, traces, wrong_role_traces):
    assert wrong_role_traces[stage] != traces['role_policy']
    baseline = json.loads(traces['role_policy'])
    changed = json.loads(wrong_role_traces[stage])
    field = 'authoritative_labels' if stage == 'projection' else 'recovery_enabled'
    before = [s['final_job']['policy_parts'].get(stage) for s in baseline['segments'].values()]
    after = [s['final_job']['policy_parts'].get(stage) for s in changed['segments'].values()]
    assert any(part and part[field] and part['source_role'] == 'integration' for part in before)
    assert any(part and not part[field] and part['source_role'] == 'sync' for part in after)
