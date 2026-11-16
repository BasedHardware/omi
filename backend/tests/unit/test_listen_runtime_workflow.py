"""CI-only routing cannot reach any existing protected deployment job."""

import copy
import ast
from functools import lru_cache
import itertools
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
GUARD = "${{ !cancelled() && (github.event_name == 'workflow_dispatch' || (github.event_name == 'push' && needs.runtime-reconstruction.result == 'success' && needs.runtime-reconstruction.outputs.deploy == 'true')) }}"


@lru_cache(maxsize=1)
def loaded():
    return yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())


def doc():
    return copy.deepcopy(loaded())


def evaluate(node):
    if isinstance(node, ast.Expression):
        return evaluate(node.body)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Compare):
        assert len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
        return evaluate(node.left) == evaluate(node.comparators[0])
    assert isinstance(node, ast.BoolOp)
    return (
        all(evaluate(n) for n in node.values) if isinstance(node.op, ast.And) else any(evaluate(n) for n in node.values)
    )


def qualified(data):
    assert set(data['jobs']) == {'runtime-reconstruction', 'helm-upgrade', 'deploy-neg-coverage-exporter'}
    proof = data['jobs']['runtime-reconstruction']
    assert proof['if'] == "github.event_name != 'workflow_dispatch'"
    assert proof['runs-on'] == 'ubuntu-22.04' and proof['timeout-minutes'] == 5
    assert proof['permissions'] == {'contents': 'read'}
    assert not ({'environment', 'strategy', 'secrets', 'env'} & set(proof))
    assert [s['name'] for s in proof['steps']] == [
        'Checkout exact reconstruction source',
        'Classify bounded source paths',
        'Reconstruct and prove runtime identities',
    ]
    assert proof['steps'][0]['with']['persist-credentials'] is False
    assert proof['steps'][1]['run'] == 'python3 .github/scripts/listen_runtime.py classify'
    assert proof['steps'][2]['if'] == "steps.paths.outputs.runtime == 'true'"
    assert 'listen_runtime.py reconstruct' in proof['steps'][2]['run']
    text = yaml.safe_dump(proof)
    for forbidden in ('id-token', 'secrets.', 'gcloud', 'kubectl', 'helm upgrade', 'upload-artifact', 'WIF'):
        assert forbidden not in text
    writer = data['jobs']['helm-upgrade']
    assert writer['needs'] == 'runtime-reconstruction' and writer['if'] == GUARD
    exporter = data['jobs']['deploy-neg-coverage-exporter']
    assert exporter['needs'] == 'helm-upgrade' and exporter['if'].startswith("${{ inputs.mode == 'deploy' &&")
    steps = {s['name']: s for s in writer['steps']}
    order = list(steps)
    assert order.index('Reconstruct evidence runtime before credentials') < order.index('Google Auth (prod WIF)')
    assert steps['Install Helm']['if'] == "${{ inputs.mode != 'evidence' }}"
    assert '-I -B' in steps['Produce private-overlay effect receipt without mutation']['run']
    assert "listen-runtime-ci-" in data['concurrency']['group']
    assert "'prod-train'" in data['concurrency']['group'] and data['concurrency']['cancel-in-progress'] is False


def test_exact_closed_ci_job_and_precredential_runtime_order():
    qualified(doc())


@pytest.mark.parametrize(
    'event,result,deploy,cancelled',
    itertools.product(
        ['pull_request', 'push', 'workflow_dispatch', 'unknown'],
        ['success', 'failure', 'cancelled', 'skipped'],
        ['true', 'false', ''],
        [True, False],
    ),
)
def test_actual_job_expression_refuses_ci_and_unknown_routing_even_after_always(event, result, deploy, cancelled):
    data = doc()
    qualified(data)
    expr = data['jobs']['helm-upgrade']['if'][3:-2].strip()
    expr = expr.replace('!cancelled()', str(not cancelled)).replace('github.event_name', repr(event))
    expr = expr.replace('needs.runtime-reconstruction.result', repr(result))
    expr = expr.replace('needs.runtime-reconstruction.outputs.deploy', repr(deploy))
    actual = evaluate(ast.parse(expr.replace('&&', ' and ').replace('||', ' or '), mode='eval'))
    expected = not cancelled and (
        event == 'workflow_dispatch' or event == 'push' and result == 'success' and deploy == 'true'
    )
    assert actual == expected
    if event in {'pull_request', 'unknown'}:
        assert actual is False  # All writer step outcomes, including always(), are fenced by this job.


@pytest.mark.parametrize('fault', ['new-job', 'new-step', 'oidc', 'environment', 'writer-condition', 'matrix'])
def test_unclassified_or_privilege_expanded_ci_route_refuses(fault):
    data = copy.deepcopy(doc())
    proof = data['jobs']['runtime-reconstruction']
    if fault == 'new-job':
        data['jobs']['new-writer'] = {'run': 'kubectl apply -f x'}
    elif fault == 'new-step':
        proof['steps'].append({'name': 'Safe discovery', 'run': 'gcloud x'})
    elif fault == 'oidc':
        proof['permissions']['id-token'] = 'write'
    elif fault == 'environment':
        proof['environment'] = 'prod'
    elif fault == 'matrix':
        proof['strategy'] = {'matrix': {'x': [1, 2]}}
    else:
        data['jobs']['helm-upgrade']['if'] = '${{ always() }}'
    with pytest.raises(AssertionError):
        qualified(data)
