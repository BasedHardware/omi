"""Every step is classified; evidence never reaches an existing writer."""

from pathlib import Path
import copy
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
EXACT_CONTROL = 'Verify exact listen control SHA'
EXPECTED = [
    'Validate Environment Input',
    'Checkout',
    EXACT_CONTROL,
    'Bind shared record token lease rollout inputs',
    'Admit checked-out production source and image identity',
    'Install Helm',
    'Google Auth (prod WIF)',
    'Google Auth',
    'Set up gcloud',
    'Get GKE credentials',
    'Checkout trusted overlay evidence controls',
    'Install evidence parser before secret injection',
    'Produce private-overlay effect receipt without mutation',
    'Upload only the sanitized overlay receipt',
    'Remove evidence private files',
    'Show Helm release history',
    'Resolve backend-listen image tag',
    'Login to GCR for the listen-edge image read',
    'Set up Docker Buildx for the listen-edge image read',
    'Admit listen-edge image digest',
    'Materialize private listen-edge values (prod only)',
    'Checkout immutable Firestore gate controls',
    'Verify serving Firestore indexes',
    'Install private-env parser before secret injection',
    'Write private listen values to Secret Manager (no roll)',
    'Apply the listen private-env ExternalSecret (no roll)',
    'Force-sync and verify private listen env against live (no roll)',
    'Carry forward config this workflow does not own',
    'Apply non-secret backend runtime config',
    'Ensure dev parity-pack bucket (development only)',
    'Resolve optional listen env overrides',
    'Helm diff (dry run)',
    'Upgrade backend-secrets Helm chart',
    'Prove private listen env is unchanged',
    'Upgrade backend-listen Helm chart',
    'Roll back backend-listen Helm release',
    'Verify rollout',
    'Reconcile prod listen NEG zones on the LB backend',
    'Upgrade listen-edge Helm chart',
    'Show listen-edge pod status',
    'Remove private listen-edge values file',
    'Show pod status',
]
SAFE = {
    'Validate Environment Input',
    'Checkout',
    EXACT_CONTROL,
    'Admit checked-out production source and image identity',
    'Install Helm',
    'Google Auth (prod WIF)',
    'Google Auth',
    'Set up gcloud',
    'Get GKE credentials',
}
NATIVE = {
    'Resolve backend-listen image tag',
    'Checkout immutable Firestore gate controls',
    'Verify serving Firestore indexes',
}
# One-time private-env migration (prod, no roll): only ever runs in its own mode, never in evidence.
MIGRATE = {
    'Install private-env parser before secret injection',
    'Write private listen values to Secret Manager (no roll)',
    'Apply the listen private-env ExternalSecret (no roll)',
    'Force-sync and verify private listen env against live (no roll)',
}
EVIDENCE = {
    'Checkout trusted overlay evidence controls',
    'Install evidence parser before secret injection',
    'Produce private-overlay effect receipt without mutation',
    'Upload only the sanitized overlay receipt',
    'Remove evidence private files',
}


def qualify(doc):
    job = doc['jobs']['helm-upgrade']
    assert [s['name'] for s in job['steps']] == EXPECTED
    guard = job['steps'][2]
    assert guard['if'] == "${{ inputs.control_sha != '' }}"
    assert '"$DEPLOY_MODE" != deploy' in guard['run']
    for step in job['steps']:
        if step['name'] in SAFE:
            continue
        if step['name'] in NATIVE:
            if step['name'] == 'Resolve backend-listen image tag':
                assert step['if'] == "${{ (github.event.inputs.mode || 'deploy') == 'deploy' }}"
                assert step['run'].count('BACKEND_LISTEN_SOURCE_SHA') == 1
            else:
                assert step['if'] == "${{ env.BACKEND_LISTEN_SOURCE_SHA != '' }}"
            continue
        expr = step.get('if', '')
        if step['name'] in MIGRATE:
            assert expr == "${{ inputs.mode == 'private-env-migrate' }}"
            continue
        if step['name'] in EVIDENCE:
            assert "inputs.mode == 'evidence'" in expr
        else:
            assert expr.startswith("${{ inputs.mode != 'evidence' &&") or expr == "${{ inputs.mode != 'evidence' }}"
    for name, other in doc['jobs'].items():
        if name != 'helm-upgrade':
            assert "inputs.mode == 'deploy'" in other.get('if', '')
    assert job['environment'] == "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"
    assert doc['concurrency']['cancel-in-progress'] is False


@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancelled'])
def test_all_steps_and_downstream_jobs_refuse_evidence_writers(outcome):
    doc = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    qualify(doc)
    for step in doc['jobs']['helm-upgrade']['steps']:
        if step['name'] not in SAFE | EVIDENCE | NATIVE | MIGRATE:
            # First conjunction is false regardless of success(), always(), or cancellation.
            assert "inputs.mode != 'evidence'" in step['if']
    clean = next(s for s in doc['jobs']['helm-upgrade']['steps'] if s['name'] == 'Remove evidence private files')
    assert 'always()' in clean['if']
    assert clean['run'].startswith('rm -rf -- "$RUNNER_TEMP/listen-overlay-evidence"')


def test_new_unclassified_step_fails_closed_even_if_name_sounds_safe():
    doc = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    doc['jobs']['helm-upgrade']['steps'].append({'name': 'Read-only preview', 'run': 'kubectl apply -f x'})
    with pytest.raises(AssertionError):
        qualify(doc)


def test_evidence_uses_control_sha_and_exact_candidate_not_deploy_for_evidence():
    doc = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    steps = {s['name']: s for s in doc['jobs']['helm-upgrade']['steps']}
    assert steps['Checkout trusted overlay evidence controls']['with']['ref'] == '${{ github.workflow_sha }}'
    assert "inputs.expected_sha" in steps['Checkout']['with']['ref']
    assert 'LISTEN_PRIVATE_VALUES_YAML' not in steps['Install evidence parser before secret injection'].get('env', {})
    upload = steps['Upload only the sanitized overlay receipt']['with']
    assert upload['path'] == '${{ runner.temp }}/listen-overlay-receipt.json'
    assert '*' not in upload['path']


def test_native_index_gate_cannot_run_in_evidence_because_only_sha_writer_is_deploy_only():
    doc = yaml.safe_load((ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text())
    steps = doc['jobs']['helm-upgrade']['steps']
    writers = [s for s in steps if 'echo "BACKEND_LISTEN_SOURCE_SHA=' in s.get('run', '')]
    assert len(writers) == 1
    assert writers[0]['name'] == 'Resolve backend-listen image tag'
    assert writers[0]['if'] == "${{ (github.event.inputs.mode || 'deploy') == 'deploy' }}"
    assert 'BACKEND_LISTEN_SOURCE_SHA' not in doc.get('env', {})
    assert 'BACKEND_LISTEN_SOURCE_SHA' not in doc['jobs']['helm-upgrade'].get('env', {})
