"""Pure, live cohort policy for copies; this module never reads either database.

Production copying resolves one owner from the current primary document. Shared
rows are deliberately omitted rather than admitting an entire scheduler shard.
``None`` means retire any existing copy, not leave a previous copy untouched.
Staging and test document shapes retain their existing projection contract;
their namespace/target admission remains the factory's responsibility.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Literal

from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_shadow_hook import shadow_mode_enabled
from utils.staging_fence import PROD_JOBSTORE_NAMESPACE, STAGING_DATABASE, is_staging, jobstore_shadow_admits

# jobs/results are keyed by segment ID; intakes by job ID; artifacts by the
# segment/URI digest. None of those keys can establish an owner.
DOCUMENT_OWNER_TABLES = frozenset({'jobs', 'results', 'intakes', 'artifacts'})
# Scheduler owner state and merge marks may contain no explicit owner fields.
OWNER_KEYED_TABLES = frozenset({'owners', 'merge_holds', 'allowance_holds'})
# Control rings include many owners; GPU reservations and pull leases are shared.
SHARED_TABLES = frozenset({'control', 'gpus', 'pull_claims'})
CLASSIFIED_TABLES = DOCUMENT_OWNER_TABLES | OWNER_KEYED_TABLES | SHARED_TABLES | {'queues'}
_OWNER_KEY = re.compile(r'[0-9a-f]{64}')
# Scheduler queue keys are emitted using config.batch_pipeline.Priority (0..2).
_QUEUE_KEY = re.compile(r'[012]_([0-9a-f]{64})')
_OFF = frozenset({'0', 'false', 'off', 'no'})

DocumentClassification = Literal['selected', 'excluded', 'unknown_owner', 'absent']


def production_policy_applies(namespace: str) -> bool:
    """Read deployment identity at the call boundary, including cached handles."""
    staging_context = is_staging() and os.getenv('FIRESTORE_DATABASE_ID', '').strip() == STAGING_DATABASE
    return namespace == PROD_JOBSTORE_NAMESPACE and not staging_context


def resolve_owner_key(table: str, key: object, doc: object) -> str | None:
    """Resolve a canonical owner, requiring every present ownership claim to agree.

    Absence permits a table-specific key fallback; an explicitly malformed or
    null field does not. No lookup of jobs, claims or other documents is allowed.
    """
    if table not in DOCUMENT_OWNER_TABLES | OWNER_KEYED_TABLES | {'queues'} or not isinstance(doc, dict) or not doc:
        return None
    claims = []
    if 'owner_key' in doc:
        owner = doc['owner_key']
        if not isinstance(owner, str) or not _OWNER_KEY.fullmatch(owner):
            return None
        claims.append(owner)
    if 'owner_id' in doc:
        uid = doc['owner_id']
        if not isinstance(uid, str) or not uid or uid != uid.strip():
            return None
        try:
            claims.append(privacy_owner_key(uid))
        except (ValueError, UnicodeError):
            return None
    if table in OWNER_KEYED_TABLES:
        if not isinstance(key, str) or not _OWNER_KEY.fullmatch(key):
            return None
        claims.append(key)
    elif table == 'queues':
        if not isinstance(key, str):
            return None
        match = _QUEUE_KEY.fullmatch(key)
        if match is None:
            return None
        claims.append(match[1])
        if 'priority' in doc and (type(doc['priority']) is not int or str(doc['priority']) != key[0]):
            return None
    if not claims or len(set(claims)) != 1:
        return None
    return claims[0]


def classify_document(namespace: str, table: str, key: str, doc: dict) -> DocumentClassification:
    """Classify a current primary row without caching owner or environment state."""
    if not doc:
        return 'absent'
    if not production_policy_applies(namespace):
        return 'selected'
    if table in SHARED_TABLES or table not in CLASSIFIED_TABLES:
        return 'excluded'
    owner = resolve_owner_key(table, key, doc)
    if owner is None:
        return 'unknown_owner'
    if not shadow_mode_enabled() or os.getenv('JOBSTORE_SHADOW_WRITES', '').strip().lower() in _OFF:
        return 'excluded'
    return 'selected' if jobstore_shadow_admits(namespace, owner_key=owner) else 'excluded'


def project_document(namespace: str, table: str, key: str, doc: dict) -> dict | None:
    """Return an independent selected document, or signal copy retirement.

    Field omissions shared with the staging mirror still belong to the caller.
    Both a killed cohort and an owner removed by a threshold reduction retire.
    """
    if classify_document(namespace, table, key, doc) != 'selected':
        return None
    return deepcopy(doc)
