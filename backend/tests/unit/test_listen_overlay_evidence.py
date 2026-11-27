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


@pytest.mark.parametrize('rollback', [False, True])
@pytest.mark.parametrize('fault', [None, 'admission', 'sibling', 'reconnect', 'ambiguous'])
def test_image_only_reference_render_and_server_dry_run(rollback, fault):
    old = 'gcr.io/based-hardware/backend:96f0631'
    new = 'gcr.io/based-hardware/backend:6790e95'
    before, after = (new, old) if rollback else (old, new)
    installed = deployment()
    primary = installed['spec']['template']['spec']['containers'][0]
    primary.update(name='backend-listen', image=old)
    primary['env'] += [
        {'name': 'SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'value': 'false'},
        {'name': 'SYNC_POLL_BACKOFF_ENABLED', 'value': 'false'},
    ]
    if fault == 'reconnect':
        primary['env'].append({'name': 'LISTEN_BATCH_RECONNECT_ENABLED', 'value': 'true'})
    if fault == 'ambiguous':
        installed['spec']['template']['spec']['initContainers'][0]['image'] = old
    raw = yaml.safe_dump(installed)
    target = next(iter(indexed(installed)))
    live = copy.deepcopy(installed)
    live['spec']['template']['spec']['containers'][0]['image'] = before
    admitted = copy.deepcopy(live)
    admitted['spec']['template']['spec']['containers'][0]['image'] = after
    if fault == 'admission':
        admitted['spec']['template']['spec']['nodeSelector']['pool'] = 'another-pool'
    calls = []
    scopes = []

    class Reader:
        def run(self, argv):
            calls.append(argv)
            if argv[0] == 'helm':
                return raw.encode()
            assert argv[-1] == '--dry-run=server'
            return json.dumps(admitted).encode()

        def reference_objects(self, keys):
            assert keys == [target]
            return {target: live}

        def obj(self, kind, name, namespace):
            scopes.append((kind, name, namespace))
            return {'data': len(scopes) if fault == 'sibling' else 'unchanged'}

    with patch.object(evidence, 'release_revision', return_value=936):
        if fault:
            with pytest.raises(evidence.Refused):
                evidence.image_only_plan(Reader(), 936, before, after)
            return
        command, _, desired, _, proof = evidence.image_only_plan(Reader(), 936, before, after)
    assert len(calls) == 2 and calls[-1] == [*command, '--dry-run=server']
    assert json.loads(command[8]) == [
        {'op': 'test', 'path': '/metadata/uid', 'value': 'uid'},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '10'},
        {'op': 'test', 'path': evidence.IMAGE_PATH, 'value': before},
        {'op': 'replace', 'path': evidence.IMAGE_PATH, 'value': after},
    ]
    expected = raw.replace(old, new)
    assert proof['before_manifest_sha256'] == evidence.sha((expected if rollback else raw).encode())
    assert proof['after_manifest_sha256'] == evidence.sha((raw if rollback else expected).encode())
    assert desired == indexed(yaml.safe_load(raw if rollback else expected))
    assert (
        scopes
        == [
            ('ConfigMap', 'prod-omi-backend-config', 'prod-omi-backend'),
            ('Deployment', 'prod-omi-neg-coverage-exporter', 'prod-omi-monitoring'),
        ]
        * 2
    )


