#!/usr/bin/env python3
# LIFECYCLE: permanent
"""Validate operator-created Prometheus replicas from read-only Kubernetes JSON."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROD_STATEFULSET = 'prometheus-prod-omi-kube-prometheus-s-prometheus'
MIN_STORAGE_BYTES = 100 * 1024**3


def _storage_bytes(quantity):
    text = str(quantity)
    for suffix, multiplier in [('Ti', 1024**4), ('Gi', 1024**3), ('Mi', 1024**2), ('Ki', 1024), ('G', 10**9)]:
        if text.endswith(suffix):
            return Decimal(text[: -len(suffix)]) * multiplier
    return Decimal(text)


def validate_readiness(statefulset, pods, pvcs, expected_name=PROD_STATEFULSET):
    """Return aggregate contract failures; never include raw API payloads in errors."""
    errors = []
    metadata = statefulset.get('metadata', {})
    spec, status = statefulset.get('spec', {}), statefulset.get('status', {})
    if statefulset.get('kind') != 'StatefulSet' or metadata.get('name') != expected_name:
        errors.append('unexpected StatefulSet identity')
    uid = metadata.get('uid')
    namespace = metadata.get('namespace')
    if not uid or not namespace or metadata.get('deletionTimestamp'):
        errors.append('StatefulSet identity missing or deletion in progress')
    generation, observed = metadata.get('generation'), status.get('observedGeneration')
    if not isinstance(generation, int) or not isinstance(observed, int) or generation < 1 or observed < generation:
        errors.append('operator-created StatefulSet generation not observed')
    if spec.get('replicas') != 2:
        errors.append('StatefulSet desired replicas must be two')
    if any(status.get(key) != 2 for key in ['replicas', 'currentReplicas', 'updatedReplicas', 'readyReplicas']):
        errors.append('StatefulSet current/updated/ready replica counts must all be two')
    if not status.get('updateRevision') or status.get('currentRevision') != status.get('updateRevision'):
        errors.append('StatefulSet rollout revision has not converged')
    if not isinstance(pods.get('items'), list) or not isinstance(pvcs.get('items'), list):
        return errors + ['Pod/PVC inputs must be Kubernetes list documents']
    expected_pods = {f'{expected_name}-{ordinal}' for ordinal in (0, 1)}
    owned = [
        pod
        for pod in pods['items']
        if any(
            owner.get('uid') == uid and owner.get('kind') == 'StatefulSet' and owner.get('controller') is True
            for owner in pod.get('metadata', {}).get('ownerReferences', [])
        )
    ]
    if len(owned) != 2 or {pod.get('metadata', {}).get('name') for pod in owned} != expected_pods:
        errors.append('expected exactly the two StatefulSet-owned ordinal pods')
    nodes = set()
    templates = spec.get('volumeClaimTemplates', [])
    if not templates:
        errors.append('StatefulSet has no data volume claim template')
    claims = {pvc.get('metadata', {}).get('name'): pvc for pvc in pvcs['items']}
    claim_names, volume_names = set(), set()
    for pod in owned:
        podmeta, podspec, podstatus = pod.get('metadata', {}), pod.get('spec', {}), pod.get('status', {})
        if (
            podmeta.get('namespace') != namespace
            or podmeta.get('deletionTimestamp')
            or podstatus.get('phase') != 'Running'
            or not any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in podstatus.get('conditions', []))
        ):
            errors.append('a replica pod is not Running/Ready or is terminating')
        node = podspec.get('nodeName')
        if not node:
            errors.append('a replica pod has no assigned node')
        else:
            nodes.add(node)
        mounted = {
            volume.get('persistentVolumeClaim', {}).get('claimName')
            for volume in podspec.get('volumes', [])
            if volume.get('persistentVolumeClaim')
        }
        for template in templates:
            claim_name = f"{template.get('metadata', {}).get('name')}-{podmeta.get('name')}"
            claim_names.add(claim_name)
            if claim_name not in mounted:
                errors.append('a replica data PVC is not mounted by its ordinal pod')
            pvc = claims.get(claim_name, {})
            pvc_spec = pvc.get('spec', {})
            if (
                pvc.get('metadata', {}).get('namespace') != namespace
                or pvc.get('metadata', {}).get('deletionTimestamp')
                or pvc.get('status', {}).get('phase') != 'Bound'
                or not pvc_spec.get('volumeName')
            ):
                errors.append('a replica data PVC is missing, unbound or terminating')
            else:
                volume_names.add(pvc_spec['volumeName'])
            if pvc_spec.get('storageClassName') != 'standard-rwo' or 'ReadWriteOnce' not in pvc_spec.get(
                'accessModes', []
            ):
                errors.append('a replica data PVC must use standard-rwo/ReadWriteOnce')
            try:
                requested = _storage_bytes(pvc_spec.get('resources', {}).get('requests', {}).get('storage', 0))
                capacity = _storage_bytes(pvc.get('status', {}).get('capacity', {}).get('storage', 0))
                if requested < MIN_STORAGE_BYTES or capacity < MIN_STORAGE_BYTES:
                    errors.append('a replica data PVC requests/capacity are below 100Gi')
            except (InvalidOperation, ValueError, TypeError):
                errors.append('a replica data PVC has invalid storage quantities')
    expected_claim_count = 2 * len(templates)
    if len(claim_names) != expected_claim_count or len(volume_names) != expected_claim_count:
        errors.append('replica data PVCs must bind distinct persistent volumes')
    if len(nodes) != 2:
        errors.append('replica pods must occupy two distinct nodes')
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--statefulset-json', type=Path, required=True)
    parser.add_argument('--pods-json', type=Path, required=True)
    parser.add_argument('--pvcs-json', type=Path, required=True)
    args = parser.parse_args()
    try:
        objects = [json.loads(path.read_text()) for path in [args.statefulset_json, args.pods_json, args.pvcs_json]]
        if not all(isinstance(obj, dict) for obj in objects):
            raise ValueError('documents must be objects')
        findings = validate_readiness(*objects)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        print('FAIL: malformed or unreadable Kubernetes readiness documents')
        return 1
    for finding in findings:
        print(f'FAIL: {finding}')
    if not findings:
        print(
            'PASS: Prometheus generation reconciled; both owned replicas Ready on separate nodes with distinct Bound100Gi PVCs'
        )
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
