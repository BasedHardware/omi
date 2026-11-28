"""Offline fixtures for the SCA-3748 image-only live lease guard."""

import contextlib
import copy
import io
import json
import unittest
from unittest import mock

import record_token_lease_live_guard as guard

NS = 'prod-omi-backend'
SERVE = {
    'RECORD_TOKEN_LEASE_MODE': 'serve',
    'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '100',
    'RECORD_TOKEN_LEASE_SECONDS': '3600',
    'RECORD_TOKEN_LEASE_DEPLOYED_AT': '1795662310',
}


def referenced(config='prod-omi-backend-config'):
    # The shape the runtime manifest renders for Listen and Pusher.
    return [{'name': key, 'valueFrom': {'configMapKeyRef': {'name': config, 'key': key}}} for key in guard.KEYS]


def deployment(env, kind='Deployment', env_from=None):
    container = {'name': 'main', 'image': 'gcr.io/x@sha256:' + '1' * 64, 'env': env}
    if env_from is not None:
        container['envFrom'] = env_from
    template = {'spec': {'containers': [container]}}
    spec = {'jobTemplate': {'spec': {'template': template}}} if kind == 'CronJob' else {'template': template}
    return {'kind': kind, 'metadata': {'name': 'target'}, 'spec': spec}


class Cluster:
    def __init__(self, objects):
        self.objects, self.calls = objects, []

    def __call__(self, namespace, *args):
        assert namespace == NS
        self.calls.append(args)
        return copy.deepcopy(self.objects[args])


