"""Private, immutable operator cohorts; no provider calls or database writes."""

import hashlib
import json
import os
import re
from pathlib import Path

from google.cloud.firestore_v1.base_query import FieldFilter


class ScopeRefused(ValueError):
    """Only closed reason codes may cross the operator stdout boundary."""


def require(condition, reason):
    if not condition:
        raise ScopeRefused(reason)


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def owner_jobs(collection, uid, *, page_size=200, read_budget=20000):
    """Document cursors avoid offsets and the former 1,000-lifetime-job ceiling."""
    query = collection.where(filter=FieldFilter('owner_id', '==', uid)).order_by('__name__')
    cursor, read = None, 0
    while True:
        page_query = query.start_after(cursor) if cursor is not None else query
        page = list(page_query.limit(min(page_size, read_budget - read + 1)).stream())
        read += len(page)
        require(read <= read_budget, 'owner_read_budget')
        yield from page
        if len(page) < page_size:
            return
        cursor = page[-1]


def eligible(job, after, before):
    """New cohorts never adopt spent operator intents or historical receipts."""
    return (
        after <= job.get('quarantined_at', 0) <= before
        and job.get('state') == 'quarantined'
        and job.get('recovery_state') == 'failed_held'
        and not job.get('speech_redrive')
        and not job.get('silence_disposition')
    )


def unit_ids(path):
    if not path:
        return None
    value = read_json(path)
    require(isinstance(value, list) and 1 <= len(value) <= 200, 'invalid_unit_ids')
    require(all(isinstance(s, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', s) for s in value), 'invalid_unit_ids')
    require(len(set(value)) == len(value), 'duplicate_unit_ids')
    return sorted(value)


def read_json(path):
    require(Path(path).stat().st_size <= 131072, 'cohort_file_too_large')
    return json.loads(Path(path).read_text())


def scope_body(uid, namespace, after, before, silent, ids):
    return dict(version=1, owner_id=uid, namespace=namespace, after=after, before=before, silent=silent, unit_ids=ids)


def load(path, scope, expected):
    manifest = read_json(path)
    require(isinstance(manifest, dict) and set(manifest) == {'scope', 'units'}, 'invalid_cohort')
    require(manifest['scope'] == scope, 'cohort_scope_changed')
    units = manifest['units']
    require(isinstance(units, list) and len(units) == expected, 'cohort_count_changed')
    seen = set()
    for unit in units:
        require(isinstance(unit, list) and len(unit) == 3, 'invalid_cohort_unit')
        sid, key, decision = unit
        require(isinstance(sid, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid), 'invalid_cohort_unit')
        require(isinstance(key, str) and re.fullmatch('[a-f0-9]{64}', key), 'invalid_cohort_unit')
        require(decision in {'speech', 'silent'} and sid not in seen, 'invalid_cohort_unit')
        seen.add(sid)
    require(units == sorted(units), 'invalid_cohort_order')
    if scope['unit_ids'] is not None:
        require(sorted(seen) == scope['unit_ids'], 'unit_ids_changed')
    return manifest


def write(path, manifest):
    """Create-only and private. Never replace the canary's approved cohort."""
    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(encoded)


def successful(outcome):
    return outcome in {'recovered', 'already_applied', 'reconciled'}