@pytest.mark.parametrize(
    'drift', [None, 'second-key', 'secret', 'live-env', 'field-path', 'field-version', 'image', 'inverse', 'missing']
)
def test_reference_render_proves_only_reconnect_without_exporting_references(drift):
    image = 'gcr.io/based-hardware/backend:96f0631'
    before = deployment()
    main = before['spec']['template']['spec']['containers'][0]
    main['image'] = image
    main['env'][1] = {
        'name': 'PRIVATE_TOKEN',
        'valueFrom': {'secretKeyRef': {'name': 'test-secret', 'key': 'PRIVATE_TOKEN', 'optional': False}},
    }
    policy = main['env'][0]['name']
    main['env'][0] = {
        'name': policy,
        'valueFrom': {'secretKeyRef': {'name': 'test-secret', 'key': policy, 'optional': False}},
    }
    main['env'].append(
        {
            'name': 'ROLLOUT_POD_TEMPLATE_HASH',
            'valueFrom': {'fieldRef': {'fieldPath': "metadata.labels['pod-template-hash']"}},
        }
    )
    wanted, live, inverse = (copy.deepcopy(before) for _ in range(3))
    field = live['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['fieldRef']
    field['apiVersion'] = 'v2' if drift == 'field-version' else 'v1'
    if drift == 'field-path':
        field['fieldPath'] = 'metadata.name'
    wanted_main = wanted['spec']['template']['spec']['containers'][0]
    wanted_main['env'].append({'name': 'LISTEN_BATCH_RECONNECT_ENABLED', 'value': 'true'})
    if drift == 'second-key':
        wanted_main['env'].append({'name': 'EXTRA', 'value': 'true'})
    elif drift == 'secret':
        wanted_main['env'][1]['valueFrom']['secretKeyRef']['name'] = 'other-secret'
    elif drift == 'live-env':
        live['spec']['template']['spec']['initContainers'][0]['env'][0]['value'] = 'false'
    elif drift == 'image':
        wanted_main['image'] = 'gcr.io/based-hardware/backend:1234567'
    elif drift == 'inverse':
        inverse['spec']['replicas'] += 1
    observed = indexed(live) if drift != 'missing' else {}
    private_keys = [policy, 'PRIVATE_TOKEN']
    args = (indexed(wanted), indexed(before), indexed(inverse), observed, private_keys, 'test-secret', image)
    if drift is None:
        assert evidence.compare_reference_render(*args) == 'listen'
        coverage = evidence.compare(args[0], args[3], args[0], set(private_keys), references=True)
        assert [(row['key'], row['effect']) for row in coverage['env'] if row['effect'] != 'same'] == [
            ('LISTEN_BATCH_RECONNECT_ENABLED', 'added')
        ]
    else:
        with pytest.raises(evidence.Refused):
            evidence.compare_reference_render(*args)


@pytest.mark.parametrize('fault', [None, 'shadow-pod', 'digest', 'foreign-owner', 'not-ready'])
def test_reference_image_must_be_running_on_all_ready_pods(fault):
    image = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
    live = deployment()
    live['spec'].update(replicas=1, selector={'matchLabels': {'app': 'listen'}})
    live['status'] = {
        'observedGeneration': 3,
        'replicas': 1,
        'updatedReplicas': 1,
        'readyReplicas': 1,
        'availableReplicas': 1,
    }
    pod = {
        'metadata': {
            'name': 'listen-pod',
            'uid': 'pod-uid',
            'resourceVersion': '12',
            'ownerReferences': [{'kind': 'ReplicaSet', 'name': 'listen-rs', 'uid': 'rs-uid', 'controller': True}],
        },
        'status': {
            'conditions': [{'type': 'Ready', 'status': 'False' if fault == 'not-ready' else 'True'}],
            'containerStatuses': [
                {'name': 'listen', 'ready': True, 'imageID': image if fault != 'digest' else image[:-1] + 'b'}
            ],
        },
    }
    replica_set = {
        'metadata': {
            'uid': 'rs-uid',
            'ownerReferences': [
                {'kind': 'Deployment', 'controller': True, 'uid': 'foreign' if fault == 'foreign-owner' else 'uid'}
            ],
        }
    }
    with patch.object(
        evidence.Reader,
        'run',
        side_effect=[
            json.dumps({'items': [pod, pod] if fault == 'shadow-pod' else [pod]}).encode(),
            json.dumps(replica_set).encode(),
        ],
    ):
        if fault is None:
            assert evidence.serving_pods(evidence.Reader(), live, 'listen', image) == {
                'listen-pod': {'uid': 'pod-uid', 'generation': None, 'resourceVersion': '12'}
            }
        else:
            with pytest.raises(evidence.Refused):
                evidence.serving_pods(evidence.Reader(), live, 'listen', image)


def test_reference_snapshot_batches_durable_objects_without_widening_scope():
    docs = [
        {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'listen', 'namespace': evidence.NS}},
        deployment(),
    ]
    keys = [(doc['apiVersion'], doc['kind'], evidence.NS, doc['metadata']['name']) for doc in docs]
    with patch.object(evidence.Reader, 'run', return_value=json.dumps({'kind': 'List', 'items': docs}).encode()) as run:
        assert evidence.Reader().reference_objects(keys) == dict(zip(keys, docs))
        run.assert_called_once_with(
            [
                'kubectl',
                '-n',
                evidence.NS,
                'get',
                'Service/listen',
                'Deployment.v1.apps/' + evidence.TARGET,
                '-o',
                'json',
            ]
        )
    with patch.object(evidence.Reader, 'run', return_value=json.dumps(docs[0]).encode()):
        with pytest.raises(evidence.Refused, match='reference_live_document_missing'):
            evidence.Reader().reference_objects(keys)


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


