"""Bounded, post-decision live audits of enforced projection precheck hits."""

from dataclasses import dataclass
import random
import time

from prometheus_client import Counter

from config.firestore_read_levers import lever_percent
from database import privacy_check_metrics as metrics
from database.batch_account_authority_schema import PRIVACY_COLLECTION
from database.batch_pipeline_privacy import BatchPrivacyBlocked, _assert_batch_write_allowed_live, privacy_owner_key
from database.batch_pipeline_reads import read_snapshot
from database.batch_privacy_tokenless import CLOCK_MARGIN, EnforcedHit, _timestamp
from database.firestore_read_origin import read_origin
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.executors import read_cache_shadow_executor

ROUTE = 'projection_precheck'
AUDIT_SECONDS = 2.0
MAX_POINT_READS = 32
AUDIT = Counter('omi_batch_pipeline_tokenless_audit_total', 'Completed enforced-hit audits', ['route', 'outcome'])
INCOMPLETE = Counter(
    'omi_batch_pipeline_tokenless_audit_incomplete_total',
    'Enforced-hit audits without a comparison',
    ['route', 'outcome'],
)
for _outcome in ('agree', 'disagree_within_window', 'disagree_beyond_window'):
    AUDIT.labels(ROUTE, _outcome)
for _outcome in ('failed', 'dropped'):
    INCOMPLETE.labels(ROUTE, _outcome)


@dataclass
class _PointReadBudget:
    budget: ArtifactReadBudget
    calls_left: int = MAX_POINT_READS

    def timeout(self, ceiling):
        if self.calls_left <= 0:
            raise ArtifactReadLimit('tokenless audit read limit')
        self.calls_left -= 1
        return self.budget.timeout(ceiling)


def _record(counter, outcome):
    try:
        counter.labels(ROUTE, outcome).inc()
    except Exception:
        pass


def submit_projection_precheck_audit(store, uid: str, hit: EnforcedHit) -> None:
    """Submit at most 1% of hits without waiting for an executor slot."""
    try:
        rate = lever_percent('bpp_tokenless_owner_audit')
        if rate == 0 or random.randrange(10_000) >= rate:
            return
        remaining = min(AUDIT_SECONDS, hit.deadline - time.time())
        if remaining > 0:
            budget = ArtifactReadBudget(time.monotonic() + remaining, max_bytes=0, max_objects=0)
            future = read_cache_shadow_executor.submit(_audit, store, uid, hit, budget)
            future.add_done_callback(_count_cancelled)
            return
    except Exception:
        pass
    _record(INCOMPLETE, 'dropped')


def _count_cancelled(future):
    if future.cancelled():
        _record(INCOMPLETE, 'dropped')


def _audit(store, uid, hit, budget):
    try:
        with read_origin('job:projection_tokenless_audit'):
            outcome = read_snapshot(store, lambda view: _compare(view, uid, hit, budget), budget)
    except Exception:
        _record(INCOMPLETE, 'failed')
    else:
        _record(AUDIT, outcome)


def _compare(view, uid, hit, budget):
    point_budget = _PointReadBudget(budget)
    client, transaction = view.client, view.transaction
    ref = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(uid))
    snapshot = metrics.read_snapshot('batch', ref, transaction=transaction, read_budget=point_budget)
    try:
        _assert_batch_write_allowed_live(
            client,
            transaction,
            uid,
            conversation_ids=hit.ids,
            expected_generation=hit.generation,
            read_budget=point_budget,
            privacy_snapshot=snapshot,
            authority_out=[],  # Use the full authority walk, including negative lookups.
        )
    except BatchPrivacyBlocked:
        allowed = False
    else:
        allowed = True

    # A delayed audit cannot judge a decision using a snapshot from outside
    # its original window. A refusal without a revision cannot date the change.
    now = time.time()
    stamp = _timestamp(getattr(snapshot, 'read_time', None))
    if stamp is None or abs(stamp - now) > CLOCK_MARGIN or stamp < hit.read_at:
        raise ValueError('uncertain tokenless audit clock')
    if max(stamp, now) >= hit.deadline:
        raise ArtifactReadLimit('tokenless audit window closed')
    if allowed:
        return 'agree'
    revision = _timestamp(getattr(snapshot, 'update_time', None))
    if revision is None or revision > stamp:
        raise ValueError('uncertain tokenless audit revision')
    return 'disagree_within_window' if hit.read_at < revision else 'disagree_beyond_window'
