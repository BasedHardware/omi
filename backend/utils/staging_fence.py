"""Boot-time isolation fence for the staging deployment (contract (i)).

Staging runs ``OMI_ENV_STAGE=prod`` so it takes production code paths. Its
isolation therefore cannot come from stage strings; it comes from project,
database and IAM. This fence is the in-process half of that: when
``OMI_DEPLOYMENT=staging`` the process refuses to start if anything in its
environment points at the production data plane.

``assert_staging_isolation()`` must run before any Firestore, Redis or GCS
client is built. It is a no-op outside staging, cached after the first call,
and never logs or raises with an environment *value* — only variable names
and reason codes.

``PROD_DATA_PLANE_HASHES`` holds sha256 hex digests (never values) of
production identifiers that must never appear in a staging environment:
filled from ``ro-prod``/``ro-dev`` describes by lane 2.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
from collections.abc import Mapping
from threading import Lock

logger = logging.getLogger(__name__)

STAGING_DEPLOYMENT = 'staging'
STAGING_PROJECT = 'based-hardware-dev'
STAGING_DATABASE = 'staging'
STAGING_SA_DOMAIN = f'@{STAGING_PROJECT}.iam.gserviceaccount.com'

# sha256(value) of production data-plane identifiers. Values are deliberately
# not committed. Sources (2026-10-19, lane 2):
PROD_DATA_PLANE_HASHES: frozenset[str] = frozenset(
    {
        # prod Firestore / customer project id (also dev's GOOGLE_CLOUD_PROJECT and
        # OMI_CUSTOMER_DATA_PROJECT: dev reads and writes prod Firestore)
        'c2ad5cbe9f87315d275db23c0d23da8087e213bc4d8866095c27e31ad5af2c1a',
        # prod BUCKET_TEMPORAL_SYNC_LOCAL (the legacy sync audio bucket)
        '84083c53564853325eb2ff02a3ea86baa11930af4b552c360afe96b24eabfcac',
        # prod BUCKET_BATCH_PIPELINE
        'f71f6f52290b4c6857b08ad49dd7e8af404f748d8763442f7bd0888db7d9c742',
        # dev BUCKET_TEMPORAL_SYNC_LOCAL
        '5a3876404fd446627a18288e59b5b413af051b6fd706597199e89dbc74a534ec',
        # dev BUCKET_BATCH_PIPELINE (based-hardware-dev-batch-pipeline-staging)
        hashlib.sha256(b'based-hardware-dev-batch-pipeline-staging').hexdigest(),
        # prod BUCKET_PRIVATE_CLOUD_SYNC (also its code default in utils/other/storage.py)
        hashlib.sha256(b'omi-private-cloud-sync').hexdigest(),
        # prod PINECONE_INDEX_NAME
        'fa470fd0229b9b377540ff00056310ddd710614c17af769190a9700b3d08eb59',
        # prod/dev REDIS_DB_HOST: added once bootstrap_iam.sh prints its hash (the host
        # is a Secret Manager payload, unreadable on agent tiers). Until then the
        # positive private-address rule below covers it: prod Redis is not RFC 1918.
    }
)

# Production references by shape. ``based-hardware`` not followed by ``-dev``,
# prod Cloud Run URL suffix, and any omi.me host (api.omi.me, parakeet.omi.me, ...).
_PROD_REFERENCE = re.compile(
    r'based-hardware(?!-dev)|hhibjajaja|208440318997|(?<![a-z0-9-])(?:[a-z0-9-]+\.)*omi\.me(?![a-z0-9-])',
    re.IGNORECASE,
)
# Production network addresses (ro-prod 2026-10-20): the prod VPC subnets, which hold the
# prod ILBs (Parakeet, diarizer), and the prod external load balancer IPs. Dev is
# 172.16.0.0/18 and Cloud SQL 172.20.0.0/16, so these never overlap a staging value.
PROD_NETWORKS: tuple[ipaddress.IPv4Network, ...] = tuple(
    ipaddress.IPv4Network(cidr)
    for cidr in (
        '172.16.128.0/20',
        '172.16.144.0/20',
        '172.16.160.0/20',
        '34.160.137.29/32',
        '34.49.188.104/32',
        '34.54.223.100/32',
    )
)
_IPV4 = re.compile(r'(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])')

_PROJECT_ENV = ('OMI_CUSTOMER_DATA_PROJECT', 'GOOGLE_CLOUD_PROJECT')
_OPTIONAL_PROJECT_ENV = ('OMI_FIRESTORE_DATA_PLANE_PROJECT', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID')
_KEY_CREDENTIAL_ENV = ('SERVICE_ACCOUNT_JSON', 'FIREBASE_AUTH_CREDENTIALS_PATH')
# Keys whose in-code default is a production resource: an unset key is a prod reference the
# value scan cannot see (2026-10-21: BUCKET_PRIVATE_CLOUD_SYNC fell back to the prod bucket).
_REQUIRED_EXPLICIT_ENV = (
    'BUCKET_PRIVATE_CLOUD_SYNC',  # prod private-cloud-sync bucket
    'MCP_AUTHORIZATION_SERVER_URL',  # https://api.omi.me
    'LIFECYCLE_EMAIL_FROM_ADDRESS',  # mail.omi.me sender
    'SHARE_EMAIL_FROM_ADDRESS',  # mail.omi.me sender
)


class StagingFenceError(RuntimeError):
    """Raised when a staging process is configured to reach production."""

    def __init__(self, reasons: list[tuple[str, str]]):
        self.reasons = reasons
        detail = ', '.join(f'{reason}:{name}' for reason, name in reasons)
        super().__init__(f'staging isolation fence refused to start: {detail}')


def _metric():
    try:
        from prometheus_client import Counter
    except ImportError:  # unit harnesses without prometheus
        return None
    global _fence_counter
    if _fence_counter is None:
        _fence_counter = Counter(
            'omi_staging_fence_total',
            'Staging isolation fence evaluations by outcome reason.',
            ['reason'],
        )
    return _fence_counter


_fence_counter = None
_checked = False
_lock = Lock()


def is_staging(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get('OMI_DEPLOYMENT') or '').strip() == STAGING_DEPLOYMENT


PROD_JOBSTORE_NAMESPACE = 'batch_pipeline_prod'


def jobstore_shadow_admits(namespace: str, env: Mapping[str, str] | None = None) -> bool:
    """Whether the A2 Postgres job-store shadow and mirror may run on ``namespace`` (ruling L02-2).

    Staging keeps the worker namespace ``batch_pipeline_prod``, so the namespace alone cannot tell staging
    from prod. That namespace is admitted only in a staging deployment on the staging Firestore database;
    production (and the staging flag on any other database) stays refused until account deletion purges
    the Postgres copy too. Every other namespace is admitted. The one gate for ``shadow_from_env`` and
    ``mirror_refresh``.
    """
    if namespace != PROD_JOBSTORE_NAMESPACE:
        return True
    env = os.environ if env is None else env
    return is_staging(env) and (env.get('FIRESTORE_DATABASE_ID') or '').strip() == STAGING_DATABASE


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _is_private_redis_host(host: str) -> bool:
    if host.endswith('.svc.cluster.local') or host == 'localhost':
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private


def _has_prod_address(text: str) -> bool:
    for literal in _IPV4.findall(text):
        try:
            address = ipaddress.ip_address(literal)
        except ValueError:
            continue
        if any(address in network for network in PROD_NETWORKS):
            return True
    return False


def staging_violations(env: Mapping[str, str]) -> list[tuple[str, str]]:
    """Return ``(reason, variable_name)`` for every fence breach. Empty means isolated."""
    if not is_staging(env):
        return []
    violations: list[tuple[str, str]] = []

    def value(name: str) -> str:
        return (env.get(name) or '').strip()

    # 1. Customer-data / compute project must be the staging project.
    for name in _PROJECT_ENV:
        if value(name) != STAGING_PROJECT:
            violations.append(('project', name))
    for name in _OPTIONAL_PROJECT_ENV:
        if value(name) and value(name) != STAGING_PROJECT:
            violations.append(('project', name))
    for name in _KEY_CREDENTIAL_ENV:
        if value(name):
            # Staging runs on its attached identity only; a mounted key can name any project.
            violations.append(('key_credential', name))

    # 2. Database, auth project and signer.
    if value('FIRESTORE_DATABASE_ID') != STAGING_DATABASE:
        violations.append(('database', 'FIRESTORE_DATABASE_ID'))
    if value('FIREBASE_AUTH_PROJECT_ID') != STAGING_PROJECT:
        violations.append(('auth_project', 'FIREBASE_AUTH_PROJECT_ID'))
    signer = value('FIREBASE_SIGNER_SERVICE_ACCOUNT')
    if signer and not signer.endswith(STAGING_SA_DOMAIN):
        violations.append(('signer', 'FIREBASE_SIGNER_SERVICE_ACCOUNT'))

    # 2b. Keys whose code default points at production must be set explicitly.
    for name in _REQUIRED_EXPLICIT_ENV:
        if not value(name):
            violations.append(('prod_default', name))

    # 3. Redis must be a private staging address, never a known prod host.
    redis_host = value('REDIS_DB_HOST')
    if redis_host and not _is_private_redis_host(redis_host):
        violations.append(('redis_host', 'REDIS_DB_HOST'))

    # 4. Known prod identifiers (by hash) or prod-shaped references anywhere in the env.
    for name, raw in env.items():
        text = (raw or '').strip()
        if not text:
            continue
        if _sha(text) in PROD_DATA_PLANE_HASHES:
            violations.append(('prod_hash', name))
        elif _PROD_REFERENCE.search(text):
            violations.append(('prod_reference', name))
        elif _has_prod_address(text):
            violations.append(('prod_address', name))
    # Stable order, no duplicates.
    return sorted(set(violations))


def assert_staging_isolation(env: Mapping[str, str] | None = None, *, force: bool = False) -> None:
    """Refuse to start a staging process that can reach production. No-op elsewhere."""
    global _checked
    if env is None:
        if _checked and not force:
            return
        with _lock:
            if _checked and not force:
                return
            _assert(os.environ)
            _checked = True
        return
    _assert(env)


def _assert(env: Mapping[str, str]) -> None:
    if not is_staging(env):
        return
    violations = staging_violations(env)
    counter = _metric()
    if not violations:
        if counter is not None:
            counter.labels(reason='ok').inc()
        return
    for reason, name in violations:
        if counter is not None:
            counter.labels(reason=reason).inc()
        logger.critical('staging_fence_violation reason=%s env=%s', reason, name)
    raise StagingFenceError(violations)


def reset_for_tests() -> None:
    global _checked
    _checked = False
