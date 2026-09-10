"""Structural release wiring tests; live GPU execution is a separate gate."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _yaml(path):
    return yaml.safe_load((ROOT / path).read_text())


@pytest.mark.parametrize('workflow', ['gcp_backend.yml', 'gcp_backend_auto_dev.yml'])
def test_release_consumes_same_run_qualified_image_before_deploy(workflow):
    jobs = _yaml(f'.github/workflows/{workflow}')['jobs']
    qualification = jobs['parakeet_qualification']
    assert qualification['uses'] == './.github/workflows/parakeet_gpu_tests.yml'
    assert 'firestore_readiness' in qualification['needs']
    assert qualification['with']['source_sha'] == '${{ needs.firestore_readiness.outputs.admitted_sha }}'
    assert qualification['with']['build_source'] is True
    deployment = jobs['deploy']
    assert 'parakeet_qualification' in deployment['needs']
    steps = deployment['steps']
    download = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('actions/download-artifact@'))
    deploy = next(i for i, step in enumerate(steps) if step.get('uses') == './.github/actions/deploy-backend-stack')
    assert download < deploy
    assert steps[download]['with']['name'] == '${{ needs.parakeet_qualification.outputs.artifact_name }}'
    assert steps[deploy]['with']['parakeet_image_ref'] == '${{ needs.parakeet_qualification.outputs.image_ref }}'
    assert (
        steps[deploy]['with']['parakeet_qualification_evidence']
        == '${{ steps.parakeet-qualification-evidence.outputs.path }}'
    )


def test_cloud_run_only_ptt_also_requires_capacity_before_runtime_render():
    steps = _yaml('.github/actions/deploy-backend-stack/action.yml')['runs']['steps']
    capacity = next(i for i, step in enumerate(steps) if step.get('id') == 'parakeet-stream')
    image = next(step for step in steps if step.get('id') == 'parakeet-image')
    assert 'if' not in steps[capacity]
    assert 'if' not in image
    assert 'docker build' not in image['run']
    rendered = [i for i, step in enumerate(steps) if 'render_backend_runtime_env.py' in step.get('run', '')]
    assert rendered and all(capacity < i for i in rendered)
    assert '--qualification-evidence' in steps[capacity]['run']
    assert '--source-sha' in steps[capacity]['run']


def test_gpu_cleanup_is_independent_of_timed_out_test_job():
    jobs = _yaml('.github/workflows/parakeet_gpu_tests.yml')['jobs']
    cleanup = jobs['cleanup']
    assert cleanup['needs'] == 'gpu-tests'
    assert cleanup['if'] in ('always()', '${{ always() }}')
    assert cleanup['environment'] == 'development'
    assert cleanup['timeout-minutes'] <= 15
    assert jobs['gpu-tests']['environment'] == 'development'
