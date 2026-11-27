"""The LLM gateway image-ownership handoff removes one managed-fields entry and nothing else.

Helm 4 applies as field manager ``helm`` and refuses to change the image while a ``kubectl-patch``
entry owns it (SCA-4959). ``scripts/handoff-llm-gateway-image-ownership.py`` gives that leaf back.
These tests pin what it may remove, what it must refuse, and the exact kubectl calls it makes.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_TOOL = BACKEND_ROOT / 'scripts/handoff-llm-gateway-image-ownership.py'
DEPLOY_HELPER = BACKEND_ROOT / 'scripts/deploy-llm-gateway.sh'
RUNBOOK = BACKEND_ROOT / 'docs/runbooks/llm-gateway-image-ownership.md'

NAMESPACE, NAME, CONTAINER = 'prod-omi-backend', 'prod-omi-llm-gateway', 'llm-gateway'
PATCH_MANAGER = 'kubectl-patch'
LIST_KEY = 'k:{"name":"llm-gateway"}'
PATCHED_IMAGE = 'gcr.io/based-hardware/llm-gateway@sha256:' + 'b' * 64
CONFLICT = (
    f'Apply failed with 1 conflict: conflict with "{PATCH_MANAGER}" using apps/v1: '
    f'.spec.template.spec.containers[name="{CONTAINER}"].image'
)
NEXT_MANIFEST = Path('next-deployment.yaml')


@pytest.fixture(scope='module')
def handoff():
    spec = importlib.util.spec_from_file_location('llm_gateway_image_ownership_handoff', HANDOFF_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered_deployment(name: str = NAME, *, kind: str = 'Deployment', namespace: str = '') -> str:
    """The Deployment as `helm template --show-only templates/deployment.yaml` renders it: no namespace."""
    lines = [
        '# Source: llm-gateway/templates/deployment.yaml',
        'apiVersion: apps/v1',
        f'kind: {kind}',
        'metadata:',
        f'  name: {name}',
        *([f'  namespace: {namespace}'] if namespace else []),
        'spec:',
        '  template:',
        '    spec:',
        '      containers:',
        f'        - name: {CONTAINER}',
        f'          image: {PATCHED_IMAGE}',
    ]
    return '\n'.join(lines) + '\n'


def write_manifest(root: Path, text: str | None) -> Path:
    path = root / NEXT_MANIFEST
    if text is not None:
        path.write_text(text, encoding='utf-8')
    return path


@pytest.fixture
def next_deployment(tmp_path) -> Path:
    return write_manifest(tmp_path, rendered_deployment())


def image_only() -> dict[str, Any]:
    return {'f:spec': {'f:template': {'f:spec': {'f:containers': {LIST_KEY: {'f:image': {}}}}}}}


def entry(manager: str, operation: str, fields: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        'manager': manager,
        'operation': operation,
        'apiVersion': 'apps/v1',
        'time': 't',
        'fieldsV1': fields,
        **extra,
    }


CONTROLLER_ENTRY = entry(
    'kube-controller-manager',
    'Update',
    {
        'f:metadata': {'f:annotations': {'.': {}, 'f:deployment.kubernetes.io/revision': {}}},
        'f:spec': {'f:replicas': {}, 'f:template': {'f:metadata': {'f:labels': {'.': {}, 'f:pod-template-hash': {}}}}},
        'f:status': {},
    },
)
HELM_ENTRY = entry(
    'helm',
    'Apply',
    {
        'f:metadata': {
            'f:annotations': {'.': {}, 'f:meta.helm.sh/release-name': {}},
            'f:labels': {'.': {}, 'f:app.kubernetes.io/managed-by': {}},
        },
        'f:spec': {
            'f:progressDeadlineSeconds': {},
            'f:template': {'f:spec': {'f:containers': {LIST_KEY: {'f:image': {}, 'f:name': {}}}}},
        },
    },
)
PATCH_ENTRY = entry(PATCH_MANAGER, 'Update', image_only())


def deployment(entries: list[dict[str, Any]], image: str = PATCHED_IMAGE) -> dict[str, Any]:
    return {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {
            'name': NAME,
            'namespace': NAMESPACE,
            'resourceVersion': '23330',
            'generation': 9,
            'labels': {'app.kubernetes.io/managed-by': 'Helm', 'app.kubernetes.io/name': 'llm-gateway'},
            'annotations': {'meta.helm.sh/release-name': NAME, 'deployment.kubernetes.io/revision': '9'},
            'managedFields': copy.deepcopy(entries),
        },
        'spec': {
            'replicas': 2,
            'selector': {'matchLabels': {'app': 'llm-gateway'}},
            'template': {'spec': {'containers': [{'name': CONTAINER, 'image': image}]}},
        },
        'status': {'readyReplicas': 2},
    }


def conflicting() -> dict[str, Any]:
    return deployment([CONTROLLER_ENTRY, PATCH_ENTRY, HELM_ENTRY])


class FakeKubectl:
    """Records every call and answers the way the API server would in a scripted scenario."""

    def __init__(
        self,
        *,
        reads: list[dict[str, Any]],
        patch_preview: dict[str, Any] | None = None,
        patch_error: str | None = None,
        applies: list[tuple[int, str]] | None = None,
    ) -> None:
        self.reads = reads
        self.patch_preview = patch_preview
        self.patch_error = patch_error
        self.applies = list(applies or [])
        self.calls: list[list[str]] = []
        self.patch_bodies: list[list[dict[str, Any]]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess:
        args = list(args)
        self.calls.append(args)
        if 'apply' in args:
            code, stderr = self.applies.pop(0)
            return subprocess.CompletedProcess(args, code, '', stderr)
        if 'patch' in args:
            patch_file = next(arg.removeprefix('--patch-file=') for arg in args if arg.startswith('--patch-file='))
            self.patch_bodies.append(json.loads(Path(patch_file).read_text(encoding='utf-8')))
            if '--dry-run=server' in args:
                if self.patch_error is not None:
                    return subprocess.CompletedProcess(args, 1, '', self.patch_error)
                return subprocess.CompletedProcess(args, 0, json.dumps(self.patch_preview), '')
            return subprocess.CompletedProcess(args, 0, '', '')
        if 'get' in args:
            payload = self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), '')
        raise AssertionError(f'unexpected kubectl call {args}')

    def verbs(self) -> list[str]:
        return [call[2] for call in self.calls]


@pytest.mark.parametrize('index', [0, 1, 2])
def test_image_only_patch_entry_is_planned_as_its_own_removal(handoff, index):
    entries = [CONTROLLER_ENTRY, HELM_ENTRY]
    entries.insert(index, PATCH_ENTRY)
    live = deployment(entries)

    plan = handoff.plan_handoff(live, CONTAINER, PATCH_MANAGER)

    assert plan['index'] == index
    assert plan['resource_version'] == '23330'
    tests = plan['patch'][:-1]
    assert [operation['op'] for operation in tests] == ['test'] * 5
    assert all(
        operation['path'].startswith(f'/metadata/managedFields/{index}/')
        or operation['path'] == '/metadata/resourceVersion'
        for operation in tests
    )
    assert plan['patch'][-1] == {'op': 'remove', 'path': f'/metadata/managedFields/{index}'}
    assert tests[-1]['value'] == image_only()


def test_entry_owning_more_than_the_image_is_refused(handoff):
    fields = image_only()
    fields['f:spec']['f:template']['f:spec']['f:containers'][LIST_KEY]['f:resources'] = {'f:limits': {'f:cpu': {}}}
    live = deployment([CONTROLLER_ENTRY, HELM_ENTRY, entry(PATCH_MANAGER, 'Update', fields)])

    with pytest.raises(handoff.Refused) as refused:
        handoff.plan_handoff(live, CONTAINER, PATCH_MANAGER)

    assert (
        'it also owns f:spec.f:template.f:spec.f:containers.k:{"name":"llm-gateway"}.f:resources.f:limits.f:cpu'
        in str(refused.value)
    )
    assert str(refused.value).startswith(f'{PATCH_MANAGER}/Update owns more than the {CONTAINER} image')


@pytest.mark.parametrize(
    ('change', 'detail'),
    [
        ({'operation': 'Apply'}, "its operation is 'Apply'"),
        ({'apiVersion': 'extensions/v1beta1'}, "its apiVersion is 'extensions/v1beta1'"),
        ({'subresource': 'scale'}, "it targets the 'scale' subresource"),
    ],
)
def test_patch_entry_of_the_wrong_shape_is_refused(handoff, change, detail):
    live = deployment([CONTROLLER_ENTRY, HELM_ENTRY, dict(entry(PATCH_MANAGER, 'Update', image_only()), **change)])

    with pytest.raises(handoff.Refused) as refused:
        handoff.plan_handoff(live, CONTAINER, PATCH_MANAGER)

    assert detail in str(refused.value)


def test_the_same_manager_owning_the_image_twice_is_refused(handoff):
    live = deployment([CONTROLLER_ENTRY, HELM_ENTRY, PATCH_ENTRY, dict(PATCH_ENTRY, time='later')])

    with pytest.raises(handoff.Refused) as refused:
        handoff.plan_handoff(live, CONTAINER, PATCH_MANAGER)

    assert 'owns the llm-gateway image through 2 managed-fields entries' in str(refused.value)


def test_an_object_helm_does_not_apply_is_refused(handoff):
    labels_only = deployment([CONTROLLER_ENTRY, PATCH_ENTRY, HELM_ENTRY])
    del labels_only['metadata']['annotations']['meta.helm.sh/release-name']
    no_apply_entry = deployment([CONTROLLER_ENTRY, PATCH_ENTRY, CONTROLLER_ENTRY])

    with pytest.raises(handoff.Refused, match='is not a Helm-managed object'):
        handoff.plan_handoff(labels_only, CONTAINER, PATCH_MANAGER)
    with pytest.raises(handoff.Refused, match="Helm has no server-side apply entry"):
        handoff.plan_handoff(no_apply_entry, CONTAINER, PATCH_MANAGER)


def test_no_out_of_band_owner_means_there_is_nothing_to_hand_off(handoff):
    assert handoff.plan_handoff(deployment([CONTROLLER_ENTRY, HELM_ENTRY]), CONTAINER, PATCH_MANAGER) is None


def test_plan_only_sends_the_patch_as_a_server_dry_run_and_never_applies_it(handoff, capsys):
    live = conflicting()
    kubectl = FakeKubectl(reads=[live], patch_preview=handoff.expected_after(live, 1))

    assert handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, None, False) == 0

    assert kubectl.verbs() == ['get', 'patch']
    preview = kubectl.calls[1]
    assert kubectl.calls[0] == ['-n', NAMESPACE, 'get', 'deployment', NAME, '--show-managed-fields', '-o', 'json']
    assert '--dry-run=server' in preview and '--type=json' in preview
    assert f'--field-manager={handoff.HANDOFF_MANAGER}' in preview
    assert preview[:2] == ['-n', NAMESPACE] and preview[2:4] == ['patch', 'deployment'] and preview[4] == NAME
    assert kubectl.patch_bodies == [handoff.plan_handoff(live, CONTAINER, PATCH_MANAGER)['patch']]
    assert 'plan only' in capsys.readouterr().out


def test_apply_patches_once_then_rereads_and_proves_the_ordinary_apply_now_passes(handoff, next_deployment, capsys):
    live = conflicting()
    after = handoff.expected_after(live, 1)
    kubectl = FakeKubectl(reads=[live, after], patch_preview=after, applies=[(1, f'error: {CONFLICT}\n'), (0, '')])

    assert handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, next_deployment, True) == 0

    assert kubectl.verbs() == ['get', 'apply', 'patch', 'patch', 'get', 'apply']
    preview, applied = kubectl.calls[2], kubectl.calls[3]
    assert '--dry-run=server' in preview and '--dry-run=server' not in applied
    for call in (kubectl.calls[1], kubectl.calls[5]):
        assert call[2:4] == ['apply', '--server-side'] and '--dry-run=server' in call and '--field-manager=helm' in call
    out = capsys.readouterr().out
    assert f'ordinary Helm apply before handoff: conflicts with {PATCH_MANAGER}' in out
    assert 'ordinary Helm apply after handoff: passes' in out


def test_a_server_dry_run_that_differs_from_the_plan_is_refused_before_any_write(handoff):
    live = conflicting()
    drifted = handoff.expected_after(live, 1)
    drifted['spec']['replicas'] = 1
    kubectl = FakeKubectl(reads=[live], patch_preview=drifted)

    with pytest.raises(handoff.Refused, match='would change spec; nothing was changed'):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, None, True)

    assert kubectl.verbs() == ['get', 'patch'] and '--dry-run=server' in kubectl.calls[1]


def test_a_patch_the_server_rejects_is_a_refusal_not_a_write(handoff):
    kubectl = FakeKubectl(
        reads=[conflicting()], patch_error='error: the server rejected our request due to an error in our request'
    )

    with pytest.raises(handoff.Refused, match='the server rejected the planned patch; nothing was changed'):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, None, True)

    assert kubectl.verbs() == ['get', 'patch']


def test_an_ordinary_apply_that_fails_for_another_reason_stops_the_handoff(handoff, next_deployment):
    kubectl = FakeKubectl(
        reads=[conflicting()], applies=[(1, 'error: Internal error occurred: failed calling webhook')]
    )

    with pytest.raises(handoff.Refused, match='the ordinary Helm apply fails for another reason'):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, next_deployment, True)

    assert kubectl.verbs() == ['get', 'apply']


@pytest.mark.parametrize(
    ('manifest', 'detail'),
    [
        pytest.param(rendered_deployment('dev-omi-llm-gateway'), 'dev-omi-llm-gateway', id='another-deployment'),
        pytest.param(
            rendered_deployment(namespace='dev-omi-backend'),
            'dev-omi-backend/prod-omi-llm-gateway',
            id='another-namespace',
        ),
        pytest.param(
            rendered_deployment(kind='Service'),
            'Service prod-omi-backend/prod-omi-llm-gateway',
            id='same-named-service',
        ),
        pytest.param(f'{rendered_deployment()}---\n{rendered_deployment()}', 'holds 2 objects', id='two-objects'),
        pytest.param('', 'holds 0 objects', id='empty'),
        pytest.param(None, 'could not read the next Deployment', id='missing-file'),
    ],
)
def test_a_next_deployment_manifest_for_another_object_is_refused_before_any_dry_run(
    handoff, tmp_path, manifest, detail
):
    """The before/after proof is about this Deployment only when the manifest is this Deployment."""
    kubectl = FakeKubectl(reads=[conflicting()])
    path = write_manifest(tmp_path, manifest)

    with pytest.raises(handoff.Refused, match=re.escape(detail)):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, path, True)

    assert kubectl.verbs() == ['get'], 'nothing is dry-run or patched with a manifest of another object'


def test_a_readback_that_differs_from_the_plan_is_a_verification_failure(handoff):
    live = conflicting()
    after = handoff.expected_after(live, 1)
    after['metadata']['generation'] = 10
    kubectl = FakeKubectl(reads=[live, after], patch_preview=handoff.expected_after(live, 1))

    with pytest.raises(
        handoff.VerificationFailed, match='the Deployment changed outside the plan after the patch: generation'
    ):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, None, True)

    assert kubectl.verbs() == ['get', 'patch', 'patch', 'get']


def test_an_ordinary_apply_that_still_conflicts_after_the_handoff_is_a_verification_failure(handoff, next_deployment):
    live = conflicting()
    after = handoff.expected_after(live, 1)
    kubectl = FakeKubectl(
        reads=[live, after], patch_preview=after, applies=[(1, f'error: {CONFLICT}\n'), (1, f'error: {CONFLICT}\n')]
    )

    with pytest.raises(handoff.VerificationFailed, match='the ordinary Helm apply still fails'):
        handoff.run_handoff(kubectl, NAMESPACE, NAME, CONTAINER, PATCH_MANAGER, next_deployment, True)


def test_main_maps_outcomes_to_exit_codes(handoff, monkeypatch):
    live = conflicting()
    kubectl = FakeKubectl(reads=[live], patch_preview=handoff.expected_after(live, 1))
    monkeypatch.setattr(handoff, 'kubectl_command', kubectl)
    assert handoff.main(['--namespace', NAMESPACE, '--deployment', NAME]) == 0
    assert kubectl.verbs() == ['get', 'patch']

    clean = deployment([CONTROLLER_ENTRY, HELM_ENTRY])
    kubectl = FakeKubectl(reads=[clean])
    monkeypatch.setattr(handoff, 'kubectl_command', kubectl)
    assert handoff.main(['--namespace', NAMESPACE, '--deployment', NAME, '--apply']) == 0
    assert kubectl.verbs() == ['get']

    fields = image_only()
    fields['f:spec']['f:template']['f:spec']['f:containers'][LIST_KEY]['f:resources'] = {'f:limits': {'f:cpu': {}}}
    kubectl = FakeKubectl(reads=[deployment([CONTROLLER_ENTRY, HELM_ENTRY, entry(PATCH_MANAGER, 'Update', fields)])])
    monkeypatch.setattr(handoff, 'kubectl_command', kubectl)
    assert handoff.main(['--namespace', NAMESPACE, '--deployment', NAME, '--apply']) == 3

    after = handoff.expected_after(live, 1)
    after['spec']['replicas'] = 1
    kubectl = FakeKubectl(reads=[live, after], patch_preview=handoff.expected_after(live, 1))
    monkeypatch.setattr(handoff, 'kubectl_command', kubectl)
    assert handoff.main(['--namespace', NAMESPACE, '--deployment', NAME, '--apply']) == 4


def test_the_repair_never_forces_a_conflict_and_the_deploy_failure_points_at_the_runbook():
    for path in (HANDOFF_TOOL, DEPLOY_HELPER):
        assert '--force-conflicts' not in path.read_text(encoding='utf-8'), path.name

    helper = DEPLOY_HELPER.read_text(encoding='utf-8')
    runbook = RUNBOOK.read_text(encoding='utf-8')
    assert f'backend/docs/runbooks/{RUNBOOK.name}' in helper
    assert f'backend/scripts/{HANDOFF_TOOL.name}' in runbook
    assert 'backend/scripts/proof-llm-gateway-ownership-handoff.sh' in runbook
