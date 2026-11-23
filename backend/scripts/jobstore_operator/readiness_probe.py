# LIFECYCLE: permanent
"""Pure preparation/verification for one state-free probe; never contacts Kubernetes or SQL."""

import argparse
import json
import re
import uuid
from pathlib import Path

from readiness_contract import CONTRACT, READINESS_ENV

NAMESPACE = 'prod-omi-backend'
KSA = 'batch-pipeline-worker'
HOSTNAME = 'jobstore-reconcile-0'
STATE_ROOT = '/home/ubuntu/.local/state/omi-jobstore-reconcile'
TOKEN_LABEL = 'omi/readiness-token'
# Exact admission labels observed on 2026-11-16. Relocation needs re-review
# and fresh independent node UID/region/zone evidence, never caller-supplied labels.
TOPOLOGY_LABELS = {'topology.kubernetes.io/region': 'us-central1', 'topology.kubernetes.io/zone': 'us-central1-a'}
COMMAND = ['/opt/operator-venv/bin/python', '/opt/runner/process_guard.py', '--readiness']
TARGET = ['jobstore_prod', 'batch-pipeline-worker@based-hardware.iam', '172.25.29.2']
INDEXES = ['jobs_due_leased_c', 'jobs_due_result_c', 'jobs_due_retry_c']


def pod_name(token):
    if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
        raise ValueError('EXACT_RANDOM_RUN_TOKEN_REQUIRED')
    return 'jobstore-readiness-' + token


def checked_uid(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('EXACT_POD_UID_REQUIRED')
    return value


def render(token, node):
    name = pod_name(token)
    if not isinstance(node, str) or not re.fullmatch(r'[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?', node):
        raise ValueError('REVIEWED_EXISTING_NODE_REQUIRED')
    return {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': name,
            'namespace': NAMESPACE,
            'labels': {TOKEN_LABEL: token, **TOPOLOGY_LABELS},
            'annotations': {
                'omi/source-sha': CONTRACT['source_sha'],
                'omi/supervisor-sha256': CONTRACT['supervisor_sha256'],
                'omi/scope': 'READINESS_PROBE_ONLY_NO_STATE_OR_SERVING',
            },
        },
        'spec': {
            # Pin an independently admitted existing node: no scheduler or replacement controller.
            'nodeName': node,
            'hostname': HOSTNAME,
            'serviceAccountName': KSA,
            'restartPolicy': 'Never',
            'activeDeadlineSeconds': 90,
            'terminationGracePeriodSeconds': 15,
            'hostNetwork': False,
            'hostPID': False,
            'hostIPC': False,
            'dnsPolicy': 'ClusterFirst',
            'enableServiceLinks': False,
            'automountServiceAccountToken': True,
            'securityContext': {
                'runAsUser': 1000,
                'runAsGroup': 1000,
                'runAsNonRoot': True,
                'seccompProfile': {'type': 'RuntimeDefault'},
            },
            'containers': [
                {
                    'name': 'readiness',
                    'image': CONTRACT['image'],
                    'imagePullPolicy': 'IfNotPresent',
                    'terminationMessagePath': '/dev/termination-log',
                    'terminationMessagePolicy': 'File',
                    'command': COMMAND.copy(),
                    'securityContext': {
                        'allowPrivilegeEscalation': False,
                        'readOnlyRootFilesystem': True,
                        'capabilities': {'drop': ['ALL']},
                    },
                    'resources': {
                        'requests': {'cpu': '100m', 'memory': '256Mi'},
                        'limits': {'cpu': '500m', 'memory': '512Mi'},
                    },
                    'env': [{'name': name, 'value': value} for name, value in READINESS_ENV.items()],
                    'volumeMounts': [{'name': 'tmp', 'mountPath': '/tmp'}],
                }
            ],
            'volumes': [{'name': 'tmp', 'emptyDir': {'sizeLimit': '64Mi'}}],
        },
    }


