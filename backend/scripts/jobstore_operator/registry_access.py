"""Gate a reviewed bounded registry attempt without inventing effective IAM proof.

The caller's permission hint is diagnostic. The real registry requests enforce
authorization; successful exact-byte copy/readback is the operation evidence.
"""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

DESTINATION = 'gcr.io/based-hardware/jobstore-reconcile-operator'
RESOURCE = 'projects/based-hardware/locations/us/repositories/gcr.io'
PRINCIPAL = 'omi-ci-deployer-prod@based-hardware.iam.gserviceaccount.com'
DECISION = 'REVIEWED_EXISTING_ALLOW_AND_TRUST_FOR_BOUNDED_ATTEMPT'
PERMISSIONS = (
    'artifactregistry.repositories.uploadArtifacts',
    'artifactregistry.repositories.downloadArtifacts',
    'artifactregistry.repositories.get',
    'artifactregistry.dockerimages.get',
    'artifactregistry.files.upload',
    'artifactregistry.files.download',
    'artifactregistry.files.get',
    'artifactregistry.packages.get',
    'artifactregistry.versions.get',
    'artifactregistry.versions.list',
    'artifactregistry.tags.create',
    'artifactregistry.tags.get',
    'artifactregistry.tags.list',
    'artifactregistry.tags.update',
)
URL = 'https://artifactregistry.googleapis.com/v1/' + RESOURCE + ':testIamPermissions'


def validate_evidence(contract):
    if contract.get('status') != 'REVIEWED_EXACT_INPUTS_FOR_GUARDED_PUBLICATION':
        raise ValueError('REVIEWED_SOURCE_CONTRACT_REQUIRED')
    evidence = contract.get('registry_access_evidence')
    if contract.get('registry_write_authorization') is not None:
        raise ValueError('DO_NOT_ASSERT_UNOBSERVED_EFFECTIVE_AUTHORIZATION')
    if (
        contract.get('destination') != DESTINATION
        or not isinstance(evidence, dict)
        or evidence.get('decision') != DECISION
        or evidence.get('repository') != DESTINATION
        or evidence.get('iam_resource') != RESOURCE
        or evidence.get('principal') != PRINCIPAL
        or evidence.get('effective_authorization') != 'UNKNOWN_UNTIL_ACTUAL_REGISTRY_OPERATIONS'
        or any(
            not isinstance(evidence.get(key), str) or not re.fullmatch('[0-9a-f]{64}', evidence[key])
            for key in ('allow_policy_receipt_sha256', 'wif_metadata_receipt_sha256', 'sa_trust_receipt_sha256')
        )
    ):
        raise ValueError('REVIEWED_EXISTING_ALLOW_AND_TRUST_FOR_BOUNDED_ATTEMPT_REQUIRED')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def permission_hint(token):
    # Fixed Google resource only. Never put a token in argv, a URL or a receipt;
    # never forward it through a redirect or log an HTTP response/error body.
    request = Request(
        URL,
        data=json.dumps({'permissions': list(PERMISSIONS)}).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            body = response.read(65537)
    except (HTTPError, URLError, TimeoutError):
        raise ValueError('REGISTRY_PERMISSION_HINT_UNAVAILABLE') from None
    if len(body) > 65536:
        raise ValueError('REGISTRY_PERMISSION_HINT_RESPONSE_TOO_LARGE')
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise ValueError('REGISTRY_PERMISSION_HINT_RESPONSE_INVALID') from None
    granted = result.get('permissions') if isinstance(result, dict) else None
    if not isinstance(granted, list) or any(not isinstance(p, str) or p not in PERMISSIONS for p in granted):
        raise ValueError('REGISTRY_PERMISSION_HINT_RESPONSE_INVALID')
    if set(granted) != set(PERMISSIONS):
        raise ValueError('REGISTRY_PERMISSION_HINT_INCOMPLETE_NO_WRITE_ATTEMPT')
    # testIamPermissions is a CLI/UI hint, not an authorization oracle. A hint
    # cannot authorize this attempt or substitute for real server enforcement.
    return {
        'result': 'CALLER_PERMISSION_HINT_COMPLETE',
        'resource': RESOURCE,
        'permissions': list(PERMISSIONS),
        'authorization_proof': False,
    }
