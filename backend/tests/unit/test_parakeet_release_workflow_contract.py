"""Structural release wiring tests; live GPU execution is a separate gate."""

from pathlib import Path
import os
import subprocess
import tempfile

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


def test_gpu_capacity_validation_generates_levels_and_target_for_each_capacity():
    steps = _yaml('.github/workflows/parakeet_gpu_tests.yml')['jobs']['gpu-tests']['steps']
    capacity_step = next(step for step in steps if step.get('name') == 'Validate stream capacity input')
    script = capacity_step['run']
    expected = {
        1: ('1', '1'),
        4: ('1,3,4', '3'),
        10: ('1,5,8,10', '8'),
        25: ('1,5,10,20,25', '20'),
        64: ('1,5,10,20,25,51,64', '51'),
    }
    for capacity, (levels, target) in expected.items():
        with tempfile.NamedTemporaryFile() as output:
            environment = os.environ | {
                'REQUESTED_STREAM_CAPACITY': str(capacity),
                'GITHUB_OUTPUT': output.name,
            }
            subprocess.run(['bash', '-euo', 'pipefail', '-c', script], check=True, env=environment)
            output.seek(0)
            values = dict(line.decode().rstrip('\n').split('=', 1) for line in output if b'=' in line)
        assert values['stream_levels'] == levels
        assert values['target_streams'] == target

    for invalid in ('0', '65', 'abc', '-1', '1.5'):
        with tempfile.NamedTemporaryFile() as output:
            environment = os.environ | {
                'REQUESTED_STREAM_CAPACITY': invalid,
                'GITHUB_OUTPUT': output.name,
            }
            result = subprocess.run(['bash', '-euo', 'pipefail', '-c', script], env=environment)
        assert result.returncode != 0


def test_gpu_capacity_variables_are_explicitly_allowlisted_and_passed_to_job():
    steps = _yaml('.github/workflows/parakeet_gpu_tests.yml')['jobs']['gpu-tests']['steps']
    create = next(step for step in steps if step.get('name') == 'Create GPU test job')
    run = create['run']
    assert (
        "envsubst '$JOB_NAME $NAMESPACE $IMAGE_REF $RUN_ID $STREAM_CAPACITY $STREAM_LEVELS $TARGET_STREAMS $SOURCE_SHA'"
        in run
    )
    template = 'apiVersion:' + run.split('\napiVersion:', 1)[1].split('\nJOBEOF', 1)[0]
    pod_env = {
        entry['name']: entry.get('value')
        for entry in yaml.safe_load(template)['spec']['template']['spec']['containers'][0]['env']
    }
    assert pod_env['PARAKEET_STREAM_LEVELS'] == '${STREAM_LEVELS}'
    assert pod_env['PARAKEET_TARGET_STREAMS'] == '${TARGET_STREAMS}'
    assert create['env']['STREAM_LEVELS'] == '${{ steps.capacity.outputs.stream_levels }}'
    assert create['env']['TARGET_STREAMS'] == '${{ steps.capacity.outputs.target_streams }}'


def test_gpu_qualification_uses_the_stream_deploy_resource_envelope():
    """Measured CPU-bound stream capacity must correspond to the deployed pod budget."""
    steps = _yaml('.github/workflows/parakeet_gpu_tests.yml')['jobs']['gpu-tests']['steps']
    script = next(step['run'] for step in steps if step.get('name') == 'Create GPU test job')
    template = 'apiVersion:' + script.split('\napiVersion:', 1)[1].split('\nJOBEOF', 1)[0]
    pod = yaml.safe_load(template)['spec']['template']['spec']
    tested = pod['containers'][0]['resources']
    for environment in ('dev', 'prod'):
        deployed = _yaml(f'backend/charts/parakeet/{environment}_omi_parakeet_stream_values.yaml')['resources']
        assert tested == deployed
