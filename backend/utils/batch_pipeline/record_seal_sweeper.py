"""Bounded CronJob coordinator. No inventory, plans, IDs or errors are logged."""

from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timezone
import math
from pathlib import Path
import ssl
import time
from typing import TypedDict
from urllib.request import Request, urlopen

from google.cloud.firestore_v1 import FieldFilter

from config import record_seal_sweeper as sweeper_config
from database.batch_pipeline_store import FirestoreStore
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline import record_seal_repair
from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget
from utils.batch_pipeline.record_producer_proof import NAMESPACE, parse_pusher_pod_proof, producer_tokens_dead
from utils.other.local_storage import create_storage_client

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
    classified: int
    candidates: int


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


def discover_pending(client, namespace, *, budget=None, limit=DISCOVERY_LIMIT):
    """Reuse the drainer's state/available_at index, with a hard read bound."""
    query = (
        client.collection(f'{namespace}_jobs')
        .where(filter=FieldFilter('state', '==', 'record_pending'))
        .order_by('available_at')
        .limit(limit)
    )
    stream = query.stream(timeout=budget.timeout(), retry=None) if budget else query.stream()
    return [doc.id for doc in stream]


class SweepReadStore:
    """Read-only view: no Begin/Commit RPCs for single-document classification.

    Planning reads need no transaction: apply_seals rechecks the exact job and
    row plus privacy and producer proof inside its original write transaction.
    No cache: planning must reread rows after classification.
    """

    def __init__(self, store, budget):
        self.client, self.namespace, self.budget = store.client, store.namespace, budget

    def run(self, body):
        return body(self)

    def get(self, table, key):
        if table == 'jobs':
            ref = self.client.collection(f'{self.namespace}_jobs').document(key)
        elif table == 'conversations':
            uid, cid = key.split('/', 1)
            ref = self.client.collection('users').document(uid).collection('conversations').document(cid)
        else:
            raise ValueError('unsupported sweep read')
        snapshot = ref.get(timeout=self.budget.timeout(), retry=None)
        self.budget.check()
        return snapshot.to_dict() or {}


def require_fresh_proof(proof):
    # The shared predicate also validates namespace and shape even with no tokens.
    if proof is None or not producer_tokens_dead({}, proof):
        raise ValueError('fresh authoritative inventory required')
    if not proof.get('resource_version'):
        raise ValueError('authoritative inventory required')


