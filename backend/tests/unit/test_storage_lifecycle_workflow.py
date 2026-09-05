"""Structural contract for the storage lifecycle workflow.

Pins the guards that keep the automatic development run honest: the bucket is
asserted per environment before any gcloud command runs, live-state describes
use the raw API representation, and rollback removal is scoped to the rules the
apply variant declared. Static tripwire by design: it mirrors the workflow YAML,
the behavioral contract lives in test_storage_lifecycle_contract.py.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / '.github/workflows/gcp_storage_lifecycle.yml'


def _workflow() -> dict:
    loaded = yaml.load(WORKFLOW.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def _step_text(workflow: dict) -> str:
    steps = workflow['jobs']['apply']['steps']
    return '\n'.join(str(step.get('run', '')) for step in steps)


def test_environment_select_step_asserts_the_expected_bucket_per_environment() -> None:
    text = _step_text(_workflow())
    assert "development) expected_bucket='omi-dev-private-cloud-sync'" in text
    assert "prod) expected_bucket='omi-private-cloud-sync'" in text
    assert 'Lifecycle file bucket $bucket does not match' in text


def test_live_state_describes_use_the_raw_api_representation() -> None:
    text = _step_text(_workflow())
    assert text.count('--raw --format=json') == 2, 'both describe fixtures must use --raw'


def test_rollback_rule_removal_is_scoped_to_the_apply_variant_rules() -> None:
    text = _step_text(_workflow())
    assert '--allow-rule-removal-of' in text
    assert '--allow-rule-removal)' not in text.replace(
        '--allow-rule-removal-of', ''
    ), 'blanket --allow-rule-removal must not be wired into the automatic rollback path'