@pytest.mark.parametrize('references', [False, True, 'image-only', 'digest'])
@pytest.mark.parametrize(
    'fault', [None, 'live-movement', 'wrong-source', 'wrong-image', 'wrong-attempt', 'helm-movement', 'missing-runtime']
)
def test_complete_producer_uses_only_bounded_reads_and_refuses_changed_binding(tmp_path, fault, references):
    digest_only = references == 'digest'
    image_only = references in {'image-only', 'digest'}
    private_file = tmp_path / 'private.yaml'
    private_file.write_text('privateEnv:\n  PRIVATE_TOKEN: "never-publish-this-value"\n')
    event_file = tmp_path / 'event.json'
    inputs = dict(evidence.DISPATCH_DEFAULTS, expected_sha='b' * 40, image_tag='b' * 7)
    event_file.write_text(json.dumps({'inputs': {**inputs, 'evidence_request_id': 'a' * 32, 'control_sha': ''}}))
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

    predecessor = deployment('prior-private-value')
    if references:
        req.update(reference_helm_revision=1, overlay_updated_at='', overlay_state='references')
        private_file.write_text('')
        primary = predecessor['spec']['template']['spec']['containers'][0]
        primary['image'] = 'gcr.io/based-hardware/backend:' + req['image_tag']
        if image_only:
            primary.update(name='backend-listen', image='gcr.io/based-hardware/backend:96f0631')
            if digest_only:
                inverse = 'gcr.io/based-hardware/backend@sha256:' + 'e' * 64
                req.update(
                    image_only={
                        'from': primary['image'],
                        'baseline': {inverse: 16, 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64: 24},
                        'inverse': inverse,
                        'source_sha': 'b' * 40,
                    },
                    image_tag='',
                    image='gcr.io/based-hardware/backend@sha256:' + 'f' * 64,
                )
                inputs['image_tag'] = ''
                event_file.write_text(json.dumps({'inputs': {**inputs, 'evidence_request_id': 'a' * 32}}))
            else:
                req['image_only_from'] = primary['image']
        for row in primary['env']:
            key = row['name']
            row.clear()
            row.update(name=key, valueFrom={'secretKeyRef': {'name': 'test-secret', 'key': key, 'optional': False}})
    candidate = copy.deepcopy(predecessor)
    candidate['spec']['template']['spec']['containers'][0]['env'].append(
        {'name': 'LISTEN_BATCH_RECONNECT_ENABLED', 'value': 'true'}
    )

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
                if 'cat-file' in args:
                    assert digest_only
                    return b'commit'
                return (('0' if fault == 'wrong-source' else 'b') * 40).encode()
            if args[0] == 'docker':
                assert digest_only and args[4] == req['image']
                return b'b' * 40
            if args[0] == 'gcloud':
                if digest_only:
                    assert args[4] == req['image_only']['inverse']
                return ('sha256:' + ('0' if fault == 'wrong-image' else 'e') * 64).encode()
            if 'history' in args:
                n = getattr(self, 'histories', 0) + 1
                self.histories = n
                return json.dumps(
                    [{'status': 'deployed', 'revision': 2 if fault == 'helm-movement' and n > 1 else 1}]
                ).encode()
            if 'get' in args:
                if 'hooks' in args:
                    return b''
                return yaml.safe_dump(predecessor).encode()
            if image_only and args[0] == 'kubectl':
                assert args[-1] == '--dry-run=server'
                admitted = copy.deepcopy(predecessor)
                admitted['spec']['template']['spec']['containers'][0]['image'] = json.loads(args[8])[-1]['value']
                return json.dumps(admitted).encode()
            assert args[0] == 'helm' and args[-2:] == ['--dry-run=client', '--output=json']
            value = 'never-publish-this-value' if '-f' in args[-4:] else 'chart-private-default'
            return json.dumps(
                {
                    'manifest': yaml.safe_dump(candidate if references else deployment(value)),
                    'hooks': [],
                    'info': {'notes': 'never-publish-notes'},
                    'ignored': 'never-publish-extra',
                }
            ).encode()

        def obj(self, *args):
            self.objects += 1
            observed = copy.deepcopy(predecessor)
            if fault == 'live-movement' and self.objects > 1:
                observed['metadata']['resourceVersion'] = '11'
            return observed

        def reference_objects(self, keys):
            return {key: self.obj() for key in keys}

    req['helm_args'] = evidence.helm_args(
        '<candidate>/backend/charts/backend-listen',
        '<candidate>/backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
        'b' * 7,
        'based-hardware',
        'based-hardware',
        [] if references else ['-f', '<private-overlay>'],
    )
    if image_only:
        req['helm_args'] = ['helm', '-n', evidence.NS, 'get', 'manifest', evidence.TARGET, '--revision', '1']
    if fault == 'missing-runtime':
        del req['bindings']['runtime_manifest_sha256']
    values = tmp_path / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml'
    values.parent.mkdir(parents=True)
    values.write_text(
        'privateSecretEnv:\n  secretName: test-secret\n'
        '  keys: [STT_CAP_DISPATCH_ENFORCEMENT, PRIVATE_TOKEN]\nenv: []\n'
        if references
        else 'privateEnv: {}\nenv: []\n'
    )
    reader = Fake()
    overrides = [] if references else ['-f', str(private_file)]
    with patch.object(evidence, 'bindings', return_value=req['bindings']), patch.object(
        evidence, 'serving_pods', return_value={'pod': 'bound'}
    ) as pods:
        if fault:
            with pytest.raises(evidence.Refused):
                evidence.produce(req, reader, environment, tmp_path, private_file, overrides, 200)
        else:
            result = evidence.produce(req, reader, environment, tmp_path, private_file, overrides, 200)
            assert result['run_attempt'] == '1'
            assert result['coverage']['env_key_count'] == (4 if references and not image_only else 3)
            if image_only:
                assert pods.call_count == 1
                assert result['image_diff']['path'] == evidence.IMAGE_PATH
                if digest_only:
                    assert result['image_diff']['before'] == req['image_only']['from']
                    assert result['image_diff']['after'] == req['image']
                    assert result['inverse'] == [req['image'], req['image_only']['inverse']]
                    assert result['image_only'] == req['image_only']
                    assert pods.call_args.args[-1] == req['image_only']['baseline']
                    assert pods.call_args.kwargs == {'check_endpoints': True}
                    for required in evidence.REQUIRED_LISTEN_ANCESTORS:
                        assert any(cmd[-3:] == ['--is-ancestor', required, 'b' * 40] for cmd in reader.commands)
                else:
                    assert result['image_diff']['before'] == req['image_only_from']
            elif references:
                assert pods.call_count == 2
                assert result['inverse'] == [
                    'helm',
                    '-n',
                    evidence.NS,
                    'rollback',
                    evidence.TARGET,
                    '1',
                    '--wait',
                    '--timeout',
                    '70m',
                ]
                assert 'test-secret' not in json.dumps(result)
            assert 'never-publish-this-value' not in json.dumps(result)
            assert 'prior-private-value' not in json.dumps(result)
            assert 'never-publish-notes' not in json.dumps(result)
            assert 'never-publish-extra' not in json.dumps(result)
    for args in reader.commands:
        assert not (args[0] == 'kubectl' and 'apply' in args)
        if args[0] == 'helm' and 'upgrade' in args:
            assert '--dry-run=client' in args
    if fault == 'missing-runtime':
        assert reader.commands == []


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
    # Keep the writer alive after flushing so this exercises the live output bound.
    with pytest.raises(evidence.Refused, match='read_output_bound'):
        reader.run(
            [
                sys.executable,
                '-c',
                'import sys, time; sys.stdout.write("x" * (20 * 1024 * 1024)); sys.stdout.flush(); time.sleep(5)',
            ]
        )
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


