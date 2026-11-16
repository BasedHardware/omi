# LIFECYCLE: permanent
"""Discriminators for state-free readiness, exact metadata proof and UID-scoped cleanup."""

import copy
import hashlib
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import readiness_probe as probe

TOKEN = 'a4' * 16
UID = 'e14da721-ef35-4e91-a986-6e7a62c06f02'
NODE = 'gke-existing-amd64-node'


def completed():
    pod = probe.render(TOKEN, NODE)
    pod['metadata']['uid'] = UID
    pod['status'] = {
        'phase': 'Succeeded',
        'containerStatuses': [
            {
                'name': 'readiness',
                'imageID': 'docker-pullable://' + probe.CONTRACT['image'],
                'restartCount': 0,
                'state': {'terminated': {'exitCode': 0}},
            }
        ],
    }
    report = {
        'result': 'COMPLETED',
        'exit_code': 0,
        'metadata': {
            'result': 'METADATA_READY_ONLY',
            'customer_rows_read': False,
            'state_initialized': False,
            'write_attempted': False,
            'session': ['jobstore_prod', 'batch-pipeline-worker@based-hardware.iam', '172.25.29.2'],
            'tls': True,
            'migrations': copy.deepcopy(probe.CONTRACT['migrations']),
            'indexes': [[n, True, True] for n in ['jobs_due_leased_c', 'jobs_due_result_c', 'jobs_due_retry_c']],
            'rollback': True,
            'source_sha': probe.CONTRACT['source_sha'],
            'supervisor_sha256': probe.CONTRACT['supervisor_sha256'],
            'python': '3.11.15',
            'psycopg': '3.2.10',
        },
    }
    return pod, report


