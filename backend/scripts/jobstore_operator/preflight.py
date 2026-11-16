"""Proposed CI preflight, intentionally closed until exact ingress/permission review."""

import json
import os
from pathlib import Path
import re
import shutil


def check(contract, environment, free_bytes):
    source = environment.get('REQUESTED_SOURCE', '')
    if not re.fullmatch('[0-9a-f]{40}', source) or source != contract['source_sha']:
        raise ValueError('EXACT_RUNTIME_SOURCE_REQUIRED')
    if (
        environment.get('SKIP_PROOF') != 'false'
        or environment.get('BREAK_GLASS_LOCK') != 'false'
        or environment.get('SERVICE_IMAGES', '')
    ):
        raise ValueError('OPERATOR_MODE_CANNOT_BYPASS_OR_DEPLOY')
    if contract.get('status') != 'REVIEWED_EXACT_INPUTS_FOR_GUARDED_PUBLICATION':
        raise ValueError('REVIEWED_SOURCE_CONTRACT_REQUIRED')
    if (
        not isinstance(contract.get('release_id'), int)
        or contract['release_id'] <= 0
        or any(
            not isinstance(p.get('asset_id'), int) or p['asset_id'] <= 0
            for p in contract['parts'] + [contract['fixture']]
        )
    ):
        raise ValueError('REVIEWED_DRAFT_AND_ASSET_IDS_REQUIRED')
    permission = contract.get('registry_write_authorization')
    destination = 'gcr.io/based-hardware/jobstore-reconcile-operator'
    if (
        contract.get('destination') != destination
        or not isinstance(permission, dict)
        or permission.get('principal') != 'omi-ci-deployer-prod@based-hardware.iam.gserviceaccount.com'
        or permission.get('existing_authorization_verified') is not True
        or permission.get('repository') != destination
        or not re.fullmatch('[0-9a-f]{64}', permission.get('evidence_sha256', ''))
    ):
        raise ValueError('EXISTING_REGISTRY_PERMISSION_EVIDENCE_REQUIRED')
    if free_bytes < contract['required_disposable_free_bytes']:
        raise ValueError('INSUFFICIENT_EXISTING_RUNNER_SCRATCH_NO_CLEANUP_OR_CAPACITY_CHANGE')


if __name__ == '__main__':
    contract = json.loads((Path(__file__).parent / 'artifact-contract.json').read_text())
    check(contract, os.environ, shutil.disk_usage(os.environ['RUNNER_TEMP']).free)