@pytest.mark.parametrize('terminal', [None, 1])
def test_reader_cleanup_permission_denial_is_ignored_only_after_terminal_poll(monkeypatch, terminal):
    ticks = iter([0, 0, 0, 11])
    reader = evidence.Reader(clock=lambda: next(ticks))
    polls = iter([None, None, terminal])
    waited, killed = [], []

    class Child:
        pid = 123456

        def poll(self):
            return next(polls)

        def wait(self):
            waited.append(True)
            return terminal

    def denied(pid, sig):
        killed.append((pid, sig))
        raise PermissionError('synthetic owned-group denial')

    monkeypatch.setattr(evidence.subprocess, 'Popen', lambda *args, **kwargs: Child())
    monkeypatch.setattr(evidence.os, 'killpg', denied)
    expected = PermissionError if terminal is None else evidence.Refused
    with pytest.raises(expected):
        reader.run(['offline-synthetic-child'])
    assert killed == [(Child.pid, evidence.signal.SIGKILL)]
    assert waited == [True]


def mixed_baseline():
    prefix = 'gcr.io/based-hardware/backend'
    inverse = prefix + '@sha256:' + 'b' * 64
    return {
        'from': prefix + ':96f0631',
        'baseline': {prefix + '@sha256:' + 'a' * 64: 24, inverse: 16},
        'inverse': inverse,
        'source_sha': 'c' * 40,
    }


