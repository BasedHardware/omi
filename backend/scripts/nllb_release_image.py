"""Pin NLLB rollback to the image observed before the preceding workflow rollout."""

import argparse
import json
from pathlib import Path
import re
from typing import Any

PREVIOUS_DIGEST = 'omi.me/previous-image-digest'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


def release_values(
    deployment: dict[str, Any],
    pods: dict[str, Any],
    repository: str,
    tag: str,
    rollback: str = '',
    candidate_digest: str = '',
) -> dict[str, Any]:
    if not rollback and not DIGEST.fullmatch(candidate_digest):
        raise ValueError('normal release requires the built candidate digest')
    if rollback and not DIGEST.fullmatch(rollback):
        raise ValueError('rollback must be a complete sha256 digest')
    if not re.fullmatch(r'[0-9a-f]{7,40}', tag):
        raise ValueError('release tag must identify the selected source commit')
    if not deployment:
        if rollback:
            raise ValueError('rollback requires a previous deployment receipt')
        return {'image': {'tag': tag, 'digest': candidate_digest}}
    template = deployment['spec']['template']
    previous = template['metadata'].get('annotations', {}).get(PREVIOUS_DIGEST)
    if rollback and rollback != previous:
        raise ValueError('rollback digest does not match the recorded prior serving image')
    selector = deployment['spec']['selector']['matchLabels']
    containers = template['spec']['containers']
    expected = next(c['image'] for c in containers if c['name'] == 'nllb-translation')
    if not expected.startswith((repository + ':', repository + '@')):
        raise ValueError('current image is outside the NLLB repository')
    if rollback:
        # Recovery must remain possible when the new image never becomes ready.
        return {'image': {'tag': tag, 'digest': rollback}, 'podAnnotations': {PREVIOUS_DIGEST: rollback}}
    status = deployment.get('status', {})
    desired = deployment['spec'].get('replicas', 1)
    if (
        desired < 1
        or status.get('observedGeneration') != deployment['metadata']['generation']
        or status.get('updatedReplicas', 0) != desired
        or status.get('readyReplicas', 0) != desired
    ):
        raise ValueError('current deployment must be fully ready before selecting a release image')
    digests: set[str] = set()
    serving = 0
    for pod in pods.get('items', []):
        metadata = pod['metadata']
        if metadata.get('deletionTimestamp') or any(
            metadata.get('labels', {}).get(k) != v for k, v in selector.items()
        ):
            continue
        serving += 1
        container = next(
            c for c in pod.get('status', {}).get('containerStatuses', []) if c['name'] == 'nllb-translation'
        )
        pod_image = next(c['image'] for c in pod['spec']['containers'] if c['name'] == 'nllb-translation')
        image_id = container.get('imageID', '').removeprefix('docker-pullable://')
        prefix = repository + '@'
        digest = image_id.removeprefix(prefix)
        if (
            not container.get('ready')
            or pod_image != expected
            or not image_id.startswith(prefix)
            or not DIGEST.fullmatch(digest)
        ):
            raise ValueError('serving pod lacks a ready immutable NLLB image identity')
        digests.add(digest)
    if serving != desired or len(digests) != 1:
        raise ValueError('serving pods must agree on one immutable image')
    current = digests.pop()
    # A retry of an already-serving artifact must not erase its rollback receipt.
    prior = (
        previous
        if current == candidate_digest and isinstance(previous, str) and DIGEST.fullmatch(previous)
        else current
    )
    return {'image': {'tag': tag, 'digest': candidate_digest}, 'podAnnotations': {PREVIOUS_DIGEST: prior}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('deployment', 'pods', 'repository', 'tag', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--rollback-digest', default='')
    parser.add_argument('--candidate-digest', default='')
    args = parser.parse_args()
    deployment = json.loads(Path(args.deployment).read_text() or '{}')
    values = release_values(
        deployment,
        json.loads(Path(args.pods).read_text()),
        args.repository,
        args.tag,
        args.rollback_digest,
        args.candidate_digest,
    )
    Path(args.output).write_text(json.dumps(values) + '\n')


if __name__ == '__main__':
    main()
