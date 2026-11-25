#!/usr/bin/env python3
"""Protected, read-only listen render evidence. Never print captured data/errors."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import tempfile
import time
import copy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import listen_runtime
import yaml

NS = 'prod-omi-backend'
TARGET = 'prod-omi-backend-listen'
WORKFLOW = '.github/workflows/gcp_backend_listen_helm.yml'
SHA = re.compile(r'[0-9a-f]{40}')
HASH = re.compile(r'[0-9a-f]{64}')
NAME = re.compile(r'[A-Za-z0-9_.:/-]{1,180}')
KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
EFFECTS = {'same', 'added', 'removed', 'changed'}
ALLOWED_KINDS = {'Deployment', 'HorizontalPodAutoscaler', 'Service', 'ServiceAccount', 'Ingress',
                 'PodDisruptionBudget', 'PodMonitoring', 'Role', 'RoleBinding', 'ClusterRole',
                 'ClusterRoleBinding', 'ConfigMap', 'Pod'}
MAX_BYTES = 16 * 1024 * 1024
MAX_RECEIPT = 256 * 1024
DISPATCH_DEFAULTS = {'mode': 'evidence', 'environment': 'prod', 'branch': 'main', 'expected_sha': '',
                     'image_tag': '', 'helm_revision': '', 'gateway_feature_mode': 'chart-default',
                     'chat_agent_route': 'chart-default', 'allow_direct_model_exception': 'chart-default',
                     'stt_service_models': '', 'translation_service_models': '', 'listen_edge_image_digest': '',
                     'break_glass_lock': 'false'}
BINDING_FIELDS = {'chart_tree', 'values_sha256', 'producer_sha256', 'env_helper_sha256', 'workflow_sha256',
                  'helm_sha256', 'helm_version', 'python_version', 'yaml_version', 'yaml_sha256', 'cluster_context',
                  'runtime_manifest_sha256'}


class Refused(Exception):
    """Only a fixed code may leave this module."""


def require(ok, code):
    if not ok:
        raise Refused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, 'duplicate_key')
        out[k] = v
    return out


def json_read(data):
    require(len(data) <= MAX_BYTES, 'input_bound')
    return json.loads(data, object_pairs_hook=unique)


class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    return unique([(loader.construct_object(k), loader.construct_object(v, deep=True)) for k, v in node.value])


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def documents(data):
    require(len(data.encode()) <= MAX_BYTES, 'render_bound')
    docs = [d for d in yaml.load_all(data, Loader=Loader) if d is not None]
    require(len(docs) <= 128, 'document_bound')
    indexed = {}
    for d in docs:
        require(isinstance(d, dict) and d.get('kind') in ALLOWED_KINDS, 'unsupported_document')
        m = d.get('metadata', {})
        name, namespace = m.get('name'), m.get('namespace', NS)
        require(isinstance(name, str) and re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}', name)
                and namespace == NS, 'document_target')
        require(isinstance(d.get('apiVersion'), str) and NAME.fullmatch(d['apiVersion']), 'document_api')
        ident = (d['apiVersion'], d['kind'], namespace, name)
        require(ident not in indexed, 'duplicate_document')
        indexed[ident] = d
    return indexed


def helm_args(chart, values, image, project, runtime_project, overrides, environment='prod'):
    """The deploy and evidence paths MUST consume this identical ordered argv."""
    require(environment in {'prod', 'dev'} and all(re.fullmatch('[a-z][a-z0-9-]+', v)
                                                  for v in (project, runtime_project)), 'project_binding')
    require(re.fullmatch(r'[0-9a-f]{7,40}|sha256:[0-9a-f]{64}', image or ''), 'image_invalid')
    require(all(isinstance(x, str) and '\n' not in x and '\0' not in x for x in overrides), 'argv_invalid')
    # Overrides are produced by the existing named env/privateEnv validator.
    require(len(overrides) % 2 == 0 and all(overrides[i] in {'--set-string', '-f'}
                                        for i in range(0, len(overrides), 2)), 'argv_invalid')
    namespace, target = f'{environment}-omi-backend', f'{environment}-omi-backend-listen'
    return ['helm', '-n', namespace, 'upgrade', '--install', target, str(chart), '-f', str(values),
            '--set', f'image.repository=gcr.io/{project}/backend', '--set', f'gcpProjectId={project}',
            '--set', f'runtimeGcpProjectId={runtime_project}', '--set-string', f'image.tag={image}', *overrides]


class Reader:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + 120
        self.calls = 0
        self.bytes = 0

    def run(self, args):
        self.calls += 1
        require(self.calls <= 32 and self.clock() < self.deadline, 'read_bound')
        # Private files, not PIPE/communicate: a producer cannot fill memory or log output.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            p = subprocess.Popen(args, stdout=out, stderr=err, start_new_session=True)
            end = min(self.deadline, self.clock() + 10)
            try:
                while p.poll() is None:
                    require(self.clock() < end, 'read_timeout')
                    require(self.bytes + os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size <= MAX_BYTES,
                            'read_output_bound')
                    time.sleep(.01)
                require(p.returncode == 0, 'read_failed')
                size = os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size
                self.bytes += size
                require(self.bytes <= MAX_BYTES, 'read_output_bound')
                out.seek(0)
                return out.read()
            finally:
                try:
                    if p.poll() is None:
                        os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    # macOS can return EPERM for the group after the child exits
                    # between poll and killpg. Never suppress denial for a live child.
                    if p.poll() is None:
                        raise
                finally:
                    p.wait()

    def obj(self, kind, name, namespace):
        require(kind in ALLOWED_KINDS and NAME.fullmatch(name), 'live_target')
        args = ['kubectl', 'get', kind, name, '--ignore-not-found=true', '-o', 'json']
        if kind not in {'ClusterRole', 'ClusterRoleBinding'}:
            args += ['-n', namespace]
        data = self.run(args)
        return json_read(data) if data.strip() else None


def version(doc):
    if doc is None:
        return None
    m = doc['metadata']
    require(isinstance(m.get('uid'), str) and re.fullmatch('[A-Za-z0-9-]+', m['uid'])
            and isinstance(m.get('resourceVersion'), str) and m['resourceVersion'].isdigit()
            and (m.get('generation') is None or type(m['generation']) is int and m['generation'] > 0),
            'live_identity_missing')
    return {k: m.get(k) for k in ('uid', 'generation', 'resourceVersion')}


def release_revision(reader):
    rows = json_read(reader.run(['helm', '-n', NS, 'history', TARGET, '--max', '1', '--output', 'json']))
    require(isinstance(rows, list) and len(rows) == 1 and rows[0].get('status') == 'deployed'
            and type(rows[0].get('revision')) is int and rows[0]['revision'] > 0, 'release_revision_unknown')
    return rows[0]['revision']


def effect(old, new):
    return 'same' if old == new else 'added' if old is None else 'removed' if new is None else 'changed'


def env(container):
    result = {}
    require(isinstance(container.get('env', []), list), 'env_invalid')
    for row in container.get('env', []):
        name = row.get('name')
        require(isinstance(name, str) and KEY.fullmatch(name) and name not in result, 'env_invalid')
        require(set(row) <= {'name', 'value', 'valueFrom'} and not ('value' in row and 'valueFrom' in row), 'env_invalid')
        result[name] = {k: v for k, v in row.items() if k != 'name'} or {'value': ''}
    return result


def containers(doc):
    if doc is None:
        return {}
    pod = doc['spec']['template']['spec']
    result = {}
    for category in ('containers', 'initContainers'):
        for c in pod.get(category, []):
            name = c.get('name')
            require(isinstance(name, str) and NAME.fullmatch(name), 'container_invalid')
            ident = f'{category}/{name}'
            require(ident not in result, 'container_duplicate')
            result[ident] = c
    require(0 < len(result) <= 16, 'container_bound')
    return result


def body(doc):
    if doc is None:
        return None
    # Server-owned metadata/status do not describe rendered behavior.
    return {k: v for k, v in doc.items() if k not in {'metadata', 'status'}} | {
        'metadata': {k: v for k, v in doc.get('metadata', {}).items()
                     if k not in {'uid', 'resourceVersion', 'generation', 'creationTimestamp', 'managedFields'}}}


def compare(desired, live, baseline, private_names, *, references=False):
    """No raw value crosses the comparison boundary, including public-looking data."""
    require(set(desired) == set(baseline), 'overlay_document_set')
    deployments = [k for k in desired if k[1] == 'Deployment']
    require(len(deployments) == 1 and deployments[0][3] == TARGET, 'deployment_coverage')
    ident = deployments[0]
    want, before = containers(desired[ident]), containers(live.get(ident))
    public = containers(baseline[ident])
    require(set(want) == set(before) == set(public), 'container_set_changed')
    main_container = 'containers/' + desired[ident]['spec']['template']['spec']['containers'][0]['name']
    require(set(private_names) <= set(env(want[main_container])), 'private_key_coverage')
    def without_env(doc):
        result = copy.deepcopy(body(doc))
        if doc is not None and doc['kind'] == 'Deployment':
            pod = result['spec']['template']['spec']
            for category in ('containers', 'initContainers'):
                for c in pod.get(category, []):
                    c.pop('env', None)
        return result
    require(without_env(desired[ident]) == without_env(baseline[ident]), 'overlay_non_env_effect')
    rows = []
    for c in sorted(want):
        have_env, want_env = env(before[c]), env(want[c])
        names = sorted(set(have_env) | set(want_env))
        for name in names:
            rows.append({'container': c, 'key': name, 'effect': effect(have_env.get(name), want_env.get(name)),
                         'private': c == main_container and name in private_names})
    require(len(rows) <= 2048, 'key_bound')
    # Mandatory live preservation is checked privately, never disclosed as a value.
    matches = [env(c).get('STT_CAP_DISPATCH_ENFORCEMENT') for c in want.values()
               if 'STT_CAP_DISPATCH_ENFORCEMENT' in env(c)]
    if references:
        require('STT_CAP_DISPATCH_ENFORCEMENT' in private_names and len(matches) == 1, 'required_policy_changed')
    else:
        require(matches == [{'value': 'true'}], 'required_policy_changed')
    docs = []
    for key in sorted(set(desired) | set(live)):
        d, old = desired.get(key), live.get(key)
        if key != ident:
            require(d == baseline.get(key), 'overlay_non_env_effect')
        docs.append({'apiVersion': key[0], 'kind': key[1], 'namespace': key[2], 'name': key[3],
                     'effect': effect(without_env(old), without_env(d)), 'live_version': version(old),
                     'changes': changed_paths(without_env(old), without_env(d))})
    # Full deployment/HPA bodies are compared in memory, not an env-only projection.
    return {'documents': docs, 'containers': sorted(want), 'env': rows,
            'document_count': len(docs), 'env_key_count': len(rows), 'complete': True,
            'policy_preserved': True, 'private_keys': sorted(private_names), 'private_container': main_container}


def compare_reference_render(desired, predecessor, inverse, live, private_keys, secret_name, image):
    """Prove the reconnect addition against a pinned Helm predecessor and live references."""
    require(set(desired) == set(predecessor) == set(inverse) == set(live), 'reference_document_set')
    require(all(live[key] is not None for key in desired), 'reference_live_document_missing')
    require(inverse == predecessor, 'reference_inverse_differs')
    deployments = [key for key in desired if key[1] == 'Deployment']
    require(len(deployments) == 1 and deployments[0][3] == TARGET, 'deployment_coverage')
    target = deployments[0]
    corrected = copy.deepcopy(desired)
    primary = corrected[target]['spec']['template']['spec']['containers'][0]
    primary_name = 'containers/' + primary['name']
    reconnect = 'LISTEN_BATCH_RECONNECT_ENABLED'
    require(env(primary).get(reconnect) == {'value': 'true'}, 'reference_reconnect_value')
    primary['env'] = [row for row in primary['env'] if row['name'] != reconnect]
    require(corrected == predecessor, 'reference_render_differs')

    expected = containers(predecessor[target])
    observed = containers(live[target])
    require(expected.keys() == observed.keys(), 'container_set_changed')
    require(all(env(expected[name]) == env(observed[name]) for name in expected), 'reference_live_env_drift')
    require(expected[primary_name]['image'] == observed[primary_name]['image'] == image, 'reference_image_changed')
    require(all(reconnect not in env(container) for container in observed.values()), 'reference_reconnect_present')

    require(isinstance(private_keys, list) and 0 < len(private_keys) == len(set(private_keys))
            and isinstance(secret_name, str) and NAME.fullmatch(secret_name), 'reference_inventory')
    private_env = env(observed[primary_name])
    for key in private_keys:
        require(isinstance(key, str) and KEY.fullmatch(key), 'reference_inventory')
        require(private_env.get(key) == {'valueFrom': {'secretKeyRef': {'name': secret_name, 'key': key}}},
                'reference_binding_changed')
    return primary['name']


def serving_pods(reader, deployment, primary, image):
    """Read only the selected Ready pods and bind the running image digest."""
    meta, spec, status = deployment['metadata'], deployment['spec'], deployment['status']
    replicas = spec['replicas']
    require(type(replicas) is int and replicas > 0 and status.get('observedGeneration') == meta['generation']
            and all(status.get(field) == replicas for field in
                    ('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas')), 'reference_not_ready')
    selector = spec['selector']
    labels = selector.get('matchLabels')
    require(set(selector) == {'matchLabels'} and isinstance(labels, dict) and labels
            and all(re.fullmatch(r'[A-Za-z0-9./_-]+', k) and re.fullmatch(r'[A-Za-z0-9._-]+', v)
                    for k, v in labels.items()), 'reference_selector_unknown')
    selected = ','.join(f'{key}={value}' for key, value in sorted(labels.items()))
    pods = json_read(reader.run(['kubectl', '-n', NS, 'get', 'pods', '--selector', selected, '-o', 'json']))['items']
    require(len(pods) == replicas, 'reference_pod_count')
    versions = {}
    owners = set()
    for pod in pods:
        pod_meta = pod['metadata']
        ready = [condition for condition in pod['status']['conditions']
                 if condition.get('type') == 'Ready' and condition.get('status') == 'True']
        primary_status = [row for row in pod['status']['containerStatuses'] if row['name'] == primary]
        require(not pod_meta.get('deletionTimestamp') and len(ready) == 1 and len(primary_status) == 1
                and primary_status[0].get('ready') is True, 'reference_pod_not_ready')
        image_id = primary_status[0]['imageID'].removeprefix('docker-pullable://')
        require(image_id == image, 'reference_serving_digest')
        owner = [row for row in pod_meta['ownerReferences']
                 if row.get('kind') == 'ReplicaSet' and row.get('controller') is True]
        require(len(owner) == 1, 'reference_pod_owner')
        owners.add((owner[0]['name'], owner[0]['uid']))
        versions[pod_meta['name']] = version(pod)
    require(len(owners) == 1 and len(versions) == replicas, 'reference_pod_owner')
    name, uid = owners.pop()
    require(isinstance(name, str) and NAME.fullmatch(name), 'reference_pod_owner')
    replica_set = json_read(reader.run(['kubectl', '-n', NS, 'get', 'replicaset', name, '-o', 'json']))
    require(replica_set and replica_set['metadata']['uid'] == uid and any(
        owner.get('kind') == 'Deployment' and owner.get('uid') == meta['uid'] and owner.get('controller') is True
        for owner in replica_set['metadata'].get('ownerReferences', [])), 'reference_replicaset_owner')
    return versions


def changed_paths(old, new, prefix=''):
    if old == new:
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        paths = []
        for key in sorted(set(old) | set(new)):
            require(isinstance(key, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,180}', key), 'unsafe_field_name')
            paths.extend(changed_paths(old.get(key), new.get(key), prefix + '/' + key))
        require(len(paths) <= 4096, 'field_bound')
        return paths
    return [prefix or '/']


def validate_request(request, now):
    fields = {'schema', 'request_id', 'created', 'expires', 'state', 'consumer_sha256', 'candidate_sha',
              'control_sha', 'target', 'namespace', 'bindings', 'dispatch_inputs', 'image', 'image_tag',
              'helm_args', 'overlay_updated_at', 'overlay_state', 'release_actor', 'approvers'}
    state = request.get('state')
    require(state in {'requested', 'bound'}, 'overlay_replayed')
    if state == 'bound':
        fields |= {'run_id', 'run_attempt'}
    reference_revision = request.get('reference_helm_revision')
    if 'reference_helm_revision' in request:
        fields.add('reference_helm_revision')
        require(type(reference_revision) is int and reference_revision > 0, 'reference_revision_unknown')
    if 'ledger_binding' in request:
        fields.add('ledger_binding')
        require(isinstance(request['ledger_binding'], str) and HASH.fullmatch(request['ledger_binding']),
                'overlay_ledger_binding')
    require(set(request) == fields, 'overlay_request_schema')
    require(request.get('schema') == 1 and re.fullmatch('[0-9a-f]{32}', request.get('request_id', '')), 'overlay_request')
    require(type(request.get('created')) is int and type(request.get('expires')) is int
            and request['created'] <= now < request['expires'] <= request['created'] + 900, 'overlay_expired')
    require(request.get('target') == TARGET and request.get('namespace') == NS, 'overlay_target')
    require(all(isinstance(request.get(k), str) and SHA.fullmatch(request[k]) and request[k] != '0'*40
                for k in ('candidate_sha', 'control_sha')), 'overlay_source')
    require(HASH.fullmatch(request.get('consumer_sha256', '')), 'overlay_consumer_binding')
    require(request.get('release_actor') and request.get('approvers'), 'overlay_release_identity_unknown')
    require(isinstance(request['release_actor'], str) and re.fullmatch(r'[A-Za-z0-9-]+', request['release_actor'])
            and isinstance(request['approvers'], list) and 0 < len(request['approvers']) <= 8
            and all(isinstance(x, str) and re.fullmatch(r'[A-Za-z0-9-]+', x) for x in request['approvers']),
            'overlay_release_identity_unknown')
    require(re.fullmatch(r'gcr.io/based-hardware/backend@sha256:[0-9a-f]{64}', request['image'])
            and re.fullmatch(r'[0-9a-f]{7,40}', request['image_tag']), 'overlay_image_binding')
    require((request['overlay_state'] == 'references' and request['overlay_updated_at'] == '')
            if reference_revision else
            (request['overlay_state'] in {'present', 'empty'}
             and isinstance(request['overlay_updated_at'], str) and bool(request['overlay_updated_at'])),
            'overlay_version_unknown')
    bindings = request.get('bindings')
    require(isinstance(bindings, dict) and set(bindings) == BINDING_FIELDS, 'overlay_tool_binding')
    for key, value in bindings.items():
        require(isinstance(value, str), 'overlay_tool_binding')
        if key.endswith('_sha256'):
            require(HASH.fullmatch(value), 'overlay_tool_binding')
        elif key == 'chart_tree':
            require(SHA.fullmatch(value), 'overlay_tool_binding')
        elif key == 'cluster_context':
            require(value == 'gke_based-hardware_us-central1_prod-omi-gke', 'overlay_tool_binding')
        else:
            require(re.fullmatch(r'v?[0-9]+\.[0-9]+\.[0-9]+(?:[a-z0-9.+-]{0,40})?', value), 'overlay_tool_binding')
    inputs = request.get('dispatch_inputs')
    require(isinstance(inputs, dict) and set(inputs) == set(DISPATCH_DEFAULTS)
            and all(isinstance(v, str) and len(v) <= 512 for v in inputs.values()), 'overlay_dispatch_binding')
    for key in ('mode', 'environment', 'branch', 'helm_revision', 'listen_edge_image_digest', 'break_glass_lock'):
        require(inputs[key] == DISPATCH_DEFAULTS[key], 'overlay_dispatch_binding')
    require(inputs['expected_sha'] == request['candidate_sha'] and inputs['image_tag'] == request['image_tag'],
            'overlay_dispatch_binding')
    require(inputs['gateway_feature_mode'] in {'chart-default', 'disabled', 'gateway'}
            and inputs['chat_agent_route'] in {'chart-default', 'direct', 'gateway'}
            and inputs['allow_direct_model_exception'] in {'chart-default', 'true', 'false'}, 'overlay_dispatch_binding')
    for key in ('stt_service_models', 'translation_service_models'):
        require(re.fullmatch('[A-Za-z0-9_.,+-]{0,512}', inputs[key]), 'overlay_dispatch_binding')
    require(isinstance(request['helm_args'], list) and all(isinstance(v, str) and '\n' not in v and '\0' not in v
                                                         for v in request['helm_args']), 'overlay_argv_binding')


def bindings(root, reader):
    scripts = Path(__file__).resolve().parent
    helm = shutil.which('helm')
    require(helm is not None, 'tool_missing')
    runtime_root = Path(os.environ['RUNNER_TEMP']) / 'listen-runtime'
    raw = (scripts / 'listen_runtime_manifest.json').read_bytes()
    observed = listen_runtime.running(raw, runtime_root)
    require(Path(helm).resolve() == runtime_root / 'helm/linux-amd64/helm', 'runtime_helm_path')
    return {
        'chart_tree': reader.run(['git', '-C', str(root), 'rev-parse', 'HEAD:backend/charts/backend-listen']).decode().strip(),
        'values_sha256': sha((root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml').read_bytes()),
        'producer_sha256': sha(Path(__file__).read_bytes()),
        'env_helper_sha256': sha((scripts / 'listen_helm_env_overrides.py').read_bytes()),
        'workflow_sha256': sha((scripts.parent / 'workflows/gcp_backend_listen_helm.yml').read_bytes()),
        **observed,
        'helm_version': reader.run(['helm', 'version', '--template', '{{.Version}}']).decode().strip(),
        'cluster_context': reader.run(['kubectl', 'config', 'current-context']).decode().strip(),
    }


def produce(request, reader, environ, root, private_file, overrides, now):
    validate_request(request, now)
    require(request['state'] == 'requested', 'request_already_bound')
    from listen_helm_env_overrides import load_values

    candidate = load_values(root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml')
    reference_revision = request.get('reference_helm_revision')
    private_spec = candidate.get('privateSecretEnv') or {}
    if reference_revision:
        require(private_spec.get('keys') and not candidate.get('privateEnv') and '-f' not in overrides,
                'reference_inventory')
    else:
        require(not private_spec.get('keys'), 'evidence_retired_private_secret_env')
    require(environ.get('GITHUB_REPOSITORY') == 'BasedHardware/omi'
            and environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and environ.get('GITHUB_REF') == 'refs/heads/main'
            and environ.get('GITHUB_WORKFLOW_SHA') == request['control_sha']
            and environ.get('GITHUB_RUN_ATTEMPT') == '1', 'workflow_binding')
    require(reader.run(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip() == request['candidate_sha'],
            'candidate_binding')
    actual_bindings = bindings(root, reader)
    require(actual_bindings == request['bindings'], 'tool_binding')
    require(actual_bindings['cluster_context'] == 'gke_based-hardware_us-central1_prod-omi-gke', 'cluster_binding')
    event = json_read(Path(environ['GITHUB_EVENT_PATH']).read_bytes())
    inputs = event.get('inputs', {})
    require(inputs.get('mode') == 'evidence' and inputs.get('environment') == 'prod'
            and str(inputs.get('break_glass_lock', 'false')) == 'false'
            and inputs.get('evidence_request_id') == request['request_id']
            and inputs.get('expected_sha') == request['candidate_sha']
            and inputs.get('image_tag') == request['image_tag']
            and not inputs.get('listen_edge_image_digest') and not inputs.get('helm_revision'), 'dispatch_binding')
    require({k: v for k, v in inputs.items() if not k.startswith('evidence_')} == request['dispatch_inputs'],
            'dispatch_binding')
    raw = private_file.read_bytes()
    require(len(raw) <= MAX_BYTES, 'overlay_bound')
    # Import the trusted existing validator, not candidate code.
    from listen_helm_env_overrides import load_private_env
    private = load_private_env(private_file) if raw else {}
    require(request['overlay_state'] == ('present' if raw else 'references' if reference_revision else 'empty'),
            'overlay_state_mismatch')
    image_tag = request['image_tag']
    require(re.fullmatch(r'[0-9a-f]{7,40}', image_tag), 'image_invalid')
    image_source = reader.run(['git', '-C', str(root), 'rev-parse', '--verify', image_tag + '^{commit}']).decode().strip()
    require(SHA.fullmatch(image_source), 'image_source_invalid')
    reader.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', image_source, request['candidate_sha']])
    image_digest = reader.run(['gcloud', 'container', 'images', 'describe',
                              'gcr.io/based-hardware/backend:' + image_tag,
                              '--format=value(image_summary.digest)']).decode().strip()
    require(request['image'] == 'gcr.io/based-hardware/backend@' + image_digest, 'image_digest_mismatch')
    overlay = {'state': request['overlay_state'], 'updatedAt': request['overlay_updated_at'], 'sha256': sha(raw)}
    args = helm_args(root / 'backend/charts/backend-listen',
                     root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
                     request['image_tag'], 'based-hardware', 'based-hardware', overrides)
    canonical_args = [str(x).replace(str(private_file), '<private-overlay>').replace(str(root), '<candidate>')
                      for x in args]
    require(canonical_args == request['helm_args'], 'request_argv_mismatch')
    # No arbitrary caller argv: only the existing helper's generated overrides.
    base_args = list(args)
    if '-f' in overrides:
        require(overrides[-2:] == ['-f', str(private_file)], 'private_argv_binding')
        base_args = args[:-2]
    helm_revision = release_revision(reader)
    require(not reference_revision or helm_revision == reference_revision, 'reference_revision_mismatch')
    current = documents(reader.run(['helm', '-n', NS, 'get', 'manifest', TARGET]).decode())
    if reference_revision:
        baseline = current
    else:
        base = json_read(reader.run([*base_args, '--dry-run=client', '--output=json']))
        baseline = documents(base['manifest'] + ''.join('\n---\n' + h['manifest'] for h in base.get('hooks', [])))
    keys = sorted(set(baseline) | set(current))
    live = {k: reader.obj(k[1], k[3], k[2]) for k in keys}
    before = {k: version(v) for k, v in live.items()}
    full = json_read(reader.run([*args, '--dry-run=client', '--output=json']))
    require(isinstance(full.get('manifest'), str) and isinstance(full.get('hooks', []), list), 'partial_render')
    rendered_hooks = ''.join('\n---\n' + h['manifest'] for h in full.get('hooks', []))
    if reference_revision:
        desired = documents(full['manifest'])
        hooks = documents(rendered_hooks)
        require(not (hooks.keys() & desired.keys()) and all(
            hook['kind'] == 'Pod' and hook['metadata'].get('annotations', {}).get('helm.sh/hook') == 'test'
            for hook in hooks.values()), 'reference_hook_unsupported')
        prior_hooks = documents(reader.run(['helm', '-n', NS, 'get', 'hooks', TARGET,
                                             '--revision', str(reference_revision)]).decode())
        require(hooks == prior_hooks, 'reference_hooks_changed')
        inverse = documents(reader.run(['helm', '-n', NS, 'get', 'manifest', TARGET,
                                        '--revision', str(reference_revision)]).decode())
        primary = compare_reference_render(desired, current, inverse, live, private_spec['keys'],
                                           private_spec['secretName'], 'gcr.io/based-hardware/backend:' + image_tag)
        deployment = next(live[key] for key in live if key[1] == 'Deployment')
        pods = serving_pods(reader, deployment, primary, request['image'])
        coverage = compare(desired, live, desired, set(private_spec['keys']), references=True)
        require(serving_pods(reader, deployment, primary, request['image']) == pods, 'reference_pods_moved')
    else:
        desired = documents(full['manifest'] + rendered_hooks)
        coverage = compare(desired, live, baseline, set(private))
    for k in keys:
        require(version(reader.obj(k[1], k[3], k[2])) == before[k], 'live_moved')
    require(release_revision(reader) == helm_revision, 'release_revision_moved')
    receipt = {'schema': 1, 'request_id': request['request_id'], 'created': now, 'expires': request['expires'],
               'candidate_sha': request['candidate_sha'], 'control_sha': request['control_sha'],
               'target': TARGET, 'namespace': NS, 'bindings': actual_bindings, 'dispatch_inputs': request['dispatch_inputs'],
               'image': request['image'], 'helm_args': canonical_args, 'overlay': overlay,
               'run_id': environ['GITHUB_RUN_ID'], 'run_attempt': environ['GITHUB_RUN_ATTEMPT'],
               'coverage': coverage, 'helm_revision': helm_revision, 'read_count': reader.calls, 'read_bytes': reader.bytes}
    if reference_revision:
        receipt['reference_helm_revision'] = reference_revision
        receipt['inverse'] = ['helm', '-n', NS, 'rollback', TARGET, str(reference_revision), '--wait', '--timeout', '70m']
    require(len(canonical(receipt)) <= MAX_RECEIPT, 'receipt_bound')
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['argv', 'produce', 'job'])
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--overrides-file', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--request', type=Path)
    p.add_argument('--private-file', type=Path)
    p.add_argument('--image-tag')
    p.add_argument('--project', default='based-hardware')
    p.add_argument('--runtime-project', default='based-hardware')
    p.add_argument('--environment', default='prod')
    a = p.parse_args()
    def interrupted(_signum, _frame):
        raise Refused('interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGALRM, interrupted)
    if a.mode != 'argv':
        signal.alarm(120)
    try:
        overrides = a.overrides_file.read_text().splitlines() if a.overrides_file else []
        if a.mode == 'job':
            from listen_helm_env_overrides import (check_private_env_against_chart, check_translation_endpoint,
                                                 load_private_env, load_values, resolve_env_override_argv)
            request = json_read(os.environ['EVIDENCE_REQUEST'].encode())
            validate_request(request, int(time.time()))
            os.umask(0o077)
            private_root = Path(os.environ['RUNNER_TEMP']) / 'listen-overlay-evidence'
            private_root.mkdir(mode=0o700, exist_ok=False)
            with tempfile.TemporaryDirectory(prefix='private-', dir=private_root) as tmp:
                private_file = Path(tmp) / 'overlay.yaml'
                overlay_text = os.environ.pop('LISTEN_PRIVATE_VALUES_YAML', '')
                require(not request.get('reference_helm_revision') or not overlay_text, 'reference_overlay_injected')
                private_file.write_text(overlay_text)
                values = load_values(a.root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml')
                names = {'gateway_feature_mode': 'OMI_LLM_GATEWAY_FEATURE_MODE',
                         'chat_agent_route': 'OMI_LLM_CHAT_AGENT_ROUTE',
                         'allow_direct_model_exception': 'OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION',
                         'stt_service_models': 'STT_SERVICE_MODELS',
                         'translation_service_models': 'TRANSLATION_SERVICE_MODELS'}
                named = {v: request['dispatch_inputs'].get(k, '') for k, v in names.items()}
                private = load_private_env(private_file) if private_file.stat().st_size else {}
                check_private_env_against_chart(private, values, named)
                check_translation_endpoint(values, named, private)
                overrides = resolve_env_override_argv(values, named)
                if private_file.stat().st_size:
                    overrides += ['-f', str(private_file)]
                result = produce(request, Reader(), os.environ, a.root.resolve(), private_file, overrides, int(time.time()))
            data = canonical(result).decode() + '\n'
        elif a.mode == 'argv':
            data = '\n'.join(helm_args(a.root / 'backend/charts/backend-listen',
                                      a.root / f'backend/charts/backend-listen/{a.environment}_omi_backend_listen_values.yaml',
                                      a.image_tag, a.project, a.runtime_project, overrides, a.environment)) + '\n'
        else:
            result = produce(json_read(a.request.read_bytes()), Reader(), os.environ, a.root.resolve(),
                             a.private_file, overrides, int(time.time()))
            data = canonical(result).decode() + '\n'
        fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(data)
        return 0
    except Exception:
        # Never stringify an exception from YAML/Helm/subprocess/private data.
        print('LISTEN_OVERLAY_EVIDENCE_REFUSED', file=__import__('sys').stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