@pytest.mark.parametrize('fault', [None, 'wrong-counts', 'missing-endpoint', 'foreign-pod'])
def test_mixed_baseline_matches_ready_service_endpoints(fault):
    attestation = mixed_baseline()
    counts = attestation['baseline']
    live = deployment()
    live['spec'].update(replicas=40, selector={'matchLabels': {'app': 'listen'}})
    live['status'] = {
        'observedGeneration': 3,
        **dict.fromkeys(('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas'), 40),
    }
    pods = []
    endpoints = []
    for digest, count in counts.items():
        for _ in range(count):
            name = f'listen-pod-{len(pods)}'
            pods.append(
                {
                    'metadata': {
                        'name': name,
                        'uid': name,
                        'resourceVersion': '12',
                        'ownerReferences': [
                            {'kind': 'ReplicaSet', 'name': 'listen-rs', 'uid': 'rs-uid', 'controller': True}
                        ],
                    },
                    'status': {
                        'conditions': [{'type': 'Ready', 'status': 'True'}],
                        'containerStatuses': [
                            {'name': 'backend-listen', 'ready': True, 'imageID': 'docker-pullable://' + digest}
                        ],
                    },
                }
            )
            endpoints.append(
                {
                    'conditions': {'ready': True},
                    'targetRef': {'kind': 'Pod', 'namespace': evidence.NS, 'name': name, 'uid': name},
                }
            )
    if fault == 'wrong-counts':
        pods[0]['status']['containerStatuses'][0]['imageID'] = attestation['inverse']
    if fault == 'foreign-pod':
        endpoints[0]['targetRef']['uid'] = 'foreign'
    if fault == 'missing-endpoint':
        endpoints[0]['conditions']['terminating'] = True
    replica_set = {
        'metadata': {'uid': 'rs-uid', 'ownerReferences': [{'kind': 'Deployment', 'controller': True, 'uid': 'uid'}]}
    }
    with patch.object(
        evidence.Reader,
        'run',
        side_effect=[
            json.dumps({'items': pods}).encode(),
            json.dumps(replica_set).encode(),
            json.dumps({'items': [{'endpoints': endpoints}]}).encode(),
        ],
    ):
        if fault:
            with pytest.raises(evidence.Refused):
                evidence.serving_pods(evidence.Reader(), live, 'backend-listen', counts, check_endpoints=True)
        else:
            assert (
                len(evidence.serving_pods(evidence.Reader(), live, 'backend-listen', counts, check_endpoints=True))
                == 40
            )


