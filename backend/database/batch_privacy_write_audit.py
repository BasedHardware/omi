"""Sample enforced scheduler hits against a fresh, bounded authority snapshot."""

from dataclasses import dataclass
import random
import time

from google.api_core.exceptions import GoogleAPICallError
from prometheus_client import Counter

from config.firestore_read_levers import lever_percent
from database import privacy_check_metrics as metrics
from database.batch_pipeline_privacy import (
    BatchPrivacyBlocked,
    PRIVACY_COLLECTION,
    privacy_owner_key,
    read_live_batch_write_authority,
)
from database.batch_privacy_attempt import token_version
from database.batch_privacy_write_cache import CLOCK_MARGIN_SECONDS, Decision, SITES, TTL_SECONDS
from database.firestore_read_origin import read_origin
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit
from utils.executors import read_cache_shadow_executor

AUDIT = Counter(
    'omi_batch_pipeline_privacy_tokenless_write_audit_total',
    'Completed enforced scheduler hit comparisons',
    ['site', 'outcome'],
)
INCOMPLETE = Counter(
    'omi_batch_pipeline_privacy_tokenless_write_audit_incomplete_total',
    'Sampled enforced scheduler hits without a completed comparison',
    ['site', 'outcome'],
)
for _site in SITES:
    for _outcome in ('agree', 'disagree_within_window', 'disagree_beyond_window'):
        AUDIT.labels(_site, _outcome)
    for _outcome in ('failed', 'dropped'):
        INCOMPLETE.labels(_site, _outcome)


@dataclass(frozen=True)
class Hit:
    uid: str
    ids: frozenset[str]
    site: str
    decision: Decision


@dataclass
class _Budget:
    deadline: float
    reads_left: int = 32

    def remaining(self, ceiling):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ArtifactReadLimit('write audit deadline')
        return min(remaining, ceiling)

    def timeout(self, ceiling):
        if self.reads_left <= 0:
            raise ArtifactReadLimit('write audit read limit')
        self.reads_left -= 1
        return self.remaining(ceiling)


def submit(client, hit: Hit) -> None:
    # The 0–100 lever is interpreted as basis points here, so the hard cap is 1%.
    try:
        rate = lever_percent('bpp_tokenless_write_audit')
        if not rate or random.randrange(10_000) >= rate:
            return
        deadline = hit.decision.started + TTL_SECONDS - CLOCK_MARGIN_SECONDS
        remaining = min(2, deadline - time.time())
        if hit.decision.fresh() and remaining > 0:
            budget = _Budget(time.monotonic() + remaining)
            future = read_cache_shadow_executor.submit(_run, client, hit, budget)
            future.add_done_callback(lambda done: _count_cancelled(done, hit.site))
            return
    except Exception:
        pass
    INCOMPLETE.labels(hit.site, 'dropped').inc()


def _count_cancelled(future, site):
    if future.cancelled():
        INCOMPLETE.labels(site, 'dropped')


def _run(client, hit, budget):
    try:
        with read_origin(f'job:batch_tokenless_write_audit_{hit.site}'):
            outcome = _live_outcome(client, hit, budget)
    except Exception:
        INCOMPLETE.labels(hit.site, 'failed').inc()
    else:
        AUDIT.labels(hit.site, outcome).inc()


def _live_outcome(client, hit, budget):
    decision = hit.decision
    if not decision.fresh():
        raise ArtifactReadLimit('write audit proof expired')
    # Use the SDK's read-only snapshot and cap each RPC, including begin and
    # rollback. The same snapshot covers the token and every authority read.
    transaction = client.transaction(read_only=True, max_attempts=1)
    api = client._firestore_api
    response = api.begin_transaction(
        request={'database': client._database_string, 'options': {'read_only': {}}},
        metadata=client._rpc_metadata,
        retry=None,
        timeout=budget.remaining(2),
    )
    transaction._id = response.transaction
    try:
        reference = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(hit.uid))
        snapshot = metrics.read_snapshot('batch', reference, transaction=transaction, read_budget=budget)
        try:
            generation = read_live_batch_write_authority(
                client,
                transaction,
                hit.uid,
                privacy_snapshot=snapshot,
                conversation_ids=hit.ids,
                expected_generation=decision.generation,
                read_budget=budget,
                walk_out=None,
            )
        except BatchPrivacyBlocked:
            generation = None
        budget.remaining(2)
        now = time.time()
        read_at = getattr(snapshot, 'read_time', None)
        if (
            not decision.fresh()
            or read_at is None
            or not (
                decision.started <= read_at.timestamp() <= now + CLOCK_MARGIN_SECONDS
                and abs(now - read_at.timestamp()) <= CLOCK_MARGIN_SECONDS
                and read_at.timestamp() < decision.started + TTL_SECONDS
            )
        ):
            raise ValueError('uncertain write audit snapshot time')
        if generation == decision.generation:
            return 'agree'
        version = token_version(snapshot)
        changed_at = getattr(snapshot, 'update_time', None)
        if version != decision.version and changed_at is not None:
            changed = changed_at.timestamp()
            if changed > read_at.timestamp():
                raise ValueError('uncertain write audit revision')
            if decision.started < changed:
                return 'disagree_within_window'
        return 'disagree_beyond_window'
    finally:
        remaining = budget.deadline - time.monotonic()
        if remaining > 0:
            try:
                api.rollback(
                    request={'database': client._database_string, 'transaction': transaction.id},
                    metadata=client._rpc_metadata,
                    retry=None,
                    timeout=min(1, remaining),
                )
            except GoogleAPICallError:
                pass
        transaction._clean_up()
