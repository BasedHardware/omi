"""Render a no-credentials public replay ConfigMap + Job; never contact Kubernetes."""

import argparse
import json
from pathlib import Path
import re

NAMESPACE = 'prod-omi-backend'
NAME = 'diarizer-batch-shadow-replay'


def render(client_image, target_image):
    for image, repository in ((client_image, 'backend'), (target_image, 'diarizer')):
        if not re.fullmatch(r'gcr\.io/based-hardware/' + repository + r'@sha256:[a-f0-9]{64}', image):
            raise ValueError('both runtime images must use the expected repository and a sha256 digest')
    scripts = Path(__file__).resolve().parent
    config = dict(
        apiVersion='v1',
        kind='ConfigMap',
        metadata=dict(name=NAME, namespace=NAMESPACE),
        immutable=True,
        data={name: (scripts / name).read_text() for name in ('bench_diarizer_batch.py', 'diarizer_shadow_replay.py')},
    )
    job = dict(
        apiVersion='batch/v1',
        kind='Job',
        metadata=dict(name=NAME, namespace=NAMESPACE),
        spec=dict(
            backoffLimit=0,
            activeDeadlineSeconds=93600,
            ttlSecondsAfterFinished=86400,
            template=dict(
                metadata=dict(
                    labels={'omi.ai/diarizer-replay': 'canary'},
                    annotations={
                        'omi.ai/target-image': target_image,
                    },
                ),
                spec=dict(
                    restartPolicy='Never',
                    automountServiceAccountToken=False,
                    securityContext=dict(runAsNonRoot=True, runAsUser=10001, runAsGroup=10001, fsGroup=10001),
                    containers=[
                        dict(
                            name='replay',
                            image=client_image,
                            imagePullPolicy='IfNotPresent',
                            workingDir='/app',
                            command=['python', '/replay/diarizer_shadow_replay.py'],
                            args=['--target-image', target_image, '--client-image', client_image],
                            env=[dict(name='PYTHONPATH', value='/app:/replay')],
                            resources=dict(
                                requests={'cpu': '1', 'memory': '2Gi', 'ephemeral-storage': '1Gi'},
                                limits={'cpu': '2', 'memory': '4Gi', 'ephemeral-storage': '4Gi'},
                            ),
                            securityContext=dict(allowPrivilegeEscalation=False, capabilities=dict(drop=['ALL'])),
                            volumeMounts=[
                                dict(name='scripts', mountPath='/replay', readOnly=True),
                                dict(name='corpus', mountPath='/data'),
                            ],
                        )
                    ],
                    volumes=[
                        dict(name='scripts', configMap=dict(name=NAME)),
                        dict(name='corpus', emptyDir=dict(sizeLimit='2Gi')),
                    ],
                ),
            ),
        ),
    )
    return dict(apiVersion='v1', kind='List', items=[config, job])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-image', required=True, help='approved main-built backend image digest (CPU)')
    parser.add_argument('--target-image', required=True, help='same diarizer digest as the shadow Helm install')
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.client_image, args.target_image), indent=2))
    except ValueError as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