@pytest.mark.parametrize('operation', ['deploy', 'rollback'])
@pytest.mark.parametrize('fault', [None, 'proof', 'peak', 'tag-inverse', 'missing-ancestor'])
def test_protected_digest_apply_rechecks_proof_and_patches_only_the_pinned_image(operation, fault):
    attestation = mixed_baseline()
    image = 'gcr.io/based-hardware/backend@sha256:' + 'e' * 64
    initial = deployment()
    initial['spec']['template']['spec']['containers'][0].update(name='backend-listen', image=attestation['from'])
    manifest = yaml.safe_dump(initial).encode()
    target = next(iter(indexed(initial)))

    class Fake:
        def __init__(self):
            self.live = copy.deepcopy(initial)
            self.writes = []

        def run(self, args):
            if args[0] == 'helm':
                return manifest
            if args[:2] == ['kubectl', 'config']:
                return b'gke_based-hardware_us-central1_prod-omi-gke'
            if args[0] == 'git':
                if 'cat-file' in args:
                    return b'commit'
                if fault == 'missing-ancestor' and evidence.REQUIRED_LISTEN_ANCESTORS[-1] in args:
                    raise evidence.Refused('read_failed')
                return b''
            if args[0] == 'docker':
                assert operation == 'deploy' and args[4] == image
                return attestation['source_sha'].encode()
            if args[0] == 'gcloud':
                assert args[4] == attestation['inverse']
                return args[4].split('@')[1].encode()
            assert args[:5] == ['kubectl', '-n', evidence.NS, 'patch', 'deployment']
            patch = json.loads(args[8])
            before, after = (entry['value'] for entry in patch[-2:])
            assert self.live['spec']['template']['spec']['containers'][0]['image'] == before
            updated = copy.deepcopy(self.live)
            updated['spec']['template']['spec']['containers'][0]['image'] = after
            if args[-1] != '--dry-run=server':
                self.live = updated
                self.writes.append(after)
            return json.dumps(updated).encode()

        def reference_objects(self, keys):
            assert keys == [target]
            return {target: self.live}

        def obj(self, kind, name, namespace):
            return self.live

    reader = Fake()
    with patch.object(evidence, 'release_revision', return_value=936), patch.object(
        evidence, 'serving_pods', return_value={f'listen-{n}': {} for n in range(40)}
    ) as pods, patch.object(evidence.time, 'gmtime') as clock:
        clock.return_value.tm_hour = 14 if fault == 'peak' else 22
        _, _, _, _, proof = evidence.image_only_plan(reader, 936, attestation['from'], image, attestation=attestation)
        if operation == 'rollback':
            reader.live['spec']['template']['spec']['containers'][0]['image'] = image
        if fault == 'proof':
            proof['inverse_manifest_sha256'] = '0' * 64
        if fault == 'tag-inverse':
            attestation['inverse'] = attestation['from']
        intent = {
            'revision': 936,
            'image_diff': proof,
            'image': image,
            'image_only': attestation,
            'control_sha': 'd' * 40,
            'operation': operation,
        }
        env = {
            'IMAGE_ONLY_PROOF': json.dumps(intent),
            'GITHUB_REPOSITORY': 'BasedHardware/omi',
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REF': 'refs/heads/main',
            'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_SHA': intent['control_sha'],
            'EXPECTED_SHA': attestation['source_sha'],
        }
        if operation == 'deploy':
            env['BACKEND_LISTEN_SOURCE_SHA'] = env['EXPECTED_SHA']
        pods.reset_mock()
        if fault:
            with pytest.raises(evidence.Refused):
                evidence.apply_image_only(reader, env)
            assert not reader.writes
        else:
            expected = image if operation == 'deploy' else attestation['inverse']
            assert evidence.apply_image_only(reader, env)['operation'] == operation
            assert reader.writes == [expected]
            assert pods.call_count == (1 if operation == 'deploy' else 0)
            assert evidence.verify_image_only(reader, env) == {'image': expected, 'ready_pods': 40}


def test_chart_only_argv_keeps_backend_digest():
    digest = 'sha256:' + 'a' * 64
    argv = evidence.helm_args('chart', 'values', digest, 'based-hardware', 'based-hardware', [])
    assert f'image.digest={digest}' in argv
    assert not any(arg.startswith('image.tag=') for arg in argv)