def sweep(
    store,
    storage_client,
    artifacts,
    *,
    inventory=read_pusher_pod_proof,
    discover=discover_pending,
    mode: str = 'apply',
    budget=None,
    progress=lambda _: None,
    interrupt_io=False,
    runtime_reads=False,
    discovery_limit=DISCOVERY_LIMIT,
    seal_limit=SEAL_LIMIT,
) -> SweepReport:
    """Fail closed before writes on any discovery, inventory or planning IO error."""
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
        'classified': 0,
        'candidates': 0,
    }
    budget = budget or SweepBudget(sweeper_config.budget_seconds())
    counts = Counter()
    phase = 'inventory'

    def emit():
        # Construct an allowlisted payload; never forward plans, IDs or errors.
        progress(
            {
                'event': 'record_seal_sweep_phase',
                'phase': phase,
                'elapsed_ms': max(0, int((budget.clock() - budget.started) * 1000)),
                'discovered': report['discovered'],
                'classified': report['classified'],
                'candidates': report['candidates'],
            }
        )

    # Kept inside the deadline context, including inventory and apply retries.
    def _sweep():
        nonlocal phase, store, storage_client, artifacts
        if mode not in {'plan', 'apply'}:
            raise ValueError('invalid sweep mode')
        if not 1 <= discovery_limit <= DISCOVERY_LIMIT or not 1 <= seal_limit <= SEAL_LIMIT:
            raise ValueError('invalid sweep limits')
        budget.check()
        proof = inventory()
        require_fresh_proof(proof)
        emit()
        phase = 'discovery'
        budget.check()
        if runtime_reads:
            store = SweepReadStore(store, budget)
            storage_client, artifacts = create_storage_client(), artifacts_for(store)
            job_ids = discover_pending(store.client, store.namespace, budget=budget, limit=discovery_limit)
        else:
            job_ids = discover(store.client, store.namespace)
        if (
            not isinstance(job_ids, list)
            or len(job_ids) > discovery_limit
            or len(set(job_ids)) != len(job_ids)
            or any(not isinstance(j, str) or not j or '/' in j or len(j) > 1500 for j in job_ids)
        ):
            raise ValueError('bounded exact jobs required')
        report['discovered'] = len(job_ids)
        report['discovery_saturated'] = len(job_ids) == discovery_limit
        emit()
        phase = 'classification'
        candidates = []
        now = time.time()
        for job_id in job_ids:
            budget.check()
            job = store.run(lambda tx: tx.get('jobs', job_id))
            budget.check()
            if job.get('state') != 'record_pending':
                counts['not_pending'] += 1
                report['classified'] += 1
                continue
            uid, cid = job.get('owner_id'), job.get('conversation_id')
            if any(not isinstance(v, str) or not v or '/' in v for v in (uid, cid)):
                raise ValueError('malformed job')
            row = store.run(lambda tx: tx.get('conversations', f'{uid}/{cid}'))
            budget.check()
            if not row:
                raise ValueError('missing conversation')
            report['classified'] += 1
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
            elif len(candidates) >= seal_limit:
                counts['seal_cap'] += 1
            else:
                candidates.append(job_id)
                report['candidates'] += 1
        emit()
        phase = 'plan'
        budget.check()
        plan = record_seal_repair.plan_seals(
            store, candidates, storage_client, artifacts, producer_proof=proof, check_budget=budget.check
        )
        emit()
        budget.check()
        if any(e['disposition'] in {'read_error', 'unavailable'} for e in plan['entries']):
            report['outcome'] = 'read_error'
            return report
        require_fresh_proof(proof)  # Tail reads may have exhausted the five-minute proof window.
        phase = 'apply'
        if mode == 'apply':
            applied = Counter()
            try:
                result = record_seal_repair.apply_seals(
                    store, plan, plan['plan_sha256'], check_budget=budget.check, outcomes=applied
                )
            except BudgetExhausted:
                counts.update(applied)
                raise
            counts.update(result)
        else:
            counts.update(entry['disposition'] for entry in plan['entries'])
        emit()
        report['outcome'] = 'write_error' if counts['write_error'] else 'ok'
        return report

    try:
        with budget.interrupt_io() if interrupt_io else nullcontext():
            return _sweep()
    except BudgetExhausted:
        report['outcome'] = 'budget_exhausted'
        emit()
    except Exception:
        # Exception messages, document IDs, plans and inventory are never emitted.
        report['outcome'] = 'error'
    finally:
        report['dispositions'] = dict(sorted(counts.items()))
        report['oldest_unsealed_over_four_hours'] = report['oldest_unsealed_seconds'] > 14400
    return report


def run(*, progress=lambda _: None):
    if not sweeper_config.enabled():
        return {'event': 'record_seal_sweep', 'outcome': 'disabled'}
    # Only the approved in-cluster production identity may perform ambient writes.
    sweeper_config.require_production_runtime()
    mode = sweeper_config.mode()
    discovery_limit, seal_limit = sweeper_config.limits()
    budget = SweepBudget(sweeper_config.budget_seconds())
    # Lazy creation keeps the in-cluster proof ahead of cloud client access.
    # The wrapper itself must be constructed only after inventory succeeds.
    store = FirestoreStore('batch_pipeline_prod')
    return sweep(
        store,
        None,
        None,
        inventory=read_pusher_pod_proof,
        mode=mode,
        budget=budget,
        progress=progress,
        interrupt_io=True,
        runtime_reads=True,
        discovery_limit=discovery_limit,
        seal_limit=seal_limit,
    )