def exact(actual, expected):
    # Python equality alone accepts 0 == False and True == 1 in evidence.
    return json.dumps(actual, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


def projection(actual, expected):
    """Require reviewed values while permitting API-added default object fields."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or any(
            k not in actual or not projection(actual[k], v) for k, v in expected.items()
        ):
            return False
        return True
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(projection(a, e) for a, e in zip(actual, expected))
        )
    return exact(actual, expected)


def cleanup_request(token, uid):
    """DELETE only this exact name/UID; API preconditions refuse name reuse."""
    return {
        'path': '/api/v1/namespaces/' + NAMESPACE + '/pods/' + pod_name(token),
        'body': {
            'apiVersion': 'v1',
            'kind': 'DeleteOptions',
            'preconditions': {'uid': checked_uid(uid)},
            'gracePeriodSeconds': 15,
            'propagationPolicy': 'Foreground',
        },
    }


def validate_manifest(pod, token, node):
    """Check server-dry-run mutations before any Pod is allowed to execute."""
    if set(pod) - {'apiVersion', 'kind', 'metadata', 'spec', 'status'}:
        raise ValueError('UNREVIEWED_POD_FIELD')
    expected = render(token, node)
    metadata = pod.get('metadata', {})
    if metadata.get('ownerReferences') or metadata.get('deletionTimestamp') or metadata.get('finalizers'):
        raise ValueError('EXACT_STANDALONE_POD_REQUIRED')
    if not exact(metadata.get('labels'), expected['metadata']['labels']) or not exact(
        metadata.get('annotations'), expected['metadata']['annotations']
    ):
        raise ValueError('REVIEWED_METADATA_REQUIRED')
    api_metadata = {
        'uid',
        'resourceVersion',
        'generation',
        'creationTimestamp',
        'managedFields',
        'selfLink',
        'finalizers',
    }
    if set(metadata) - set(expected['metadata']) - api_metadata:
        raise ValueError('UNREVIEWED_METADATA_FIELD')
    spec = pod.get('spec', {})
    if spec.get('initContainers') or spec.get('ephemeralContainers'):
        raise ValueError('NO_ADDITIONAL_CONTAINERS_ALLOWED')
    # Native KSA token projection can be injected by the API. No other added mounts/volumes.
    candidate = json.loads(json.dumps(pod))
    # These non-pointer Kubernetes bools are omitted when false in API JSON.
    # Normalize absence only; true, null and numeric substitutions still refuse.
    for field in ('hostNetwork', 'hostPID', 'hostIPC'):
        candidate.setdefault('spec', {}).setdefault(field, False)
    volumes = candidate.get('spec', {}).get('volumes', [])
    mounts = candidate.get('spec', {}).get('containers', [{}])[0].get('volumeMounts', [])
    injected = [v for v in volumes if v.get('name', '').startswith('kube-api-access-')]
    if len(injected) > 1:
        raise ValueError('UNREVIEWED_VOLUME')
    if injected:
        volume = injected[0]
        projected = volume.get('projected', {})
        sources = projected.get('sources', [])
        if (
            set(volume) != {'name', 'projected'}
            or set(projected) != {'defaultMode', 'sources'}
            or not exact(projected['defaultMode'], 420)
        ):
            raise ValueError('UNREVIEWED_TOKEN_PROJECTION')
        if len(sources) != 3 or any(not isinstance(s, dict) or len(s) != 1 for s in sources):
            raise ValueError('UNREVIEWED_TOKEN_PROJECTION')
        entries = {next(iter(s)): next(iter(s.values())) for s in sources}
        service_token = entries.get('serviceAccountToken', {})
        expiration = service_token.get('expirationSeconds')
        if (
            set(entries) != {'serviceAccountToken', 'configMap', 'downwardAPI'}
            or set(service_token) != {'path', 'expirationSeconds'}
            or service_token['path'] != 'token'
            or type(expiration) is not int
            or not 600 <= expiration <= 3607
            or not exact(
                entries['configMap'], {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}
            )
            or not exact(
                entries['downwardAPI'],
                {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]},
            )
        ):
            raise ValueError('UNREVIEWED_TOKEN_PROJECTION')
        token_mount = {
            'name': volume['name'],
            'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount',
            'readOnly': True,
        }
        if sum(exact(m, token_mount) for m in mounts) != 1:
            raise ValueError('UNREVIEWED_TOKEN_MOUNT')
        volumes.remove(volume)
        mounts.remove(token_mount)
    if not projection(candidate, expected):
        raise ValueError('REVIEWED_POD_SPEC_REQUIRED')
    container = spec['containers'][0]
    if any(
        container.get(k)
        for k in (
            'args',
            'envFrom',
            'ports',
            'lifecycle',
            'readinessProbe',
            'livenessProbe',
            'startupProbe',
            'workingDir',
            'volumeDevices',
        )
    ):
        raise ValueError('NO_ADDITIONAL_RUNTIME_INPUTS_ALLOWED')
    if any(spec.get(k) for k in ('shareProcessNamespace', 'hostAliases', 'dnsConfig', 'runtimeClassName', 'overhead')):
        raise ValueError('NO_ADDITIONAL_PRIVILEGE_ALLOWED')
    if not exact(container.get('resources'), expected['spec']['containers'][0]['resources']):
        raise ValueError('REVIEWED_RESOURCE_CEILINGS_REQUIRED')
    for mount in mounts:
        if mount.get('readOnly') is False:
            mount.pop('readOnly')
    if not exact(mounts, expected['spec']['containers'][0]['volumeMounts']):
        raise ValueError('REVIEWED_MOUNTS_REQUIRED')
    for volume in volumes:
        if volume.get('emptyDir', {}).get('medium') == '':
            volume['emptyDir'].pop('medium')
    if not exact(volumes, expected['spec']['volumes']):
        raise ValueError('REVIEWED_VOLUMES_REQUIRED')
    security = dict(container.get('securityContext', {}))
    if security.pop('privileged', False) is not False or not exact(
        security, expected['spec']['containers'][0]['securityContext']
    ):
        raise ValueError('REVIEWED_CONTAINER_SECURITY_REQUIRED')
    if not exact(spec.get('securityContext'), expected['spec']['securityContext']):
        raise ValueError('REVIEWED_POD_SECURITY_REQUIRED')
    # Normalize only enumerated API defaults, then compare the entire remaining
    # spec. A newly introduced field must be reviewed, never accepted implicitly.
    normalized = candidate['spec']
    defaults = {
        'serviceAccount': KSA,
        'schedulerName': 'default-scheduler',
        'priority': 0,
        'preemptionPolicy': 'PreemptLowerPriority',
    }
    for key, value in defaults.items():
        if key in normalized:
            if not exact(normalized.pop(key), value):
                raise ValueError('UNREVIEWED_API_DEFAULT')
    if 'tolerations' in normalized:
        tolerations = normalized.pop('tolerations')
        standard = [
            {'key': 'node.kubernetes.io/' + key, 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}
            for key in ('not-ready', 'unreachable')
        ]
        if (
            not isinstance(tolerations, list)
            or len(tolerations) != 2
            or not all(sum(exact(actual, allowed) for actual in tolerations) == 1 for allowed in standard)
        ):
            raise ValueError('UNREVIEWED_TOLERATIONS')
    normalized_container = normalized['containers'][0]
    for key, value in {'stdin': False, 'stdinOnce': False, 'tty': False}.items():
        if key in normalized_container and not exact(normalized_container.pop(key), value):
            raise ValueError('UNREVIEWED_CONTAINER_DEFAULT')
    normalized_container['securityContext'] = security
    if not exact(normalized, expected['spec']):
        raise ValueError('UNREVIEWED_SPEC_FIELD')
    return {
        'result': 'REVIEWED_PROBE_MANIFEST_ONLY',
        'pod_name': pod_name(token),
        'node': node,
        'runtime_admission': 'CLOSED',
    }


def validate(pod, report, token, node, uid):
    validate_manifest(pod, token, node)
    if pod.get('metadata', {}).get('uid') != checked_uid(uid):
        raise ValueError('EXACT_STANDALONE_POD_REQUIRED')
    spec = pod['spec']
    status = pod.get('status', {})
    statuses = status.get('containerStatuses', [])
    if status.get('phase') != 'Succeeded' or len(statuses) != 1:
        raise ValueError('ONE_SUCCEEDED_CONTAINER_REQUIRED')
    live = statuses[0]
    image = CONTRACT['image']
    digest = image.split('@')[1]
    identities = {image, 'docker-pullable://' + image, digest, 'containerd://' + digest}
    identities.add(image.replace('gcr.io/based-hardware/', 'us-docker.pkg.dev/based-hardware/gcr.io/'))
    if (
        live.get('imageID') not in identities
        or live.get('name') != 'readiness'
        or not exact(live.get('restartCount'), 0)
    ):
        raise ValueError('EXACT_RUNNING_IMAGE_WITHOUT_RESTART_REQUIRED')
    if not exact(live.get('state', {}).get('terminated', {}).get('exitCode'), 0):
        raise ValueError('SUCCESSFUL_PROCESS_EXIT_REQUIRED')
    expected_report = {
        'result': 'COMPLETED',
        'exit_code': 0,
        'metadata': {
            'result': 'METADATA_READY_ONLY',
            'customer_rows_read': False,
            'state_initialized': False,
            'write_attempted': False,
            'session': TARGET,
            'tls': True,
            'migrations': [row.copy() for row in CONTRACT['migrations']],
            'indexes': [[n, True, True] for n in INDEXES],
            'rollback': True,
            'source_sha': CONTRACT['source_sha'],
            'supervisor_sha256': CONTRACT['supervisor_sha256'],
            'python': '3.11.15',
            'psycopg': '3.2.10',
        },
    }
    if not exact(report, expected_report):
        raise ValueError('EXACT_READ_ONLY_METADATA_RECEIPT_REQUIRED')
    return {
        'result': 'READINESS_PROBE_ONLY_CLEANUP_PENDING',
        'pod_name': pod_name(token),
        'pod_uid': uid,
        'node': node,
        'image': image,
        'image_id': live['imageID'],
        'source_sha': CONTRACT['source_sha'],
        'mode': '--readiness',
        'metadata': expected_report['metadata'],
        'persistent_state_mounted': False,
        'runtime_admission': 'CLOSED',
        'serving_proven': False,
        'cleanup_verified': False,
    }


def read_json(path, limit=1048576):
    with open(path, 'rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('BOUNDED_INPUT_REQUIRED')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('render', 'check-manifest', 'validate', 'cleanup'))
    parser.add_argument('--run-token', required=True)
    parser.add_argument('--node-name')
    parser.add_argument('--pod-uid')
    parser.add_argument('--pod-receipt', type=Path)
    parser.add_argument('--log-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == 'render':
            result = render(args.run_token, args.node_name)
        elif args.mode == 'cleanup':
            result = cleanup_request(args.run_token, args.pod_uid)
        elif args.mode == 'check-manifest':
            result = validate_manifest(read_json(args.pod_receipt), args.run_token, args.node_name)
        else:
            result = validate(
                read_json(args.pod_receipt),
                read_json(args.log_file, 65536),
                args.run_token,
                args.node_name,
                args.pod_uid,
            )
        with args.output.open('x') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
    except Exception as error:
        # Exception text may contain receipt bytes or paths. Class names expose
        # a useful fixed category without publishing that input.
        print(
            json.dumps({'result': 'HOLD', 'scope': 'READINESS_PREPARATION_ONLY', 'failure_class': type(error).__name__})
        )
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
