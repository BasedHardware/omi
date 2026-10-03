"""Render a dev-only isolated workload. Does not call kubectl or read secrets."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from testing.live_stt_soak.safety import NAMESPACE, PROJECT


def render(image: str, mode: str, sessions: int, fault_after: float, order: str, paid_secret: str | None) -> list[dict]:
    if not re.fullmatch(r'gcr\.io/(based-hardware|based-hardware-dev)/backend@sha256:[0-9a-f]{64}', image):
        raise ValueError('backend image digest required')
    if mode not in ('fake', 'paid') or not 1 <= sessions <= 40 or not 0 <= fault_after <= 120:
        raise ValueError('invalid mode, concurrency or fault time')
    if order not in (
        'soniox,modulate-velma-2',
        'modulate-velma-2,soniox',
        'parakeet-window,soniox,modulate-velma-2',
        'parakeet-window,modulate-velma-2,soniox',
    ):
        raise ValueError('only the two paid adapter orders are supported')
    if mode == 'paid' and not paid_secret:
        raise ValueError('paid mode requires an existing dev-namespace secret containing only provider keys')
    labels = {'app': 'live-stt-soak'}
    values = {
        'OMI_STT_SOAK_ISOLATED': '1',
        'OMI_HARNESS_INSTANCE': 'live-stt-soak',
        'OMI_ENV_STAGE': 'offline',
        'PROVIDER_MODE': 'offline',
        'OMI_JIT_QA_LOCAL_STACK': '1',
        'GOOGLE_CLOUD_PROJECT': PROJECT,
        'FIREBASE_PROJECT_ID': PROJECT,
        'FIRESTORE_EMULATOR_HOST': '127.0.0.1:8085',
        'REDIS_DB_HOST': '127.0.0.1',
        'REDIS_DB_PORT': '6379',
        'OMI_STT_SOAK_MODE': mode,
        'OMI_STT_SOAK_SESSIONS': str(sessions),
        'OMI_STT_SOAK_FAULT_AFTER': str(fault_after),
        'OMI_STT_SOAK_FAULTS': '0' if order.startswith('parakeet-window,') else str(sessions),
        'STT_CONNECT_ORDER_FROM_CONFIG': 'true',
        'STT_ROUTING_MODE': 'shadow',
        'STT_ROUTING_ON_PERCENT': '0',
        'STT_SERVICE_MODELS': order,
        'STT_FAILOVER_RECOVERY_ENABLED': 'true',
        'SONIOX_MONTHLY_CEILING_USD': '0',
        'FAIR_USE_ENABLED': 'false',
        'CONVERSATION_APPS_OPT_IN_ONLY': 'true',
        'LISTEN_FINALIZATION_DISPATCH_MODE': 'inline',
        'MEMORY_ENABLED': 'off',
        'ENCRYPTION_SECRET': 'isolated-stt-soak-encryption-secret-32-bytes',
        'HOSTED_PARAKEET_API_URL': 'http://127.0.0.1:8080',
        'PARAKEET_BATCH_PRESSURE_POOL_HOST': '127.0.0.1',
        'PARAKEET_BATCH_PRESSURE_MIN_REPLICAS': '1',
        'PARAKEET_WINDOW_ALLOCATION_PERCENT': '100',
        'PARAKEET_WINDOW_MAX_SESSIONS': str(sessions),
    }
    env = [{'name': key, 'value': value} for key, value in values.items()]
    for key in ('SONIOX_API_KEY', 'MODULATE_API_KEY'):
        env.append(
            {'name': key, 'value': 'local-protocol-peer'}
            if mode == 'fake'
            else {
                'name': key,
                'valueFrom': {'secretKeyRef': {'name': paid_secret, 'key': key}},
            }
        )
    for key in ('ADMIN_KEY', 'METRICS_SECRET'):
        env.append({'name': key, 'valueFrom': {'secretKeyRef': {'name': 'live-stt-soak-auth', 'key': key}}})
    deployment = {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {'name': 'live-stt-soak', 'namespace': NAMESPACE},
        'spec': {
            'replicas': 1,
            'strategy': {'type': 'Recreate'},
            'selector': {'matchLabels': labels},
            'template': {
                'metadata': {'labels': labels},
                'spec': {
                    'automountServiceAccountToken': False,
                    'terminationGracePeriodSeconds': 120,
                    'containers': [
                        {
                            'name': 'listen',
                            'image': image,
                            'env': env,
                            'command': [
                                'uvicorn',
                                'testing.live_stt_soak.app:create_app',
                                '--factory',
                                '--host',
                                '0.0.0.0',
                                '--port',
                                '8080',
                                '--loop',
                                'uvloop',
                            ],
                            'ports': [{'containerPort': 8080}],
                            'readinessProbe': {'httpGet': {'path': '/v1/health', 'port': 8080}},
                            'resources': {
                                'requests': {'cpu': '1', 'memory': '1.5Gi'},
                                'limits': {'cpu': '2', 'memory': '3.5Gi'},
                            },
                        },
                        {
                            'name': 'redis',
                            'image': 'redis:7.2.5',
                            'args': ['--bind', '127.0.0.1', '--save', '', '--appendonly', 'no'],
                            'resources': {'limits': {'cpu': '1', 'memory': '256Mi'}},
                        },
                        {
                            'name': 'firestore',
                            'image': 'gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators',
                            'command': [
                                'gcloud',
                                'emulators',
                                'firestore',
                                'start',
                                f'--project={PROJECT}',
                                '--host-port=127.0.0.1:8085',
                                '--quiet',
                            ],
                            'resources': {'limits': {'cpu': '1', 'memory': '1Gi'}},
                        },
                    ],
                },
            },
        },
    }
    policy = {
        'apiVersion': 'networking.k8s.io/v1',
        'kind': 'NetworkPolicy',
        'metadata': {'name': 'live-stt-soak', 'namespace': NAMESPACE},
        'spec': {
            'podSelector': {'matchLabels': labels},
            'policyTypes': ['Ingress', 'Egress'],
            'ingress': [],
            'egress': [],
        },
    }
    if mode == 'paid':
        policy['spec']['egress'] = [
            {
                'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}}}],
                'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}],
            },
            {
                'to': [
                    {
                        'ipBlock': {
                            'cidr': '0.0.0.0/0',
                            'except': [
                                '10.0.0.0/8',
                                '172.16.0.0/12',
                                '192.168.0.0/16',
                                '169.254.0.0/16',
                            ],
                        }
                    }
                ],
                'ports': [{'protocol': 'TCP', 'port': 443}],
            },
        ]
    return [policy, deployment]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--mode', choices=('fake', 'paid'), default='fake')
    parser.add_argument('--sessions', type=int, default=4)
    parser.add_argument('--fault-after', type=float, default=12)
    parser.add_argument('--order', default='parakeet-window,soniox,modulate-velma-2')
    parser.add_argument('--paid-secret')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        yaml.safe_dump_all(
            render(args.image, args.mode, args.sessions, args.fault_after, args.order, args.paid_secret),
            sort_keys=False,
        )
    )


if __name__ == '__main__':
    main()
