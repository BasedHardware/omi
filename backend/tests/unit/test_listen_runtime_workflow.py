"""Evidence runtime preserves admitted deployment routing and writer bodies."""

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_no_public_ci_route_and_original_writer_dependencies():
    data = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    events = data.get('on', data.get(True))
    assert set(events) == {'push', 'workflow_dispatch'}
    assert events['push'] == {
        'branches': ['main'],
        'paths': ['backend/charts/backend-listen/**', 'backend/charts/backend-secrets/**'],
    }
    assert set(data['jobs']) == {'helm-upgrade', 'deploy-neg-coverage-exporter'}
    assert not {'if', 'needs'} & set(data['jobs']['helm-upgrade'])
    assert data['concurrency'] == {
        'group': "${{ github.event.inputs.environment == 'prod' && github.event.inputs.break_glass_lock != 'true' && 'prod-train' || format('deploy-backend-stack-{0}', github.event.inputs.environment || 'development') }}",
        'cancel-in-progress': False,
    }


def test_verified_runtime_precedes_credentials_and_private_overlay():
    data = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    job = data['jobs']['helm-upgrade']
    steps = {s['name']: s for s in job['steps']}
    order = list(steps)
    assert order.index('Reconstruct evidence runtime before credentials') < order.index('Google Auth (prod WIF)')
    assert steps['Reconstruct evidence runtime before credentials']['if'] == "${{ inputs.mode == 'evidence' }}"
    assert steps['Install Helm']['if'] == "${{ inputs.mode != 'evidence' }}"
    assert '-I -B' in steps['Produce private-overlay effect receipt without mutation']['run']
    assert job['runs-on'] == "${{ inputs.mode == 'evidence' && 'ubuntu-22.04' || 'ubuntu-latest' }}"