class ReadinessTests(unittest.TestCase):
    def validate(self, pod, report):
        return probe.validate(pod, report, TOKEN, NODE, UID)

    def test_render_pins_reviewed_topology_without_mutable_label_aliases(self):
        expected = {
            'omi/readiness-token': TOKEN,
            'topology.kubernetes.io/region': 'us-central1',
            'topology.kubernetes.io/zone': 'us-central1-a',
        }
        first = probe.render(TOKEN, NODE)
        self.assertEqual(first['metadata']['labels'], expected)
        first['metadata']['labels']['topology.kubernetes.io/zone'] = 'other'
        self.assertEqual(probe.render(TOKEN, NODE)['metadata']['labels'], expected)

    def test_topology_and_token_mutations_refuse_manifest_and_completed_receipts(self):
        original = json.loads((Path(__file__).parent / 'fixtures/pod-api-response.json').read_text())
        report = completed()[1]
        mutations = []
        for key in ('topology.kubernetes.io/region', 'topology.kubernetes.io/zone', 'omi/readiness-token'):
            mutations.append(lambda labels, key=key: labels.pop(key))
            for value in ('other', '', 0, False, None, ['us-central1'], {'value': 'us-central1'}):
                mutations.append(lambda labels, key=key, value=value: labels.update({key: value}))
        mutations.extend(
            [
                lambda labels: labels.update({'topology.kubernetes.io/hostname': NODE}),
                lambda labels: labels.update({'unreviewed': 'extra'}),
            ]
        )
        for mutate in mutations:
            pod = copy.deepcopy(original)
            mutate(pod['metadata']['labels'])
            with self.subTest(labels=pod['metadata']['labels']), self.assertRaisesRegex(
                ValueError, '^REVIEWED_METADATA_REQUIRED$'
            ):
                probe.validate_manifest(pod, TOKEN, NODE)
            with self.assertRaisesRegex(ValueError, '^REVIEWED_METADATA_REQUIRED$'):
                self.validate(pod, report)

    def test_exact_completed_probe_still_requires_cleanup_and_never_proves_serving(self):
        result = self.validate(*completed())
        self.assertEqual(result['result'], 'READINESS_PROBE_ONLY_CLEANUP_PENDING')
        self.assertFalse(result['cleanup_verified'])
        self.assertFalse(result['persistent_state_mounted'])
        self.assertFalse(result['serving_proven'])
        self.assertEqual(result['runtime_admission'], 'CLOSED')

    def test_independent_api_receipt_accepts_omitted_false_host_fields_without_relaxing_identity(self):
        pod = json.loads((Path(__file__).parent / 'fixtures/pod-api-response.json').read_text())
        report = completed()[1]
        for field in ('hostNetwork', 'hostPID', 'hostIPC'):
            self.assertNotIn(field, pod['spec'])
        self.assertEqual(probe.validate_manifest(pod, TOKEN, NODE)['result'], 'REVIEWED_PROBE_MANIFEST_ONLY')
        self.assertFalse(self.validate(pod, report)['serving_proven'])
        mutations = [
            lambda p: p['metadata'].update(name='another-pod'),
            lambda p: p['metadata'].update(namespace='another-namespace'),
            lambda p: p.update(unreviewed='extra'),
        ]
        for field in ('hostNetwork', 'hostPID', 'hostIPC'):
            for value in (True, 0, None, 'false'):
                mutations.append(lambda p, field=field, value=value: p['spec'].update({field: value}))
        for mutate in mutations:
            changed = copy.deepcopy(pod)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                probe.validate_manifest(changed, TOKEN, NODE)
            with self.assertRaises(ValueError):
                self.validate(changed, report)

    def test_no_retry_controller_or_persistent_ledger_is_rendered(self):
        pod = probe.render(TOKEN, NODE)
        self.assertEqual(pod['kind'], 'Pod')
        self.assertEqual(pod['spec']['nodeName'], NODE)
        self.assertEqual(pod['spec']['restartPolicy'], 'Never')
        self.assertEqual(pod['spec']['activeDeadlineSeconds'], 90)
        self.assertEqual(pod['spec']['volumes'], [{'name': 'tmp', 'emptyDir': {'sizeLimit': '64Mi'}}])
        self.assertNotIn(probe.STATE_ROOT, json.dumps(pod))
        self.assertEqual(pod['spec']['containers'][0]['command'][-1], '--readiness')

    def test_manifest_can_be_verified_before_execution_without_accepting_run_evidence(self):
        pod = probe.render(TOKEN, NODE)
        result = probe.validate_manifest(pod, TOKEN, NODE)
        self.assertEqual(result['result'], 'REVIEWED_PROBE_MANIFEST_ONLY')
        with self.assertRaises(ValueError):
            self.validate(pod, completed()[1])
        pod['spec']['containers'][0]['command'] = ['python', '-m', 'database.jobstore', 'migrate']
        with self.assertRaises(ValueError):
            probe.validate_manifest(pod, TOKEN, NODE)

    def test_native_ksa_projection_is_accepted_but_extra_sources_or_paths_refuse(self):
        pod, report = completed()
        name = 'kube-api-access-abcde'
        pod['spec']['volumes'].append(
            {
                'name': name,
                'projected': {
                    'defaultMode': 420,
                    'sources': [
                        {'serviceAccountToken': {'expirationSeconds': 3607, 'path': 'token'}},
                        {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}},
                        {
                            'downwardAPI': {
                                'items': [
                                    {
                                        'path': 'namespace',
                                        'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'},
                                    }
                                ]
                            }
                        },
                    ],
                },
            }
        )
        pod['spec']['containers'][0]['volumeMounts'].append(
            {
                'name': name,
                'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount',
                'readOnly': True,
            }
        )
        self.validate(pod, report)
        for mutate in (
            lambda p: p['spec']['volumes'][1]['projected']['sources'].append({'secret': {'name': 'other'}}),
            lambda p: p['spec']['volumes'][1]['projected']['sources'][0]['serviceAccountToken'].update(
                audience='other'
            ),
            lambda p: p['spec']['volumes'][1]['projected']['sources'][1]['configMap'].update(name='other'),
            lambda p: p['spec']['containers'][0]['volumeMounts'][1].update(mountPath=probe.STATE_ROOT),
        ):
            mutated = copy.deepcopy(pod)
            mutate(mutated)
            with self.assertRaises(ValueError):
                self.validate(mutated, report)

    def test_contract_matches_pinned_image_and_first_eight_source_migrations(self):
        package = Path(probe.__file__).parent
        artifact = json.loads((package / 'artifact-contract.json').read_text())
        self.assertEqual(probe.CONTRACT['source_sha'], artifact['source_sha'])
        self.assertEqual(probe.CONTRACT['supervisor_sha256'], artifact['supervisor_sha256'])
        self.assertEqual(probe.CONTRACT['image'], artifact['destination'] + '@' + artifact['oci_manifest_digest'])
        self.assertEqual(
            hashlib.sha256((package / 'runner_readiness.py').read_bytes()).hexdigest(), artifact['readiness_sha256']
        )
        self.assertEqual([r[0] for r in probe.CONTRACT['migrations']], list(range(1, 9)))
        for version, name, checksum in probe.CONTRACT['migrations']:
            path = package.parents[1] / 'database/jobstore/migrations' / f'{version:04d}_{name}.sql'
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)

    def test_api_defaults_are_enumerated_without_accepting_metadata_or_spec_mutations(self):
        pod, report = completed()
        pod['metadata'].update(resourceVersion='123', managedFields=[], creationTimestamp='2026-11-16T00:00:00Z')
        pod['spec'].update(
            serviceAccount=probe.KSA,
            schedulerName='default-scheduler',
            priority=0,
            preemptionPolicy='PreemptLowerPriority',
            tolerations=[
                {
                    'key': 'node.kubernetes.io/' + key,
                    'operator': 'Exists',
                    'effect': 'NoExecute',
                    'tolerationSeconds': 300,
                }
                for key in ('unreachable', 'not-ready')
            ],
        )
        pod['spec']['containers'][0].update(stdin=False, stdinOnce=False, tty=False)
        self.validate(pod, report)
        for mutate in (
            lambda p: p['metadata'].update(finalizers=['example.com/hold']),
            lambda p: p['metadata']['annotations'].update(
                {'container.apparmor.security.beta.kubernetes.io/readiness': 'unconfined'}
            ),
            lambda p: p['metadata']['labels'].update({'injected': 'true'}),
            lambda p: p['metadata'].update(generateName='another-'),
            lambda p: p['spec'].update(priorityClassName='system-node-critical'),
            lambda p: p['spec'].update(priority=1000),
            lambda p: p['spec'].update(nodeSelector={'other': 'node'}),
            lambda p: p['spec'].update(imagePullSecrets=[{'name': 'other'}]),
            lambda p: p['spec'].update(schedulingGates=[{'name': 'example.com/hold'}]),
            lambda p: p['spec']['tolerations'][0].update(tolerationSeconds=600),
            lambda p: p['spec']['containers'][0].update(tty=True),
            lambda p: p['spec']['containers'][0].update(
                resizePolicy=[{'resourceName': 'cpu', 'restartPolicy': 'RestartContainer'}]
            ),
            lambda p: p['spec']['containers'][0]['env'][0].update(extra='unreviewed'),
        ):
            changed = copy.deepcopy(pod)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                probe.validate_manifest(changed, TOKEN, NODE)
            with self.assertRaises(ValueError):
                self.validate(changed, report)

    def test_unique_run_and_existing_node_identifiers_reject_paths_and_shell_text(self):
        for token in ('', 'a' * 31, 'A' * 32, '../other', 'a' * 32 + ';delete', None):
            with self.subTest(token=token), self.assertRaises(ValueError):
                probe.render(token, NODE)
        for node in ('', '*', '../node', 'node;other', 'node/name', None):
            with self.subTest(node=node), self.assertRaises(ValueError):
                probe.render(TOKEN, node)

    def test_identity_or_lifecycle_mismatch_refuses_acceptance(self):
        mutations = [
            lambda p: p['metadata'].update(uid='fe837f7c-2e31-4e15-83d9-d7f981a05cc0'),
            lambda p: p['metadata'].update(namespace='other'),
            lambda p: p['metadata'].update(ownerReferences=[{'kind': 'Job'}]),
            lambda p: p['metadata'].update(deletionTimestamp='2026-11-16T00:00:00Z'),
            lambda p: p['spec'].update(nodeName='other-node'),
            lambda p: p['spec'].update(hostname='other-host'),
            lambda p: p['spec'].update(serviceAccountName='other'),
            lambda p: p['spec'].update(restartPolicy='Always'),
            lambda p: p['spec'].update(activeDeadlineSeconds=900),
            lambda p: p['status'].update(phase='Running'),
            lambda p: p['status']['containerStatuses'][0].update(restartCount=1),
            lambda p: p['status']['containerStatuses'][0].update(
                imageID='sha256:724e762154931739b8d230ba722102a488b458f55fdc33a6331b3683be72e34e'
            ),
            lambda p: p['status']['containerStatuses'][0]['state']['terminated'].update(exitCode=2),
        ]
        for index, mutate in enumerate(mutations):
            pod, report = completed()
            mutate(pod)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.validate(pod, report)

    def test_added_credentials_state_or_privilege_cannot_hide_in_api_default_fields(self):
        mutations = [
            lambda p: p['spec']['volumes'].append({'name': 'state', 'persistentVolumeClaim': {'claimName': 'other'}}),
            lambda p: p['spec']['containers'][0]['volumeMounts'].append({'name': 'tmp', 'mountPath': probe.STATE_ROOT}),
            lambda p: p['spec']['containers'].append(copy.deepcopy(p['spec']['containers'][0])),
            lambda p: p['spec'].update(initContainers=[{'name': 'writer'}]),
            lambda p: p['spec'].update(ephemeralContainers=[{'name': 'debug'}]),
            lambda p: p['spec']['containers'][0].update(args=['--apply']),
            lambda p: p['spec']['containers'][0].update(livenessProbe={'exec': {'command': ['python', 'write.py']}}),
            lambda p: p['spec']['containers'][0].update(readinessProbe={'httpGet': {'path': '/', 'port': 80}}),
            lambda p: p['spec']['containers'][0].update(startupProbe={'exec': {'command': ['python', 'write.py']}}),
            lambda p: p['spec']['containers'][0].update(
                terminationMessagePath='/var/run/secrets/kubernetes.io/serviceaccount/token'
            ),
            lambda p: p['spec']['containers'][0]['resources']['requests'].update(**{'nvidia.com/gpu': '1'}),
            lambda p: p['spec']['containers'][0]['volumeMounts'][0].update(subPath='unreviewed'),
            lambda p: p['spec']['volumes'][0]['emptyDir'].update(medium='Memory'),
            lambda p: p['spec']['containers'][0].update(envFrom=[{'secretRef': {'name': 'credentials'}}]),
            lambda p: p['spec']['containers'][0]['env'].append(
                {'name': 'GOOGLE_OAUTH_ACCESS_TOKEN', 'value': 'fixture'}
            ),
            lambda p: p['spec']['containers'][0]['securityContext'].update(runAsUser=0),
            lambda p: p['spec']['containers'][0]['securityContext']['capabilities'].update(add=['SYS_ADMIN']),
            lambda p: p['spec']['securityContext'].update(fsGroup=0),
            lambda p: p['spec'].update(hostNetwork=True),
            lambda p: p['spec'].update(hostAliases=[{'ip': '1.2.3.4', 'hostnames': ['metadata.google.internal']}]),
        ]
        for index, mutate in enumerate(mutations):
            pod, report = completed()
            mutate(pod)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.validate(pod, report)

    def test_metadata_requires_exact_schema_identity_and_read_only_outcomes(self):
        for key, value in (
            ('result', 'HOLD'),
            ('session', ['other', 'other', 'other']),
            ('tls', False),
            ('tls', 1),
            ('write_attempted', True),
            ('customer_rows_read', True),
            ('state_initialized', True),
            ('rollback', False),
            ('python', '3.12.3'),
            ('psycopg', 'other'),
            ('source_sha', 'other'),
            ('supervisor_sha256', 'other'),
            ('failure_class', 'CloseFailure'),
        ):
            pod, report = completed()
            report['metadata'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(pod, report)
        for mutate in (
            lambda r: r['metadata']['migrations'].append([9, 'protected_share', 'unexpected']),
            lambda r: r['metadata']['migrations'][0].__setitem__(2, 'changed'),
            lambda r: r['metadata']['indexes'][0].__setitem__(2, False),
            lambda r: r.update(result='PROCESS_TERMINATED'),
            lambda r: r.update(exit_code=False),
        ):
            pod, report = completed()
            mutate(report)
            with self.assertRaises(ValueError):
                self.validate(pod, report)

    def test_cleanup_request_fences_reused_name_with_uid_precondition(self):
        request = probe.cleanup_request(TOKEN, UID)
        self.assertEqual(request['path'], '/api/v1/namespaces/prod-omi-backend/pods/jobstore-readiness-' + TOKEN)
        self.assertEqual(request['body']['preconditions'], {'uid': UID})
        self.assertEqual(request['body']['gracePeriodSeconds'], 15)
        self.assertEqual(request['body']['propagationPolicy'], 'Foreground')
        for value in (None, '', '*', '../another', UID + '/other'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.cleanup_request(TOKEN, value)

    def test_receipt_inputs_are_bounded_and_duplicate_json_keys_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'receipt.json'
            path.write_text('{"result":"HOLD","result":"COMPLETED"}')
            with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
                probe.read_json(path)
            path.write_text('x' * 65537)
            with self.assertRaisesRegex(ValueError, 'BOUNDED_INPUT_REQUIRED'):
                probe.read_json(path, 65536)

    def test_cli_renders_and_validates_locally_and_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = [
                sys.executable,
                probe.__file__,
                'render',
                '--run-token',
                TOKEN,
                '--node-name',
                NODE,
                '--output',
                str(root / 'pod.json'),
            ]
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads((root / 'pod.json').read_text())['kind'], 'Pod')
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['result'], 'HOLD')
            self.assertEqual(json.loads(result.stdout)['failure_class'], 'FileExistsError')
            pod, report = completed()
            (root / 'completed-pod.json').write_text(json.dumps(pod))
            (root / 'log.json').write_text(json.dumps(report))
            args = [
                sys.executable,
                probe.__file__,
                'validate',
                '--run-token',
                TOKEN,
                '--node-name',
                NODE,
                '--pod-uid',
                UID,
                '--pod-receipt',
                str(root / 'completed-pod.json'),
                '--log-file',
                str(root / 'log.json'),
                '--output',
                str(root / 'validated.json'),
            ]
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse(json.loads((root / 'validated.json').read_text())['cleanup_verified'])


if __name__ == '__main__':
    unittest.main()