class LiveGuardTests(unittest.TestCase):
    def cluster(self, data=None, workload=None):
        return Cluster(
            {
                ('deployment/prod-omi-pusher',): workload or deployment(referenced()),
                ('configmap', 'prod-omi-backend-config'): {'data': dict(SERVE if data is None else data)},
            }
        )

    def test_live_serve_vector_through_config_map_passes_with_reads_only(self):
        cluster = self.cluster()
        receipt = guard.check(NS, ['deployment/prod-omi-pusher'], [], read=cluster)
        self.assertEqual(receipt['verdict'], 'serve')
        self.assertEqual(
            receipt['workloads']['deployment/prod-omi-pusher']['main'],
            {'mode': 'serve', 'serve_percent': 100, 'seconds': 3600.0, 'deployed_at': 1795662310.0},
        )
        # One workload read and one ConfigMap read; no Secret, no write verb exists.
        self.assertEqual(cluster.calls, [('deployment/prod-omi-pusher',), ('configmap', 'prod-omi-backend-config')])

    def test_every_non_serving_live_vector_refuses(self):
        cases = {
            'off': {'RECORD_TOKEN_LEASE_MODE': 'off'},
            'shadow': {'RECORD_TOKEN_LEASE_MODE': 'shadow'},
            'blank_mode': {'RECORD_TOKEN_LEASE_MODE': ''},
            'typo': {'RECORD_TOKEN_LEASE_MODE': 'serv'},
            'percent_10': {'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': '10'},
            'percent_blank': {'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT': ''},
            'epoch_zero': {'RECORD_TOKEN_LEASE_DEPLOYED_AT': '0'},
            'epoch_nan': {'RECORD_TOKEN_LEASE_DEPLOYED_AT': 'nan'},
            'seconds_short': {'RECORD_TOKEN_LEASE_SECONDS': '60'},
        }
        for label, change in cases.items():
            with self.subTest(label):
                with self.assertRaises(guard.Refused):
                    guard.check(NS, ['deployment/prod-omi-pusher'], [], read=self.cluster({**SERVE, **change}))

    def test_required_target_missing_a_key_or_its_config_map_key_refuses(self):
        with self.assertRaises(guard.Refused):
            guard.check(NS, ['deployment/prod-omi-pusher'], [], read=self.cluster({}))
        workload = deployment(referenced()[:3])
        with self.assertRaisesRegex(guard.Refused, 'missing RECORD_TOKEN_LEASE_DEPLOYED_AT'):
            guard.check(NS, ['deployment/prod-omi-pusher'], [], read=self.cluster(workload=workload))

    def test_secret_or_field_reference_is_refused_without_reading_it(self):
        env = referenced()
        env[0] = {'name': guard.KEYS[0], 'valueFrom': {'secretKeyRef': {'name': 'backend-secrets', 'key': 'x'}}}
        cluster = self.cluster(workload=deployment(env))
        with self.assertRaisesRegex(guard.Refused, 'literal or a ConfigMap key reference'):
            guard.check(NS, ['deployment/prod-omi-pusher'], [], read=cluster)
        self.assertNotIn(('secret', 'backend-secrets'), cluster.calls)

    def test_allow_unset_target_passes_unset_and_validates_any_key_it_carries(self):
        unset = Cluster({('deployment/prod-omi-batch-pipeline-worker',): deployment([])})
        receipt = guard.check(NS, [], ['deployment/prod-omi-batch-pipeline-worker'], read=unset)
        self.assertEqual(
            receipt['workloads']['deployment/prod-omi-batch-pipeline-worker'], {'main': 'unset (runtime serves)'}
        )
        literal = [{'name': key, 'value': value} for key, value in SERVE.items()]
        for mode, refused in (('serve', False), ('off', True), ('shadow', True)):
            with self.subTest(mode):
                env = [dict(entry) for entry in literal]
                env[0]['value'] = mode
                cluster = Cluster({('deployment/prod-omi-batch-pipeline-worker',): deployment(env)})
                call = lambda: guard.check(NS, [], ['deployment/prod-omi-batch-pipeline-worker'], read=cluster)
                if refused:
                    self.assertRaises(guard.Refused, call)
                else:
                    self.assertEqual(call()['verdict'], 'serve')
        # A lone mode key is a partial vector, not unset: refuse it.
        partial = Cluster({('deployment/prod-omi-batch-pipeline-worker',): deployment([literal[0]])})
        with self.assertRaises(guard.Refused):
            guard.check(NS, [], ['deployment/prod-omi-batch-pipeline-worker'], read=partial)

    def test_allow_unset_target_reads_an_env_from_config_map(self):
        workload = deployment([], env_from=[{'configMapRef': {'name': 'worker-config'}}, {'secretRef': {'name': 's'}}])
        cluster = Cluster(
            {
                ('deployment/prod-omi-batch-pipeline-worker',): workload,
                ('configmap', 'worker-config'): {'data': {**SERVE, 'RECORD_TOKEN_LEASE_MODE': 'off'}},
            }
        )
        with self.assertRaisesRegex(guard.Refused, "'off'"):
            guard.check(NS, [], ['deployment/prod-omi-batch-pipeline-worker'], read=cluster)
        self.assertNotIn(('secret', 's'), cluster.calls)

    def test_cron_job_pod_template_is_read(self):
        cluster = Cluster(
            {
                ('cronjob/record-seal-repair',): deployment(referenced(), kind='CronJob'),
                ('configmap', 'prod-omi-backend-config'): {'data': dict(SERVE, RECORD_TOKEN_LEASE_MODE='off')},
            }
        )
        with self.assertRaises(guard.Refused):
            guard.check(NS, ['cronjob/record-seal-repair'], [], read=cluster)

    def test_unsupported_or_empty_target_refuses(self):
        for required in ([], ['secret/backend-secrets'], ['deployment/']):
            with self.subTest(required):
                with self.assertRaises(guard.Refused):
                    guard.check(NS, required, [], read=self.cluster())

    def test_main_exits_nonzero_on_refusal_or_read_failure_and_prints_the_receipt(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(guard, 'kubectl', self.cluster()), contextlib.redirect_stdout(out):
            self.assertEqual(guard.main(['--namespace', NS, '--require', 'deployment/prod-omi-pusher']), 0)
        self.assertEqual(json.loads(out.getvalue())['verdict'], 'serve')
        off = self.cluster(dict(SERVE, RECORD_TOKEN_LEASE_MODE='off'))
        with mock.patch.object(guard, 'kubectl', off), contextlib.redirect_stderr(err):
            self.assertEqual(guard.main(['--namespace', NS, '--require', 'deployment/prod-omi-pusher']), 1)
        self.assertIn('engage the kill', err.getvalue())

        def unreachable(*args):
            raise guard.subprocess.CalledProcessError(1, 'kubectl')

        with mock.patch.object(guard, 'kubectl', unreachable), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(guard.main(['--namespace', NS, '--require', 'deployment/prod-omi-pusher']), 1)


if __name__ == '__main__':
    unittest.main()
