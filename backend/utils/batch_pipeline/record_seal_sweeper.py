"""Bounded CronJob coordinator. No inventory, plans, IDs or errors are logged."""

from collections import Counter
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import ssl
import time
from typing import TypedDict
from urllib.request import Request, urlopen

from utils.batch_pipeline.record_producer_proof import NAMESPACE, parse_pusher_pod_proof, producer_tokens_dead

DISCOVERY_LIMIT = 128
SEAL_LIMIT = 64
POD_LIST_PATH = f'/api/v1/namespaces/{NAMESPACE}/pods?labelSelector=app.kubernetes.io%2Fname%3Dpusher'
SERVICE_ACCOUNT_PATH = Path('/var/run/secrets/kubernetes.io/serviceaccount')
MAX_INVENTORY_BYTES = 8 * 1024 * 1024


class SweepReport(TypedDict):
    event: str
    outcome: str
    mode: str
    discovered: int
    backlog: int
    oldest_unsealed_seconds: int
    oldest_unsealed_over_four_hours: bool
    bare_token_skips: int
    discovery_saturated: bool
    dispositions: dict[str, int]


def read_pusher_pod_proof():
    """One TLS-verified, consistent PodList. Partial lists never prove absence."""
    captured_at = datetime.now(timezone.utc).isoformat()
    token = (SERVICE_ACCOUNT_PATH / 'token').read_text().strip()
    if not token or (SERVICE_ACCOUNT_PATH / 'namespace').read_text().strip() != NAMESPACE:
        raise ValueError('scoped in-cluster identity required')
    context = ssl.create_default_context(cafile=str(SERVICE_ACCOUNT_PATH / 'ca.crt'))
    request = Request(
        'https://kubernetes.default.svc' + POD_LIST_PATH,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'},
    )
    with urlopen(request, context=context, timeout=15) as response:
        payload = response.read(MAX_INVENTORY_BYTES + 1)
    if len(payload) > MAX_INVENTORY_BYTES:
        raise ValueError('inventory budget exceeded')
    # The shared parser retains only names/start epochs and a digest in memory.
    return parse_pusher_pod_proof(payload, captured_at)


def discover_pending(client, namespace):
    """Reuse the drainer's state/available_at index, with a hard read bound."""
    from google.cloud.firestore_v1 import FieldFilter

    query = (
        client.collection(f'{namespace}_jobs')
        .where(filter=FieldFilter('state', '==', 'record_pending'))
        .order_by('available_at')
        .limit(DISCOVERY_LIMIT)
    )
    return [doc.id for doc in query.stream()]


def _fresh(proof):
    # The shared predicate also validates namespace and shape even with no tokens.
    if proof is None or not producer_tokens_dead({}, proof):
        raise ValueError('fresh authoritative inventory required')
    if not proof.get('resource_version'):
        raise ValueError('authoritative inventory required')


def sweep(
    store, storage_client, artifacts, *, inventory=read_pusher_pod_proof, discover=discover_pending, mode: str = 'apply'
) -> SweepReport:
    """Fail closed before writes on any discovery, inventory or planning IO error."""
    from utils.batch_pipeline.record_seal_repair import plan_seals, apply_seals

    report: SweepReport = {
        'event': 'record_seal_sweep',
        'outcome': 'error',
        'mode': mode,
        'discovered': 0,
        'backlog': 0,
        'oldest_unsealed_seconds': 0,
        'oldest_unsealed_over_four_hours': False,
        'bare_token_skips': 0,
        'discovery_saturated': False,
        'dispositions': {},
    }
    try:
        if mode not in {'plan', 'apply'}:
            raise ValueError('invalid sweep mode')
        proof = inventory()
        _fresh(proof)
        job_ids = discover(store.client, store.namespace)
        if (
            not isinstance(job_ids, list)
            or len(job_ids) > DISCOVERY_LIMIT
            or len(set(job_ids)) != len(job_ids)
            or any(not isinstance(j, str) or not j or '/' in j or len(j) > 1500 for j in job_ids)
        ):
            raise ValueError('bounded exact jobs required')
        report['discovered'] = len(job_ids)
        report['discovery_saturated'] = len(job_ids) == DISCOVERY_LIMIT
        candidates = []
        counts = Counter()
        now = time.time()
        for job_id in job_ids:
            job = store.run(lambda tx: tx.get('jobs', job_id))
            if job.get('state') != 'record_pending':
                counts['not_pending'] += 1
                continue
            uid, cid = job.get('owner_id'), job.get('conversation_id')
            if any(not isinstance(v, str) or not v or '/' in v for v in (uid, cid)):
                raise ValueError('malformed job')
            row = store.run(lambda tx: tx.get('conversations', f'{uid}/{cid}'))
            if not row:
                raise ValueError('missing conversation')
            if row.get('record_audio_closed'):
                counts['already_closed'] += 1
                continue
            report['backlog'] += 1
            finished = row.get('finished_at')
            if isinstance(finished, datetime) and finished.tzinfo is not None:
                age = now - finished.timestamp()
                if math.isfinite(age):
                    report['oldest_unsealed_seconds'] = max(report['oldest_unsealed_seconds'], max(0, int(age)))
            tokens = row.get('record_upload_sessions')
            if isinstance(tokens, dict) and any(v is True for v in tokens.values()):
                report['bare_token_skips'] += 1
                counts['bare_token'] += 1
            elif row.get('record_upload_failed'):
                counts['upload_failed'] += 1
            elif not isinstance(tokens, dict) or not tokens:
                counts['no_tokens'] += 1
            elif len(candidates) >= SEAL_LIMIT:
                counts['seal_cap'] += 1
            else:
                candidates.append(job_id)
        plan = plan_seals(store, candidates, storage_client, artifacts, producer_proof=proof)
        report['oldest_unsealed_over_four_hours'] = report['oldest_unsealed_seconds'] > 14400
        if any(e['disposition'] in {'read_error', 'unavailable'} for e in plan['entries']):
            report['outcome'] = 'read_error'
            return report
        _fresh(proof)  # Tail reads may have exhausted the five-minute proof window.
        if mode == 'apply':
            counts.update(apply_seals(store, plan, plan['plan_sha256']))
        else:
            counts.update(entry['disposition'] for entry in plan['entries'])
        report['dispositions'] = dict(sorted(counts.items()))
        report['outcome'] = 'write_error' if counts['write_error'] else 'ok'
    except Exception:
        # Exception messages, document IDs, plans and inventory are never emitted.
        report['outcome'] = 'error'
    return report


def run():
    if os.getenv('RECORD_SEAL_SWEEPER_ENABLED', 'true').strip().lower() != 'true':
        return {'event': 'record_seal_sweep', 'outcome': 'disabled'}
    # Only the approved in-cluster production identity may perform ambient writes.
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('OMI_ENV_STAGE') != 'prod':
        raise ValueError('production in-cluster runtime required')
    mode = os.getenv('RECORD_SEAL_SWEEPER_MODE', 'apply')
    if mode not in {'plan', 'apply'}:
        raise ValueError('invalid sweep mode')
    proof = read_pusher_pod_proof()  # Prove in-cluster scope before any cloud access.
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.artifact_policy import artifacts_for
    from utils.other.local_storage import create_storage_client

    store = FirestoreStore('batch_pipeline_prod')
    return sweep(store, create_storage_client(), artifacts_for(store), inventory=lambda: proof, mode=mode)
