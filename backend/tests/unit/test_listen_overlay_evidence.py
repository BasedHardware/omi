"""Private-render and evidence-mode boundaries; no network or live cluster."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / '.github/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('listen_overlay_evidence', SCRIPTS / 'listen_overlay_evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def deployment(secret='kept-private', *, resource_version='10'):
    return {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {
            'name': evidence.TARGET,
            'namespace': evidence.NS,
            'uid': 'uid',
            'generation': 3,
            'resourceVersion': resource_version,
        },
        'spec': {
            'replicas': 2,
            'template': {
                'spec': {
                    'nodeSelector': {'pool': 'listen'},
                    'containers': [
                        {
                            'name': 'listen',
                            'envFrom': [{'configMapRef': {'name': 'public-config'}}],
                            'env': [
                                {'name': 'STT_CAP_DISPATCH_ENFORCEMENT', 'value': 'true'},
                                {'name': 'PRIVATE_TOKEN', 'value': secret},
                            ],
                        }
                    ],
                    'initContainers': [{'name': 'init', 'env': [{'name': 'MODE', 'value': 'ready'}]}],
                }
            },
        },
    }


def indexed(doc):
    return evidence.documents(yaml.safe_dump(doc))


def test_private_value_never_leaves_complete_comparison():
    before = deployment('old-private-value')
    wanted = deployment('new-private-value')
    base = deployment('chart-value')
    result = evidence.compare(indexed(wanted), indexed(before), indexed(base), {'PRIVATE_TOKEN'})
    encoded = json.dumps(result)
    for forbidden in ('old-private-value', 'new-private-value', 'chart-value', 'public-config'):
        assert forbidden not in encoded
    assert result['complete'] is True
    assert result['containers'] == ['containers/listen', 'initContainers/init']
    assert {(r['key'], r['effect']) for r in result['env']} == {
        ('MODE', 'same'),
        ('PRIVATE_TOKEN', 'changed'),
        ('STT_CAP_DISPATCH_ENFORCEMENT', 'same'),
    }
    assert result['documents'][0]['changes'] == []


@pytest.mark.parametrize('change', ['container', 'init-container', 'duplicate-env', 'policy', 'private-annotation'])
def test_incomplete_or_privacy_widening_render_refuses(change):
    live, wanted, base = deployment(), deployment(), deployment()
    pod = wanted['spec']['template']['spec']
    if change == 'container':
        pod['containers'].append({'name': 'unexpected'})
    elif change == 'init-container':
        pod['initContainers'] = []
    elif change == 'duplicate-env':
        pod['containers'][0]['env'].append({'name': 'PRIVATE_TOKEN', 'value': 'do-not-echo'})
    elif change == 'policy':
        pod['containers'][0]['env'][0]['value'] = 'false'
    else:
        wanted['metadata']['annotations'] = {'wrong': 'do-not-echo'}
    with pytest.raises(evidence.Refused):
        evidence.compare(indexed(wanted), indexed(live), indexed(base), {'PRIVATE_TOKEN'})


@pytest.mark.parametrize('kind', ['Secret', 'ExternalSecret', 'UnknownWriter'])
def test_unsupported_documents_never_become_partial_coverage(kind):
    with pytest.raises(evidence.Refused, match='unsupported_document'):
        evidence.documents(yaml.safe_dump({'apiVersion': 'v1', 'kind': kind, 'metadata': {'name': 'do-not-export'}}))


def test_duplicate_documents_and_duplicate_yaml_keys_refuse():
    data = yaml.safe_dump(deployment())
    with pytest.raises(evidence.Refused, match='duplicate_document'):
        evidence.documents(data + '\n---\n' + data)
    with pytest.raises(evidence.Refused, match='duplicate_key'):
        evidence.documents('kind: Service\nkind: Secret\n')


def test_full_hpa_replica_node_and_envfrom_effects_are_covered_without_values():
    old, desired = deployment(), deployment()
    desired['spec']['replicas'] = 3
    desired['spec']['template']['spec']['nodeSelector'] = {'pool': 'changed-private-looking-pool'}
    desired['spec']['template']['spec']['containers'][0]['envFrom'] = []
    result = evidence.compare(indexed(desired), indexed(old), indexed(desired), {'PRIVATE_TOKEN'})
    paths = result['documents'][0]['changes']
    assert '/spec/replicas' in paths
    assert '/spec/template/spec/nodeSelector/pool' in paths
    assert '/spec/template/spec/containers' in paths
    assert 'changed-private-looking-pool' not in json.dumps(result)
    hpa_before = {'spec': {'behavior': {'scaleDown': {'stabilizationWindowSeconds': 60}}, 'metrics': [1]}}
    hpa_after = copy.deepcopy(hpa_before)
    hpa_after['spec']['metrics'] = [2]
    assert evidence.changed_paths(hpa_before, hpa_after) == ['/spec/metrics']


def test_canonical_argv_preserves_override_order_and_uses_exact_same_deploy_prefix():
    args = evidence.helm_args(
        'chart',
        'values',
        'a' * 7,
        'based-hardware',
        'based-hardware',
        ['--set-string', 'env[0].value=off', '-f', '/private/file'],
    )
    assert args[-4:] == ['--set-string', 'env[0].value=off', '-f', '/private/file']
    dry = [*args, '--dry-run=client', '--output=json']
    assert dry[:-2] == args
    assert args[:6] == ['helm', '-n', evidence.NS, 'upgrade', '--install', evidence.TARGET]


def test_version_binds_uid_generation_and_resource_version():
    assert evidence.version(deployment()) == {'uid': 'uid', 'generation': 3, 'resourceVersion': '10'}
    doc = deployment()
    del doc['metadata']['resourceVersion']
    with pytest.raises(evidence.Refused):
        evidence.version(doc)


def test_rendered_key_union_includes_removed_and_added_keys():
    old, desired = deployment(), deployment()
    old['spec']['template']['spec']['containers'][0]['env'].append({'name': 'REMOVED', 'value': 'x'})
    desired['spec']['template']['spec']['containers'][0]['env'].append({'name': 'ADDED', 'value': 'y'})
    result = evidence.compare(indexed(desired), indexed(old), indexed(desired), {'PRIVATE_TOKEN'})
    assert ('REMOVED', 'removed') in {(r['key'], r['effect']) for r in result['env']}
    assert ('ADDED', 'added') in {(r['key'], r['effect']) for r in result['env']}


@pytest.mark.parametrize(
    'fault', [None, 'live-movement', 'wrong-source', 'wrong-image', 'wrong-attempt', 'helm-movement']
)
def test_complete_producer_uses_only_bounded_reads_and_refuses_changed_binding(tmp_path, fault):
    private_file = tmp_path / 'private.yaml'
    private_file.write_text('privateEnv:\n  PRIVATE_TOKEN: "never-publish-this-value"\n')
    event_file = tmp_path / 'event.json'
    inputs = dict(evidence.DISPATCH_DEFAULTS, expected_sha='b' * 40, image_tag='b' * 7)
    event_file.write_text(json.dumps({'inputs': {**inputs, 'evidence_request_id': 'a' * 32}}))
    req = {
        'schema': 1,
        'request_id': 'a' * 32,
        'created': 100,
        'expires': 1000,
        'candidate_sha': 'b' * 40,
        'control_sha': 'c' * 40,
        'target': evidence.TARGET,
        'namespace': evidence.NS,
        'bindings': {
            k: (
                'b' * 40
                if k == 'chart_tree'
                else (
                    'gke_based-hardware_us-central1_prod-omi-gke'
                    if k == 'cluster_context'
                    else '3.1.0' if k.endswith('version') else 'd' * 64
                )
            )
            for k in evidence.BINDING_FIELDS
        },
        'state': 'requested',
        'consumer_sha256': 'f' * 64,
        'release_actor': 'release-owner',
        'approvers': ['release-owner'],
        'helm_args': [],
        'dispatch_inputs': inputs,
        'overlay_updated_at': '2026-11-15T15:00:00Z',
        'overlay_state': 'present',
        'image': 'gcr.io/based-hardware/backend@sha256:' + 'e' * 64,
        'image_tag': 'b' * 7,
    }
    environment = {
        'GITHUB_REPOSITORY': 'BasedHardware/omi',
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_WORKFLOW_SHA': 'c' * 40,
        'GITHUB_EVENT_PATH': str(event_file),
        'GITHUB_RUN_ID': '123',
        'GITHUB_RUN_ATTEMPT': '2' if fault == 'wrong-attempt' else '1',
    }

    class Fake:
        calls = 0
        bytes = 0

        def __init__(self):
            self.commands = []
            self.objects = 0

        def run(self, args):
            self.commands.append(args)
            self.calls += 1
            if args[0] == 'git':
                if 'merge-base' in args:
                    return b''
                return (('0' if fault == 'wrong-source' else 'b') * 40).encode()
            if args[0] == 'gcloud':
                return ('sha256:' + ('0' if fault == 'wrong-image' else 'e') * 64).encode()
            if 'history' in args:
                n = getattr(self, 'histories', 0) + 1
                self.histories = n
                return json.dumps(
                    [{'status': 'deployed', 'revision': 2 if fault == 'helm-movement' and n > 1 else 1}]
                ).encode()
            if 'get' in args:
                return yaml.safe_dump(deployment('prior-private-value')).encode()
            assert args[0] == 'helm' and args[-2:] == ['--dry-run=client', '--output=json']
            value = 'never-publish-this-value' if '-f' in args[-4:] else 'chart-private-default'
            return json.dumps(
                {
                    'manifest': yaml.safe_dump(deployment(value)),
                    'hooks': [],
                    'info': {'notes': 'never-publish-notes'},
                    'ignored': 'never-publish-extra',
                }
            ).encode()

        def obj(self, *args):
            self.objects += 1
            return deployment(
                'prior-private-value', resource_version='11' if fault == 'live-movement' and self.objects > 1 else '10'
            )

    req['helm_args'] = evidence.helm_args(
        '<candidate>/backend/charts/backend-listen',
        '<candidate>/backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
        'b' * 7,
        'based-hardware',
        'based-hardware',
        ['-f', '<private-overlay>'],
    )
    values = tmp_path / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml'
    values.parent.mkdir(parents=True)
    values.write_text('privateEnv: {}\nenv: []\n')  # a pre-privateSecretEnv candidate
    reader = Fake()
    with patch.object(evidence, 'bindings', return_value=req['bindings']):
        if fault:
            with pytest.raises(evidence.Refused):
                evidence.produce(req, reader, environment, tmp_path, private_file, ['-f', str(private_file)], 200)
        else:
            result = evidence.produce(req, reader, environment, tmp_path, private_file, ['-f', str(private_file)], 200)
            assert result['run_attempt'] == '1'
            assert result['coverage']['env_key_count'] == 3
            assert 'never-publish-this-value' not in json.dumps(result)
            assert 'prior-private-value' not in json.dumps(result)
            assert 'never-publish-notes' not in json.dumps(result)
            assert 'never-publish-extra' not in json.dumps(result)
    for args in reader.commands:
        assert not (args[0] == 'kubectl' and 'apply' in args)
        if args[0] == 'helm' and 'upgrade' in args:
            assert '--dry-run=client' in args


def test_evidence_is_retired_once_the_candidate_declares_private_secret_env(tmp_path):
    values = tmp_path / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml'
    values.parent.mkdir(parents=True)
    values.write_text('privateSecretEnv:\n  secretName: s\n  keys: [STT_CAP_DISPATCH_COHORT]\nenv: []\n')
    request = {'state': 'requested'}
    with patch.object(evidence, 'validate_request'), pytest.raises(evidence.Refused) as caught:
        evidence.produce(request, None, {}, tmp_path, tmp_path / 'unused', [], 200)
    assert 'evidence_retired_private_secret_env' in str(caught.value)


def test_real_subprocess_output_is_capped_and_private_error_is_never_echoed(tmp_path):
    reader = evidence.Reader()
    with pytest.raises(evidence.Refused, match='read_output_bound'):
        reader.run([sys.executable, '-c', 'import sys;sys.stdout.write("x"*(20*1024*1024))'])
    request = tmp_path / 'invalid.json'
    request.write_text('{"private_payload":"never-log-this-canary",broken}')
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / 'listen_overlay_evidence.py'),
            'produce',
            '--request',
            str(request),
            '--output',
            str(tmp_path / 'receipt.json'),
        ],
        capture_output=True,
        timeout=5,
        text=True,
    )
    assert result.returncode == 3
    assert result.stdout == ''
    assert result.stderr.strip() == 'LISTEN_OVERLAY_EVIDENCE_REFUSED'
    assert not (tmp_path / 'receipt.json').exists()
